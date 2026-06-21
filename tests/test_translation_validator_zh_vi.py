from src.translation_validator import validate_translation


def test_validate_zh_cn_length_expansion_is_warning_only():
    segments = [
        {
            "id": 1,
            "text": "\u8fd9\u5c31\u662f\u4f20\u8bf4\u4e2d",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
            "text_vi": "\u0110\u00e2y ch\u00ednh l\u00e0 thuy\u1ec1n bay n\u1ed5i ti\u1ebfng trong truy\u1ec1n thuy\u1ebft.",
        }
    ]

    report = validate_translation(segments, mode="subtitle_only", source_language="zh-CN")

    assert report["bad_segments"] == 0
    assert any(issue["type"] == "LENGTH_RATIO_WARNING" for issue in report["issues"])
    assert all(issue["type"] != "TRUE_HALLUCINATION" for issue in report["issues"])


def test_validate_banned_wrong_term_blocks_glossary_entity():
    segments = [
        {
            "id": 1,
            "text": "\u98de\u5929\u753b\u4f34",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
            "text_vi": "Tranh bay ng\u00e0n d\u1eb7m.",
        }
    ]
    glossary = {"terms": {"\u98de\u5929\u753b\u823b": "thuy\u1ec1n bay"}}

    report = validate_translation(
        segments,
        mode="subtitle_only",
        source_language="zh-CN",
        glossary=glossary,
    )

    banned = [issue for issue in report["issues"] if issue["type"] == "BANNED_WRONG_TERM"]
    assert len(banned) == 1
    assert report["bad_segments"] == 1


def test_fragmented_subtitle_pair_is_warning_only():
    segments = [
        {
            "id": 7,
            "text": "\u8fd9\u5c31\u662f\u4f20\u8bf4\u4e2d",
            "start": 0.0,
            "end": 1.4,
            "duration": 1.4,
            "text_vi": "\u0110\u00e2y l\u00e0.",
            "subtitle_vi": "\u0110\u00e2y l\u00e0.",
        },
        {
            "id": 8,
            "text": "\u4e00\u65e5\u884c\u5343\u91cc\u7684\u98de\u5929\u753b\u4f34",
            "start": 1.4,
            "end": 3.34,
            "duration": 1.94,
            "text_vi": "Thuy\u1ec1n bay ng\u00e0n d\u1eb7m trong truy\u1ec1n thuy\u1ebft.",
            "subtitle_vi": "Thuy\u1ec1n bay ng\u00e0n d\u1eb7m trong truy\u1ec1n thuy\u1ebft.",
        },
    ]

    report = validate_translation(segments, mode="subtitle_only", source_language="zh-CN")

    fragmented = [issue for issue in report["issues"] if issue["type"] == "FRAGMENTED_SUBTITLE"]
    assert len(fragmented) == 1
    assert report["bad_segments"] == 0
