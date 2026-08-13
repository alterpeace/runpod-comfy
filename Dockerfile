# =============================================================================
# Stage 1: Base with PyTorch (CACHED - rarely changes)
# =============================================================================
FROM nvidia/cuda:12.9.0-devel-ubuntu24.04 AS base

# =============================================================================
# BUILD CONFIGURATION - Version args
# =============================================================================
ARG TORCH_VERSION=2.10.0
ARG TORCH_FLAVOR=cu129
ARG XFORMERS_VERSION=0.0.34
# LTX-2.3 native support landed in ComfyUI ~v0.16.1 (Mar 2026). Pin to a
# recent tagged release rather than v0.10.0 so LTX-2.3 nodes (LTXAVTextEncoderLoader,
# LTXVConcatAVLatent, CreateVideo, etc.) are available out of the box.
ARG COMFYUI_VERSION=v0.27.0

# =============================================================================
# BUILD CONFIGURATION - Optional attention mechanisms (set to "true" to enable)
# These can significantly increase build time due to CUDA compilation
# =============================================================================
ARG ENABLE_XFORMERS=true
ARG ENABLE_SAGEATTENTION=true
ARG ENABLE_FLASHATTENTION=true
ARG ENABLE_TENSORRT=false

# CUDA compilation settings (reduce MAX_JOBS if build crashes)
ARG TORCH_CUDA_ARCH_LIST="8.9"
ARG MAX_JOBS=2

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.12 python3.12-dev python3.12-venv git build-essential curl \
    libgl1 libglib2.0-0 libgthread-2.0-0 libgtk-3-0 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

ADD https://github.com/astral-sh/uv/releases/download/0.8.6/uv-x86_64-unknown-linux-gnu.tar.gz /tmp/uv.tar.gz
RUN tar -xzf /tmp/uv.tar.gz --strip-components=1 && mv uv /usr/local/bin/uv && rm /tmp/uv.tar.gz

ENV UV_CACHE_DIR=/cache/uv \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=5

WORKDIR /comfyui
RUN uv venv venv

# Install PyTorch + core ML deps
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    . venv/bin/activate && \
    uv pip install \
    torch==${TORCH_VERSION}+${TORCH_FLAVOR} \
    torchvision==0.25.0+${TORCH_FLAVOR} \
    torchaudio==2.10.0+${TORCH_FLAVOR} \
    --extra-index-url https://download.pytorch.org/whl/${TORCH_FLAVOR} && \
    uv pip install \
    ninja wheel packaging setuptools \
    'diffusers>=0.32.0' 'transformers>=4.47.0' 'peft>=0.14.0' \
    accelerate sentencepiece protobuf torchsde einops tokenizers \
    pyyaml pillow scipy tqdm psutil spandrel soundfile \
    huggingface_hub[cli,hf_transfer] 'kornia==0.7.2'

# Set CUDA compilation environment
ENV TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST} MAX_JOBS=${MAX_JOBS}

# =============================================================================
# OPTIONAL: SageAttention (compiles from source - adds ~5-15 min to build)
# =============================================================================
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    if [ "${ENABLE_SAGEATTENTION}" = "true" ]; then \
        echo ">>> Installing SageAttention (ENABLE_SAGEATTENTION=true)..." && \
        . venv/bin/activate && \
        uv pip install sageattention --no-build-isolation; \
    else \
        echo ">>> Skipping SageAttention (ENABLE_SAGEATTENTION=${ENABLE_SAGEATTENTION})"; \
    fi

# =============================================================================
# Stage 2: ComfyUI + All Python Dependencies
# =============================================================================
FROM base AS deps

# Re-declare ARGs for this stage
ARG TORCH_VERSION=2.10.0
ARG TORCH_FLAVOR=cu129
ARG XFORMERS_VERSION=0.0.34
ARG COMFYUI_VERSION=v0.10.0
ARG ENABLE_XFORMERS=true
ARG ENABLE_SAGEATTENTION=true
ARG ENABLE_FLASHATTENTION=true
ARG ENABLE_TENSORRT=false
ARG TORCH_CUDA_ARCH_LIST="8.9"
ARG MAX_JOBS=2

