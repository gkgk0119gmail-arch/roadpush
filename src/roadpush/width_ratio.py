"""프레임별 유효보행폭 비율 (RoadPush 핵심 기여).

입력은 세그 모델이 준 보도 마스크와 장애물 인스턴스 마스크들.
원근 오차 때문에 절대폭 대신 **비율**을 쓴다(제안자 답변서 1번).

정의 (한 스캔라인 y 기준):
    corridor : 보도(S) 또는 장애물(O) 픽셀이 연속된 구간 중 보도 픽셀이 가장 많은 것
    span     : corridor 길이(px)                  … 원래 보도 폭
    free     : corridor 안에서 S & ~O 가 연속된 최대 길이 … 실제로 지나갈 수 있는 최대 폭
    blocked  : corridor 안의 O 픽셀 수
    ratio    : free / span                        … 유효보행폭 비율 (0~1)

프레임 값은 하단 여러 스캔라인의 중앙값. 보도가 거의 안 보이면 sidewalk_present=False.

절대폭(보조 지표, 1.2 m 법정 유효폭 비교용) — metric_width():
    평지·직선·폭 일정한 보도를 카메라 롤 0 으로 보면 행 y 의 보도 폭(px)은 span(y) = a·(y − y_h) (y_h: 지평선).
    핀홀 모델에서 지면 거리 Z = h·f/(y − y_h), 실제 폭 W = span·Z/f = h·a  → 초점거리 없이 **카메라 높이 h 만** 필요.
    지나갈 수 있는 폭 = h·free(y)/(y − y_h). 가정이 깨지면(곡선·경사·화면 밖) 적합도(R²)로 걸러 None.

장애물은 "보도 위에 있는 것"만 센다: 인스턴스의 발점(footpoint, 가장 아래 행의 중앙 x)이
팽창시킨 보도 마스크 안에 있으면 보도 위로 판정 (차도 위 차량 배제).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

Mask = np.ndarray  # bool, (H, W)


@dataclass
class RowResult:
    y: int
    span: int
    free: int
    blocked: int
    x0: int = 0          # corridor 시작 x
    x1: int = 0          # corridor 끝 x (exclusive)

    @property
    def ratio(self) -> float:
        return self.free / self.span if self.span > 0 else 0.0


@dataclass
class FrameResult:
    ratio: float                 # 중앙값 (보도 없으면 0.0)
    min_ratio: float             # 가장 나쁜 스캔라인
    sidewalk_present: bool
    rows: list[RowResult] = field(default_factory=list)
    n_rows_requested: int = 0
    metric: "MetricWidth | None" = None

    @property
    def valid_fraction(self) -> float:
        return len(self.rows) / self.n_rows_requested if self.n_rows_requested else 0.0


# ---------------------------------------------------------------- 유틸

def runs(row: np.ndarray) -> list[tuple[int, int]]:
    """bool 1D → True 연속 구간 [(start, end_exclusive), ...]"""
    row = np.asarray(row, dtype=bool)
    if row.size == 0 or not row.any():
        return []
    padded = np.concatenate(([False], row, [False]))
    d = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), ends.tolist()))


def dilate(mask: Mask, px: int) -> Mask:
    """정사각 커널 팽창 (numpy 전용, 분리 가능 max 필터)."""
    if px <= 0:
        return mask.astype(bool)
    m = mask.astype(bool)
    out = m.copy()
    for k in range(1, px + 1):           # 가로
        out[:, k:] |= m[:, :-k]
        out[:, :-k] |= m[:, k:]
    m2 = out.copy()
    for k in range(1, px + 1):           # 세로
        out[k:, :] |= m2[:-k, :]
        out[:-k, :] |= m2[k:, :]
    return out


def footpoint(inst: Mask) -> tuple[int, int] | None:
    """인스턴스 마스크의 발점 (y_bottom, x_median). 비어 있으면 None."""
    ys = np.flatnonzero(inst.any(axis=1))
    if ys.size == 0:
        return None
    y = int(ys.max())
    xs = np.flatnonzero(inst[y])
    return y, int(np.median(xs))


def obstacles_on_sidewalk(sidewalk: Mask, instances: Iterable[Mask], dilate_px: int = 15) -> Mask:
    """발점이 (팽창된) 보도 안에 있는 인스턴스만 합친 마스크."""
    sw = dilate(sidewalk, dilate_px)
    out = np.zeros_like(sidewalk, dtype=bool)
    for inst in instances:
        fp = footpoint(inst)
        if fp is None:
            continue
        y, x = fp
        if sw[y, x]:
            out |= inst.astype(bool)
    return out


# ---------------------------------------------------------------- 핵심

def row_ratio(sidewalk_row: np.ndarray, obstacle_row: np.ndarray, y: int = 0,
              min_sidewalk_px: int = 40) -> RowResult | None:
    S = np.asarray(sidewalk_row, dtype=bool)
    O = np.asarray(obstacle_row, dtype=bool)
    best = None
    best_key = (-1, -1)
    for a, b in runs(S | O):
        n_s = int(S[a:b].sum())
        key = (n_s, b - a)
        if key > best_key:
            best_key, best = key, (a, b)
    if best is None or best_key[0] < min_sidewalk_px:
        return None
    a, b = best
    free_runs = runs(S[a:b] & ~O[a:b])
    free = max((e - s for s, e in free_runs), default=0)
    blocked = int(O[a:b].sum())
    return RowResult(y=y, span=b - a, free=free, blocked=blocked, x0=a, x1=b)


def default_rows(height: int, fractions: Sequence[float] = (0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9)) -> list[int]:
    return [min(height - 1, int(round(height * f))) for f in fractions]


@dataclass
class MetricWidth:
    width_m: float          # 보도 폭 (h·a)
    min_free_m: float       # 스캔라인 중 가장 좁은 통과 가능 폭
    horizon_y: float
    r2: float
    n_rows: int


def metric_width(rows: Sequence[RowResult], img_w: int, cam_h: float = 1.3, min_rows: int = 4,
                 min_r2: float = 0.9, edge_px: int = 2) -> MetricWidth | None:
    """스캔라인 폭의 선형성으로 지평선을 추정해 m 단위 폭 계산. 가정이 안 맞으면 None."""
    rs = [r for r in rows if r.x0 > edge_px and r.x1 < img_w - edge_px]   # 화면 가장자리에 잘린 행 제외
    if len(rs) < min_rows:
        return None
    y = np.array([r.y for r in rs], float)
    span = np.array([r.span for r in rs], float)
    a, c = np.polyfit(y, span, 1)
    if a <= 0:
        return None
    pred = a * y + c
    ss = float(((span - span.mean()) ** 2).sum())
    r2 = 1.0 - float(((span - pred) ** 2).sum()) / ss if ss > 0 else 0.0
    y_h = -c / a
    if r2 < min_r2 or y_h >= y.min():
        return None
    free_m = [cam_h * r.free / (r.y - y_h) for r in rs]
    return MetricWidth(round(float(cam_h * a), 3), round(float(min(free_m)), 3), round(float(y_h), 1), round(r2, 3), len(rs))


def frame_ratio(sidewalk: Mask, obstacle: Mask, rows: Sequence[int] | None = None,
                min_sidewalk_px: int = 40, min_valid_fraction: float = 0.5, cam_h: float = 1.3) -> FrameResult:
    """프레임 하나의 유효보행폭 비율.

    sidewalk : 걸을 수 있는 면(sidewalk ∪ braille) 마스크
    obstacle : 보도 위 장애물 마스크 (obstacles_on_sidewalk 결과 권장)
    """
    assert sidewalk.shape == obstacle.shape, "마스크 크기 불일치"
    H = sidewalk.shape[0]
    rows = list(rows) if rows is not None else default_rows(H)
    results: list[RowResult] = []
    for y in rows:
        r = row_ratio(sidewalk[y], obstacle[y], y=y, min_sidewalk_px=min_sidewalk_px)
        if r is not None:
            results.append(r)
    if len(results) < max(1, int(np.ceil(min_valid_fraction * len(rows)))):
        return FrameResult(0.0, 0.0, False, results, len(rows))
    ratios = np.array([r.ratio for r in results])
    mw = metric_width(results, sidewalk.shape[1], cam_h)
    return FrameResult(float(np.median(ratios)), float(ratios.min()), True, results, len(rows), mw)
