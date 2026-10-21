"""멀티모달 LLM(Qwen3-VL) 판단·설명 층.

역할 분담: 세그 모델이 폭을 재고(width_ratio), 규칙이 점수를 매기고(scoring),
VLM 은 **측정 근거를 받아** 장면을 확인하고 담당자용 원인·조치 문장을 쓴다.
VLM 단독 판단은 환각이 심해서(2B: 사진과 무관하게 프롬프트 예시를 그대로 나열) 다음을 지킨다.
    1) 열린 나열 대신 닫힌 예/아니오 질문 (CHECKS)
    2) 세그 결과와 교차검증 → 일치 여부를 함께 저장, 불일치는 문장 생성 시 근거로 쓰지 않음
    3) bench 모드로 AI Hub GT 대비 환각률을 수치화

라이선스: Qwen3-VL Apache 2.0. 배포(CPU Space)에는 모델을 넣지 않고 결과 JSON 만 넣는다.

사용:
    # GT 대비 예/아니오 정확도 (환각률)
    python -m roadpush.vlm bench --gt data/coco/polygon_v1/valid --max-images 200 --model Qwen/Qwen3-VL-8B-Instruct
    # 링크별 확인 + 조치 제안 → <run>/links_vlm.json
    python -m roadpush.vlm explain --run outputs/sim_aihub_1 --top 20
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

DEFAULT_MODEL = "Qwen/Qwen3-VL-8B-Instruct"

# 닫힌 질문. key → (질문, 대응 RoadPush 클래스들 — GT/세그 교차검증용)
CHECKS: dict[str, tuple[str, tuple[str, ...]]] = {
    "sidewalk_visible": ("사진에 보행자 전용 보도(인도)가 보입니까?", ("sidewalk", "braille_guide_blocks")),
    "car": ("사진에 승용차가 있습니까?", ("car",)),
    "truck_bus": ("사진에 트럭이나 버스가 있습니까?", ("truck_bus",)),
    "two_wheeler": ("사진에 오토바이·자전거·킥보드가 있습니까?", ("two_wheeler",)),
    "person": ("사진에 사람이 있습니까?", ("person",)),
    "bollard": ("사진에 볼라드(차량 진입 방지 말뚝)가 있습니까?", ("bollard",)),
    "movable_signage": ("사진에 입간판(세워 둔 광고판)이 있습니까?", ("movable_signage",)),
    "construction": ("사진에 공사 구간이나 공사용 펜스·바리케이드가 있습니까?", ("repair_zone", "barricade")),
    "stairs": ("사진에 계단이나 높은 턱이 있습니까?", ("stairs",)),
    "pushed_to_road": ("이 지점에서 보행자가 차도나 차량 통행로로 내려가야 지나갈 수 있습니까?", ()),
}

SYSTEM = ("당신은 지자체 보도 점검 담당자를 돕는 시각 검사원입니다. 사진에 실제로 보이는 것만 답하고, "
          "확실하지 않으면 false 로 답합니다.")


class VLM:
    def __init__(self, model_id: str = DEFAULT_MODEL, max_side: int = 1024):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.proc = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.bfloat16, device_map="cuda")
        self.model_id = model_id
        self.max_side = max_side

    def _image(self, path):
        from PIL import Image
        im = Image.open(path).convert("RGB")
        s = self.max_side / max(im.size)
        return im.resize((round(im.width * s), round(im.height * s))) if s < 1 else im

    def chat(self, images: list, text: str, max_new_tokens: int = 256) -> str:
        content = [{"type": "image", "image": self._image(p)} for p in images] + [{"type": "text", "text": text}]
        msgs = [{"role": "system", "content": [{"type": "text", "text": SYSTEM}]},
                {"role": "user", "content": content}]
        inp = self.proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                            return_tensors="pt").to(self.model.device)
        out = self.model.generate(**inp, max_new_tokens=max_new_tokens, do_sample=False)
        return self.proc.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    def check(self, image) -> dict[str, bool | None]:
        """닫힌 질문 전부를 한 번에. 키별 true/false JSON."""
        qs = "\n".join(f"- {k}: {q}" for k, (q, _) in CHECKS.items())
        text = ("다음 질문 각각에 사진만 보고 true 또는 false 로 답하세요. 다른 말 없이 JSON 객체 하나만 출력합니다.\n"
                f"{qs}")
        return parse_bool_json(self.chat([image], text, 200), list(CHECKS))


def parse_bool_json(s: str, keys: list[str]) -> dict[str, bool | None]:
    m = re.search(r"\{.*\}", s, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    out = {}
    for k in keys:
        v = d.get(k)
        out[k] = v if isinstance(v, bool) else ({"true": True, "false": False}.get(str(v).lower()) if v is not None else None)
    return out


# ---------------------------------------------------------------- bench

def bench(args) -> None:
    from .evaluate import _load_coco

    gt, id2name, by = _load_coco(args.gt / "_annotations.coco.json")
    labeled = {id2name[a["category_id"]] for a in gt["annotations"]}
    keys = [k for k, (_, cls) in CHECKS.items() if cls and set(cls) & labeled]
    ims = gt["images"][:: max(1, len(gt["images"]) // args.max_images)][: args.max_images]
    vlm = VLM(args.model)
    stat = {k: defaultdict(int) for k in keys}
    t0 = time.time()
    for i, im in enumerate(ims):
        present = {id2name[a["category_id"]] for a in by[im["id"]] if a["area"] >= args.min_area}
        ans = vlm.check(args.gt / im["file_name"])
        for k in keys:
            g = bool(set(CHECKS[k][1]) & present)
            p = ans.get(k)
            stat[k]["tp" if g and p else "fn" if g else "fp" if p else "tn"] += 1
            stat[k]["unparsed"] += p is None
        if i % 20 == 0:
            print(f"  {i + 1}/{len(ims)} {(time.time() - t0) / (i + 1):.1f}s/img", flush=True)
    rep = {"model": args.model, "gt": str(args.gt), "n": len(ims), "min_area": args.min_area, "checks": {}}
    for k, s in stat.items():
        n = s["tp"] + s["fp"] + s["tn"] + s["fn"]
        rep["checks"][k] = {**s, "acc": round((s["tp"] + s["tn"]) / n, 3) if n else None,
                            "precision": round(s["tp"] / (s["tp"] + s["fp"]), 3) if s["tp"] + s["fp"] else None,
                            "recall": round(s["tp"] / (s["tp"] + s["fn"]), 3) if s["tp"] + s["fn"] else None,
                            "false_alarm_rate": round(s["fp"] / (s["fp"] + s["tn"]), 3) if s["fp"] + s["tn"] else None}
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- explain

SEG_KEYS = {k: cls for k, (_, cls) in CHECKS.items() if cls}


def seg_flags(counts: dict[str, int]) -> dict[str, bool]:
    return {k: any(counts.get(c, 0) > 0 for c in cls) for k, cls in SEG_KEYS.items()}


# 단절 유형별 사실 규칙 + 담당자 조치 메뉴 (일반론 "보도를 정비" 방지)
TYPE_GUIDE = {
    "vanish": ("보도가 없는 구간이다. '보도 위'라는 표현을 쓰지 말고 '보행자가 차량과 같은 공간을 지난다'고 쓴다.",
               "보행자 우선도로 지정·속도 저감(30 km/h)·노면 보행로 표시·보도 신설 검토"),
    "narrow": ("보도는 있으나 장애물로 통과 폭이 좁아진 구간이다. 확인된 요소를 원인으로 쓴다.",
               "불법 주정차 단속(차량·이륜차)·적치물·입간판 정비·볼라드/시설물 재배치"),
    "repair": ("공사·파손으로 통행이 막힌 구간이다.", "공사 구간 임시 보행로 확보·안내 표지·파손 보수"),
    "stairs": ("계단·턱으로 휠체어·유모차 통행이 막힌 구간이다.", "경사로·턱 낮춤 설치"),
    "none": ("측정상 큰 단절은 없다.", "정기 모니터링"),
}


def explain_prompt(link: dict, frames: list[dict]) -> str:
    lines = [f"- 프레임 {i + 1}: 유효보행폭 비율 {f['ratio']:.2f}, 보도 감지 {'예' if f['sidewalk_present'] else '아니오'}, "
             f"보도 위 장애물 {f.get('n_obstacles_on_sidewalk', 0)}개, 확인된 요소: {', '.join(f['confirmed']) or '없음'}"
             for i, f in enumerate(frames)]
    return (
        "아래는 한 도로 구간(링크)에서 AI가 측정한 결과와 해당 구간의 가장 나쁜 프레임 사진입니다.\n"
        f"링크 점수 {link['score']:.0f}/100 ({link['grade']}), 대표 단절 유형: {link['primary_type_ko']}, "
        f"하위 10% 유효보행폭 비율 {link['p10_ratio']:.2f}, 비율 0.5 미만 프레임 비중 {link['frac_below'] * 100:.0f}%.\n"
        + "\n".join(lines) + "\n\n"
        f"유형 규칙: {TYPE_GUIDE.get(link['primary_type'], TYPE_GUIDE['none'])[0]}\n"
        f"조치 선택지(이 중에서 골라 구체적으로): {TYPE_GUIDE.get(link['primary_type'], TYPE_GUIDE['none'])[1]}\n\n"
        "측정 결과와 사진을 근거로, 구청 보도 담당자에게 보낼 메모를 쓰세요. 사진과 측정에 없는 내용은 쓰지 마세요. "
        "유형 규칙 문장을 그대로 베끼지 말고, 원인에는 사진에서 실제로 보이는 구체 요소(예: 어느 쪽에 무엇이 몇 대, "
        "골목 폭, 노면 상태)를 하나 이상 넣으세요.\n"
        '출력은 JSON 하나: {"cause": "보행 단절 원인 한 문장", "action": "권고 조치 한 문장(단속/정비/구조 개선 중 무엇인지 포함)", '
        '"priority": "즉시|단기|중기"}'
    )


def explain(args) -> None:
    import csv

    import geopandas as gpd

    run = args.run
    res = {}
    with open(run / "frame_results.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            res[r["frame"]] = r
    by_link = defaultdict(list)
    with open(run / "frames_linked.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["link_id"]:
                by_link[r["link_id"]].append(res[r["frame"]])
    links = gpd.read_file(run / "links_scored.geojson").sort_values("score", ascending=False)
    links = links[links.grade != "안전"].head(args.top) if not args.include_safe else links.head(args.top)

    vlm = VLM(args.model)
    out, agree, total = {}, 0, 0
    for _, L in links.iterrows():
        frs = sorted(by_link[L.link_id], key=lambda r: r["ratio"])[: args.frames]
        evid = []
        for fr in frs:
            img = run / "frames" / fr["frame"]
            ans = vlm.check(img)
            seg = seg_flags(fr.get("counts", {}))
            # 교차검증: 세그와 VLM 이 모두 '있다'고 한 요소만 확인됨으로
            confirmed = [k for k, v in seg.items() if v and ans.get(k)]
            for k in SEG_KEYS:
                if ans.get(k) is not None:
                    total += 1
                    agree += ans[k] == seg[k]
            evid.append({**fr, "vlm": ans, "seg": seg, "confirmed": confirmed})
        imgs = [run / "frames" / e["frame"] for e in evid]
        raw = vlm.chat(imgs, explain_prompt(L.to_dict(), evid), 300)
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            memo = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            memo = {}
        out[L.link_id] = {"memo": memo, "raw": raw if not memo else "", "pushed_to_road":
                          sum(bool(e["vlm"].get("pushed_to_road")) for e in evid) / max(1, len(evid)),
                          "frames": [{k: e[k] for k in ("frame", "ratio", "vlm", "seg", "confirmed")} for e in evid]}
        print(f"  {L.link_id} {L.score:.0f} → {memo.get('cause', raw[:60])}", flush=True)
    meta = {"model": args.model, "seg_vlm_agreement": round(agree / total, 3) if total else None}
    (run / "links_vlm.json").write_text(json.dumps({"meta": meta, "links": out}, ensure_ascii=False, indent=2))
    print("seg-VLM 일치율", meta["seg_vlm_agreement"], "→", run / "links_vlm.json")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench")
    b.add_argument("--gt", required=True, type=Path)
    b.add_argument("--max-images", type=int, default=200)
    b.add_argument("--min-area", type=float, default=1500.0, help="이보다 작은 GT 객체는 '없음'으로 (원거리 점 객체)")
    b.add_argument("--model", default=DEFAULT_MODEL)
    b.add_argument("--out", type=Path)
    e = sub.add_parser("explain")
    e.add_argument("--run", required=True, type=Path)
    e.add_argument("--top", type=int, default=20)
    e.add_argument("--frames", type=int, default=3)
    e.add_argument("--include-safe", action="store_true")
    e.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args(argv)
    bench(args) if args.cmd == "bench" else explain(args)


if __name__ == "__main__":
    main()
