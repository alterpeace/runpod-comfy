# Package Management — `uv` Only, Never `pip`

## The Rule

The container has NO `pip` binary. The venv at `/comfyui/venv/` was created
by `uv` and doesn't include `pip`. All package management goes through `uv`.

## Correct Commands

```bash
# Install into ComfyUI's venv (inside the container)
uv pip install --python /comfyui/venv/bin/python <package>

# Install project dependencies (local development)
uv sync

# Run Python scripts
uv run python scripts/<script>.py
```

## Wrong Commands (will fail)

```bash
pip install <package>                          # pip doesn't exist
/comfyui/venv/bin/pip install <package>         # pip not in venv
python -m pip install <package>               # pip module not available
```

## Why

The Dockerfile uses `uv` to create the venv and install all dependencies.
`uv` creates venvs without `pip` by default. Adding `pip` back would require
bootstrapping it, which is unnecessary when `uv pip install` works for all
use cases.

## Local Development

On the host machine (outside the container), `uv` is also the package manager:

```bash
# Install all project deps from pyproject.toml
uv sync

# Run scripts
uv run python scripts/invoke_v2v_with_upload.py --video rhizome.mp4

# Add a new dependency
uv add <package>
```

## Container Custom Node Dependencies

Custom node pip dependencies are installed via `uv pip install` in
[`entrypoint.sh`](../../entrypoint.sh) during container boot. See
[`scripts/collect_custom_node_deps.sh`](../../scripts/collect_custom_node_deps.sh)
for how dependencies are gathered from custom node `requirements.txt` files.
