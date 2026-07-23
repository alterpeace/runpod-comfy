# LTX-2.3 V2V — VRAM-Tiered Workflows

Two variants of the V2V music-visuals pipeline (`ltx23_v2v_music_visuals_patch.json`),
split by available VRAM. Both keep the same two-pass design: pass 1 generates at the
input resolution, `LTXVLatentUpsampler` doubles the latent, pass 2 refines it —
so the final output is ~2x the working resolution in each dimension.

## Tier comparison

| | `ltx23_v2v_8gb_gguf.json` (local) | `ltx23_v2v_runpod_fp8.json` (RunPod) |
|---|---|---|
| Target GPU | RTX 2070/3060/4060 class, **8 GB** | RTX 4090/5090/A100, **24 GB+** |
| Model | `ltx-2.3-22b-distilled-1.1-Q4_K_M.gguf` (GGUF Q4) | `ltx-2.3-22b-dev-fp8.safetensors` (fp8) |
| Distilled LoRA | not needed (baked into distilled GGUF) | `ltx-2.3-22b-distilled-lora-384-1.1` |
| IC-LoRAs | decompression only (0.7) | decompression (0.7) + OmniNFT RL (2.0) |
| Working res | 512×320 | 960×544 |
| Frames | 73 (~3 s @ 24 fps) | 257 (~10.7 s @ 24 fps) |
| Output res (after 2x latent pass) | ~1024×640 | ~1920×1088 (~1080p) |
| Steps | 8 (distilled) | 8 (distilled LoRA) |
| ComfyUI args | `--lowvram --disable-smart-memory` | default (or `--highvram`) |

## Required models

### 8 GB tier — install with the `low_vram_8gb` profile

```bash
./scripts/install_ltx23.sh --profile low_vram_8gb
```

| File | Goes in |
|---|---|
| `ltx-2.3-22b-distilled-1.1-Q4_K_M.gguf` | `models/unet/` |
| `gemma_3_12B_it_fp4_mixed.safetensors` | `models/text_encoders/` |
| `ltx-2.3-22b-dev_video_vae.safetensors` | `models/vae/` |
| `ltx-2.3-22b-ic-lora-decompression-0.9.safetensors` | `models/loras/` |

Notes for 8 GB:
- The GGUF is loaded via **ComfyUI-GGUF's** `UnetLoaderGGUF` node (already in the image).
  It outputs MODEL only, so the video VAE is loaded separately with `VAELoader`.
- Keep clips short (~3 s). If you OOM, drop to 49 frames or 480×288 before touching LoRAs.
- Optional: add the OmniNFT IC-LoRA back at strength 1.0–1.5 if you have headroom
  (chain it after the decompression loader and repoint the sampler/guide model inputs).

### RunPod tier — install with the `mid_vram_12_24gb` profile

```bash
./scripts/install_ltx23.sh --profile mid_vram_12_24gb
# plus OmniNFT from the manifest (full profile) if not already present
```

| File | Goes in |
|---|---|
| `ltx-2.3-22b-dev-fp8.safetensors` | `models/checkpoints/` (VAE bundled) |
| `gemma_3_12B_it_fp4_mixed.safetensors` | `models/text_encoders/` |
| `ltx-2.3-22b-distilled-lora-384-1.1.safetensors` | `models/loras/` |
| `ltx-2.3-22b-ic-lora-decompression-0.9.safetensors` | `models/loras/` |
| `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` | `models/loras/` |

Notes for RunPod:
- 960×544 @ 257 frames fits ~24 GB with fp8. For 32 GB+ you can raise to 385 frames.
- Both tiers decode with `LTXVTiledVAEDecode`, so the 2x output doesn't blow up VAE VRAM.

## Input

Both expect an input video at `input_video.mp4` (resized in-graph via `ImageScale`,
lanczos, no crop). With the serverless handler, supply it via the job's image/video
upload mechanism the same way as the base patch workflow — see
`ltx23_v2v_music_visuals_patch_README.md`.

## Usage (serverless handler)

```python
import json

with open('examples/ltx23_v2v_8gb_gguf.json') as f:       # or ltx23_v2v_runpod_fp8.json
    workflow = json.load(f)

job = {"id": "v2v-job-1", "input": {"workflow": workflow}}
# result = handler(job)
```