# Set CUDA compilation environment for this stage
ENV TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST} MAX_JOBS=${MAX_JOBS}

RUN curl -L "https://github.com/Comfy-Org/ComfyUI/archive/refs/tags/${COMFYUI_VERSION}.tar.gz" -o /tmp/comfyui.tar.gz && \
    tar -xzf /tmp/comfyui.tar.gz -C /comfyui --strip-components=1 && \
    rm /tmp/comfyui.tar.gz

COPY extra-requirements.txt /tmp/extra-requirements.txt

# Install base dependencies (without optional attention libs)
# NOTE: We install ON TOP of the existing venv from the base stage (which
# already has torch + core ML deps). The alternative approach of `rm -rf
# site-packages/*` before reinstalling causes uv's "File exists (os error 17)"
# bug: the rm removes files from the overlay upper layer but the base stage's
# read-only lower layer still contains them, so uv sees stale files and fails
# to overwrite. Installing on top lets uv handle conflicts properly.
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    . venv/bin/activate && \
    uv pip install \
    "torch==${TORCH_VERSION}+${TORCH_FLAVOR}" \
    "torchvision==0.25.0+${TORCH_FLAVOR}" \
    "torchaudio==2.10.0+${TORCH_FLAVOR}" \
    -r requirements.txt -r /tmp/extra-requirements.txt \
    rotary-embedding-torch evalidate fal-client google-genai gguf \
    cmake fairscale gitpython imageio joblib matplotlib numba \
    pilgram rembg scikit-image scikit-learn timm PyWavelets \
    opencv-contrib-python pymunk deepdiff \
    'kornia==0.7.2' \
    --index-strategy unsafe-best-match \
    --extra-index-url https://download.pytorch.org/whl/cu129 && \
    if [ "${ENABLE_TENSORRT}" = "true" ]; then \
        echo ">>> Installing TensorRT (ENABLE_TENSORRT=true)..." && \
        uv pip install tensorrt tensorrt-cu12 --extra-index-url https://pypi.nvidia.com; \
    else \
        echo ">>> Skipping TensorRT (ENABLE_TENSORRT=false, saves ~6.2GB)"; \
    fi

# =============================================================================
# OPTIONAL: xformers (prebuilt wheel - fast install)
# =============================================================================
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    if [ "${ENABLE_XFORMERS}" = "true" ]; then \
        echo ">>> Installing xformers ${XFORMERS_VERSION} (ENABLE_XFORMERS=true)..." && \
        . venv/bin/activate && \
        uv pip install xformers==${XFORMERS_VERSION} --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/${TORCH_FLAVOR}; \
    else \
        echo ">>> Skipping xformers (ENABLE_XFORMERS=${ENABLE_XFORMERS})"; \
    fi

# =============================================================================
# OPTIONAL: Flash Attention (compiles from source - adds ~30-60 min to build)
# =============================================================================
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    if [ "${ENABLE_FLASHATTENTION}" = "true" ]; then \
        echo ">>> Installing Flash Attention (ENABLE_FLASHATTENTION=true)..." && \
        . venv/bin/activate && \
        uv pip install packaging && \
        uv pip install flash_attn --no-build-isolation; \
    else \
        echo ">>> Skipping Flash Attention (ENABLE_FLASHATTENTION=${ENABLE_FLASHATTENTION})"; \
    fi

# Install git dependencies
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    . venv/bin/activate && \
    uv pip install \
    "git+https://github.com/WASasquatch/img2texture.git" \
    "git+https://github.com/WASasquatch/cstr" \
    "git+https://github.com/WASasquatch/ffmpy.git" \
    "git+https://github.com/facebookresearch/sam2.git" \
    "git+https://github.com/facebookresearch/sam3.git"

# Skip flash-attn and xformers - they cause ABI issues and aren't required
# ComfyUI will use PyTorch's native SDPA attention instead


