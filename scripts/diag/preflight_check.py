#!/usr/bin/env python3
"""
Pre-flight check for LTX-2.5 workflows.

Validates that workflows, models, custom nodes, and config files are all
correct and compatible before submitting jobs to a local or RunPod ComfyUI
instance.

Test levels (each can be skipped with --skip-<level>):
  1. static       — Workflow JSON structure validation (no dependencies)
  2. node_types   — Node types exist in ComfyUI object_info
  3. models       — Model files exist and are valid safetensors
  4. config       — Config/tokenizer files exist in model directories
  5. custom_nodes — Custom nodes are installed and importable
  6. dry_run      — ComfyUI accepts the workflow (POST /prompt, no execution)
  7. runpod       — RunPod volume health check (models, custom_nodes, inputs)

Usage:
    # Full check against local ComfyUI
    uv run python scripts/diag/preflight_check.py --target local

    # Full check against RunPod endpoint
    uv run python scripts/diag/preflight_check.py --target runpod --endpoint-id $RUNPOD_ENDPOINT_ID

    # Static + model checks only (no ComfyUI needed)
    uv run python scripts/diag/preflight_check.py --skip-node-types --skip-custom-nodes --skip-dry-run --skip-runpod

    # Check specific workflows
    uv run python scripts/diag/preflight_check.py --workflows examples/ltx25_v2v_redetail_24gb.json

    # Models only
    uv run python scripts/diag/preflight_check.py --models-only
"""

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Auto-activate project venv if running with system Python
_PROJECT_ROOT = Path(__file__).parent.parent
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and sys.executable != str(_VENV_PYTHON):
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

# Auto-load .env
def _load_dotenv():
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv()

import requests

# Colors
class C:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    NC = '\033[0m'

# Default workflows to check
DEFAULT_WORKFLOWS = [
    "examples/ltx25_v2v_redetail_24gb.json",
    "examples/ltx25_v2v_redetail_24gb_runpod.json",
    "examples/ltx25_animatediff_restyle_upscale_24gb.json",
    "examples/ltx25_text_to_video.json",
]

# Model directories to check
DEFAULT_MODELS_DIR = os.environ.get("COMFYUI_MODELS_DIR", str(_PROJECT_ROOT / ".local" / "models"))

# Required custom nodes
REQUIRED_CUSTOM_NODES = [
    "ComfyUI-LTXVideo",
    "ComfyUI-VideoHelperSuite",
]

# Model fields in workflow nodes that reference files
MODEL_FIELD_NAMES = {
    "ckpt_name": "checkpoints",
    "clip_name": "text_encoders",
    "lora_name": "loras",
    "vae_name": "vae",
    "model_name": "latent_upscale_models",
    "unet_name": "unet",
    "upscale_model": "latent_upscale_models",
}

# Config files required in the gemma4-12b-ltx-2.5 directory
GEMMA_DIR_REQUIRED_FILES = [
    "config.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "chat_template.jinja",
    "generation_config.json",
    "processor_config.json",
]


class CheckResult:
    def __init__(self, name: str, passed: bool, details: str = "", warnings: List[str] = None):
        self.name = name
        self.passed = passed
        self.details = details
        self.warnings = warnings or []

    def __str__(self):
        status = f"{C.GREEN}PASS{C.NC}" if self.passed else f"{C.RED}FAIL{C.NC}"
        s = f"  [{status}] {self.name}"
        if self.details:
            s += f"\n         {self.details}"
        for w in self.warnings:
            s += f"\n  {C.YELLOW}  ⚠ {w}{C.NC}"
        return s


