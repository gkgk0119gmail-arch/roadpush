"""영상 → 1fps 프레임 + GPX 시각 매칭.

촬영 규약(PLAN 6장): 폰 1080p 30fps, 동시에 GPX 로거 앱 기록.
영상 시작 시각은 ffprobe creation_time(UTC)을 쓰고, 어긋나면 --offset 초로 보정한다.

출력 CSV (frames.csv):
    frame, t_sec, utc, lat, lon, gps_ok
gps_ok=0 : GPX 범위 밖이거나 앞뒤 포인트 간격이 max_gap_s 초과

사용:
    python -m roadpush.frames --video data/raw/footage/20261022_sinchon/a.mp4 \
        --gpx data/raw/footage/20261022_sinchon/a.gpx --out outputs/20261022_sinchon/a
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


@dataclass
class Track:
    t: np.ndarray     # unix seconds, 오름차순
    lat: np.ndarray
    lon: np.ndarray


def load_gpx(path: str | Path) -> Track:
    import gpxpy

    with open(path, encoding="utf-8") as f:
        g = gpxpy.parse(f)
    pts = [p for trk in g.tracks for seg in trk.segments for p in seg.points if p.time is not None]
    pts.sort(key=lambda p: p.time)
    t = np.array([p.time.replace(tzinfo=p.time.tzinfo or timezone.utc).timestamp() for p in pts])
    return Track(t, np.array([p.latitude for p in pts]), np.array([p.longitude for p in pts]))


def smooth(track: Track, window: int = 5) -> Track:
    """이동평균 (PLAN 10장: GPS 오차 대응). window는 홀수 포인트 수."""
    if window <= 1 or len(track.t) < window:
        return track
    k = np.ones(window) / window
    pad = window // 2

    def ma(a):
        return np.convolve(np.pad(a, pad, mode="edge"), k, mode="valid")

    return Track(track.t, ma(track.lat), ma(track.lon))


def interpolate(track: Track, times: np.ndarray, max_gap_s: float = 10.0):
    """times(unix)의 위치. (lat, lon, ok) 배열."""
    lat = np.interp(times, track.t, track.lat)
    lon = np.interp(times, track.t, track.lon)
    idx = np.searchsorted(track.t, times)
    inside = (idx > 0) & (idx < len(track.t))
    gap = np.full(times.shape, np.inf)
    gap[inside] = track.t[idx[inside]] - track.t[idx[inside] - 1]
    exact = np.isin(times, track.t)
    ok = (inside & (gap <= max_gap_s)) | exact
    return lat, lon, ok


def video_start_utc(video: str | Path) -> float | None:
    """ffprobe creation_time → unix seconds. 없으면 None."""
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video)],
        capture_output=True, text=True, check=False)
    try:
        tag = json.loads(out.stdout)["format"]["tags"]["creation_time"]
    except (KeyError, json.JSONDecodeError):
        return None
    return datetime.fromisoformat(tag.replace("Z", "+00:00")).timestamp()


def extract_frames(video: str | Path, out_dir: str | Path, fps: float = 1.0, width: int = 1280) -> list[Path]:
    """ffmpeg로 fps 간격 프레임 추출. frame_000001.jpg 는 t=0.5/fps 근방(ffmpeg fps 필터 규약)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
         "-vf", f"fps={fps},scale={width}:-2", "-q:v", "3", str(out_dir / "frame_%06d.jpg")],
        check=True)
    return sorted(out_dir.glob("frame_*.jpg"))


def frame_times(n: int, fps: float) -> np.ndarray:
    return (np.arange(n) + 0.5) / fps


def write_frames_csv(path: Path, frames: list[Path], t_sec: np.ndarray, t0: float | None,
                     track: Track | None, max_gap_s: float = 10.0) -> None:
    if track is not None and t0 is not None:
        lat, lon, ok = interpolate(track, t0 + t_sec, max_gap_s)
    else:
        lat = lon = np.full(len(frames), np.nan)
        ok = np.zeros(len(frames), dtype=bool)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t_sec", "utc", "lat", "lon", "gps_ok"])
        for i, fp in enumerate(frames):
            utc = datetime.fromtimestamp(t0 + t_sec[i], timezone.utc).isoformat() if t0 else ""
            w.writerow([fp.name, f"{t_sec[i]:.2f}", utc, f"{lat[i]:.7f}", f"{lon[i]:.7f}", int(ok[i])])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--gpx", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--offset", type=float, default=0.0, help="영상 시작 시각 보정(초, +면 늦춤)")
    ap.add_argument("--smooth", type=int, default=5)
    args = ap.parse_args(argv)

    frames = extract_frames(args.video, args.out / "frames", args.fps)
    t_sec = frame_times(len(frames), args.fps)
    t0 = video_start_utc(args.video)
    t0 = t0 + args.offset if t0 is not None else None
    track = smooth(load_gpx(args.gpx), args.smooth) if args.gpx else None
    write_frames_csv(args.out / "frames.csv", frames, t_sec, t0, track)
    print(f"frames={len(frames)} t0={t0} gpx={'yes' if track else 'no'} → {args.out / 'frames.csv'}")


if __name__ == "__main__":
    main()
