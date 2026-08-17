# RunPod Steering Directions

Context and guidance for working with RunPod infrastructure, CLI tools, agent
skills, serverless handlers, and MCP servers. Tailored to this project
(`runpod-comfy` — a ComfyUI serverless deployment on RunPod).

---

## 1. RunPod CLI (`runpodctl`)

**Docs:** <https://docs.runpod.io/runpodctl/overview>

`runpodctl` is the official CLI for managing RunPod resources from your local
machine. It complements the Python SDK used in this project's
[`lifecycle/`](../lifecycle/) scripts.

### Install

```bash
# Linux/macOS install script
bash <(curl -sL cli.runpod.io)

# Or Homebrew (macOS)
brew install runpod/runpodctl/runpodctl
```

### Configure

```bash
runpodctl doctor    # First-time setup: API key + SSH keys
# Or set env var:
export RUNPOD_API_KEY=<your-key>
```

### Key commands for this project

```bash
# GPU availability (critical — we hit capacity shortages)
runpodctl gpu list

# Pod management (for debugging — preferred over serverless for development)
runpodctl pod create --template-id <id> --gpu-id "NVIDIA RTX 4090"
runpodctl pod list
runpodctl pod stop <pod-id>
runpodctl pod remove <pod-id>   # TERMINATE (stops billing)

# Serverless endpoints
runpodctl serverless list
runpodctl serverless logs <endpoint-id>

# File transfer (upload input videos to volume)
runpodctl send <local-file> <pod-id>:/runpod-volume/input/
runpodctl receive <pod-id>:/runpod-volume/outputs/ <local-dir>

# Network volumes
runpodctl network-volume list

# SSH into a pod
runpodctl ssh <pod-id>
```

### When to use `runpodctl` vs the Python SDK

| Use case | Tool |
|---|---|
| Quick one-off commands (list pods, check GPUs) | `runpodctl` |
| Scripted automation (deploy, invoke, poll) | Python SDK ([`lifecycle/`](../lifecycle/)) |
| File transfer to/from pods | `runpodctl send/receive` |
| Debugging serverless workers | `runpodctl serverless logs` or SSH |

### Project-specific notes

- This project's endpoint ID: `taea2mhlwbdkuq` (set in `.env` as
  `RUNPOD_ENDPOINT_ID`)
- Network volume ID: `el6aj9vatl` (set in `.env` as needed)
- The Python lifecycle scripts in [`lifecycle/runpod_pods.py`](../lifecycle/runpod_pods.py)
  and [`lifecycle/runpod_serverless.py`](../lifecycle/runpod_serverless.py) wrap
  the RunPod SDK and are preferred for scripted operations
- `runpodctl` is useful for ad-hoc debugging and file transfers

---

## 2. Agent Skills for AI Coding Tools

**Docs:** <https://docs.runpod.io/get-started/agent-skills>

RunPod provides a skills plugin that teaches AI coding agents (Claude Code,
Codex, Cursor, etc.) how to manage GPU workloads on RunPod through natural
language.

### Install

```bash
# Install the skills plugin (works with any AI agent)
npx skills add runpod/runpod-plugins-official

# Install the CLI the skills rely on
curl -sSL https://cli.runpod.net | bash

# Authenticate
export RUNPOD_API_KEY=<key>
# Or: runpodctl doctor
```

### What the skills provide

| Skill | Description |
|---|---|
| `runpod` | Router — reads your task and hands it to the right skill |
| `runpod-mcp` | Manages Pods, endpoints, templates, volumes via MCP server |
| `runpodctl` | Manages resources from the CLI (pods, files, SSH, caching) |
| `flash` | Deploys Python code to RunPod Serverless using `runpod-flash` SDK |
| `companion-clis` | Uses supporting CLIs (Hugging Face, Docker, AWS) when needed |
| `runpod-usage` | Conceptual knowledge about Pods, Serverless, storage, GPU selection |

### Example prompts

