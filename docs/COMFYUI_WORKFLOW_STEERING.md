# ComfyUI Workflow Steering for AI Agents

Guidance for AI coding agents building, testing, and deploying ComfyUI
workflows on this project's RunPod serverless infrastructure.

**Philosophy (from [ComfyUI Skills](https://github.com/Comfy-Org/comfy-skills)):**
*Steer the approach, defer the specifics.* Don't hardcode model names, node IDs,
or template names — they change. Instead, point the agent at discovery tools
that return the current set.

---

## 1. Connecting AI Agents to ComfyUI

### Option A: Comfy MCP (local connection)

The [Comfy MCP server](https://docs.comfy.org/agent-tools/mcp) connects AI
agents to any running ComfyUI instance — including a debug Pod or the
serverless worker's ComfyUI.

```bash
# Install
pip install comfy-mcp comfy-cli

# For Claude Code:
claude mcp add comfy-mcp -- comfy-mcp

# For VS Code / Kilo Code (.mcp.json):
# {
#   "mcpServers": {
#     "comfy-mcp": {
#       "command": "comfy-mcp",
#       "env": { "COMFY_BIN": "/path/to/comfy" }
#     }
#   }
# }
```

The MCP server provides tools for:
- `search_nodes` — find available nodes by type/category
- `search_models` — find available models
- `search_templates` — find workflow templates
- `generate_image` / `generate_video` — run workflows
- `launch_comfyui` — start a local ComfyUI instance

**For this project:** Point the MCP at a debug Pod's ComfyUI (port 8188) or
use the serverless API directly (see Section 3).

### Option B: ComfyUI Skills (Claude Code plugins)

```bash
# Install ComfyUI Cloud skills (for Comfy Cloud workflows)
/plugin marketplace add Comfy-Org/comfy-skills
/plugin install comfy-cloud@comfy-skills
```

Provides slash commands: `/comfy-cloud:generate-image`,
`/comfy-cloud:generate-video`, `/comfy-cloud:search-models`,
`/comfy-cloud:search-nodes`, `/comfy-cloud:search-templates`.

**Note:** These connect to Comfy Cloud, not your self-hosted instance. Use
Option A for this project.

### Option C: RunPod MCP server

```bash
# For Claude Code:
claude mcp add runpod --scope user \
  -e RUNPOD_API_KEY=your_key \
  -- npx -y @runpod/mcp-server@latest
```

Manages RunPod infrastructure (pods, endpoints, volumes) from AI agents.
See [`docs/RUNPOD_STEERING.md`](RUNPOD_STEERING.md) for details.

---

## 2. Workflow-Building Patterns for LTX-2.5

### Discovery: Don't guess, query

Before writing a workflow, discover what's available:

```bash
# Check what models are on the volume
set -a && source .env && set +a
uv run python -c "
import boto3, os
s3 = boto3.client('s3',
    endpoint_url=os.environ['RUNPOD_S3_ENDPOINT'],
    region_name=os.environ['RUNPOD_S3_REGION'],
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])
paginator = s3.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket=os.environ['RUNPOD_S3_BUCKET'], Prefix='models/'):
    for obj in page.get('Contents', []):
        if obj['Size'] > 0:
            print(f'{obj[\"Size\"]:>15,} B  {obj[\"Key\"]}')
"

# Check what nodes are available (via object_info)
# When ComfyUI is running on a pod:
curl http://localhost:8188/object_info | python3 -m json.tool | head -100
```

### LTX-2.5 V2V Redetail Workflow Pattern

The canonical workflow is at
[`examples/ltx25_v2v_redetail_24gb_runpod.json`](../examples/ltx25_v2v_redetail_24gb_runpod.json).
Key nodes:

| Node ID | Type | Purpose |
|---|---|---|
| 1 | `CheckpointLoaderSimple` | Load LTX-2.5 transformer (int8-convrot) |
| 2 | `LTXVGemmaCLIPModelLoader` | Load Gemma 4 text encoder + tokenizer |
| 3 | `LoraLoader` | Load distilled LoRA (speed) |
| 4 | `LTXICLoRALoaderModelOnly` | Load IC-LoRA (spatial upscaler) |
| 5 | `CLIPTextEncode` | Positive prompt |
| 6 | `CLIPTextEncode` | Negative prompt |
| 7 | `VHS_LoadVideo` | Load input video |
| 8 | `ImageScale` | Resize to 768×448 |
| 9 | `LTXVImgToVideo` | Image-to-video conditioning |
| 10 | `LTXAddVideoICLoRAGuide` | Add IC-LoRA guide |
| 12 | `BasicScheduler` | Linear quadratic schedule, 8 steps |
| 14 | `SamplerCustomAdvanced` | First pass (8 steps) |
| 15 | `LTXVLatentUpsampler` | 2× latent upscale |
| 18 | `SamplerCustomAdvanced` | Second pass (3 steps) |
| 19 | `LTXVTiledVAEDecode` | Decode latents to video |
| 20 | `VHS_VideoCombine` | Save output video |

### Workflow-Building Rules

1. **Always use `LTXVGemmaCLIPModelLoader`** (node 2) — not the standard
   `CLIPTextEncode` loader. LTX-2.5 requires Gemma 4 for text encoding.

2. **Model paths are relative to ComfyUI directories:**
   - Checkpoints: `ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors`
   - Text encoders: `gemma4-12b-ltx-2.5/model.safetensors` (symlink to int8)
   - LoRAs: `ltx-2.5-22b-distilled-lora-450-bf16.safetensors`
   - VAE: `ltx-2.5-video-vae-bf16.safetensors`

3. **VHS_LoadVideo video path** is relative to `/comfyui/input/`:
   - `rhizome.mp4` → `/comfyui/input/rhizome.mp4`
   - `sample/clip_001.mp4` → `/comfyui/input/sample/clip_001.mp4`

4. **Two-pass pattern for quality:**
   - Pass 1: 8 steps at 768×448 (base resolution)
   - Pass 2: 3 steps at 1536×896 (2× upscaled, latent domain)

5. **VRAM management:**
   - 24GB (4090): 768×448, 385 frames max, `--lowvram`
   - 48GB (A6000/L40): 768×448 or higher, more LoRAs
   - 80GB (A100): full resolution, BF16, audio

6. **Output format:** `video/h264-mp4` with `frame_rate: 24`

### Common Pitfalls

| Pitfall | Fix |
|---|---|
| `Invalid video file` | File not in `/comfyui/input/` — upload via `input_images` or fix entrypoint linking |
| `NoneType object is not callable` in Gemma | Stale image — rebuild and push, or force worker to pull latest |
| `Value not in list` for model | Model not on volume or not linked — check `download_models` action |
| `StrictDataclassFieldValidationError` | Wrong Gemma tokenizer config — use `config/gemma4-12b-ltx-2.5/` |
| Cold start timeout | Set `TIMEOUT=600+`, first job takes 3-8 min |

---

## 3. Submitting Workflows via Serverless API

### Standard workflow submission

```python
import runpod, os
runpod.api_key = os.environ['RUNPOD_API_KEY']
endpoint = runpod.Endpoint('taea2mhlwbdkuq')

job = endpoint.run({
    "input": {
        "workflow": workflow_dict,
        "timeout": 600,
    }
})
```

### With input video upload (bypasses symlink issues)

```bash
set -a && source .env && set +a
uv run python scripts/invoke/invoke_v2v_with_upload.py --video rhizome.mp4
```

See [`scripts/invoke/invoke_v2v_with_upload.py`](../scripts/invoke/invoke_v2v_with_upload.py).

### Diagnostic commands (when available)

```python
job = endpoint.run({
    "input": {
        "action": "diagnostic",
        "commands": ["ls -la /comfyui/input/", "cat /comfyui/custom_nodes/ComfyUI-LTXVideo/gemma_encoder.py | head -20"],
        "timeout": 15,
    }
})
```

### Model download

```python
job = endpoint.run({
    "input": {
        "action": "download_models",
        "manifest": "ltx-2.5",
        "profile": "mid_vram_24gb",
    }
})
```

---

## 4. Testing Workflows Locally

### Using the mock server

```bash
# Start mock RunPod server
uv run python scripts/build/mock_runpod_server.py

# Test workflow
uv run python scripts/build/test_local.sh
```

### Using the debug workflow script

```bash
# Validate workflow structure without submitting
uv run python scripts/invoke/debug_workflow.py --workflow examples/ltx25_v2v_redetail_24gb_runpod.json --dry-run
```

### Using the preflight check

```bash
# Check models, nodes, and workflow validity
uv run python scripts/diag/preflight_check.py
```

---

## 5. Debugging Decision Tree

```
Workflow fails?
├── "Invalid video file" → File not in /comfyui/input/
│   ├── Check: diagnostic action → ls -la /comfyui/input/
│   ├── Fix: upload via input_images
│   └── Fix: rebuild image with input linking code
├── "NoneType not callable" in Gemma → Stale image
│   ├── Check: diagnostic action → if "Unknown action", image is stale
│   ├── Fix: force endpoint to pull latest image
│   └── Fix: rebuild and push image
├── "Value not in list" → Model not found
│   ├── Check: S3 listing for models/
│   ├── Fix: download_models action with correct profile
│   └── Fix: check entrypoint model linking
├── Cold start timeout → ComfyUI boot slow
│   ├── Fix: increase TIMEOUT to 600+
│   └── Fix: use warm workers (min_workers=1)
└── Other errors → SSH into worker or use diagnostic action
    ├── Check: ComfyUI logs
    ├── Check: custom node versions
    └── Check: model file integrity
```

---

## 6. Reference: Project Resources

| Resource | Path | Purpose |
|---|---|---|
| Handler | [`src/handler.py`](../src/handler.py) | Serverless entry point |
| Entrypoint | [`entrypoint.sh`](../entrypoint.sh) | Container boot script |
| ComfyUI client | [`src/comfyui_client.py`](../src/comfyui_client.py) | ComfyUI API client |
| Model manifest | [`config/ltx-2.5-models.json`](../config/ltx-2.5-models.json) | Model download config |
| Gemma config | [`config/gemma4-12b-ltx-2.5/`](../config/gemma4-12b-ltx-2.5/) | Tokenizer files |
| Example workflows | [`examples/`](../examples/) | LTX-2.3/2.5 workflow JSONs |
| V2V invocation | [`scripts/invoke/invoke_v2v.py`](../scripts/invoke/invoke_v2v.py) | Submit V2V workflow |
| V2V with upload | [`scripts/invoke/invoke_v2v_with_upload.py`](../scripts/invoke/invoke_v2v_with_upload.py) | Submit with video upload |
| Debug workflow | [`scripts/invoke/debug_workflow.py`](../scripts/invoke/debug_workflow.py) | Validate workflow |
| Preflight check | [`scripts/diag/preflight_check.py`](../scripts/diag/preflight_check.py) | Pre-deployment checks |
| RunPod steering | [`docs/RUNPOD_STEERING.md`](RUNPOD_STEERING.md) | RunPod CLI/MCP/handler guide |
| Serverless deploy | [`docs/SERVERLESS_DEPLOY.md`](SERVERLESS_DEPLOY.md) | Deployment guide |
| LTX-2.5 setup | [`docs/LTX_2.5_SETUP.md`](LTX_2.5_SETUP.md) | Model setup guide |
