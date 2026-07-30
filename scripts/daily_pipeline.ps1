# Daily autonomous continuation of the VoC pipeline.
# Runs locally (not in a cloud sandbox) because it needs the local .env
# (Gemini API key) and the machine's already-authenticated git/GitHub CLI
# credentials - neither is available to a cloud-scheduled agent.
#
# Registered via Windows Task Scheduler (see scripts/register_task.ps1).
# Safe to run when the Gemini free-tier daily quota is still exhausted:
# each step is independently wrapped, quota errors are logged and skipped
# rather than crashing the whole run.

$ErrorActionPreference = "Continue"
$ProjectDir = "C:\Users\welcome\Desktop\Non Tech\Product Analyst\voc-intelligence-platform"
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("daily_pipeline_" + (Get-Date -Format "yyyy-MM-dd_HHmmss") + ".log")

Set-Location $ProjectDir

function Log {
    param([string]$msg)
    $line = "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $msg
    Add-Content -Path $LogFile -Value $line
}

Log "=== Daily pipeline run starting ==="

$beforeCounts = & $Python -c "from src.common.db import ENGINE; from sqlalchemy import text; c = ENGINE.connect(); print(c.execute(text('select count(*) from review_classifications')).scalar())"
$beforeCounts = [int]($beforeCounts | Select-Object -Last 1)
Log ("Classified reviews before: " + $beforeCounts)

Log "Step 1: incremental scrape + classify (limit 400)"
& $Python -m src.automation.run_pipeline --incremental --classify-limit 400 2>&1 | ForEach-Object { Log $_ }

Log "Step 2: generate_alerts (root cause + recommendations, needs LLM quota)"
$alertsOutput = & $Python -m src.alerts.generate_alerts 2>&1
$alertsOutput | ForEach-Object { Log $_ }
$alertsText = $alertsOutput -join "`n"
$alertsFailed = $alertsText -match "RESOURCE_EXHAUSTED|RetryError"

$afterCounts = & $Python -c "from src.common.db import ENGINE; from sqlalchemy import text; c = ENGINE.connect(); print(c.execute(text('select count(*) from review_classifications')).scalar())"
$afterCounts = [int]($afterCounts | Select-Object -Last 1)
Log ("Classified reviews after: " + $afterCounts)

$alertCountRaw = & $Python -c "from src.common.db import ENGINE; from sqlalchemy import text; c = ENGINE.connect(); print(c.execute(text('select count(*) from alerts')).scalar())"
$alertCount = [int]($alertCountRaw | Select-Object -Last 1)
Log ("Total alerts in DB: " + $alertCount)

$madeProgress = ($afterCounts -gt $beforeCounts) -or ((-not $alertsFailed) -and ($alertCount -gt 0))

if ($madeProgress) {
    Log "Progress detected - regenerating report and pushing to GitHub."
    & $Python -m src.reports.weekly_report 2>&1 | ForEach-Object { Log $_ }

    git add db/voc.db reports/ 2>&1 | ForEach-Object { Log $_ }
    $statusOutput = git status --short db/voc.db reports/ 2>&1
    if ($statusOutput) {
        $newClassified = $afterCounts - $beforeCounts
        $commitMsg = "Automated daily pipeline run: classified " + $newClassified + " new reviews, " + $alertCount + " total alerts"
        git commit -m $commitMsg 2>&1 | ForEach-Object { Log $_ }
        git push origin master 2>&1 | ForEach-Object { Log $_ }
        Log "Pushed changes to GitHub."
    } else {
        Log "No file changes to commit despite progress counters differing (unexpected, check manually)."
    }
} else {
    Log "No meaningful progress this run (quota likely still exhausted). Nothing committed."
}

Log "=== Daily pipeline run finished ==="