# =============================================================================
# Stage 2: ComfyUI Download (SEPARATE - only rebuilds on version change)
# =============================================================================
FROM base AS comfyui

# ARG declared here so changing it only invalidates THIS stage, not base
ARG COMFYUI_VERSION=v0.3.66
ADD https://github.com/comfyanonymous/ComfyUI/archive/refs/tags/${COMFYUI_VERSION}.tar.gz /tmp/comfyui.tar.gz
RUN tar -xzf /tmp/comfyui.tar.gz -C /comfyui --strip-components=1 && \
    rm -rf /tmp/comfyui.tar.gz

# Install ComfyUI requirements
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    . venv/bin/activate && \
    uv pip install "numpy<2.4" && \
    uv pip install dill librosa PyPDF2 pynvml google-cloud-storage pymupdf numexpr addict yapf glitch-this && \
    uv pip install --reinstall opencv-contrib-python

# CRITICAL: Force PyTorch version consistency at the very end
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    . venv/bin/activate && \
    uv pip uninstall torch torchvision torchaudio 2>/dev/null || true && \
    uv pip install \
    "torch==${TORCH_VERSION}+${TORCH_FLAVOR}" \
    "torchvision==0.25.0+${TORCH_FLAVOR}" \
    "torchaudio==2.10.0+${TORCH_FLAVOR}" \
    --extra-index-url https://download.pytorch.org/whl/${TORCH_FLAVOR} && \
    if [ "${ENABLE_XFORMERS}" = "true" ]; then \
        uv pip install "xformers==${XFORMERS_VERSION}" --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/${TORCH_FLAVOR}; \
    fi

# =============================================================================
# Stage 3: Runtime base
# =============================================================================
FROM nvidia/cuda:12.9.0-runtime-ubuntu24.04 AS runtime-base

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev \
    build-essential g++ gosu \
    libgl1 libglib2.0-0 libgthread-2.0-0 libgtk-3-0 libopengl0 \
    openssh-server curl wget fuse unzip git ffmpeg \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 LTS — required by comfyui-mcp (MCP server for agent-driven control)
# Installed via NodeSource to get v22 (Ubuntu 24.04 ships Node 18 in apt, too old)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    node --version && npm --version

# Install rclone for B2/S3-compatible model storage mounting.
RUN curl https://rclone.org/install.sh | bash

RUN mkdir -p /var/run/sshd /root/.ssh /runpod-volume && chmod 700 /root/.ssh

RUN useradd -m -s /bin/bash -u 1024 comfy && \
    echo "comfy ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# =============================================================================
# Stage 4: Final image
# =============================================================================
FROM runtime-base AS runtime

# Re-declare ARGs for final stage
ARG TORCH_VERSION=2.10.0
ARG TORCH_FLAVOR=cu129
ARG XFORMERS_VERSION=0.0.34
ARG ENABLE_XFORMERS=true
ARG ENABLE_SAGEATTENTION=true
ARG ENABLE_FLASHATTENTION=true
ARG ENABLE_TENSORRT=false

COPY --from=base /usr/local/bin/uv /usr/local/bin/uv
COPY --from=deps /comfyui /comfyui

WORKDIR /workspace

# =============================================================================
# TORCH_LOCK: Prevent runtime package upgrades from changing PyTorch versions
# =============================================================================
RUN mkdir -p /comfyui/venv/constraints /comfyui/models /comfyui/output /comfyui/input /comfyui/custom_nodes && \
    printf "# TORCH_LOCK - Prevents ComfyUI-Manager from upgrading PyTorch\n\
numpy<2.4\n\
torch==${TORCH_VERSION}+${TORCH_FLAVOR}\n\
torchvision==0.25.0+${TORCH_FLAVOR}\n\
torchaudio==2.10.0+${TORCH_FLAVOR}\n" > /comfyui/venv/constraints/torch_lock.txt && \
    if [ "${ENABLE_XFORMERS}" = "true" ]; then \
        echo "xformers==${XFORMERS_VERSION}" >> /comfyui/venv/constraints/torch_lock.txt; \
    fi

