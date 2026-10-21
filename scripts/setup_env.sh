#!/usr/bin/env bash
# RoadPush 환경 세팅 (Linux / WSL2 Ubuntu, NVIDIA RTX 3090, conda 필요)
# 사용: bash scripts/setup_env.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== [1/3] roadpush env (py3.11): torch cu128 + rfdetr + app =="
conda create -y -n roadpush python=3.11
conda run -n roadpush pip install --upgrade pip
conda run -n roadpush pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
conda run -n roadpush pip install rfdetr supervision
# rfdetr가 torch를 CPU 버전으로 바꿔치기하면 아래 줄을 다시 실행
# conda run -n roadpush pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu128
conda run -n roadpush pip install -e ".[train,geo,app,dev]"
conda run -n roadpush python - <<'PY'
import torch
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu", torch.cuda.get_device_name(0), round(torch.cuda.get_device_properties(0).total_memory/2**30,1), "GB")
from rfdetr import RFDETRSegMedium  # import 확인만
print("rfdetr OK")
PY

echo "== [2/3] sam3 env (py3.12): teacher 전용 =="
conda create -y -n sam3 python=3.12
conda run -n sam3 pip install --upgrade pip
conda run -n sam3 pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
mkdir -p third_party
[ -d third_party/sam3 ] || git clone https://github.com/facebookresearch/sam3 third_party/sam3
conda run -n sam3 pip install -e third_party/sam3
conda run -n sam3 pip install huggingface_hub opencv-python-headless
echo "SAM 3 체크포인트는 HF 게이트 승인 후:  conda run -n sam3 hf auth login"

echo "== [3/3] 시스템 도구 =="
command -v ffmpeg >/dev/null || echo "ffmpeg 없음: sudo apt install -y ffmpeg"
command -v tmux   >/dev/null || echo "tmux 없음:   sudo apt install -y tmux"
command -v pdftotext >/dev/null || echo "pdftotext 없음: sudo apt install -y poppler-utils"
echo "완료. 학습은 반드시 tmux 안에서:  tmux new -s train"
