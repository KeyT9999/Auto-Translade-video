import config

from src.contextual_translator import select_translation_window_size


def test_adaptive_window_size_for_long_video(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATION_ADAPTIVE_WINDOW_ENABLED", True)
    monkeypatch.setattr(config, "TRANSLATION_WINDOW_SIZE", 35)
    monkeypatch.setattr(config, "TRANSLATION_LONG_VIDEO_WINDOW_SIZE", 20)
    monkeypatch.setattr(config, "TRANSLATION_VERY_LONG_VIDEO_WINDOW_SIZE", 15)
    monkeypatch.setattr(config, "TRANSLATION_LONG_VIDEO_SEGMENT_THRESHOLD", 200)
    monkeypatch.setattr(config, "TRANSLATION_VERY_LONG_VIDEO_SEGMENT_THRESHOLD", 500)

    window_size, adaptive = select_translation_window_size(337)

    assert adaptive is True
    assert window_size == 20


def test_adaptive_window_size_keeps_default_for_shorter_video(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATION_ADAPTIVE_WINDOW_ENABLED", True)
    monkeypatch.setattr(config, "TRANSLATION_WINDOW_SIZE", 35)
    monkeypatch.setattr(config, "TRANSLATION_LONG_VIDEO_WINDOW_SIZE", 20)
    monkeypatch.setattr(config, "TRANSLATION_VERY_LONG_VIDEO_WINDOW_SIZE", 15)
    monkeypatch.setattr(config, "TRANSLATION_LONG_VIDEO_SEGMENT_THRESHOLD", 200)
    monkeypatch.setattr(config, "TRANSLATION_VERY_LONG_VIDEO_SEGMENT_THRESHOLD", 500)

    window_size, adaptive = select_translation_window_size(50)

    assert adaptive is True
    assert window_size == 35
