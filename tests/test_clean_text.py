import pandas as pd

from src.cleaning.clean_text import clean_text, detect_language


def test_clean_text_removes_urls():
    assert "http" not in clean_text("Check https://example.com/path?x=1 for details")


def test_clean_text_removes_emails():
    assert "@" not in clean_text("Contact me at someone@example.com please")


def test_clean_text_removes_emoji():
    cleaned = clean_text("Great app! 😍🔥 loved it")
    assert "😍" not in cleaned and "🔥" not in cleaned
    assert "Great app" in cleaned


def test_clean_text_collapses_whitespace():
    assert clean_text("too   many\n\nspaces   here") == "too many spaces here"


def test_clean_text_handles_non_string():
    assert clean_text(None) == ""
    assert clean_text(float("nan")) == ""


def test_detect_language_english():
    assert detect_language("This app is absolutely wonderful and works great every day") == "en"


def test_detect_language_short_text_is_unknown():
    assert detect_language("ok") == "unknown"
