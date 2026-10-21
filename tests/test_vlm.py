from roadpush.vlm import CHECKS, TYPE_GUIDE, explain_prompt, parse_bool_json, seg_flags
from roadpush.scoring import TYPE_LABEL_KO


def test_parse_bool_json_variants():
    s = '모델 답: ```json\n{"car": true, "person": "false", "bollard": "True", "stairs": null}\n```'
    d = parse_bool_json(s, ["car", "person", "bollard", "stairs", "missing"])
    assert d == {"car": True, "person": False, "bollard": True, "stairs": None, "missing": None}
    assert parse_bool_json("JSON 없음", ["car"]) == {"car": None}
    assert parse_bool_json("{깨진 json", ["car"]) == {"car": None}


def test_seg_flags_and_guides():
    f = seg_flags({"car": 2, "sidewalk": 1, "barricade": 1})
    assert f["car"] and f["sidewalk_visible"] and f["construction"] and not f["person"]
    assert set(TYPE_GUIDE) <= set(TYPE_LABEL_KO)            # 모든 유형에 한글 라벨
    assert all(k in CHECKS for k in ("shared_street", "pushed_to_road"))


def test_explain_prompt_contains_rules():
    link = {"score": 55, "grade": "주의", "primary_type": "shared", "primary_type_ko": "보차 혼용",
            "space_type_ko": "보차 혼용", "p10_ratio": 0.4, "frac_below": 0.3}
    fr = [{"ratio": 0.4, "sidewalk_present": True, "n_obstacles_on_sidewalk": 2, "confirmed": ["car"]}]
    p = explain_prompt(link, fr)
    assert "보행자 우선도로" in p and "car" in p and "JSON" in p