| Category | Example |
|---|---|
| Create resources | "Create a Pod with an RTX 4090" |
| List resources | "List my Pods" or "Show my Serverless endpoints" |
| GPU availability | "What GPUs are available?" |
| Deploy endpoints | "Deploy a Serverless endpoint using my template" |
| Manage Pods | "Stop my Pod" or "SSH into my Pod" |
| File transfer | "Upload my video to the volume" |

### Project-specific guidance

When using AI agents with this project:
- **Always check GPU availability first** — RunPod frequently runs out of
  capacity. Use `runpodctl gpu list` or ask "What GPUs are available?"
- **Prefer Pods for debugging** — serverless endpoints don't give you shell
  access or WebUI. Create a Pod with SSH, debug interactively, then deploy to
  serverless.
- **Use the MCP server** (see section 4) for programmatic resource management
  from within AI agents.

---

## 3. Serverless Handler Functions

**Docs:** <https://docs.runpod.io/serverless/workers/handler-functions>

Handler functions are the core of RunPod Serverless applications. They define
how workers process requests and return results. This project's handler is at
[`src/handler.py`](../src/handler.py).

### Basic structure

```python
import runpod

def handler(job):
    job_input = job["input"]
    # Process the input
    return {"status": "success", "output": result}

runpod.serverless.start({"handler": handler})
```

### This project's handler architecture

The handler in [`src/handler.py`](../src/handler.py) supports multiple actions
via an `action` field in the job input:

| Action | Description | Key function |
|---|---|---|
| `run_workflow` (default) | Execute a ComfyUI workflow | `handler()` → `execute_workflow()` |
| `download_models` | Download LTX models to the volume | `download_models()` |
| `diagnostic` | Run shell commands on the worker for debugging | `run_diagnostic()` |

### Job input structure

```json
{
    "id": "job-uuid",
    "input": {
        "action": "run_workflow",
        "workflow": { ... },
        "input_images": { "filename.mp4": "base64data..." },
        "timeout": 600,
        "clear_cache": true
    }
}
```

### Handler best practices (from RunPod docs + lessons learned)

1. **Validate inputs early** — use `ValidationError` for bad input before
   starting expensive operations
2. **Clean up temporary files** — ComfyUI generates temp files; use
   `clear_cache` to prevent corrupted outputs
3. **Write logs** — use Python `logging`; RunPod captures stdout/stderr
4. **Use environment variables** — configure via endpoint env vars, not
   hardcoded values
5. **Handle cold starts** — ComfyUI takes 3-8 min to boot on first job;
   set `TIMEOUT=600+`
6. **Test locally first** — use `test_input.json` with
   `runpod.serverless.start({"handler": handler})`

### Debugging handler issues

