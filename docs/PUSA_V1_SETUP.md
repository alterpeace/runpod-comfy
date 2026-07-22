# PUSA v1 Setup Guide

## Overview

PUSA v1 is a fine-tuned version of Wan 2.1 optimized for animation generation. This guide covers setup for 8GB VRAM systems.

## Available Workflows

| Workflow | Description |
|----------|-------------|
| `pusa_v1_perfect_loops.json` | Single image to looping animation |
| `pusa_v1_transitions.json` | Batch images from folder with ControlNet/inpainting |

## Required Custom Nodes

Install these via ComfyUI Manager or git clone into `custom_nodes/`:

```bash
# ComfyUI-WanVideoWrapper (required for Wan 2.1 models)
git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git

# VideoHelperSuite (for video output)
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git

# Optional: Frame interpolation for smoother loops
git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git
```

## Required Models

### Option 1: Base Wan 2.1 + PUSA LoRA
Download to `models/` directory:

1. **Wan 2.1 1.3B** (smaller, fits 8GB):
   - Auto-downloads via node, or manually from HuggingFace
   - Path: `models/wan/Wan2.1-T2V-1.3B/`

2. **PUSA v1 LoRA** (if using LoRA version):
   - Download from CivitAI
   - Path: `models/loras/pusa_v1.safetensors`

### Option 2: PUSA v1 Full Checkpoint
If PUSA v1 is released as a full checkpoint:
- Path: `models/wan/pusa_v1/`

## VRAM Optimization Settings

### docker-compose.yml
```yaml
environment:
  - COMFYUI_ARGS=--use-sage-attention --lowvram --fp8_e4m3fn-unet
```

### Recommended Settings for 8GB VRAM

| Setting | Value | Notes |
|---------|-------|-------|
| Resolution | 480x832 or 832x480 | Portrait/Landscape |
| Frames | 33 max | ~1.4 seconds at 24fps |
| CFG | 3.0-5.0 | Lower = faster |
| Steps | 15-20 | More steps = better quality but slower |

### If you run out of VRAM:
1. Reduce resolution to 384x672
2. Reduce frames to 25
3. Add `--cpu-vae` flag (slower but saves VRAM)
4. Close other GPU applications

## Perfect Loop Techniques

### Method 1: Ping-Pong
- Generate forward animation
- Reverse and append
- Creates seamless back-and-forth loop

### Method 2: Circular Motion Prompts
Use prompts that describe cyclical motion:
- "rotating", "spinning", "orbiting"
- "breathing", "pulsing", "oscillating"
- "waving", "swaying", "rocking"

### Method 3: Frame Blending
- Generate slightly longer sequence
- Blend first and last frames
- Trim to desired length

## Workflow Usage

1. Load `examples/pusa_v1_perfect_loops.json` in ComfyUI
2. Upload a starting image (or use text-to-video)
3. Adjust prompt for your desired animation
4. Set seed for reproducibility
5. Queue prompt and wait for generation

## Troubleshooting

### "CUDA out of memory"
- Reduce resolution or frame count
- Ensure `--lowvram` flag is set
- Try `--fp8_e4m3fn-unet` for additional savings

### Jerky/stuttering animation
- Increase frame count
- Use frame interpolation node
- Lower CFG scale

### Loop doesn't connect smoothly
- Use ping-pong method
- Try circular motion prompts
- Apply frame blending at loop point


## Transitions Workflow

The `pusa_v1_transitions.json` workflow supports loading images from a folder and animating between them.

### Folder Structure

```
input/
├── transitions/     # Your keyframe images (001.png, 002.png, ...)
└── masks/           # Optional inpainting masks
```

### How It Works

1. **Load images from folder** — `VHS_LoadImagesPath` reads all images from `input/transitions/`
2. **Extract first/last frames** — Uses these as start/end keyframes
3. **Generate animation** — Wan 2.1 interpolates motion between frames
4. **Optional ControlNet** — Add depth/pose guidance for consistent motion
5. **Optional Inpainting** — Animate only masked regions

### ControlNet Options

| Type | Use Case |
|------|----------|
| Depth | Maintain spatial consistency, camera movement |
| Pose | Character animation, consistent body position |
| Canny | Edge-guided animation, preserve structure |

### Inpainting Mode

Use masks to animate specific regions while keeping others static:
- **White areas** = animate
- **Black areas** = keep original

Great for:
- Animating a character while background stays still
- Adding motion to specific elements (fire, water, hair)
- Seamless object transitions

### Batch Processing Tips

Name your transition images sequentially:
```
001_scene_start.png
002_scene_middle.png  
003_scene_end.png
```

The workflow will animate between consecutive pairs.
