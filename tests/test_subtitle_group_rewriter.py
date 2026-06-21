from src.subtitle_group_rewriter import detect_fragmented_subtitle_pairs, rewrite_subtitle_groups


def test_subtitle_group_rewriter_fixes_fragmented_pair():
    segments = [
        {
            "id": 7,
            "text": "\u8fd9\u5c31\u662f\u4f20\u8bf4\u4e2d",
            "text_vi": "\u0110\u00e2y l\u00e0.",
            "subtitle_vi": "\u0110\u00e2y l\u00e0.",
        },
        {
            "id": 8,
            "text": "\u4e00\u65e5\u884c\u5343\u91cc\u7684\u98de\u5929\u753b\u4f34",
            "text_vi": "Tranh bay ng\u00e0n d\u1eb7m trong truy\u1ec1n thuy\u1ebft.",
            "subtitle_vi": "Tranh bay ng\u00e0n d\u1eb7m trong truy\u1ec1n thuy\u1ebft.",
        },
    ]

    assert len(detect_fragmented_subtitle_pairs(segments)) == 1

    rewritten = rewrite_subtitle_groups(segments)

    assert rewritten[0]["text_vi"] == "\u0110\u00e2y ch\u00ednh l\u00e0"
    assert "thuy\u1ec1n bay" in rewritten[1]["text_vi"]
    assert rewritten[0]["subtitle_group_rewritten"] is True
    assert rewritten[1]["subtitle_group_rewritten"] is True
    assert detect_fragmented_subtitle_pairs(rewritten) == []