- **SSH into workers:** See
  [RunPod docs](https://docs.runpod.io/serverless/development/ssh-into-workers)
- **View logs:** `runpodctl serverless logs <endpoint-id>` or RunPod console
- **Diagnostic action:** This project's handler has a `diagnostic` action that
  runs shell commands on the worker (see [`src/handler.py`](../src/handler.py:772))
- **Creative debugging without SSH:** The `download_models` action's
  `inline_manifest` + `symlink_target` feature can be exploited to create
  symlinks and check file existence on the worker (see
  [`scripts/diag/fix_input_symlink.py`](../scripts/diag/fix_input_symlink.py) and
  [`scripts/diag/check_files.py --mode volume`](../scripts/diag/check_files.py --mode volume))

### Key lessons from this project

1. **Symlinks and ComfyUI's path traversal check:** ComfyUI's
   `is_within_directory()` uses `os.path.realpath()` which follows symlinks.
   Symlinks from `/comfyui/input/` → `/runpod-volume/input/` are rejected
   because the resolved path is outside the input directory. Workaround: use
   relative symlinks within `/comfyui/input/` + upload files via
   `input_images`.

2. **Stale images cause silent failures:** The deployed Docker image may not
   match the current code. Always rebuild and push after code changes. Check
   with the `diagnostic` action — if it returns "Unknown action", the image is
   stale.

3. **Pod-first development:** Debug workflows in a Pod with SSH/WebUI access
   before deploying to serverless. Serverless is for production, not
   development.

---

## 4. RunPod MCP Servers

**Docs:** <https://docs.runpod.io/get-started/mcp-servers>

RunPod provides two MCP (Model Context Protocol) servers:

1. **RunPod API MCP server** — manage Pods, endpoints, templates, volumes via
   the RunPod REST API (requires API key)
2. **RunPod docs MCP server** — search RunPod documentation (no auth required)

### Install for Claude Code

```bash
claude mcp add runpod --scope user \
  -e RUNPOD_API_KEY=your_api_key_here \
  -- npx -y @runpod/mcp-server@latest
```

### Install for VS Code / Kilo Code

Add to `.mcp.json` (this project already has one at [`.mcp.json`](../.mcp.json)):

```json
{
  "mcpServers": {
    "runpod": {
      "command": "npx",
      "args": ["-y", "@runpod/mcp-server@latest"],
      "env": {
        "RUNPOD_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Install for Cursor

Add to `.cursor/mcp.json` or `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "runpod": {
      "command": "npx",
      "args": ["-y", "@runpod/mcp-server@latest"],
      "env": {
        "RUNPOD_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### What the MCP server provides

The RunPod API MCP server gives AI tools access to the full RunPod REST API:
- Create/manage Pods
- Create/manage Serverless endpoints
- Manage templates and network volumes
- View billing and account info
- Check GPU availability

### Project-specific usage

This project's [`.mcp.json`](../.mcp.json) may already be configured. Check
it and add the RunPod MCP server if not present. With the MCP server
connected, you can ask your AI agent to:
- "List my RunPod endpoints"
- "Check GPU availability"
- "Create a debug pod with SSH"
- "Show my serverless endpoint logs"
- "Upload files to the network volume"

### Docs MCP server (no auth)

The docs MCP server lets AI agents search RunPod documentation:
- "How do I write a handler function?"
- "What are the serverless endpoint settings?"
- "How do I SSH into a worker?"

---

## Quick Reference: This Project's RunPod Resources

| Resource | Value | Source |
|---|---|---|
| Serverless endpoint ID | `taea2mhlwbdkuq` | `.env` → `RUNPOD_ENDPOINT_ID` |
| Network volume ID | `el6aj9vatl` | `.env` |
| Docker image | `ghcr.io/alterpeace/runpod-comfy:latest` | `scripts/build/build.sh` |
| Handler | [`src/handler.py`](../src/handler.py) | Serverless entry point |
| Entrypoint | [`entrypoint.sh`](../entrypoint.sh) | Container boot script |
| Models config | [`config/ltx-2.5-models.json`](../config/ltx-2.5-models.json) | Model manifest |
| S3 endpoint | `RUNPOD_S3_ENDPOINT` | `.env` |
| S3 bucket | `RUNPOD_S3_BUCKET` | `.env` |

## Decision Tree: Debugging Approach

```
Is the workflow failing?
├── Can you create a Pod? (runpodctl gpu list)
│   ├── YES → Create Pod with SSH, debug in ComfyUI WebUI (port 8188)
│   │         Fix the issue, rebuild & push image, then test serverless
│   └── NO (capacity shortage)
│       ├── Is the `diagnostic` action available?
│       │   ├── YES → Send diagnostic commands via serverless API
│       │   └── NO (stale image) → Rebuild & push image (./scripts/build/build.sh --push)
│       └── Can you exploit `download_models` action?
│           ├── Create symlinks via inline_manifest + symlink_target
│           ├── Check file existence via skip-if-exists logic
│           └── Upload files via input_images in run_workflow
└── Is it a model loading issue?
    └── Rebuild image with updated dependencies (transformers, custom nodes)
```
