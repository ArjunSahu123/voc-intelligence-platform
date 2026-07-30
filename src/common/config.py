"""Central configuration for the Voice of Customer Intelligence Platform.

Every path and tunable lives here so pipelines never hardcode a path inline.
"""
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"
DB_DIR = ROOT_DIR / "db"
REPORTS_DIR = ROOT_DIR / "reports"
DB_PATH = ROOT_DIR / os.getenv("DB_PATH", "db/voc.db")

APP_PACKAGE = os.getenv("APP_PACKAGE", "com.application.zomato")
APP_NAME = os.getenv("APP_NAME", "Zomato")
COUNTRY = os.getenv("COUNTRY", "in")
LANG = os.getenv("LANG", "en")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# LLM_PROVIDER selects which backend src/common/llm_client.py dispatches to.
# Every classification/root-cause/recommendation/report-narrative call goes
# through that one abstraction, so switching providers is this one env var
# (plus the matching *_API_KEY) — no call site elsewhere needs to change.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
ACTIVE_LLM_MODEL = GEMINI_MODEL if LLM_PROVIDER == "gemini" else CLAUDE_MODEL
ACTIVE_LLM_API_KEY = GEMINI_API_KEY if LLM_PROVIDER == "gemini" else ANTHROPIC_API_KEY

for _dir in (DATA_RAW_DIR, DATA_PROCESSED_DIR, DB_DIR, REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
