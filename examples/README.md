# Example ComfyUI Workflows

This directory contains sample ComfyUI workflow JSON files for testing the RunPod serverless handler.

## Available Workflows

### text_to_image_simple.json

A basic text-to-image workflow using Stable Diffusion XL.

**Features:**
- Simple KSampler workflow
- 512x512 output resolution
- 20 steps with euler sampler
- Positive and negative prompts

**Usage:**
```python
import json

with open('examples/text_to_image_simple.json') as f:
    workflow = json.load(f)

job_input = {
    'workflow': workflow
}
```

### image_to_image.json

An image-to-image transformation workflow.

**Features:**
- Loads an input image
- Applies style transfer with 75% denoise
- Uses VAE encoding/decoding
- Requires input image upload

**Usage:**
```python
import json
import base64

with open('examples/image_to_image.json') as f:
    workflow = json.load(f)

# Load and encode input image
with open('input.png', 'rb') as img:
    image_data = base64.b64encode(img.read()).decode('utf-8')

job_input = {
    'workflow': workflow,
    'input_images': {
        'input_image.png': image_data
    }
}
```

## Customizing Workflows

You can modify these workflows to:
- Change model checkpoints (`ckpt_name`)
- Adjust generation parameters (steps, cfg, seed)
- Modify prompts (positive/negative text)
- Change output resolution (width/height)
- Adjust denoise strength for img2img

## Testing Locally

Use these workflows with the test scripts:

```bash
# Test with local container
./test_local.sh examples/text_to_image_simple.json

# Test with RunPod endpoint
python test_runpod.py --workflow examples/text_to_image_simple.json
```

### ltx23_v2v_music_visuals_patch.json / ltx23_v2v_music_visuals_patch_ui.json

An LTX-2.3 video-to-video workflow for fixing bad AnimateDiff renders and
adding style to music video footage. Designed for abstract/music visual
content (no lip-sync or characters).

**Features:**
- Two-pass V2V pipeline: 640×352 → 1280×720 (8-step + 3-step)
- IC-LoRA stack: `distilled_lora` + `iclora_decompression` + `omninft_rl_lora`
- `euler` sampler with `linear_quadratic` scheduler (fast tier)
- Tiled VAE decode to prevent edge artifacts
- API format for RunPod serverless, UI format for ComfyUI web interface

**Usage:**
```bash
# Download required models
python scripts/download_ltx23_models.py --ids \
  checkpoint_fp8 distilled_lora \
  iclora_decompression omninft_rl_lora \
  spatial_upscaler

# Test locally
IMAGE_NAME=comfyui-serverless:local ./scripts/test_local.sh \
  examples/ltx23_v2v_music_visuals_patch.json
```

See [`ltx23_v2v_music_visuals_patch_README.md`](ltx23_v2v_music_visuals_patch_README.md)
for full parameter guide, LoRA swap table, and troubleshooting.

## Creating Custom Workflows

1. Design your workflow in ComfyUI WebUI
2. Export the workflow as JSON (Save API Format)
3. Place the JSON file in this directory
4. Test with the provided scripts

**Note:** Make sure any referenced models or custom nodes are available in your deployment.
