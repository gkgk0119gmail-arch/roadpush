"""프레임 분석 → 링크 점수·단절 유형 (PLAN.md 7장).

프레임:
    analyze_frame(클래스별 인스턴스 마스크) → FrameAnalysis(ratio, tags)
    tags ⊂ {"vanish", "repair", "stairs"}   (폭 협소 "narrow"는 링크 단계에서 ratio로 판정)

링크 L (0~100):
    S_L = 100 × [0.4·(1 − P10(r)) + 0.3·frac(r < θ) + 0.3·type_weight]
    type_weight = max_t( frac(tag t) × w_t ),  w = {vanish 1.0, repair 0.8, stairs 0.6}
    등급: 안전(<30) / 주의(30~60) / 위험(≥60)
휠체어 모드: θ 0.5 → 0.7, stairs 가중 0.6 → 1.0 (확장 기능).
보조 지표: 절대 통과 가능 폭(m, width_ratio.metric_width) 이 법정 유효폭 1.2 m 미만인 프레임 비중.
점수에는 넣지 않는다(카메라 높이 가정 의존, 제안자 답변대로 비율이 기본).

보도가 안 보이는 프레임은 r=0, tag=vanish.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np

from .classes import BLOCKING_SURFACES, OBSTACLE_CLASSES, WALKABLE_SURFACES
from .width_ratio import FrameResult, Mask, frame_ratio, obstacles_on_sidewalk

TYPE_WEIGHTS = {"vanish": 1.0, "repair": 0.8, "stairs": 0.6}
TYPE_WEIGHTS_WHEELCHAIR = {"vanish": 1.0, "repair": 0.8, "stairs": 1.0}
TYPE_LABEL_KO = {"vanish": "보도 소멸", "narrow": "폭 협소", "repair": "공사·파손",
                 "stairs": "단차·계단", "none": "이상 없음"}
GRADES = ((60.0, "위험"), (30.0, "주의"), (0.0, "안전"))
LEGAL_MIN_WIDTH_M = 1.2   # 장애인등편의법 시행규칙 보도 유효폭


@dataclass
class Profile:
    """판정 프로필. 일반 보행자가 기본(제안자 답변 4번)."""
    name: str = "pedestrian"
    theta: float = 0.5
    type_weights: Mapping[str, float] = field(default_factory=lambda: dict(TYPE_WEIGHTS))


PEDESTRIAN = Profile()
WHEELCHAIR = Profile("wheelchair", 0.7, dict(TYPE_WEIGHTS_WHEELCHAIR))


# ---------------------------------------------------------------- 프레임

@dataclass
class FrameAnalysis:
    ratio: float
    min_ratio: float
    sidewalk_present: bool
    tags: list[str]
    n_obstacles_on_sidewalk: int = 0
    width_m: float | None = None          # 보조: 보도 폭(m)
    free_width_m: float | None = None     # 보조: 가장 좁은 통과 가능 폭(m)

    def to_dict(self) -> dict:
        return asdict(self)


def _union(masks: Iterable[Mask], shape: tuple[int, int]) -> Mask:
    out = np.zeros(shape, dtype=bool)
    for m in masks:
        out |= m.astype(bool)
    return out


def _lower_band(shape: tuple[int, int], top: float = 0.5) -> Mask:
    band = np.zeros(shape, dtype=bool)
    band[int(shape[0] * top):] = True
    return band


def analyze_frame(class_masks: Mapping[str, Sequence[Mask]], shape: tuple[int, int],
                  tag_min_frac: float = 0.05, cam_h: float = 1.3) -> FrameAnalysis:
    """클래스명 → 인스턴스 마스크 리스트 를 받아 프레임 지표 계산.

    repair/stairs 태그: 하단 절반에서 해당 면적이 (보도 ∪ 해당 면) 대비 tag_min_frac 이상.
    """
    walk = _union((m for c in WALKABLE_SURFACES for m in class_masks.get(c, ())), shape)
    instances = [m for c in (*OBSTACLE_CLASSES, *BLOCKING_SURFACES) for m in class_masks.get(c, ())]
    obstacle = obstacles_on_sidewalk(walk, instances)
    n_on = sum(1 for m in instances if (m & obstacle).any())
    fr: FrameResult = frame_ratio(walk, obstacle, cam_h=cam_h)

    tags: list[str] = []
    if not fr.sidewalk_present:
        tags.append("vanish")
    band = _lower_band(shape)
    walk_band = int((walk & band).sum())
    for cls, tag in (("repair_zone", "repair"), ("stairs", "stairs")):
        area = int((_union(class_masks.get(cls, ()), shape) & band).sum())
        if area and area / max(1, walk_band + area) >= tag_min_frac:
            tags.append(tag)
    mw = fr.metric
    return FrameAnalysis(fr.ratio, fr.min_ratio, fr.sidewalk_present, tags, n_on,
                         mw.width_m if mw else None, mw.min_free_m if mw else None)


# ---------------------------------------------------------------- 링크

@dataclass
class LinkScore:
    link_id: str
    n_frames: int
    score: float
    grade: str
    primary_type: str            # vanish | narrow | repair | stairs | none
    p10_ratio: float
    median_ratio: float
    frac_below: float
    type_weight: float
    type_fracs: dict[str, float]
    median_free_width_m: float | None = None
    frac_below_legal: float | None = None   # 절대폭 추정된 프레임 중 1.2 m 미만 비중

    def to_dict(self) -> dict:
        d = asdict(self)
        d["primary_type_ko"] = TYPE_LABEL_KO[self.primary_type]
        return d


def grade_of(score: float) -> str:
    for th, g in GRADES:
        if score >= th:
            return g
    return GRADES[-1][1]


def score_link(link_id: str, frames: Sequence[FrameAnalysis], profile: Profile = PEDESTRIAN,
               type_min_frac: float = 0.2) -> LinkScore | None:
    """링크 하나의 점수. 프레임이 없으면 None."""
    if not frames:
        return None
    r = np.array([f.ratio if f.sidewalk_present else 0.0 for f in frames], dtype=float)
    p10 = float(np.percentile(r, 10))
    below = float((r < profile.theta).mean())
    fracs = {t: float(np.mean([t in f.tags for f in frames])) for t in profile.type_weights}
    tw = max((fracs[t] * w for t, w in profile.type_weights.items()), default=0.0)
    s = 100.0 * (0.4 * (1.0 - p10) + 0.3 * below + 0.3 * tw)
    s = float(np.clip(s, 0.0, 100.0))

    # 대표 유형: 가중 빈도가 가장 큰 태그, 없으면 폭 협소 여부
    cand = {t: fracs[t] * profile.type_weights[t] for t in fracs if fracs[t] >= type_min_frac}
    if cand:
        primary = max(cand, key=cand.get)
    elif below >= type_min_frac:
        primary = "narrow"
    else:
        primary = "none"
    fw = np.array([f.free_width_m for f in frames if f.free_width_m is not None], dtype=float)
    return LinkScore(link_id, len(frames), round(s, 1), grade_of(s), primary,
                     round(p10, 3), round(float(np.median(r)), 3), round(below, 3), round(tw, 3),
                     {k: round(v, 3) for k, v in fracs.items()},
                     round(float(np.median(fw)), 2) if len(fw) else None,
                     round(float((fw < LEGAL_MIN_WIDTH_M).mean()), 3) if len(fw) else None)


def score_links(frames_by_link: Mapping[str, Sequence[FrameAnalysis]], profile: Profile = PEDESTRIAN,
                min_frames: int = 3) -> list[LinkScore]:
    out = []
    for lid, frs in frames_by_link.items():
        if len(frs) < min_frames:
            continue
        ls = score_link(lid, frs, profile)
        if ls is not None:
            out.append(ls)
    return sorted(out, key=lambda x: -x.score)
