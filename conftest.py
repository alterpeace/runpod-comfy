"""
Pytest configuration / path bootstrap.

The application modules (``handler``, ``comfyui_client``, ``storage_s3``) live in
``src/``. Inside the Docker container they are copied to ``/workspace/`` and the
runtime tests add ``/workspace`` to ``sys.path`` themselves. For *local* test
runs (``uv run python -m pytest``) we need ``src/`` on the path instead, so the
imports in ``tests/test_*.py`` resolve without touching every test file.

This file is NOT copied into the Docker image (the Dockerfile only COPYs
``src/*.py``, ``config/``, ``entrypoint.sh``, etc.), so it has no effect on the
built image or RunPod deployments.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
