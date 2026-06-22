from src.translation_validator import validate_translation


def test_numeric_serial_spoken_out_is_not_marked_as_true_hallucination():
    segments = [
        {
            "id": 12,
            "text": "0010019819800",
            "text_vi": "không không một, không không một, chín tám, một chín tám, không không",
            "subtitle_vi": "không không một, không không một, chín tám, một chín tám, không không",
            "dub_vi": "không không một, không không một, chín tám, một chín tám, không không",
            "final_dub_vi": "không không một, không không một, chín tám, một chín tám, không không",
            "literal_vi": "không không một, không không một, chín tám, một chín tám, không không",
            "duration": 8.32,
            "speaker_gender": "neutral",
        }
    ]

    report = validate_translation(segments, mode="subtitle_only", source_language="en-US")

    assert not any(issue["type"] == "TRUE_HALLUCINATION" for issue in report["issues"])
    assert report["blocking_segments"] == 0
