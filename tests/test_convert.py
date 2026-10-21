import json
from pathlib import Path

import numpy as np

from roadpush.classes import CLASS_TO_ID, map_aihub
from roadpush.convert_aihub_to_coco import main, parse_cvat_xml, shoelace_area

XML = """<?xml version="1.0" encoding="utf-8"?>
<annotations>
  <version>1.1</version>
  <meta><task><name>test</name></task></meta>
  <image id="0" name="imgs/a.jpg" width="200" height="100">
    <polygon label="sidewalk" occluded="0" points="10,90;190,90;190,60;10,60" z_order="0">
      <attribute name="attribute">blocks</attribute>
    </polygon>
    <polygon label="caution_zone" occluded="0" points="50,70;80,70;80,60;50,60" z_order="1">
      <attribute name="attribute">repair_zone</attribute>
    </polygon>
    <polygon label="car" occluded="0" points="100,90;140,90;140,70;100,70" z_order="2"/>
    <polygon label="unicorn" occluded="0" points="0,0;1,0;1,1" z_order="3"/>
    <box label="bollard" occluded="0" xtl="20" ytl="70" xbr="25" ybr="90" z_order="4"/>
  </image>
  <image id="1" name="imgs/b.jpg" width="200" height="100">
    <polygon label="roadway" occluded="0" points="0,99;199,99;199,80;0,80" z_order="0"/>
  </image>
</annotations>
"""


def test_map_aihub():
    assert map_aihub("sidewalk", "blocks") == "sidewalk"
    assert map_aihub("caution_zone", "stairs") == "stairs"
    assert map_aihub("caution_zone", "manhole") == "caution_other"
    assert map_aihub("bus") == "truck_bus"
    assert map_aihub("unicorn") is None


def test_shoelace():
    assert shoelace_area([0, 0, 10, 0, 10, 5, 0, 5]) == 50.0


def test_parse_and_convert(tmp_path: Path):
    from collections import Counter
    raw = tmp_path / "raw"; (raw / "labels").mkdir(parents=True); (raw / "imgs").mkdir()
    (raw / "labels" / "x.xml").write_text(XML, encoding="utf-8")
    # 더미 이미지 파일 (내용 무관)
    (raw / "imgs" / "a.jpg").write_bytes(b"\xff\xd8\xff")
    (raw / "imgs" / "b.jpg").write_bytes(b"\xff\xd8\xff")

    unknown = Counter()
    recs = parse_cvat_xml(raw / "labels" / "x.xml", include_boxes=True, unknown=unknown)
    assert len(recs) == 2
    assert [s.cls for s in recs[0].shapes] == ["sidewalk", "repair_zone", "car", "bollard"]
    assert unknown["unicorn"] == 1

    out = tmp_path / "coco"
    main(["--xml-dir", str(raw / "labels"), "--img-root", str(raw), "--out", str(out),
          "--val-ratio", "0.0", "--include-boxes", "--link", "copy"])
    coco = json.loads((out / "train" / "_annotations.coco.json").read_text())
    assert len(coco["images"]) == 2
    assert len(coco["annotations"]) == 5
    assert (out / "train" / "a.jpg").exists()
    cats = {c["name"]: c["id"] for c in coco["categories"]}
    assert cats == CLASS_TO_ID
    car = next(a for a in coco["annotations"] if a["category_id"] == CLASS_TO_ID["car"])
    assert car["bbox"] == [100.0, 70.0, 40.0, 20.0] and car["area"] == 800.0
