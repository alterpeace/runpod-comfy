# LTX-2.5 Workflow Catalog

All available workflows, their features, and what they do beyond a basic LTX-2.5 pass.

---

## Workflow Comparison

### V2V Redetail Workflows

| Workflow | Tier | Model | Resolution | Passes | IC-LoRA | Upscale | LoRA | Steps | Unique Features |
|---|---|---|---|---|---|---|---|---|---|
| `ltx25_v2v_redetail_entry_runpod.json` | Entry (24GB) | GGUF Q4 | 640×352 | Single | No | No | Distilled | 8 | Basic redetail — re-renders video with AI detail enhancement |
| `ltx25_v2v_redetail_entry.json` | Entry (24GB) | GGUF Q4 | 640×352 | Single | No | No | Distilled | 8 | Same as above, different filename |
| `ltx25_v2v_redetail_entry_fp8.json` | Entry (24GB) | FP8 | 640×352 | Single | No | No | Distilled | 8 | Better quality than Q4 (FP8 > INT4) |
| `ltx25_v2v_redetail_comfortable.json` | Comfortable (48GB) | int8 | 768×448 | Two | Yes | 2× latent | Distilled + IC-LoRA | 8+3 | Two-pass with IC-LoRA spatial upscaler |
| `ltx25_v2v_redetail_comfortable_runpod.json` | Comfortable (48GB) | int8 | 768×448 → 1536×896 | Two | Yes | 2× latent | Distilled + IC-LoRA | 8+3 | Full two-pass pipeline for RunPod |
| `ltx25_v2v_redetail_recommended_runpod.json` | Recommended (80GB+) | BF16 | 1024×576 → 2048×1152 | Two | Yes | 2× latent | Distilled + IC-LoRA | 8+3 | Highest quality, ProRes output |

### Other Workflows

| Workflow | Type | Tier | Model | Unique Features |
|---|---|---|---|---|
| `ltx25_t2v_entry.json` | T2V | Entry (24GB) | GGUF Q4 | Text-to-video generation (no input video) |
| `ltx25_animatediff_restyle_comfortable.json` | V2V Restyle | Comfortable (48GB) | int8 | AnimateDiff-style restyling with upscale |
| `ltx25_v2v_redetail_entry_ui.json` | V2V (UI format) | Entry (8GB) | GGUF Q4 | UI format for local ComfyUI WebUI |

### Official LTXVideo Workflows (in `examples/test/`)

| Workflow | Type | Features |
|---|---|---|
| `LTX-2.5_T2V_I2V_Single_Stage_Distilled-api.json` | T2V/I2V | Single-pass, prompt enhancement, CLIPLoader |
| `LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled-api.json` | V2V | IC-LoRA, single-pass, LoadVideo |
| `LTX-2.5_ICLoRA_Outpaint_Two_Stage_Distilled-api.jsom.json` | Outpaint | Two-stage, IC-LoRA outpainting |

---

## What Each Workflow Does Beyond Basic LTX-2.5

### Basic LTX-2.5 Pass (what all workflows share)
- Loads LTX-2.5 model + Gemma 4 text encoder
- Encodes input video to latents
- Runs KSampler (8 steps, euler, linear_quadratic)
- Decodes latents to video
- Saves as h264-mp4

### Redetail (all V2V workflows)
- **What it adds:** Re-renders the input video with AI-enhanced detail
- **How:** Uses the input video as a conditioning guide (VAEEncode → KSampler with denoise 0.3)
- **Effect:** Fixes blur, adds detail, smooths motion, applies cinematic style
- **Strength:** Controlled by `denoise` parameter (0.3 = 70% original, 30% new)

### IC-LoRA (comfortable + recommended tiers)
- **What it adds:** Spatial upscaling via learned IC-LoRA
- **How:** Loads `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors`
- **Effect:** 2× resolution enhancement in pixel space
- **Node:** `LTXICLoRALoaderModelOnly` + `LTXAddVideoICLoRAGuide`

### Two-Pass Upscale (comfortable + recommended tiers)
- **What it adds:** Latent-space 2× upscaling + second sampling pass
- **How:** `LTXVLatentUpsampler` (2× in latent space) → second `SamplerCustomAdvanced` (3 steps)
- **Effect:** Higher resolution output (768×448 → 1536×896 or 1024×576 → 2048×1152)
- **Quality:** Better than simple resize — generates new detail at higher resolution

### Prompt Enhancement (official workflows)
- **What it adds:** AI-powered prompt expansion using Gemma text generation
- **How:** `TextGenerateLTX2Prompt` node uses the text encoder to expand the prompt
- **Effect:** Richer, more detailed prompts → better video quality

### Turbo LoRA (planned for FP8 workflow)
- **What it adds:** Faster generation (4 steps instead of 8)
- **How:** `ltx25-turbo-distill-lora` LoRA
- **Effect:** 2× faster generation with minimal quality loss

---

## Maintaining Consistent Visual Signature

### Color Grading Consistency

1. **Fixed positive prompt** — Use the same prompt across all clips:
   ```
   cinematic, film grain, shallow depth of field, golden hour lighting,
   professional color grading, enhanced detail, smooth motion, high contrast,
   neon accents, dramatic shadows, lens flares, 4k detail
   ```

2. **Fixed negative prompt** — Block unwanted styles:
   ```
   blurry, low quality, distorted, amateur, shaky, wobbly, cartoon, anime
   ```

3. **Fixed seed** — Use `noise_seed: 42` (or any fixed value) for reproducible noise patterns

4. **Fixed denoise** — `denoise: 0.3` ensures consistent blend of original + AI

### Resolution and Output Size

| Tier | Input Resolution | Output Resolution | File Size (15s, h264) |
|---|---|---|---|
| Entry | 640×352 | 640×352 | ~6 MB |
| Comfortable | 768×448 | 1536×896 | ~80 MB |
| Recommended | 1024×576 | 2048×1152 | ~150 MB |

### Upscaling Techniques

| Technique | When | Quality | VRAM Impact |
|---|---|---|---|
| **Latent upscale** (LTXVLatentUpsampler) | Two-pass workflows | Best — generates new detail | +2GB for upscaled latents |
| **IC-LoRA pixel upscale** | Comfortable+ tiers | Good — learned upscaling | +0.3GB for IC-LoRA |
| **Image resize** (ImageScale) | All workflows | Basic — no new detail | Minimal |
| **Post-process upscale** (external) | After generation | Varies — Topaz, etc. | None (CPU) |

### Best Practices for Consistent Output

1. **Use the same workflow file** for all clips in a project
2. **Fix the seed** (`noise_seed: 42`) for reproducible results
3. **Use the same prompts** — only change the input video
4. **Match frame rates** — `force_rate: 24` and `frame_rate: 24` for all clips
5. **Match frame counts** — use the same `frame_load_cap` for all clips
6. **Post-process consistently** — apply the same LUT/color grade in editing
7. **Output format** — use the same `format` (h264-mp4 or ProRes) for all clips
