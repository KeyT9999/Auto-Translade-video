from src.glossary_enforcer import apply_glossary_to_segments


def test_glossary_enforcer_replaces_banned_wrong_term():
    segments = [
        {
            "id": 1,
            "text": "\u98de\u5929\u753b\u50cf\u90fd\u5f00\u59cb\u9e23\u7b1b\u4e86",
            "text_vi": "Tranh bay \u0111\u00e3 b\u1eaft \u0111\u1ea7u k\u00e8n r\u1ed3i.",
            "subtitle_vi": "Tranh bay \u0111\u00e3 b\u1eaft \u0111\u1ea7u k\u00e8n r\u1ed3i.",
            "dub_vi": "Tranh bay \u0111\u00e3 b\u1eaft \u0111\u1ea7u k\u00e8n r\u1ed3i.",
            "final_dub_vi": "Tranh bay \u0111\u00e3 b\u1eaft \u0111\u1ea7u k\u00e8n r\u1ed3i.",
        }
    ]
    glossary = {"terms": {"\u98de\u5929\u753b\u823b": "thuy\u1ec1n bay"}}

    updated = apply_glossary_to_segments(segments, glossary)

    assert updated[0]["text_vi"].startswith("thuy\u1ec1n bay")
    assert updated[0]["subtitle_vi"].startswith("thuy\u1ec1n bay")
    assert updated[0]["dub_vi"].startswith("thuy\u1ec1n bay")
    assert updated[0]["final_dub_vi"].startswith("thuy\u1ec1n bay")
    assert updated[0]["glossary_enforced"] is True

