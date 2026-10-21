"""클래스 체계 (단일 진실 공급원).

AI Hub 인도보행 영상의 라벨(+속성)을 RoadPush 학습 클래스로 합친다.
변경하면 PLAN.md 6장도 같이 갱신.
"""
from __future__ import annotations

# ---- 보도면(surface) : 폭 계산과 단절 유형 판정에 쓰임
SURFACE_CLASSES: list[str] = [
    "sidewalk",             # 보도 (속성: blocks/cement/asphalt/urethane/soil_stone/damaged/other)
    "braille_guide_blocks", # 점자블록 (보도의 일부로 취급)
    "roadway",              # 차도
    "alley",                # 이면도로(사람·차 혼용)
    "bike_lane",            # 자전거도로
    "stairs",               # caution_zone/stairs → 단차 유형
    "repair_zone",          # caution_zone/repair_zone → 공사 유형
    "caution_other",        # caution_zone/manhole,grating,tree_zone
]

# ---- 장애물(obstacle) : 유효폭을 깎는 요소
OBSTACLE_CLASSES: list[str] = [
    "car",
    "truck_bus",
    "two_wheeler",          # motorcycle, bicycle, scooter
    "bollard",
    "pole",
    "barricade",
    "movable_signage",      # 입간판
    "potted_plant",
    "person",
    "other_fixed",          # bench, chair, table, kiosk, fire_hydrant, ... tree_trunk
    "other_moving",         # carrier, stroller, wheelchair, dog, cat
]

CLASSES: list[str] = SURFACE_CLASSES + OBSTACLE_CLASSES
CLASS_TO_ID: dict[str, int] = {c: i + 1 for i, c in enumerate(CLASSES)}  # COCO id는 1부터

# 보도 폭 계산 시 "걸을 수 있는 면"으로 합칠 클래스
WALKABLE_SURFACES: frozenset[str] = frozenset({"sidewalk", "braille_guide_blocks"})

# AI Hub 라벨 → 클래스 (속성 무관)
_DIRECT: dict[str, str] = {
    "sidewalk": "sidewalk",
    "braille_guide_blocks": "braille_guide_blocks",
    "roadway": "roadway",
    "alley": "alley",
    "bike_lane": "bike_lane",
    "car": "car",
    "bus": "truck_bus",
    "truck": "truck_bus",
    "motorcycle": "two_wheeler",
    "bicycle": "two_wheeler",
    "scooter": "two_wheeler",
    "bollard": "bollard",
    "pole": "pole",
    "barricade": "barricade",
    "movable_signage": "movable_signage",
    "potted_plant": "potted_plant",
    "person": "person",
    # fixed etc.
    "bench": "other_fixed",
    "chair": "other_fixed",
    "table": "other_fixed",
    "kiosk": "other_fixed",
    "fire_hydrant": "other_fixed",
    "parking_meter": "other_fixed",
    "power_controller": "other_fixed",
    "stop": "other_fixed",
    "traffic_light": "other_fixed",
    "traffic_light_controller": "other_fixed",
    "traffic_sign": "other_fixed",
    "tree_trunk": "other_fixed",
    # moving etc.
    "carrier": "other_moving",
    "stroller": "other_moving",
    "wheelchair": "other_moving",
    "dog": "other_moving",
    "cat": "other_moving",
}

# 속성으로 갈라지는 라벨
_CAUTION_BY_ATTR: dict[str, str] = {
    "stairs": "stairs",
    "repair_zone": "repair_zone",
}


def map_aihub(label: str, attribute: str | None = None) -> str | None:
    """AI Hub 라벨(+속성)을 RoadPush 클래스로. 모르는 라벨은 None."""
    label = label.strip().lower()
    attr = (attribute or "").strip().lower()
    if label == "caution_zone":
        return _CAUTION_BY_ATTR.get(attr, "caution_other")
    return _DIRECT.get(label)