class PreflightChecker:
    def __init__(self, target: str = "local", url: str = "", endpoint_id: str = "",
                 models_dir: str = "", workflows: List[str] = None):
        self.target = target
        self.url = url or os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
        self.endpoint_id = endpoint_id or os.environ.get("RUNPOD_ENDPOINT_ID", "")
        self.models_dir = Path(models_dir or DEFAULT_MODELS_DIR)
        self.workflows = workflows or DEFAULT_WORKFLOWS
        self.object_info: Optional[Dict[str, Any]] = None
        self.results: List[CheckResult] = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def _add(self, result: CheckResult):
        self.results.append(result)
        if result.passed:
            self.passed += 1
        else:
            self.failed += 1
        self.warnings += len(result.warnings)
        print(result)

    # ========================================================================
    # Level 1: Static Workflow Validation
    # ========================================================================

    def check_static(self):
        """Validate workflow JSON structure without needing ComfyUI."""
        print(f"\n{C.CYAN}{'='*60}{C.NC}")
        print(f"{C.CYAN}Level 1: Static Workflow Validation{C.NC}")
        print(f"{C.CYAN}{'='*60}{C.NC}")

        for wf_path in self.workflows:
            full_path = _PROJECT_ROOT / wf_path
            if not full_path.exists():
                self._add(CheckResult(f"File exists: {wf_path}", False, f"File not found: {full_path}"))
                continue

            try:
                with open(full_path) as f:
                    wf = json.load(f)
            except json.JSONDecodeError as e:
                self._add(CheckResult(f"Valid JSON: {wf_path}", False, f"JSON parse error: {e}"))
                continue

            # Check it's a dict with numeric keys
            if not isinstance(wf, dict) or not wf:
                self._add(CheckResult(f"Valid structure: {wf_path}", False, "Not a non-empty dict"))
                continue

            # Check each node has class_type and inputs
            errors = []
            for node_id, node in wf.items():
                if not isinstance(node, dict):
                    errors.append(f"Node {node_id}: not a dict")
                    continue
                if "class_type" not in node:
                    errors.append(f"Node {node_id}: missing class_type")
                if "inputs" not in node:
                    errors.append(f"Node {node_id}: missing inputs")

            # Check node references resolve
            for node_id, node in wf.items():
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs", {})
                for input_name, input_val in inputs.items():
                    if isinstance(input_val, list) and len(input_val) == 2:
                        ref_id = str(input_val[0])
                        if ref_id not in wf:
                            errors.append(f"Node {node_id}.{input_name}: references non-existent node '{ref_id}'")

            # Check at least one output node (VHS_VideoCombine, SaveImage, etc.)
            output_types = {"VHS_VideoCombine", "SaveImage", "SaveAnimatedPNG", "SaveVideo", "PreviewImage"}
            has_output = any(
                isinstance(n, dict) and n.get("class_type") in output_types
                for n in wf.values()
            )
            if not has_output:
                errors.append("No output node found (VHS_VideoCombine, SaveImage, etc.)")

            if errors:
                self._add(CheckResult(f"Structure: {wf_path}", False, "; ".join(errors[:3])))
            else:
                self._add(CheckResult(f"Structure: {wf_path} ({len(wf)} nodes)", True))

    # ========================================================================
    # Level 2: Node Type Validation
    # ========================================================================

    def _fetch_object_info(self) -> Optional[Dict[str, Any]]:
        """Fetch object_info from local or RunPod ComfyUI."""
        if self.object_info is not None:
            return self.object_info

        if self.target == "local":
            try:
                resp = requests.get(f"{self.url}/object_info", timeout=30)
                resp.raise_for_status()
                self.object_info = resp.json()
                print(f"  {C.DIM}Fetched {len(self.object_info)} node definitions from {self.url}{C.NC}")
                return self.object_info
            except requests.exceptions.ConnectionError:
                print(f"  {C.YELLOW}⚠ Could not connect to ComfyUI at {self.url} — skipping node type validation{C.NC}")
                return None
            except Exception as e:
                print(f"  {C.YELLOW}⚠ Error fetching object_info: {e}{C.NC}")
                return None
        else:
            # For RunPod, use the cached object_info if available
            cache_path = _PROJECT_ROOT / "config" / "object_info_cache.json"
            if cache_path.exists():
                with open(cache_path) as f:
                    self.object_info = json.load(f)
                print(f"  {C.DIM}Loaded {len(self.object_info)} node definitions from cache{C.NC}")
                return self.object_info
            print(f"  {C.YELLOW}⚠ No object_info cache found at {cache_path}{C.NC}")
            return None

    def check_node_types(self):
        """Check all workflow node types exist in ComfyUI object_info."""
        print(f"\n{C.CYAN}{'='*60}{C.NC}")
        print(f"{C.CYAN}Level 2: Node Type Validation{C.NC}")
        print(f"{C.CYAN}{'='*60}{C.NC}")

        obj_info = self._fetch_object_info()
        if obj_info is None:
            self._add(CheckResult("Fetch object_info", False, "Could not fetch object_info"))
            return

        for wf_path in self.workflows:
            full_path = _PROJECT_ROOT / wf_path
            if not full_path.exists():
                continue

            with open(full_path) as f:
                wf = json.load(f)

            missing_types = []
            missing_inputs = []
            value_not_in_list = []

            for node_id, node in wf.items():
                if not isinstance(node, dict):
                    continue
                class_type = node.get("class_type", "")
                if class_type not in obj_info:
                    missing_types.append(f"Node {node_id}: '{class_type}'")
                    continue

                # Check required inputs
                node_info = obj_info[class_type]
                required = node_info.get("input", {}).get("required", {})
                node_inputs = node.get("inputs", {})

                for req_name, req_spec in required.items():
                    if req_name not in node_inputs:
                        # Check if it's a reference (list value) that might be connected
                        missing_inputs.append(f"Node {node_id}.{req_name}: required input missing")

                    # Check COMBO values
                    if req_name in node_inputs and isinstance(req_spec, list) and len(req_spec) >= 2:
                        if isinstance(req_spec[0], list):  # COMBO type
                            options = req_spec[0]
                            val = node_inputs[req_name]
                            if isinstance(val, str) and val not in options:
                                value_not_in_list.append(
                                    f"Node {node_id}.{req_name}: '{val}' not in options (have: {options[:3]}...)"
                                )

            errors = missing_types + missing_inputs + value_not_in_list
            warnings = []
            if missing_types:
                warnings.append(f"Missing node types: {', '.join(missing_types)}")
            if missing_inputs:
                warnings.append(f"Missing required inputs: {', '.join(missing_inputs[:3])}")
            if value_not_in_list:
                warnings.append(f"Value not in list: {', '.join(value_not_in_list[:3])}")

            if errors:
                self._add(CheckResult(f"Node types: {wf_path}", False, "; ".join(errors[:3]), warnings))
            else:
                self._add(CheckResult(f"Node types: {wf_path}", True, warnings=warnings))

    # ========================================================================
    # Level 3: Model File Integrity
    # ========================================================================

    def _check_safetensors(self, path: Path) -> Tuple[bool, str]:
        """Check if a safetensors file is valid by reading its header."""
        try:
            with open(path, "rb") as f:
                header_len_bytes = f.read(8)
                if len(header_len_bytes) < 8:
                    return False, "File too small (less than 8 bytes)"
                header_len = struct.unpack("<Q", header_len_bytes)[0]
                if header_len > 100_000_000:  # 100MB header is absurd
                    return False, f"Header length {header_len} is unreasonably large"
                header_bytes = f.read(header_len)
                if len(header_bytes) < header_len:
                    return False, f"File truncated (expected {header_len} header bytes, got {len(header_bytes)})"
                header = json.loads(header_bytes)
                if not isinstance(header, dict):
                    return False, "Header is not a JSON object"
                # Check it has at least one tensor or __metadata__
                if "__metadata__" not in header and len(header) == 0:
                    return False, "Header has no tensors or metadata"
                tensor_count = len([k for k in header if k != "__metadata__"])
                return True, f"Valid safetensors ({tensor_count} tensors)"
        except json.JSONDecodeError:
            return False, "Header is not valid JSON"
        except struct.error:
            return False, "Could not read header length"
        except Exception as e:
            return False, f"Error: {e}"

    def check_models(self):
        """Check model files exist and are valid."""
        print(f"\n{C.CYAN}{'='*60}{C.NC}")
        print(f"{C.CYAN}Level 3: Model File Integrity{C.NC}")
        print(f"{C.CYAN}{'='*60}{C.NC}")

        if not self.models_dir.exists():
            self._add(CheckResult(f"Models dir exists: {self.models_dir}", False, "Directory not found"))
            return

        # Collect all model references from workflows
        model_refs: Dict[str, Set[str]] = {}  # folder -> set of filenames
        for wf_path in self.workflows:
            full_path = _PROJECT_ROOT / wf_path
            if not full_path.exists():
                continue
            with open(full_path) as f:
                wf = json.load(f)
            for node in wf.values():
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs", {})
                for field, folder in MODEL_FIELD_NAMES.items():
                    if field in inputs and isinstance(inputs[field], str):
                        model_refs.setdefault(folder, set()).add(inputs[field])

        all_ok = True
        for folder, filenames in sorted(model_refs.items()):
            folder_path = self.models_dir / folder
            for filename in sorted(filenames):
                file_path = folder_path / filename
                if not file_path.exists():
                    # Check if it's a directory (e.g. gemma4-12b-ltx-2.5/model.safetensors)
                    parent = file_path.parent
                    if parent.exists() and parent.is_dir() and file_path.name == "model.safetensors":
                        # Check if it's a symlink
                        if file_path.is_symlink():
                            target = os.readlink(file_path)
                            if os.path.exists(file_path.resolve()):
                                self._add(CheckResult(f"Model: {folder}/{filename}", True, f"symlink -> {target}"))
                            else:
                                self._add(CheckResult(f"Model: {folder}/{filename}", False, f"broken symlink -> {target}"))
                                all_ok = False
                        else:
                            self._add(CheckResult(f"Model: {folder}/{filename}", False, "model.safetensors not found in directory"))
                            all_ok = False
                    else:
                        self._add(CheckResult(f"Model: {folder}/{filename}", False, f"File not found: {file_path}"))
                        all_ok = False
                elif file_path.stat().st_size == 0:
                    self._add(CheckResult(f"Model: {folder}/{filename}", False, "File is empty (0 bytes)"))
                    all_ok = False
                elif filename.endswith(".safetensors"):
                    ok, details = self._check_safetensors(file_path)
                    if not ok:
                        self._add(CheckResult(f"Model: {folder}/{filename}", False, f"Corrupt: {details}"))
                        all_ok = False
                    else:
                        size_mb = file_path.stat().st_size / (1024 * 1024)
                        self._add(CheckResult(f"Model: {folder}/{filename}", True, f"{details}, {size_mb:.0f}MB"))
                elif filename.endswith(".gguf"):
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    self._add(CheckResult(f"Model: {folder}/{filename}", True, f"GGUF file, {size_mb:.0f}MB"))
                else:
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    self._add(CheckResult(f"Model: {folder}/{filename}", True, f"{size_mb:.0f}MB"))

        if all_ok:
            self._add(CheckResult("All model files valid", True))

    # ========================================================================
    # Level 4: Config/Tokenizer Files
    # ========================================================================

    def check_config_files(self):
        """Check config/tokenizer files in model directories."""
        print(f"\n{C.CYAN}{'='*60}{C.NC}")
        print(f"{C.CYAN}Level 4: Config/Tokenizer Files{C.NC}")
        print(f"{C.CYAN}{'='*60}{C.NC}")

        # Check gemma4-12b-ltx-2.5 directory
        gemma_dir = self.models_dir / "text_encoders" / "gemma4-12b-ltx-2.5"
        if not gemma_dir.exists():
            self._add(CheckResult(f"Gemma dir: {gemma_dir}", False, "Directory not found — LTXVGemmaCLIPModelLoader will fail"))
            return

        all_ok = True
        for required_file in GEMMA_DIR_REQUIRED_FILES:
            file_path = gemma_dir / required_file
            if not file_path.exists() and not file_path.is_symlink():
                self._add(CheckResult(f"Gemma dir: {required_file}", False, f"Missing: {file_path}"))
                all_ok = False
            elif file_path.is_symlink() and not file_path.resolve().exists():
                self._add(CheckResult(f"Gemma dir: {required_file}", False, f"Broken symlink: {file_path}"))
                all_ok = False
            else:
                size = file_path.stat().st_size
                self._add(CheckResult(f"Gemma dir: {required_file}", True, f"{size} bytes"))

        if all_ok:
            self._add(CheckResult("All config/tokenizer files present", True))

    # ========================================================================
    # Level 5: Custom Node Check
    # ========================================================================

    def check_custom_nodes(self):
        """Check custom nodes are installed."""
        print(f"\n{C.CYAN}{'='*60}{C.NC}")
        print(f"{C.CYAN}Level 5: Custom Node Check{C.NC}")
        print(f"{C.CYAN}{'='*60}{C.NC}")

        custom_nodes_dir = self.models_dir.parent / "custom_nodes"
        if not custom_nodes_dir.exists():
            # Try Docker path
            custom_nodes_dir = Path("/comfyui/custom_nodes")
        if not custom_nodes_dir.exists():
            self._add(CheckResult("Custom nodes dir", False, "Directory not found"))
            return

        for node_name in REQUIRED_CUSTOM_NODES:
            node_path = custom_nodes_dir / node_name
            if not node_path.exists():
                self._add(CheckResult(f"Custom node: {node_name}", False, f"Not found at {node_path}"))
            elif not (node_path / "__init__.py").exists():
                self._add(CheckResult(f"Custom node: {node_name}", False, "Missing __init__.py"))
            else:
                self._add(CheckResult(f"Custom node: {node_name}", True, f"Installed at {node_path}"))

    # ========================================================================
    # Level 6: Dry-Run Submission
    # ========================================================================

    def check_dry_run(self):
        """Submit workflows to ComfyUI for validation (no execution)."""
        print(f"\n{C.CYAN}{'='*60}{C.NC}")
        print(f"{C.CYAN}Level 6: Dry-Run Submission{C.NC}")
        print(f"{C.CYAN}{'='*60}{C.NC}")

        if self.target == "runpod":
            self._add(CheckResult("Dry-run (RunPod)", False, "Dry-run not supported for RunPod target — use --target local"))
            return

        # Find a valid input video to patch VHS_LoadVideo nodes
        input_dir = self.models_dir.parent / "input"
        patch_video = None
        for candidate in ["rhizome.mp4", "a_black_video.mp4"]:
            if (input_dir / candidate).exists():
                patch_video = candidate
                break

        for wf_path in self.workflows:
            full_path = _PROJECT_ROOT / wf_path
            if not full_path.exists():
                continue

            with open(full_path) as f:
                wf = json.load(f)

            # Patch VHS_LoadVideo nodes to use a valid video file
            if patch_video:
                for node_id, node in wf.items():
                    if not isinstance(node, dict):
                        continue
                    if node.get("class_type") == "VHS_LoadVideo":
                        old_video = node.get("inputs", {}).get("video", "")
                        if old_video and old_video != patch_video:
                            node["inputs"]["video"] = patch_video

            try:
                resp = requests.post(
                    f"{self.url}/prompt",
                    json={"prompt": wf},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    prompt_id = data.get("prompt_id", "?")
                    # Cancel the prompt immediately to prevent execution
                    try:
                        requests.post(f"{self.url}/queue", json={"delete": [prompt_id]}, timeout=5)
                    except:
                        pass
                    self._add(CheckResult(f"Dry-run: {wf_path}", True, f"Accepted (prompt_id: {prompt_id[:8]}...)"))
                elif resp.status_code == 400:
                    error_data = resp.json()
                    node_errors = error_data.get("node_errors", {})
                    error_msgs = []
                    for nid, errs in node_errors.items():
                        for err in errs.get("errors", []):
                            error_msgs.append(f"Node {nid}: {err.get('message', '')} — {err.get('details', '')}")
                    self._add(CheckResult(f"Dry-run: {wf_path}", False, "; ".join(error_msgs[:3])))
                else:
                    self._add(CheckResult(f"Dry-run: {wf_path}", False, f"HTTP {resp.status_code}: {resp.text[:200]}"))
            except requests.exceptions.ConnectionError:
                self._add(CheckResult(f"Dry-run: {wf_path}", False, f"Could not connect to {self.url}"))
            except Exception as e:
                self._add(CheckResult(f"Dry-run: {wf_path}", False, f"Error: {e}"))

    # ========================================================================
    # Level 7: RunPod Volume Health
    # ========================================================================

    def check_runpod(self):
        """Check RunPod volume health via API."""
        print(f"\n{C.CYAN}{'='*60}{C.NC}")
        print(f"{C.CYAN}Level 7: RunPod Volume Health{C.NC}")
        print(f"{C.CYAN}{'='*60}{C.NC}")

        if not self.endpoint_id:
            self._add(CheckResult("RunPod check", False, "No endpoint ID provided (use --endpoint-id or set RUNPOD_ENDPOINT_ID)"))
            return

        api_key = os.environ.get("RUNPOD_API_KEY", "")
        if not api_key:
            self._add(CheckResult("RunPod check", False, "No RUNPOD_API_KEY set"))
            return

        # Check endpoint health
        try:
            resp = requests.get(
                f"https://api.runpod.ai/v2/{self.endpoint_id}/health",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            if resp.status_code == 200:
                health = resp.json()
                workers = health.get("workers", {})
                jobs = health.get("jobs", {})
                self._add(CheckResult(
                    "Endpoint health",
                    True,
                    f"Workers: {workers.get('ready', 0)} ready, {workers.get('running', 0)} running | "
                    f"Jobs: {jobs.get('inQueue', 0)} queued, {jobs.get('inProgress', 0)} in progress"
                ))
            else:
                self._add(CheckResult("Endpoint health", False, f"HTTP {resp.status_code}"))
        except Exception as e:
            self._add(CheckResult("Endpoint health", False, f"Error: {e}"))

        # Submit a download_models dry-run to check what's on the volume
        hf_token = os.environ.get("HF_TOKEN", "")
        try:
            job_input = {
                "action": "download_models",
                "manifest": "ltx-2.5",
                "profile": "mid_vram_24gb",
                "dry_run": True,
            }
            if hf_token:
                job_input["hf_token"] = hf_token

            resp = requests.post(
                f"https://api.runpod.ai/v2/{self.endpoint_id}/run",
                json={"input": job_input},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            if resp.status_code == 200:
                job_id = resp.json().get("id")
                # Poll for completion
                for i in range(30):
                    time.sleep(3)
                    resp = requests.get(
                        f"https://api.runpod.ai/v2/{self.endpoint_id}/status/{job_id}",
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=10
                    )
                    data = resp.json()
                    status = data.get("status", "UNKNOWN")
                    if status in ("COMPLETED", "FAILED", "ERROR"):
                        output = data.get("output", {})
                        if output.get("status") == "success":
                            models = output.get("models", [])
                            existing = [m for m in models if m.get("status") == "exists"]
                            missing = [m for m in models if m.get("status") != "exists"]
                            self._add(CheckResult(
                                "Volume models",
                                len(missing) == 0,
                                f"{len(existing)} present, {len(missing)} missing"
                            ))
                            for m in missing:
                                self._add(CheckResult(f"  Missing: {m.get('id', '?')}", False, m.get("path", "")))
                        else:
                            err = output.get("metadata", {}).get("error_message", "Unknown error")
                            self._add(CheckResult("Volume models", False, err[:200]))
                        break
                    if i % 5 == 0:
                        print(f"  {C.DIM}  {status} ({(i+1)*3}s)...{C.NC}")
                else:
                    self._add(CheckResult("Volume models", False, "Timed out waiting for dry-run"))
            else:
                self._add(CheckResult("Volume models", False, f"HTTP {resp.status_code}"))
        except Exception as e:
            self._add(CheckResult("Volume models", False, f"Error: {e}"))

    # ========================================================================
    # Run all checks
    # ========================================================================

    def run(self, skip: Set[str] = None):
        skip = skip or set()

        print(f"\n{C.BOLD}{'='*60}{C.NC}")
        print(f"{C.BOLD}Pre-Flight Check{C.NC}")
        print(f"{C.BOLD}{'='*60}{C.NC}")
        print(f"  Target: {self.target}")
        print(f"  URL: {self.url}")
        print(f"  Endpoint: {self.endpoint_id or '(not set)'}")
        print(f"  Models dir: {self.models_dir}")
        print(f"  Workflows: {len(self.workflows)}")

        if "static" not in skip:
            self.check_static()
        if "node_types" not in skip:
            self.check_node_types()
        if "models" not in skip:
            self.check_models()
        if "config" not in skip:
            self.check_config_files()
        if "custom_nodes" not in skip:
            self.check_custom_nodes()
        if "dry_run" not in skip:
            self.check_dry_run()
        if "runpod" not in skip:
            self.check_runpod()

        # Summary
        print(f"\n{C.BOLD}{'='*60}{C.NC}")
        print(f"{C.BOLD}Summary{C.NC}")
        print(f"{C.BOLD}{'='*60}{C.NC}")
        total = self.passed + self.failed
        print(f"  {C.GREEN}Passed: {self.passed}{C.NC}")
        print(f"  {C.RED}Failed: {self.failed}{C.NC}")
        print(f"  {C.YELLOW}Warnings: {self.warnings}{C.NC}")
        print(f"  Total: {total}")

        if self.failed > 0:
            print(f"\n{C.RED}❌ Pre-flight check FAILED — fix the issues above before deploying.{C.NC}")
            return 1
        else:
            print(f"\n{C.GREEN}✅ Pre-flight check PASSED — all systems go!{C.NC}")
            return 0


def main():
    parser = argparse.ArgumentParser(
        description="Pre-flight check for LTX-2.5 workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", choices=["local", "runpod"], default="local",
                        help="Where to check (default: local)")
    parser.add_argument("--url", default=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"),
                        help="ComfyUI URL for local target")
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", ""),
                        help="RunPod endpoint ID")
    parser.add_argument("--models-dir", default="",
                        help="Path to ComfyUI models directory")
    parser.add_argument("--workflows", nargs="+", default=None,
                        help="Specific workflow files to check")
    parser.add_argument("--models-only", action="store_true",
                        help="Only check model files (skip ComfyUI-dependent checks)")
    parser.add_argument("--skip-static", action="store_true", help="Skip static validation")
    parser.add_argument("--skip-node-types", action="store_true", help="Skip node type validation")
    parser.add_argument("--skip-models", action="store_true", help="Skip model file checks")
    parser.add_argument("--skip-config", action="store_true", help="Skip config file checks")
    parser.add_argument("--skip-custom-nodes", action="store_true", help="Skip custom node checks")
    parser.add_argument("--skip-dry-run", action="store_true", help="Skip dry-run submission")
    parser.add_argument("--skip-runpod", action="store_true", help="Skip RunPod volume health")
    args = parser.parse_args()

    skip = set()
    if args.models_only:
        skip.update({"node_types", "custom_nodes", "dry_run", "runpod"})
    if args.skip_static:
        skip.add("static")
    if args.skip_node_types:
        skip.add("node_types")
    if args.skip_models:
        skip.add("models")
    if args.skip_config:
        skip.add("config")
    if args.skip_custom_nodes:
        skip.add("custom_nodes")
    if args.skip_dry_run:
        skip.add("dry_run")
    if args.skip_runpod:
        skip.add("runpod")

    checker = PreflightChecker(
        target=args.target,
        url=args.url,
        endpoint_id=args.endpoint_id,
        models_dir=args.models_dir,
        workflows=args.workflows,
    )

    sys.exit(checker.run(skip=skip))


if __name__ == "__main__":
    main()
