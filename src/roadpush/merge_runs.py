"""여러 분석 run(프레임·추론 결과)을 하나의 세션으로 합친다 (예: 일반 사진 + 360° 변환 사진).

각 run 은 frames/, frames.csv, frame_results.jsonl, overlay/, (attribution.json) 을 가진 infer 이후 상태.
프레임 이름 충돌을 막기 위해 run 별 접두어를 붙이고, 파일은 심볼릭 링크로 연결한다.
합친 뒤 aggregate.py 로 링크 점수를 다시 계산한다.

사용:
    python -m roadpush.merge_runs --out outputs/mly_downtown --run p:outputs/mly_downtown_all --run v:outputs/mly_downtown_pano
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path


def merge(runs: list[tuple[str, Path]], out: Path) -> int:
    for sub in ("frames", "overlay"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    rows, header, attrib, n = [], None, [], 0
    with open(out / "frame_results.jsonl", "w", encoding="utf-8") as fr:
        for prefix, run in runs:
            with open(run / "frames.csv", encoding="utf-8") as f:
                rd = csv.DictReader(f)
                header = header or rd.fieldnames
                for r in rd:
                    rows.append({**r, "frame": f"{prefix}_{r['frame']}"})
            for line in open(run / "frame_results.jsonl", encoding="utf-8"):
                d = json.loads(line)
                d["frame"] = f"{prefix}_{d['frame']}"
                fr.write(json.dumps(d, ensure_ascii=False) + "\n")
                n += 1
            for sub in ("frames", "overlay"):
                for p in (run / sub).glob("*.jpg"):
                    dst = out / sub / f"{prefix}_{p.name}"
                    if not dst.exists():
                        os.symlink(p.resolve(), dst)
            a = run / "attribution.json"
            if a.exists():
                for it in json.loads(a.read_text())["images"]:
                    attrib.append({**it, "frame": f"{prefix}_{it['frame']}"})
    with open(out / "frames.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    if attrib:
        (out / "attribution.json").write_text(json.dumps(
            {"license": "CC BY-SA 4.0", "source": "Mapillary", "images": attrib}, ensure_ascii=False, indent=1))
    return n


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--run", action="append", required=True, help="<접두어>:<run 폴더>")
    args = ap.parse_args(argv)
    runs = [(s.partition(":")[0], Path(s.partition(":")[2])) for s in args.run]
    print(f"합친 프레임 {merge(runs, args.out)} → {args.out}")


if __name__ == "__main__":
    main()
