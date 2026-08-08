#!/bin/bash

ROOT_DIR=/comfyui

. ${ROOT_DIR}/venv/bin/activate

apt-get update -y 
apt-get install git-all -y

uv add transformers compel opencv-contrib-python ffmpeg

uv pip install \
        -r https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/requirements.txt \
        -r https://raw.githubusercontent.com/crystian/ComfyUI-Crystools/main/requirements.txt \
        -r https://raw.githubusercontent.com/Kosinkadink/ComfyUI-VideoHelperSuite/main/requirements.txt \
        -r https://raw.githubusercontent.com/Fannovel16/comfyui_controlnet_aux/main/requirements.txt \
        -r https://raw.githubusercontent.com/ryanontheinside/ComfyUI_RyanOnTheInside/main/requirements.txt \
        -r https://raw.githubusercontent.com/kijai/ComfyUI-KJNodes/main/requirements.txt \
        -r https://raw.githubusercontent.com/FizzleDorf/ComfyUI_FizzNodes/main/requirements.txt \
        -r https://raw.githubusercontent.com/edenartlab/eden_comfy_pipelines/main/requirements.txt

uv pip install -r extra-requirements.txt
uv pip install cv2 deepdiff librosa matplotlib open_clip insightface omegaconf pydub lark ffmpeg ftfy compel tagger_model_names

# --- LTX-2.3 support -------------------------------------------------------
# LTX-2.3 itself is natively supported by ComfyUI core (v0.16.1+), but the
# IC-LoRA nodes (LTXAddVideoICLoRAGuide, LTXICLoRALoaderModelOnly,
# LTXVImgToVideoConditionOnly, LTXVTiledVAEDecode, etc.) live in this repo.
# ComfyUI-GGUF lets low-VRAM cards load quantized LTX-2.3 GGUF checkpoints.
mkdir -p "${ROOT_DIR}/custom_nodes"
for repo in \
    "https://github.com/Lightricks/ComfyUI-LTXVideo.git" \
    "https://github.com/city96/ComfyUI-GGUF.git" \
    "https://github.com/alisson-anjos/ComfyUI-BFSNodes.git" \
    "https://github.com/Rogala/ComfyUI-rogala.git" \
    "https://github.com/kijai/ComfyUI-MemoryVisualization.git" \
    "https://github.com/kijai/ComfyUI-KJNodes.git" \
    "https://github.com/filliptm/ComfyUI-FL-DiffVSR.git"; do
  name="$(basename "$repo" .git)"
  target="${ROOT_DIR}/custom_nodes/${name}"
  if [ -d "$target/.git" ]; then
    echo "--- ${name} already present, pulling latest ---"
    git -C "$target" pull --ff-only || true
  else
    echo "--- Cloning ${name} ---"
    git clone --depth 1 "$repo" "$target"
  fi
  if [ -f "${target}/requirements.txt" ]; then
    uv pip install -r "${target}/requirements.txt"
  fi
done

for d in ${ROOT_DIR}/custom_nodes/*/; do
  if [ -f "${d}requirements.txt" ]; then
    echo "--- Found requirements in ${d}, installing... ---"
    uv pip install -r "${d}requirements.txt"
  fi
done
echo "--- All done. ---"

# pip uninstall -y onnxruntime onnxruntime-gpu
# pip install -U onnxruntime-gpu

# pip install opencv-python-headless insightface "segment-anything" numexpr lark ftfy omegaconf numba piexif matplotlib librosa pydub open-clip-torch deepdiff
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
# pip install standard-imghdr pymunk openapi librosa pygame mido clip-interrogator simpleeval
# pip install flet peft librosa protobuf openai

# flash-attn is installed in Dockerfile with proper CUDA toolkit