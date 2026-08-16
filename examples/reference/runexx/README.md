# RuneXX LTX-2.3 Reference Workflows

Downloaded from [huggingface.co/RuneXX/LTX-2.3-Workflows](https://huggingface.co/RuneXX/LTX-2.3-Workflows)

841 likes, 374 commits — the most comprehensive community collection of LTX-2.3 ComfyUI workflows.

## Files

| File | Size | Source Directory | Relevance |
|---|---|---|---|
| `v2v_general_purpose_ic_lora.json` | 136 kB | Video-2-Video/ | 🔥 Directly comparable to our V2V redetail workflow |
| `music_video_multi_scene.json` | 761 kB | Music-Video-Creator/ | 🔥 Multi-scene music video — basis for VJ set workflow |
| `long_video_audio_loop.json` | 375 kB | Long-Video-Experimental/ | 🔥 Long video with audio loop — perfect loop techniques |
| `3pass_experimental.json` | 155 kB | 3-Pass-Experimental/ | Multi-pass with upscaler — comfortable tier approach |
| `3pass_dev.json` | 186 kB | 3-Pass-Experimental/ | Dev model 3-pass — higher quality version |
| `custom_audio_id_lora.json` | 123 kB | Custom-Audio/ | Audio-driven generation — BPM sync potential |
| `basic_gguf.json` | 115 kB | Root | GGUF basic — confirms our GGUF approach is standard |
| `simple_single_pass.json` | 105 kB | Root | Single pass — similar to our entry tier |

## Key Takeaways

1. **V2V workflow** — Compare node setup, parameters, and LoRA handling to our `ltx25_v2v_redetail_entry_runpod.json`
2. **Music-Video-Creator** — Multi-scene generation could inspire a "VJ set" workflow
3. **3-Pass-Experimental** — Generate at low res → upscale 1.5x → detail pass (our comfortable tier)
4. **Long-Video-Experimental** — Chaining generation passes with overlapping frames for longer loops
5. **GGUF basic** — Confirms GGUF quantization is community-standard for consumer GPUs

## Note

These are LTX-2.3 workflows (not 2.5). Node names and parameters may differ from LTX-2.5.
Use as reference for techniques and approaches, not direct imports.