# Create userscripts directory
RUN mkdir -p /userscripts_dir && chmod 755 /userscripts_dir

# Ensure /comfyui/user is writable by the comfy user (UID 1024).
# ComfyUI creates comfyui.db here; without write permission it fails with
# [Errno 13] Permission denied: '/comfyui/user/comfyui.db.bkp'
RUN mkdir -p /comfyui/user && chown -R 1024:1024 /comfyui/user

# Store build config for runtime inspection
RUN printf "TORCH_VERSION=${TORCH_VERSION}\n\
TORCH_FLAVOR=${TORCH_FLAVOR}\n\
XFORMERS_VERSION=${XFORMERS_VERSION}\n\
ENABLE_XFORMERS=${ENABLE_XFORMERS}\n\
ENABLE_SAGEATTENTION=${ENABLE_SAGEATTENTION}\n\
ENABLE_FLASHATTENTION=${ENABLE_FLASHATTENTION}\n" > /comfyui/build_config.txt

ENV UV_CACHE_DIR=/cache/uv \
    UV_LINK_MODE=copy \
    PIP_CONSTRAINT=/comfyui/venv/constraints/torch_lock.txt \
    UV_CONSTRAINT=/comfyui/venv/constraints/torch_lock.txt \
    TORCH_VERSION=${TORCH_VERSION} \
    TORCH_FLAVOR=${TORCH_FLAVOR} \
    COMFYUI_PORT=8188 \
    COMFYUI_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    WANTED_UID=1024 \
    WANTED_GID=1024

COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/cache/uv,sharing=locked \
    if [ -f pyproject.toml ]; then \
        uv pip compile pyproject.toml -o /tmp/proj-req.txt --no-header 2>/dev/null && \
        . /comfyui/venv/bin/activate && uv pip install -r /tmp/proj-req.txt || true; \
    fi

# Install extra requirements
COPY extra-requirements.txt* ./
RUN if [ -f extra-requirements.txt ]; then \
        echo "Installing extra requirements..." && \
        . /comfyui/venv/bin/activate && uv pip install -r extra-requirements.txt; \
    fi

# Remove problematic packages that may have been installed by extra-requirements
# and re-pin kornia to avoid flash_attn issues
# Use --no-deps since torch is already installed with CUDA local version (e.g. 2.10.0+cu129)
# which pip's constraint resolver doesn't understand
RUN . /comfyui/venv/bin/activate && \
    uv pip uninstall flash-attn xformers 2>/dev/null || true && \
    rm -rf /comfyui/venv/lib/python*/site-packages/flash_attn* && \
    rm -rf /comfyui/venv/lib/python*/site-packages/xformers* && \
    uv pip install 'kornia==0.7.2' --no-deps --force-reinstall

# Execute additional dependency script if present
COPY scripts/add-dependancies.sh* ./
RUN if [ -f add-dependancies.sh ]; then \
        chmod +x add-dependancies.sh && ./add-dependancies.sh; \
    fi

# Install compatible xformers for PyTorch 2.10.0 + CUDA 12.9
# Unset UV_CONSTRAINT/PIP_CONSTRAINT to avoid conflict with xformers version pin
RUN . /comfyui/venv/bin/activate && \
    echo "Installing compatible xformers..." && \
    uv pip uninstall flash-attn xformers 2>/dev/null || true && \
    rm -rf /comfyui/venv/lib/python*/site-packages/flash_attn* && \
    rm -rf /comfyui/venv/lib/python*/site-packages/xformers* && \
    UV_CONSTRAINT= PIP_CONSTRAINT= uv pip install xformers --index-url https://download.pytorch.org/whl/cu129 && \
    UV_CONSTRAINT= PIP_CONSTRAINT= uv pip install 'kornia==0.7.2' --no-deps --force-reinstall && \
    echo "xformers installation complete"

