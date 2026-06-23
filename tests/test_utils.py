import os
import logging
from src.utils import setup_logging, ensure_dir, format_timestamp


def test_setup_logging_returns_logger():
    logger = setup_logging("test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_ensure_dir_creates_directory(tmp_path):
    new_dir = tmp_path / "subdir" / "nested"
    result = ensure_dir(str(new_dir))
    assert os.path.isdir(result)
    assert result == str(new_dir)


def test_ensure_dir_existing_directory(tmp_path):
    result = ensure_dir(str(tmp_path))
    assert os.path.isdir(result)


def test_format_timestamp_zero():
    assert format_timestamp(0.0) == "00:00:00,000"


def test_format_timestamp_seconds():
    assert format_timestamp(3.2) == "00:00:03,200"


def test_format_timestamp_minutes():
    assert format_timestamp(65.5) == "00:01:05,500"


def test_format_timestamp_hours():
    assert format_timestamp(3661.123) == "01:01:01,123"


def test_extract_url():
    from src.utils import extract_url
    
    # 1. Clean URL
    assert extract_url("https://v.douyin.com/RhbRuqdworA/") == "https://v.douyin.com/RhbRuqdworA/"
    
    # 2. Mixed text with URL
    raw_msg = "7.64 10/29 :1pm O@x.SY kCH:/ 紫藤花开，思念的人会如期归来。 #超能演剧场2026 https://v.douyin.com/RhbRuqdworA/ 复制此链接，打开Dou音"
    assert extract_url(raw_msg) == "https://v.douyin.com/RhbRuqdworA/"
    
    # 3. URL with trailing punctuation commonly captured
    assert extract_url("Check this: https://v.douyin.com/RhbRuqdworA/!!!") == "https://v.douyin.com/RhbRuqdworA/"
    assert extract_url("https://v.douyin.com/RhbRuqdworA/, yes") == "https://v.douyin.com/RhbRuqdworA/"
    assert extract_url("Link: (https://v.douyin.com/RhbRuqdworA/)") == "https://v.douyin.com/RhbRuqdworA/"
    assert extract_url("Link: [https://v.douyin.com/RhbRuqdworA/]\"") == "https://v.douyin.com/RhbRuqdworA/"
    
    # 4. No URL fallback
    assert extract_url("no url here") == "no url here"
    assert extract_url("") == ""
