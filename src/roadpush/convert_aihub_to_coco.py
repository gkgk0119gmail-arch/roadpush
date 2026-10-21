"""AI Hub 인도보행 영상 라벨(CVAT XML 1.1 가정) → COCO instance-seg (RF-DETR 레이아웃).

출력:
    <out>/train/_annotations.coco.json  + 이미지(symlink|copy)
    <out>/valid/_annotations.coco.json  + 이미지

사용:
    python -m roadpush.convert_aihub_to_coco --xml-dir data/raw/aihub --img-root data/raw/aihub --inspect
    python -m roadpush.convert_aihub_to_coco --xml-dir data/raw/aihub --img-root data/raw/aihub \
        --out data/coco/aihub_v1 --val-ratio 0.1 --link symlink

주의: 실데이터 XML 구조는 받아서 --inspect 로 먼저 확인할 것. 아래 파서는
<image id name width height>
    <polygon label=".." points="x,y;x,y;..." occluded z_order><attribute name="..">v</attribute></polygon>
    <box label=".." xtl ytl xbr ybr> ... </box>
를 가정한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .classes import CLASSES, CLASS_TO_ID, map_aihub

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


@dataclass
class Shape:
    cls: str
    polygon: list[float]  # [x1,y1,x2,y2,...]
    attributes: dict[str, str] = field(default_factory=dict)
    source: str = "polygon"  # polygon | box


@dataclass
class ImageRecord:
    name: str
    width: int
    height: int
    shapes: list[Shape]
    xml_path: str


def _parse_points(s: str) -> list[float]:
    pts: list[float] = []
    for pair in s.strip().split(";"):
        if not pair:
            continue
        x, y = pair.split(",")
        pts.extend([float(x), float(y)])
    return pts


def _attrs(el) -> dict[str, str]:
    return {a.get("name", ""): (a.text or "").strip() for a in el.findall("attribute")}


def _first_attr_value(attrs: dict[str, str]) -> str | None:
    """AI Hub는 속성 이름이 'attribute' 하나인 경우가 많다. 첫 값을 대표 속성으로."""
    if not attrs:
        return None
    if "attribute" in attrs:
        return attrs["attribute"]
    return next(iter(attrs.values()))


def parse_cvat_xml(path: Path, include_boxes: bool, unknown: Counter) -> list[ImageRecord]:
    tree = etree.parse(str(path))
    root = tree.getroot()
    records: list[ImageRecord] = []
    for img in root.iter("image"):
        name = img.get("name")
        w, h = int(float(img.get("width"))), int(float(img.get("height")))
        shapes: list[Shape] = []
        for poly in img.findall("polygon"):
            attrs = _attrs(poly)
            cls = map_aihub(poly.get("label", ""), _first_attr_value(attrs))
            if cls is None:
                unknown[poly.get("label", "")] += 1
                continue
            pts = _parse_points(poly.get("points", ""))
            if len(pts) < 6:
                continue
            shapes.append(Shape(cls, pts, attrs, "polygon"))
        if include_boxes:
            for box in img.findall("box"):
                attrs = _attrs(box)
                cls = map_aihub(box.get("label", ""), _first_attr_value(attrs))
                if cls is None:
                    unknown[box.get("label", "")] += 1
                    continue
                x1, y1 = float(box.get("xtl")), float(box.get("ytl"))
                x2, y2 = float(box.get("xbr")), float(box.get("ybr"))
                shapes.append(Shape(cls, [x1, y1, x2, y1, x2, y2, x1, y2], attrs, "box"))
        records.append(ImageRecord(name, w, h, shapes, str(path)))
    return records


def shoelace_area(pts: list[float]) -> float:
    xs, ys = pts[0::2], pts[1::2]
    n = len(xs)
    return abs(sum(xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i] for i in range(n))) / 2.0


def polygon_bbox(pts: list[float]) -> list[float]:
    xs, ys = pts[0::2], pts[1::2]
    x0, y0 = min(xs), min(ys)
    return [x0, y0, max(xs) - x0, max(ys) - y0]


def build_image_index(img_root: Path) -> dict[str, Path]:
    """basename → 실제 경로. 동일 basename이 여러 개면 첫 것(경고)."""
    index: dict[str, Path] = {}
    dup = 0
    for p in img_root.rglob("*"):
        if p.suffix.lower() in IMG_EXTS and "MASK" not in p.parts:   # MASK/*.png 는 라벨 렌더링
            key = p.name
            if key in index:
                dup += 1
                continue
            index[key] = p
    if dup:
        print(f"[warn] 동일 파일명 중복 {dup}개: 첫 경로만 사용")
    return index


def stable_split(name: str, val_ratio: float) -> str:
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "valid" if h < val_ratio else "train"


def to_coco(records: list[ImageRecord], img_index: dict[str, Path]) -> tuple[dict, int]:
    images, annotations = [], []
    ann_id, missing = 1, 0
    for img_id, rec in enumerate(records, start=1):
        base = Path(rec.name).name
        src = img_index.get(base)
        if src is None:
            missing += 1
            continue
        images.append({"id": img_id, "file_name": base, "width": rec.width, "height": rec.height})
        for s in rec.shapes:
            area = shoelace_area(s.polygon)
            if area < 1.0:
                continue
            annotations.append({
                "id": ann_id,
                "image_id": img_id,
                "category_id": CLASS_TO_ID[s.cls],
                "segmentation": [s.polygon],
                "bbox": polygon_bbox(s.polygon),
                "area": area,
                "iscrowd": 0,
                "attributes": s.attributes,   # COCO 비표준 필드(무시돼도 무해)
                "source": s.source,
            })
            ann_id += 1
    categories = [{"id": CLASS_TO_ID[c], "name": c, "supercategory": "roadpush"} for c in CLASSES]
    return {"images": images, "annotations": annotations, "categories": categories}, missing


def materialize(coco: dict, img_index: dict[str, Path], out_dir: Path, link: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for im in coco["images"]:
        dst = out_dir / im["file_name"]
        if dst.exists() or link == "none":
            continue
        src = img_index[im["file_name"]]
        if link == "symlink":
            os.symlink(src.resolve(), dst)
        else:
            shutil.copy2(src, dst)
    (out_dir / "_annotations.coco.json").write_text(json.dumps(coco, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml-dir", required=True, type=Path)
    ap.add_argument("--img-root", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/coco/aihub_v1"))
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--split-by", choices=["xml", "image"], default="xml",
                    help="xml: XML(=연속 촬영 폴더) 단위 분할. 인접 프레임이 train/valid 로 새는 것 방지")
    ap.add_argument("--include-boxes", action="store_true", help="<box>를 사각 폴리곤으로 포함")
    ap.add_argument("--link", choices=["symlink", "copy", "none"], default="symlink")
    ap.add_argument("--max-images", type=int, default=0, help="디버그용 상한(0=전체)")
    ap.add_argument("--inspect", action="store_true", help="라벨/속성 분포만 출력하고 종료")
    ap.add_argument("--select-classes", default="",
                    help="쉼표 목록 중 하나라도 포함한 이미지만 남김 (희소 클래스 보강용)")
    args = ap.parse_args(argv)

    xml_files = sorted(args.xml_dir.rglob("*.xml"))
    if not xml_files:
        raise SystemExit(f"XML 없음: {args.xml_dir}")
    print(f"XML {len(xml_files)}개")

    unknown: Counter = Counter()
    records: list[ImageRecord] = []
    for xp in xml_files:
        records.extend(parse_cvat_xml(xp, args.include_boxes, unknown))
        if args.max_images and len(records) >= args.max_images:
            records = records[: args.max_images]
            break
    print(f"이미지 레코드 {len(records)}개")
    if args.select_classes:
        want = set(args.select_classes.split(","))
        records = [r for r in records if any(sh.cls in want for sh in r.shapes)]
        print(f"선택 클래스 포함 이미지 {len(records)}개 ({','.join(sorted(want))})")

    if args.inspect:
        cls_cnt: Counter = Counter()
        attr_cnt: dict[str, Counter] = defaultdict(Counter)
        for r in records:
            for s in r.shapes:
                cls_cnt[s.cls] += 1
                for k, v in s.attributes.items():
                    attr_cnt[s.cls][f"{k}={v}"] += 1
        print("\n[클래스 분포]")
        for c in CLASSES:
            print(f"  {c:22s} {cls_cnt.get(c, 0):8d}")
        print("\n[속성 분포(상위 8)]")
        for c, cnt in attr_cnt.items():
            print(f"  {c}: {cnt.most_common(8)}")
        if unknown:
            print("\n[매핑 안 된 라벨]", unknown.most_common())
        return

    img_index = build_image_index(args.img_root)
    print(f"이미지 파일 인덱스 {len(img_index)}개")

    by_split: dict[str, list[ImageRecord]] = {"train": [], "valid": []}
    for r in records:
        key = Path(r.xml_path).stem if args.split_by == "xml" else Path(r.name).name
        by_split[stable_split(key, args.val_ratio)].append(r)

    for split, recs in by_split.items():
        coco, missing = to_coco(recs, img_index)
        materialize(coco, img_index, args.out / split, args.link)
        print(f"{split}: images={len(coco['images'])} anns={len(coco['annotations'])} missing_img={missing}")
    if unknown:
        print("[매핑 안 된 라벨]", unknown.most_common())
    print("완료:", args.out)


if __name__ == "__main__":
    main()
