---
title: Python Package Management
inclusion: always
---

# Python Package Management Standards

## Package Manager

This project uses **uv** for Python dependency management.

### Why uv?

- Extremely fast (10-100x faster than pip)
- Written in Rust for performance and reliability
- Drop-in replacement for pip and pip-tools
- Built-in virtual environment management
- Generates deterministic builds with uv.lock
- Compatible with standard pyproject.toml

### Required Files

- `pyproject.toml`: Declares project dependencies and metadata
- `uv.lock`: Locks exact versions for reproducible builds

### Commands

**Install dependencies:**
```bash
uv sync
```

**Add a new package:**
```bash
uv add package-name
```

**Add a dev package:**
```bash
uv add --dev package-name
```

**Run commands in virtual environment:**
```bash
uv run python script.py
uv run pytest
```

**Install specific package versions:**
```bash
uv pip install package-name==1.0.0
```

### DO NOT use:

- `pip install` directly (use `uv pip install` or `uv add`)
- `pipenv` or `poetry` for this project
- `venv` or `virtualenv` manually (uv handles this)

### Exception

Docker images may use `requirements.txt` for build optimization:
```bash
uv pip compile pyproject.toml -o requirements.txt
```
