# Container Layout — `/workspace` ≠ `/comfyui`

## The Two Worlds

```
/workspace     ← project code (handler.py, entrypoint.sh, scripts/)
/comfyui       ← ComfyUI installation (main.py, venv, custom_nodes, models/)
```

When you `docker exec -it comfy bash`, you land in `/workspace` (this project's
code). ComfyUI itself lives at `/comfyui` — a separate directory.

## Full Layout

```
/workspace                    ← This project (cloned from git)
/workspace/src/handler.py     ← RunPod serverless handler
/workspace/entrypoint.sh      ← Container boot script
/workspace/scripts/           ← Build, deploy, test scripts

/comfyui                      ← ComfyUI installation
/comfyui/main.py              ← ComfyUI entry point
/comfyui/venv                 ← Python venv (created by uv, NO pip)
/comfyui/custom_nodes         ← Custom nodes (ComfyUI-LTXVideo, etc.)
/comfyui/input  → /runpod-volume/input    (symlink — entire dir)
/comfyui/output → /runpod-volume/output   (symlink — entire dir)
/comfyui/models → /runpod-volume/models   (symlink)
```

## Symlink Strategy (Critical)

`/comfyui/input`, `/comfyui/output`, and `/comfyui/models` are **entire-directory
symlinks** to `/runpod-volume/`. This is critical:

- ✅ **CORRECT**: `ln -s /runpod-volume/input /comfyui/input` (entire dir)
- ❌ **WRONG**: `ln -s /runpod-volume/input/rhizome.mp4 /comfyui/input/rhizome.mp4` (individual file)

**Why:** ComfyUI's `is_within_directory()` uses `os.path.realpath()` which follows
symlinks. Individual file symlinks resolve to `/runpod-volume/input/rhizome.mp4`,
which is outside `/comfyui/input/`, failing the path traversal check. When the
**entire directory** is the symlink, `realpath` resolves both the dir and files
to the same base, passing the check.

This was discovered in the Aug 14-15 debugging session. See
[`docs/SESSION_SUMMARY_2026_08_14_15.md`](../../docs/SESSION_SUMMARY_2026_08_14_15.md)
issue #1.

## Output Persistence

`/comfyui/output` is symlinked to `/runpod-volume/output` so output files
persist across worker restarts. Without this, output videos are lost when
serverless workers scale down (ephemeral container disk).

See session summary issue #7 for the fix history.

## Entering the Container

```bash
docker exec -it comfy bash
# You're now in /workspace
# ComfyUI is at /comfyui
# ComfyUI's venv is at /comfyui/venv
# Custom nodes are at /comfyui/custom_nodes
# Models are at /comfyui/models (symlinked from /runpod-volume/models)
```
