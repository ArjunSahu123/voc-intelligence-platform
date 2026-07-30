import pandas as pd

from src.recommendations.strategic_roadmap import assign_quadrants


def test_high_reach_high_severity_is_fix_now():
    df = pd.DataFrame(
        {
            "category": ["A", "B", "C", "D"],
            "issue_pct": [0.10, 0.10, 0.01, 0.01],
            # severity_score baked with volume; severity_intensity = severity_score/(100*issue_pct)
            "severity_score": [10.0, 1.0, 1.0, 0.1],
        }
    )
    result, reach_median, severity_median = assign_quadrants(df)
    # A: reach=0.10 (>=median), intensity=10/(100*0.10)=1.0
    # B: reach=0.10 (>=median), intensity=1/(100*0.10)=0.1
    # C: reach=0.01 (<median... equal actually), intensity=1/(100*0.01)=1.0
    # D: reach=0.01, intensity=0.1/(100*0.01)=0.1
    a = result[result["category"] == "A"].iloc[0]
    assert a["severity_intensity"] == 1.0
    assert a["quadrant"] in ("Fix Now",)  # high reach, high intensity


def test_severity_intensity_decouples_from_volume():
    # Two categories with the SAME severity_score but very different volume
    # must NOT get the same severity_intensity — that would mean the axis
    # collapsed back into a volume proxy, which is exactly the bug this
    # module was built to avoid.
    df = pd.DataFrame(
        {
            "category": ["HighVolume", "LowVolume"],
            "issue_pct": [0.20, 0.01],
            "severity_score": [10.0, 10.0],
        }
    )
    result, _, _ = assign_quadrants(df)
    high_vol_intensity = result[result["category"] == "HighVolume"]["severity_intensity"].iloc[0]
    low_vol_intensity = result[result["category"] == "LowVolume"]["severity_intensity"].iloc[0]
    assert low_vol_intensity > high_vol_intensity  # same total severity, spread over fewer issues -> more severe per issue


def test_quadrants_partition_all_rows():
    df = pd.DataFrame(
        {
            "category": ["A", "B", "C", "D", "E"],
            "issue_pct": [0.20, 0.15, 0.05, 0.02, 0.01],
            "severity_score": [15.0, 2.0, 8.0, 0.5, 3.0],
        }
    )
    result, _, _ = assign_quadrants(df)
    assert set(result["quadrant"].unique()).issubset({"Fix Now", "Quick Wins", "Investigate Deeply", "Monitor"})
    assert result["quadrant"].notna().all()
