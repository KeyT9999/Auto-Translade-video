from src.timeline_rewriter import rewrite_timeline


def test_timeline_rewriter_rejects_longer_rewrite(monkeypatch):
    segments = [
        {
            "id": 4,
            "text": "放心好了有我在呢",
            "duration": 5.28,
            "dub_vi": "Yên tâm nha, có em ở đây mà.",
            "original_dub_vi": "Yên tâm nha, có em ở đây mà.",
            "timing_rewrite_applied": False,
        }
    ]

    from src.ai import ai_router

    monkeypatch.setattr(
        ai_router,
        "rewrite_timeline",
        lambda prompt: {
            "rewritten_segments": [
                {"id": 4, "final_dub_vi": "Yên tâm nha, có em ở đây mà, mọi người đừng lo lắng nhé."}
            ]
        },
    )

    rewritten = rewrite_timeline(segments, {"video_type": "dialogue"}, {"characters": []})

    assert rewritten[0]["final_dub_vi"] == "Yên tâm nha, có em ở đây mà."
    assert rewritten[0]["timing_rewrite_applied"] is False


def test_timeline_rewriter_rejects_added_audience_clause(monkeypatch):
    segments = [
        {
            "id": 5,
            "text": "哥这对姐妹花在逃婚啊",
            "duration": 1.2,
            "dub_vi": "Anh ơi, hai chị em này đang trốn cưới đấy nhé.",
            "original_dub_vi": "Anh ơi, hai chị em này đang trốn cưới đấy nhé.",
            "timing_rewrite_applied": False,
        }
    ]

    from src.ai import ai_router

    monkeypatch.setattr(
        ai_router,
        "rewrite_timeline",
        lambda prompt: {
            "rewritten_segments": [
                {"id": 5, "final_dub_vi": "Anh ơi, hai chị em này trốn cưới đấy, mọi người thấy không."}
            ]
        },
    )

    rewritten = rewrite_timeline(segments, {"video_type": "dialogue"}, {"characters": []})

    assert rewritten[0]["final_dub_vi"] == "Anh ơi, hai chị em này đang trốn cưới đấy nhé."
    assert rewritten[0]["timing_rewrite_applied"] is False


def test_timeline_rewriter_accepts_shorter_safe_rewrite(monkeypatch):
    segments = [
        {
            "id": 5,
            "text": "哥这对姐妹花在逃婚啊",
            "duration": 0.9,
            "dub_vi": "Anh ơi, hai chị em này đang trốn cưới đấy nhé.",
            "original_dub_vi": "Anh ơi, hai chị em này đang trốn cưới đấy nhé.",
            "timing_rewrite_applied": False,
        }
    ]

    from src.ai import ai_router

    monkeypatch.setattr(
        ai_router,
        "rewrite_timeline",
        lambda prompt: {
            "rewritten_segments": [
                {"id": 5, "final_dub_vi": "Anh ơi, hai chị em này trốn cưới đấy."}
            ]
        },
    )

    rewritten = rewrite_timeline(segments, {"video_type": "dialogue"}, {"characters": []})

    assert rewritten[0]["final_dub_vi"] == "Anh ơi, hai chị em này trốn cưới đấy."
    assert rewritten[0]["timing_rewrite_applied"] is True
