# RunPod Deployment & Serverless Rules

## Serverless Endpoint

- **Endpoint ID**: `taea2mhlwbdkuq` (set in `.env` as `RUNPOD_ENDPOINT_ID`)
- **Network volume ID**: `el6aj9vatl`
- Workers cache Docker images and don't auto-pull new `latest` tags — you must
  force an image update in the RunPod console after rebuilding.

## Diagnostic Action

Use the `diagnostic` action for remote debugging on serverless workers:

```python
job = endpoint.run({
    "input": {
        "action": "diagnostic",
        "commands": ["ls -la /comfyui/models/", "nvidia-smi"],
        "timeout": 15,
    }
})
```

The `diagnostic` action runs shell commands on the worker and returns
stdout/stderr. Use it to:
- Check file existence and paths
- Inspect GPU memory usage
- Patch files on the worker (ephemeral — lost on restart)
- Kill/restart ComfyUI process

If `diagnostic` is not available, the worker is running a stale image.

## Workflow JSON Format

All workflows must be in **API format** (dict of `node_id → {class_type, inputs}`).

UI format (with `nodes` array, `links`, `widgets_values`) doesn't work with
the serverless handler. Convert UI workflows to API format using ComfyUI's
"Save (API Format)" in the WebUI.

## Testing Order

1. Test locally first: `./scripts/run_local.sh --logs` → WebUI at `http://localhost:8188`
2. If local works, test on serverless:
   ```bash
   set -a && source .env && set +a
   uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4
   ```
3. If serverless fails but local works, check:
   - Worker image is up to date (is `diagnostic` action available?)
   - Model files exist on the volume
   - `COMFYUI_ARGS` doesn't have `--use-sage-attention`
   - GPU VRAM is sufficient for the model size

## Git Workflow

```bash
git add -A
git commit -m "fix: <description of what and why>"
git push github main   # remote is 'github', not 'origin'
```

Commit and push after each fix. Don't accumulate changes.

## runpodctl vs Python SDK

| Use case | Tool |
|---|---|
| Quick one-off commands (list pods, check GPUs) | `runpodctl` |
| Scripted automation (deploy, invoke, poll) | Python SDK ([`lifecycle/`](../../lifecycle/)) |
| File transfer to/from pods | `runpodctl send/receive` |
| Debugging serverless workers | `runpodctl serverless logs` or SSH |

See [`docs/RUNPOD_STEERING.md`](../../docs/RUNPOD_STEERING.md) for full details.
