# Continuous Improvement / Context Preservation Strategy

## Error Prevention Through Documentation

When
- encountering errors that occurred due to lack of vital information like project setup, architecture, configuration or similar
OR
- discovering crucial information whose unavailability could cause such errors in the future:

**IMMEDIATELY suggest to the user:**
"I notice [current error/potential future confusion] related to [specific topic]. Should I create a concise reference file in `.kilocode/rules/` covering [specific topic] to prevent similar issues in future sessions?"

**Trigger conditions:**
- **Retroactive**: Current errors from missing project context, configuration misunderstandings, or architectural confusion
- **Proactive**: Discovery of important project/architecture/configuration information that could cause future session confusion

## Common Documentation Targets
- Build processes and file copying behavior
- Environment-specific routing patterns
- Architecture decisions and folder relationships
- Deployment vs development differences
- Tool-specific behaviors (Vite, Apache, etc.)

**Key principle:** Future sessions will NOT have current context - only what you document NOW.

## How This Project Uses This Pattern

This project (`runpod-comfy`) has already captured several hard-won lessons:

- **Symlink strategy**: `/comfyui/input` and `/comfyui/output` must be entire-directory symlinks to `/runpod-volume/`, not individual file symlinks (individual file symlinks fail ComfyUI's `realpath` check). See [`container-layout.md`](container-layout.md).

- **Model loader choice**: `CLIPLoader` with `type: "ltxv"` works with `comfy_quant` int8-convrot models; `LTXVGemmaCLIPModelLoader` does not. See [`model-loading.md`](model-loading.md).

- **Sage attention crash**: `--use-sage-attention` crashes because `comfy_kitchen` CUDA backend needs cu130 but we have cu129. See [`model-loading.md`](model-loading.md).

- **VRAM limits**: int8-convrot transformer (21.5GB) OOMs on 24GB GPUs; use GGUF Q4 (~6GB) instead. See [`model-loading.md`](model-loading.md).

When you encounter a NEW lesson like these, add it to the appropriate `.kilocode/rules/` file or create a new one, then suggest the change to the user.
