# LTX-2.3 Workflow Enhancements

## Music Video Pipeline: Redetail, Extend, Beat-Sync

Three distinct techniques for working with already-produced footage set to
music (V2V redetailing, clip extension, and audio-driven generation
parameters) rather than generating from scratch.

### Redetailing / restyling existing clips

No new mechanism needed — this is the same V2V IC-LoRA chain already in
this repo's manifest. Stack multiple LoRAs in one `LTXAddVideoICLoRAGuide`
pass: `distilled_lora` (required for the fast pipeline) plus whichever
effect LoRAs apply — `iclora_deblur`/`iclora_decompression` for detail
restoration, `iclora_water_simulation`/`iclora_day_to_night`/
`omninft_rl_lora` for style changes, `audio_reactive` for beat-driven
visual effects. Strength per-LoRA controls how much each contributes;
denoise/CFG controls how far the output can drift from the source (see
CFG note in the Edit Anything section above — same tradeoff applies here).

### Extending clip duration (e.g. 15s → 30s+)

LTX-2.3 has no "extend this clip" parameter — each generation produces a
fixed frame count. Extension is done by **chaining**: take the last frame(s)
of clip A, feed them into `LTXVImgToVideoConditionOnly` (or the FFLF-style
conditioning) as the starting point for a new generation, then concatenate
outputs. This is the same technique documented in markdkberry's LTX-2
extension workflows (referenced elsewhere in this doc) — works the same way
on 2.3, just swap in the 2.3 checkpoint and nodes.

Reported reliability: clean chaining up to ~5 extensions before visible
degradation (drift in color/lighting/motion) sets in — treat that as a
soft ceiling, not a hard one; verify per-clip since content-dependent drift
varies. For batch work across hundreds of clips, one extension (15s→30s) is
low-risk; chaining several times to reach a full minute per clip should be
spot-checked, not batch-automated blindly.

### Beat detection → NLE markers → generation-parameter driving

`scripts/analyze_beats.py` (added to this repo) runs `librosa` beat/onset
detection on an audio track and produces:

1. **`<name>_markers.csv`** — a CSV with `Timecode In`, `Name`, `Comment`
   columns, importable as timeline markers in Premiere Pro or DaVinci
   Resolve via [editingtools.io/marker](https://editingtools.io/marker)
   (CSV → DaVinci Resolve EDL, or CSV → Premiere Pro XML). Use this to see
   beat/downbeat positions directly on your editing timeline.
2. **`<name>_beats.json`** — the same beat/downbeat/onset data as seconds
   *and* frame indices at your target fps, for scripting against.

```bash
python scripts/analyze_beats.py song.wav --fps 24 --output-dir ./beats --onsets
```

Tested against a synthetic 120 BPM click track — correctly detected
117.45 BPM (close given click-track timing imprecision) and the expected
beat count. `librosa` is already installed in this repo's Dockerfile
(`deps` stage), no extra dependency needed.

**Using the frame indices to drive LTX-2.3 generation** (this is the part
that replaces "even spacing" with "beat-aware"):

- **Non-uniform guide-image placement**: `ComfyUI-rogala`'s `FMLFLTX_2.3`
  node (added to this repo — see Node Packs section) distributes up to 6
  guide images at fixed evenly-spaced percentages (0%, 25%, 50%, 75%, etc.).
  It does not accept per-image custom timing directly, so to align guide
  images with actual downbeats you'd pick which % slot to use per image
  based on the closest downbeat's `frame_index / total_frames` from the
  JSON output, rather than relying on the node's default even spacing.
- **IC-LoRA guide strength keyframing**: `LTXAddVideoICLoRAGuide`'s
  strength parameter is static per-run in the example workflows. To vary
  effect intensity per-beat (e.g. stronger `audio_reactive` pull on
  downbeats), you'd need to render in per-beat-aligned segments rather than
  one continuous pass — generate each segment between two downbeats as a
  separate LTX-2.3 call with strength tuned per segment, then concatenate.
  This is more render calls, not a single-workflow toggle.
- **Effect timing generally**: use the finer-grained `onsets` list (not
  `beats`) for fast transient-driven effects (hi-hat flickers, hit-flashes)
  — onsets catch sub-beat detail that pure beat-tracking misses, at the
  cost of being noisier. Beats/downbeats are the more reliable signal for
  structural sync (cut points, guide-image placement, segment boundaries).

**Honest limitation**: there's no ComfyUI node in this stack that ingests
an audio file and automatically re-times a generation frame-by-frame to
match detected beats within a single sampler pass — the `audio_reactive`
LoRA biases the model toward beat-reactive *motion tendencies* during
generation, but it isn't frame-accurate triggering like Resolume. The
markers/frame-index workflow above is the practical middle ground: you get
precise beat timestamps to plan segment boundaries and guide-image
placement around, but the actual beat-to-visual mapping within a segment is
still the model's generative interpretation, not a guaranteed hit.


Community-sourced tuning notes for LTX-2.3 generation quality, sampler
selection, and scheduling. These are workflow/parameter tweaks, not model or
node installs — see `docs/LTX_2.3_V2V_ICLORA_SETUP.md` for the install side.

## Scheduler: Replace ManualSigmas with linear_quadratic

The official Lightricks workflows hardcode sigma values via a `ManualSigmas`
node:

- **Pass 1** (8 steps): `1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0`
- **Pass 2** (after `LTXVLatentUpsampler` ×2, 3 steps): `0.85, 0.725, 0.4219, 0.0`

A community finding ([r/StableDiffusion](https://www.reddit.com/r/StableDiffusion/comments/1rw8453/ltx_23_manual_sigmas_can_be_replaced/))
showed that the `linear_quadratic` scheduler with `denoise=1.0` reproduces
the Pass 1 sigmas exactly. This means `ManualSigmas` can be replaced with a
standard `BasicScheduler` node for Pass 1, simplifying the graph.

Pass 2 doesn't map as cleanly — `linear_quadratic` starts from `1.0` and
scales by `denoise`, so no single `denoise` value lands on `0.85` as the
first sigma. Options for Pass 2:
- Keep `ManualSigmas` (simplest, matches official behavior exactly)
- Use `ClownScheduler` (from RES4LYF) with `start_value=0.85` — produces the
  exact target sigmas, but outputs to a non-standard `sigmas` socket instead
  of `SIGMAS`, so it needs `SamplerCustomAdvanced` rather than connecting
  directly to a `PainterSamplerLTXV`.

## Sampler Selection

A 63-sampler benchmark on LTX-2.3 with `linear_quadratic`
([source](https://www.reddit.com/r/StableDiffusion/comments/1sqy9iu/ltx23_testing_63_samplers_with_linear_quadratic/))
found:

**Avoid — crashed ComfyUI during generation:**
- `dpm_adaptive`
- `legacy_rk`
- `rk`

**Fast tier** (~200s total for an 8-step/3-step two-pass run on a 385-frame
clip at 640x352 → 1280x720, RTX 5060 Ti 16GB): `euler`, `ddim`, `dpmpp_2m_sde_gpu`,
`res_multistep`, `euler_ancestral`, `lcm`, `gradient_estimation`, `er_sde`.
Reasonable default choice for iteration speed.

**Slow tier** (10-20x slower, `res_*`/`dpm_2`/`heun` family): noticeably
better in some subjective reports but not universally — no consensus winner
emerged. `dpmpp_2m_sde_gpu` and `seeds_2`/`seeds_3` were each called out by
different reviewers as favorites (sync accuracy vs. motion quality,
respectively). Treat "best sampler" as unresolved and subjective — test
against your own footage rather than taking one config as ground truth.

**Do not use:** `dpmpp_2s_ancestral_cfg_pp` — took ~23 minutes in the same
test, dramatically slower than everything else with no corresponding quality
benefit reported.

Full per-sampler timing table is in the source thread linked above.

## Known Issue: Hair / Fine Motion Doesn't Animate

Independently reported by two sources testing LTX-2.3: hair (and likely
other fine, physics-driven motion) stays static across generations
regardless of sampler choice, even with explicit prompting for
wind/movement. Workarounds:

- **Repeat the motion cue in the prompt** — mention hair/wind movement
  *twice* rather than once (e.g. "a wind breezes through the scene and hair
  of the person" stated twice).
- **Use the distilled `fp8_scaled` variant over `mxfp8_block32`** for
  consistency in fine details (hair, clothing) across frames, especially
  when a subject re-enters frame after being briefly out of shot.
- **VBVR-family LoRA** ("Video Reasoning" — physics/object interaction,
  motion logic between frames), trained on ~1M reasoning-task videos
  (trajectories, collisions, causal chains, spatial relationships). Added to
  the manifest as `vbvr_i2v_lora`, sourced from
  [`LiconStudio/Ltx2.3-VBVR-lora-I2V`](https://huggingface.co/LiconStudio/Ltx2.3-VBVR-lora-I2V)'s
  `VBVR-official-comfyui.safetensors` — this is the community-reported
  strongest of the available ports. Background:
  - Originates from [`Video-Reason/VBVR-LTX2.3-diffsynth`](https://huggingface.co/Video-Reason/VBVR-LTX2.3-diffsynth),
    which does **not** load directly in ComfyUI (diffsynth format).
  - [`siraxe/VBVR-LTX2.3-diffsynth_comfyui`](https://huggingface.co/siraxe/VBVR-LTX2.3-diffsynth_comfyui) —
    an earlier, more literal key-conversion port. Reddit thread reported this
    one as weaker/had no effect for one tester; not added to the manifest,
    use the LiconStudio one instead unless you have a specific reason to
    compare them.
  - A Civitai variant also circulates: `LTX-2.3 I2V/T2V Video Reasoning LoRA (VBVR)` — used at strength 0.85 in the source report; the manifest entry is the HF-native equivalent.

This isn't fully solved — one tester found no global change in hair/motion
behavior across multiple model quantizations (`bf16`, `fp8_scaled`,
`mxfp8_block32`) and 4 different LoRA combinations. Worth a dedicated test
if this matters for your use case, rather than assuming any single fix
above resolves it.

## Edit Anything LoRAs (Alissonerdx) — Prompting Rules

Added to the manifest as `editanything_multitask`, `editanything_motion_transfer`,
and the `editanything_refv2v_standard`/`editanything_refv2v_module` pair
([source](https://huggingface.co/Alissonerdx/EditAnything)). The author is
explicit these are **research experiments, not production-ready** — expect
failures on many inputs.

Requires the [`ComfyUI-BFSNodes`](https://github.com/alisson-anjos/ComfyUI-BFSNodes)
custom node pack (now added to `scripts/add-dependancies.sh`) — needed for the
Ref V2V module sidecar loader regardless of which LoRA you use; the
multitask and motion-transfer LoRAs are plain standard LoRAs and technically
load through any ComfyUI LoRA loader without BFSNodes, but BFSNodes' `LTXV
Edit Anything (Apply)` node is the documented path for all three.

**Which one to use:**

| Want | Use |
|---|---|
| Multi-task edits (add/remove/replace/style) driven only by prompt | `editanything_multitask` |
| Motion transfer (edit first frame externally, model copies motion) | `editanything_motion_transfer` |
| Strong identity transfer from a reference image (add/replace) | `editanything_refv2v_standard` + `editanything_refv2v_module` (must load both, matching build) |

**Caption shape matters a lot** — deviating from the trained format degrades
quality noticeably:

- **Add**: 15-30+ words. `Add <detailed subject description>, <position in frame>, <surrounding context>.`
- **Remove**: 4-10 words only. `Remove the <object>`. Longer prompts drift off-distribution.
- **Replace**: 20-35 words, describe *both* old and new subject: `Replace <original + location> with <new subject>.`
- **Style**: fixed template only — `Convert the video into a <STYLE NAME> style.` (300+ style names trained; not all work equally well)
- **No compositional prompts** — "add X and remove Y" is not in the training distribution; split into separate runs.
- **No generic "change background"** — phrase it as a Replace on a concrete background element instead.

**CFG note**: default distilled/accelerated LoRA setup runs at `cfg=1.0`,
which makes edits weak. If the model is ignoring your prompt or the edit
isn't landing, raise CFG (up to 6-8) — this means dropping the distilled
LoRA and using more sampling steps, trading speed for prompt adherence.

## Detailer/Upscale Landscape (community survey)

Cross-referencing a community workflow archive
([markdkberry.com](https://markdkberry.com/workflows/research-2026/#detailers),
low-VRAM-focused, RTX 3060 12GB) for how people are chaining detailers/upscalers
after LTX generation. None of this is installed — reference only, useful
context for the trade-offs if a second-pass polish step gets added later.

- **LTX-2/2.3 self-detailer (v2v, upscale-in-one-pass)**: input a small clip
  (e.g. 480p) back through LTX-2.3 itself (GGUF or FP4) to reach 1080p.
  Reported as the best result achievable on a 12GB card, but **destroys
  dialogue/mouth-sync** — only use where lip movement doesn't matter. Can
  OOM on VAE decode on low VRAM unless models are kept loaded between runs.
- **HuMO detailer** ([AbleJones/drozbay](https://github.com/drozbay)): v2v
  polish pass using a WAN-based model with ClownShark sampling. Notable
  for genuine **character-consistency** — uses the first frame of the input
  video to anchor character identity across the extension, similar in
  spirit to Phantom/MAGREF. Heavy on VRAM (OOMs above 480p on a 12GB card in
  the source report) — not worth adopting unless resolution ceiling is
  fixed.
- **USDU (Ultimate SD Upscaler)** ([ssitu/ComfyUI_UltimateSDUpscale](https://github.com/ssitu/ComfyUI_UltimateSDUpscale)):
  tiled diffusion upscale/detail pass, works with either WAN or LTX as the
  underlying model. Low denoise (0.1-0.35) preserves mouth movement/dialogue
  better than the LTX self-detailer above — the go-to when dialogue must be
  preserved. WAN pass is slow (~40 min for 1080p/233 frames on a 12GB card)
  but more reliable than LTX (~15 min, "quirky" per the source).
- **WAN detailer (simple v2v polish)**: low-denoise (0.3-0.8) pass through a
  standard WAN 2.2 t2v model to fix specific artifacts (example given: a
  snake's head rendering wrong) without a specialized detailer workflow.
  Simplest option if you just need a targeted fix, not a systematic
  upscaler.
- **FlashVSR** ([naxci1/ComfyUI-FlashVSR_Stable](https://github.com/naxci1/ComfyUI-FlashVSR_Stable)):
  this is a genuinely relevant find — a dedicated video super-resolution
  node (not a diffusion detailer) with explicit VRAM tiers from 8GB to 24GB+,
  auto-downloading models, and built-in OOM protection with progressive
  fallback (tiled VAE → tiled DiT → chunking). Reported 720p→1080p in ~10
  min on a 3060 12GB. This is the closest match to our existing VRAM-tier
  approach (`config/ltx-2.3-models.json` profiles) and the most promising
  candidate if a dedicated upscale step gets added — evaluate before
  adopting, not yet in the manifest.

None of the above are wired into `scripts/add-dependancies.sh` or the model
manifest. FlashVSR is the standout candidate if you want a low-VRAM
upscale step; the others either conflict with dialogue preservation goals
or don't clear the VRAM bar this repo targets.

## Comfy MCP / Comfy Skills (agent tooling)

### Comfy Cloud MCP (hosted, not integrated)

[Comfy MCP](https://blog.comfy.org/p/comfy-mcp-turn-your-agent-into-a) is
Comfy Org's hosted Model Context Protocol server
([docs](https://docs.comfy.org/agent-tools/cloud)) — lets an MCP-compatible
agent (Claude Code, Claude Desktop, Cursor, Codex) generate images/video/
audio/3D, search models/nodes/templates, and run or share ComfyUI workflows
via natural language, without a local GPU.

**Important distinction: this is a Comfy Cloud feature, not something that
runs against our self-hosted container.** Workflows execute on Comfy Cloud's
GPUs and consume Comfy Cloud credits (public beta, requires a
cloud.comfy.org account and subscription/credit balance for generation
tools — discovery tools are free). It complements this repo's local/RunPod
image rather than replacing it — useful for quick agent-driven prototyping
or template discovery, not for production inference on our own
infrastructure or models.

[Comfy Skills](https://github.com/Comfy-Org/comfy-skills/) hosts the Claude
Code plugin (`comfy-cloud`) that bundles the MCP connection with slash
commands (`/comfy-cloud:generate-video`, `/comfy-cloud:search-models`,
etc.). Install via:

```
/plugin marketplace add Comfy-Org/comfy-skills
/plugin install comfy-cloud@comfy-skills
```

then `/mcp` → `comfy-cloud` → Authenticate (OAuth).

This is an agent-side tool for whoever is driving Claude/Cursor/etc., not a
container dependency. Worth knowing about for workflow discovery/prototyping
(e.g. asking an agent to find a matching LTX-2.3 template) but doesn't change
anything about the Docker image, model manifest, or install scripts here.

## New Node Packs Added

Both added to `scripts/add-dependancies.sh` alongside LTXVideo/GGUF/BFSNodes.

- **[`ComfyUI-rogala`](https://github.com/Rogala/ComfyUI-rogala)** — the
  author of the LTX-2.3 sampler research thread's own node pack. Relevant
  pieces for this repo's LTX-2.3 focus:
  - `SmartAttentionDispatcher` — auto-detects GPU architecture and switches
    SageAttention kernels (SA2/SA3) per diffusion step. Reports +25-50% speed
    on `ltx-2.3-22b-distilled` for large-sequence video on Blackwell
    (RTX 50xx, 16GB). **Do not combine with `--use-sage-attention`** (this
    repo's `runpod-config-*.json` currently sets that flag — see note below).
  - `FMLFLTX_2.3` / `SamplerLTXV_2.3` — a ready-made two-pass (low-res → 2x
    upscale/refine) sampler pipeline for LTX-2.3 distilled models with up to
    6 guide images, matching the pass-1/pass-2 `linear_quadratic` pattern
    described above.
  - `LTX Resolution Selector` — computes correct width/height/frame-count
    for LTX-2.3 Dev or Distilled (x1.5/x2 upscale) modes, avoiding manual
    multiple-of-32 arithmetic.
  - `Sampler Scheduler Iterator` — automates sampler x scheduler sweeps
    (like the 63-sampler benchmark above) instead of manual reruns.
  - Also includes non-LTX utilities (Advanced Style Selector, text overlay
    nodes, node-alignment toolbar) — harmless extras, not evaluated in
    detail here.

  **Action needed**: `SmartAttentionDispatcher` conflicts with
  `--use-sage-attention`, which is set in `config/runpod-config-serverless.json`
  and `config/runpod-config-pods.json`. If you adopt this node, remove that
  flag from `COMFYUI_ARGS` in both configs to avoid double-patching attention.
  Not changed automatically — decide if you want the node's dynamic kernel
  switching over the static flag first.

- **[`ComfyUI-MemoryVisualization`](https://github.com/kijai/ComfyUI-MemoryVisualization)** —
  real-time VRAM/RAM monitoring panel from Kijai (ComfyUI-KJNodes' author,
  already a dependency via `scripts/add-dependancies.sh`). When
  `comfy-aimdo` (dynamic VRAM, on by default since ComfyUI ~v0.24) is
  active, it also shows per-model page-level residency heatmaps and
  watermark controls — directly useful for diagnosing the aggressive-offload
  issue flagged in the LTX-2.3 setup doc
  ([Comfy-Org/ComfyUI#14447](https://github.com/Comfy-Org/ComfyUI/issues/14447)).
  Purely diagnostic, no model weights, low risk to add.

## Comfy MCP — Now Has an Official Local Server (Comfy Partner MCP)

Previously reviewed Comfy Cloud MCP only worked against Comfy's hosted
cloud GPUs. Comfy Org has since published **Comfy Partner MCP**
([docs](https://docs.comfy.org/agent-tools/partner-mcp)) — currently
**private preview, invite-only** — which is different in an important way:

| | Comfy Cloud MCP | Comfy Partner MCP |
|---|---|---|
| Where it runs | Hosted at `cloud.comfy.org/mcp` | **Local** — runs on your machine (Node.js) |
| What it drives | Your Comfy Cloud account's GPUs, full workflow graphs | 30+ partner API providers (BFL, Ideogram, Kling, Runway, Veo, ElevenLabs, etc.) — **not** your local ComfyUI install |
| Auth | Comfy Cloud account/OAuth | Comfy API key (`comfyui-...`) |
| Cost | Comfy Cloud credits | Per-provider API costs via Comfy's proxy |

**Neither of these drives our self-hosted RunPod/local container.** Comfy
Partner MCP runs locally as a process, but it's a local *client* that calls
*remote partner APIs* — it does not connect to a ComfyUI server (local or
ours) at all. There is still no first-party MCP server for driving a
self-hosted ComfyUI instance; Comfy's own docs
([agent-tools overview](https://docs.comfy.org/agent-tools)) explicitly
list this as a gap and point to **community-maintained** options instead:

- [`artokun/comfyui-mcp`](https://github.com/artokun/comfyui-mcp) — most
  actively developed of the community options, explicitly supports local,
  LAN, VPS, or Comfy Cloud targets; ships a Claude Code plugin with 108
  tools and pre-built LTX-2.3/Wan/Flux/Qwen/Z-Image skills
- [`joenorton/comfyui-mcp-server`](https://github.com/joenorton/comfyui-mcp-server) — lightweight, listed directly in Comfy's own docs
- [`shawnrushefsky/comfyui-mcp`](https://github.com/shawnrushefsky/comfyui-mcp) — also listed in Comfy's docs

Comfy Org also ships **Comfy CLI** (`pip install comfy-cli`,
[docs](https://docs.comfy.org/comfy-cli/getting-started)), which is a real
first-party tool but is a terminal command runner, not an MCP server — it
can `comfy install`/`comfy launch` a local ComfyUI, or route `comfy run` /
`comfy generate` to local or cloud, and optionally installs "agent skills"
for Claude Code/Cursor/AGENTS.md-aware tools via `comfy skills install`.
Worth knowing about for scripting/CI, but separate from MCP.

## Third-Party Node Pack Reviewed (Not Installed)

[`TenStrip/10S-Comfy-nodes`](https://github.com/TenStrip/10S-Comfy-nodes) —
single-author, MIT-licensed, ~190 stars. Monkey-patches ComfyUI's internal
LTX2 class structure (`LTXAVModel`, `BasicAVTransformerBlock`) via forward
hooks and instance-level method patches — not a public API, so a ComfyUI
version bump could break it without upstream notice (no CI/tests visible,
single contributor).

Two nodes stood out as potentially useful if revisited later:

- **LTX Tiled Sampler** — addresses a real, documented issue: a second
  sampling pass on a 2x-upscaled latent runs the model outside its trained
  spatial-token-count range, causing hue shifts and color drift. Splits the
  latent into tiles, samples each at the trained token distribution, blends
  with cosine-windowed overlap. Refinement-pass only, not for first-pass
  generation from noise.
- **LTX Reference Enable/Conditioning** — prepends an encoded reference
  image's tokens into the video token sequence via self-attention, as an
  identity-preservation mechanism distinct from IC-LoRA. Composes with
  `iclora_ingredients` (different intervention point: sequence input vs.
  attention-output modification) rather than replacing it.

Not currently added to `scripts/add-dependancies.sh` or the model manifest —
holding off given the maintenance risk described above. Revisit if the
upscale color-drift issue or a lightweight reference-based identity lock
becomes a real blocker.