# Install TensorRT for depth-anything-tensorrt and other TRT nodes (optional, ~6.2GB)
RUN . /comfyui/venv/bin/activate && \
    if [ "${ENABLE_TENSORRT}" = "true" ]; then \
        echo ">>> Installing TensorRT (ENABLE_TENSORRT=true)..." && \
        uv pip install tensorrt tensorrt-cu12 --extra-index-url https://pypi.nvidia.com; \
    else \
        echo ">>> Skipping TensorRT (ENABLE_TENSORRT=false, saves ~6.2GB)"; \
    fi

# Install additional dependencies for custom nodes
# NOTE: taehv (git+https://github.com/deinferno/taehv.git) was removed —
# the repo has been deleted (404) and no custom node requires it.
RUN . /comfyui/venv/bin/activate && \
    uv pip install rotary-embedding-torch evalidate fal-client google-genai

# Install WAS Node Suite dependencies
# numba>=0.63.1 required for NumPy 2.4 compatibility
RUN . /comfyui/venv/bin/activate && \
    uv pip install cmake fairscale gitpython imageio joblib matplotlib 'numba>=0.63.1' \
    pilgram rembg scikit-image scikit-learn timm \
    git+https://github.com/WASasquatch/img2texture.git \
    git+https://github.com/WASasquatch/cstr \
    git+https://github.com/WASasquatch/ffmpy.git

# Install libopengl0 for OpenGL support (fixes "libOpenGL.so.0" error)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libopengl0 && \
    rm -rf /var/lib/apt/lists/*

# Install SAM2 (required by Impact Pack)
RUN . /comfyui/venv/bin/activate && \
    uv pip install git+https://github.com/facebookresearch/sam2.git

# Install SAM3 (newest version with text prompts - experimental)
RUN . /comfyui/venv/bin/activate && \
    uv pip install git+https://github.com/facebookresearch/sam3.git

# FINAL: Force opencv-contrib-python and prevent other opencv variants
# This MUST be at the end to override any opencv installed by other packages
# Create a persistent constraint file to prevent pip from installing conflicting opencv packages
RUN mkdir -p /comfyui/venv/constraints && \
    echo "# Prevent conflicting opencv packages" > /comfyui/venv/constraints/opencv.txt && \
    echo "opencv-python < 0" >> /comfyui/venv/constraints/opencv.txt && \
    echo "opencv-python-headless < 0" >> /comfyui/venv/constraints/opencv.txt && \
    . /comfyui/venv/bin/activate && \
    uv pip uninstall opencv-python opencv-contrib-python opencv-python-headless 2>/dev/null || true && \
    uv pip install opencv-contrib-python

# Set PIP_CONSTRAINT to always use the opencv constraint file
ENV PIP_CONSTRAINT=/comfyui/venv/constraints/opencv.txt

# Copy application files
COPY src/handler.py src/comfyui_client.py src/storage_s3.py ./
COPY config/runpod-config-serverless.json config/runpod-config-pods.json .env.example ./

COPY ssh/ ./ssh/
COPY storage/ ./storage/
RUN chmod +x ./ssh/*.sh ./storage/*.sh 2>/dev/null || true

COPY src/handler.py src/comfyui_client.py src/storage_s3.py ./
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# =============================================================================
# FINAL CLEANUP: Remove system CUDA deb packages (~3.1GB) and build toolchain
# torch uses pip-bundled nvidia/* libs, so system CUDA debs are redundant.
# This runs last so it doesn't interfere with any install steps above.
# =============================================================================
RUN dpkg-query -W --showformat='${Package}\n' 2>/dev/null | \
      grep -iE "cuda|nccl|npp|cublas|cusparse|cusolver|cufft|curand|nvjitlink|cupti|nvrtc" | \
      xargs -r apt-get purge -y --allow-change-held-packages 2>/dev/null || true && \
    apt-get autoremove -y 2>/dev/null || true && \
    rm -rf /usr/local/cuda-12.9 /usr/local/cuda /usr/local/cuda-12 /var/lib/apt/lists/* && \
    find /comfyui -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

EXPOSE 8188 22 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8188/ || exit 1

ENTRYPOINT ["/workspace/entrypoint.sh"]
