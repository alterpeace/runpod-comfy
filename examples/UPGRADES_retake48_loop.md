# retake48_loop — Dormant Upgrades Reminder

Workflow: `examples/ltx25_v2v_retake48_loop_runpod.json`
State after first-test request (2026-09-17): **NAG + IC-LoRA added but DORMANT** (validated, never executed, zero runtime cost).

2026-09-19 UPDATE: the dormant NAG node used a phantom class (`LTX2_NAG`) that
exists in NO installed pack — ComfyUI validates every node in a graph (connected
or not), so it 400-rejected EVERY run of all four files. Fixes applied:
- base + iclora variants: dormant node removed (dangling nodes with required
  inputs can never validate — "dormant in the same file" is impossible).
- nag + both variants: node 14b rewritten to ComfyUI core `NAGuidance`
  (comfy_extras/nodes_nag.py: model + nag_scale/nag_alpha/nag_tau; the
  invented `nag_cond_video` input dropped). Knobs preserved.

## Ready-made variant files (2026-09-18) — no manual rewiring needed:
- `examples/ltx25_v2v_retake48_loop_nag.json` — NAG on (core NAGuidance)
- `examples/ltx25_v2v_retake48_loop_iclora.json` — IC-LoRA guided
- `examples/ltx25_v2v_retake48_loop_both.json` — both on
Each is the base file with the rewires below applied; the base file itself stays dormant.

## After the first smoke test (1 clip), enable ONE at a time:

### 1. NAG (node `14b`, already present)
- Rewire: node `14a` (`LTXVApplySTG`) `model`: `["3",0]` → `["14b",0]`
- Knobs in `14b`: `nag_scale` 11.0, `nag_alpha` 0.25, `nag_tau` 2.5 (NAG paper defaults — tune scale first)
- Cost: ~+20–40% pass-1 sampling time. Expected win: negative prompt (node 6) actually works at cfg 1.0.

### 2. IC-LoRA guide (nodes `4` + `27`, already present)
- Rewire: nodes `11`/`14a`/`25` `model`: `["3",0]` → `["4",0]`
- Rewire: node `14` (`CFGGuider`) `positive`: `["5",0]` → `["27",0]`, `negative`: `["6",0]` → `["27",1]`
- Knob: node `27` `strength` 0.8 (comfortable-workflow pattern). Guide = source frames at 768×448.
- Cost: ~neutral. Expected win: sharper IC-guided pass-1 (the pixel-upscaler skill actually gets used).

## Validation gate (both)
1. Run 1 clip through the driver: `./scripts/skypilot/retake_loop_batch.sh <one-clip>.mp4`
2. `tools/loop-checker.html`: retake Loop diff <5%, Start match <5% (End match will diverge if the original doesn't loop — expected)
3. Keep NAG if junk/flicker visibly drops; keep IC-LoRA if pass-1 detail visibly improves; otherwise revert rewires (dormant nodes can stay in the file forever).

Timing note: neither changes step count (8) or resolution; only NAG costs real time (~+20–40% of pass-1). Measure on the first clip before the 37-clip batch.
