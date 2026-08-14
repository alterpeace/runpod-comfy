"""
Pre-flight tests for LTX-2.5 workflows.

Tests are organized by level (see plans/preflight-test-suite.md):
  1. Static workflow validation (no dependencies)
  2. Node type validation (needs object_info cache)
  3. Model file integrity (needs filesystem)
  4. Config/tokenizer files (needs filesystem)
  5. Custom node check (needs ComfyUI install)
  6. Dry-run submission (needs running ComfyUI)

Run specific levels:
  uv run pytest tests/test_preflight.py -k "static"
  uv run pytest tests/test_preflight.py -k "node_types"
  uv run pytest tests/test_preflight.py -k "models"
  uv run pytest tests/test_preflight.py -k "config"
  uv run pytest tests/test_preflight.py -k "custom_nodes"
  uv run pytest tests/test_preflight.py -k "dry_run"
"""

import json
import os
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent

# Workflows to test
LTX25_WORKFLOWS = [
    "examples/ltx25_v2v_redetail_24gb.json",
    "examples/ltx25_v2v_redetail_24gb_runpod.json",
    "examples/ltx25_animatediff_restyle_upscale_24gb.json",
    "examples/ltx25_text_to_video.json",
]

# Model fields in workflow nodes
MODEL_FIELD_NAMES = {
    "ckpt_name": "checkpoints",
    "clip_name": "text_encoders",
    "lora_name": "loras",
    "vae_name": "vae",
    "model_name": "latent_upscale_models",
    "unet_name": "unet",
    "upscale_model": "latent_upscale_models",
}

# Required custom nodes
REQUIRED_CUSTOM_NODES = ["ComfyUI-LTXVideo", "ComfyUI-VideoHelperSuite"]

# Config files required in gemma4-12b-ltx-2.5 directory
GEMMA_DIR_REQUIRED_FILES = [
    "config.json", "tokenizer_config.json", "tokenizer.json",
    "chat_template.jinja", "generation_config.json", "processor_config.json",
]


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def workflows():
    """Load all LTX-2.5 workflow JSON files."""
    result = {}
    for wf_path in LTX25_WORKFLOWS:
        full_path = PROJECT_ROOT / wf_path
        if full_path.exists():
            with open(full_path) as f:
                result[wf_path] = json.load(f)
    return result


@pytest.fixture
def models_dir():
    """Get the models directory."""
    return Path(os.environ.get("COMFYUI_MODELS_DIR", str(PROJECT_ROOT / ".local" / "models")))


@pytest.fixture
def object_info_cache():
    """Load object_info from cache file."""
    cache_path = PROJECT_ROOT / "config" / "object_info_cache.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    return None


# ============================================================================
# Level 1: Static Workflow Validation
# ============================================================================

class TestStaticValidation:
    """Validate workflow JSON structure without needing ComfyUI."""

    def test_all_workflows_exist(self, workflows):
        """All workflow files should exist and be loadable."""
        assert len(workflows) >= 3, f"Expected at least 3 workflows, got {len(workflows)}"

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_workflow_is_valid_json(self, wf_path):
        """Each workflow should be valid JSON."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        with open(full_path) as f:
            wf = json.load(f)
        assert isinstance(wf, dict), f"{wf_path}: not a dict"
        assert len(wf) > 0, f"{wf_path}: empty workflow"

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_nodes_have_class_type(self, wf_path):
        """Every node should have a class_type field."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        with open(full_path) as f:
            wf = json.load(f)
        for node_id, node in wf.items():
            if not isinstance(node, dict):
                pytest.fail(f"{wf_path} node {node_id}: not a dict")
                continue
            assert "class_type" in node, f"{wf_path} node {node_id}: missing class_type"
            assert "inputs" in node, f"{wf_path} node {node_id}: missing inputs"

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_node_references_resolve(self, wf_path):
        """All node references should point to existing nodes."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        with open(full_path) as f:
            wf = json.load(f)
        for node_id, node in wf.items():
            if not isinstance(node, dict):
                continue
            for input_name, input_val in node.get("inputs", {}).items():
                if isinstance(input_val, list) and len(input_val) == 2:
                    ref_id = str(input_val[0])
                    assert ref_id in wf, f"{wf_path} node {node_id}.{input_name}: references non-existent node '{ref_id}'"

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_has_output_node(self, wf_path):
        """Each workflow should have at least one output node."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        with open(full_path) as f:
            wf = json.load(f)
        output_types = {"VHS_VideoCombine", "SaveImage", "SaveAnimatedPNG", "SaveVideo", "PreviewImage"}
        has_output = any(
            isinstance(n, dict) and n.get("class_type") in output_types
            for n in wf.values()
        )
        assert has_output, f"{wf_path}: no output node found"

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_no_deprecated_node_types(self, wf_path):
        """Workflows should not use deprecated/non-existent node types."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        with open(full_path) as f:
            wf = json.load(f)
        deprecated = {
            "LTXVLatentUpscaler": "Use LTXVLatentUpsampler (with 'r') instead",
            "LTXVLatentUpscalerLoader": "Use LatentUpscaleModelLoader instead",
            "LTXVLatentUpscale": "Use LTXVLatentUpsampler instead",
            "LTXVLatentTemporalUpscale": "Use LTXVLatentUpsampler with temporal upscaler model instead",
            "LTXVImgToVideoConditionOnly": "Use LTXVImgToVideo instead (different API in ComfyUI v0.27.0)",
        }
        for node_id, node in wf.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            assert class_type not in deprecated, f"{wf_path} node {node_id}: uses deprecated '{class_type}' — {deprecated[class_type]}"


# ============================================================================
# Level 2: Node Type Validation
# ============================================================================

class TestNodeTypes:
    """Check node types exist in ComfyUI object_info."""

    @pytest.fixture
    def object_info(self, object_info_cache):
        if object_info_cache is None:
            pytest.skip("No object_info cache found — run: python scripts/fetch_object_info.py --source local")
        return object_info_cache

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_all_node_types_exist(self, wf_path, object_info):
        """All class_types in the workflow should exist in object_info."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        with open(full_path) as f:
            wf = json.load(f)
        for node_id, node in wf.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            assert class_type in object_info, f"{wf_path} node {node_id}: '{class_type}' not found in object_info"

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_required_inputs_present(self, wf_path, object_info):
        """All required inputs from object_info should be present in the workflow."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        with open(full_path) as f:
            wf = json.load(f)
        for node_id, node in wf.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            if class_type not in object_info:
                continue
            required = object_info[class_type].get("input", {}).get("required", {})
            node_inputs = node.get("inputs", {})
            for req_name in required:
                assert req_name in node_inputs, f"{wf_path} node {node_id}.{req_name}: required input missing"


# ============================================================================
# Level 3: Model File Integrity
# ============================================================================

class TestModelFiles:
    """Check model files exist and are valid."""

    def _get_model_refs(self, workflows) -> Dict[str, Set[str]]:
        """Extract model file references from workflows."""
        refs = {}
        for wf in workflows.values():
            for node in wf.values():
                if not isinstance(node, dict):
                    continue
                for field, folder in MODEL_FIELD_NAMES.items():
                    val = node.get("inputs", {}).get(field)
                    if isinstance(val, str):
                        refs.setdefault(folder, set()).add(val)
        return refs

    def test_models_dir_exists(self, models_dir):
        """Models directory should exist."""
        if not models_dir.exists():
            pytest.skip(f"Models directory not found: {models_dir}")

    @pytest.mark.parametrize("wf_path", LTX25_WORKFLOWS)
    def test_model_files_exist(self, wf_path, models_dir):
        """All model files referenced in workflows should exist."""
        full_path = PROJECT_ROOT / wf_path
        if not full_path.exists():
            pytest.skip(f"Workflow not found: {wf_path}")
        if not models_dir.exists():
            pytest.skip(f"Models directory not found: {models_dir}")
        with open(full_path) as f:
            wf = json.load(f)
        for node_id, node in wf.items():
            if not isinstance(node, dict):
                continue
            for field, folder in MODEL_FIELD_NAMES.items():
                val = node.get("inputs", {}).get(field)
                if isinstance(val, str):
                    file_path = models_dir / folder / val
                    assert file_path.exists() or file_path.is_symlink(), \
                        f"{wf_path} node {node_id}.{field}: file not found: {file_path}"

    def test_safetensors_valid(self, models_dir, workflows):
        """All .safetensors model files should have valid headers."""
        if not models_dir.exists():
            pytest.skip(f"Models directory not found: {models_dir}")
        refs = self._get_model_refs(workflows)
        for folder, filenames in refs.items():
            for filename in filenames:
                if not filename.endswith(".safetensors"):
                    continue
                file_path = models_dir / folder / filename
                if not file_path.exists():
                    continue
                with open(file_path, "rb") as f:
                    header_len_bytes = f.read(8)
                    if len(header_len_bytes) < 8:
                        pytest.fail(f"{filename}: file too small")
                    header_len = struct.unpack("<Q", header_len_bytes)[0]
                    assert header_len < 100_000_000, f"{filename}: header length {header_len} is unreasonably large"
                    header_bytes = f.read(header_len)
                    assert len(header_bytes) == header_len, f"{filename}: file truncated"
                    header = json.loads(header_bytes)
                    assert isinstance(header, dict), f"{filename}: header is not a JSON object"


# ============================================================================
# Level 4: Config/Tokenizer Files
# ============================================================================

class TestConfigFiles:
    """Check config/tokenizer files in model directories."""

    def test_gemma_dir_has_all_files(self, models_dir):
        """The gemma4-12b-ltx-2.5 directory should have all required files."""
        gemma_dir = models_dir / "text_encoders" / "gemma4-12b-ltx-2.5"
        if not gemma_dir.exists():
            pytest.skip(f"Gemma directory not found: {gemma_dir}")
        for required_file in GEMMA_DIR_REQUIRED_FILES:
            file_path = gemma_dir / required_file
            assert file_path.exists() or file_path.is_symlink(), \
                f"Missing: {file_path}"
            if file_path.is_symlink():
                assert file_path.resolve().exists(), \
                    f"Broken symlink: {file_path} -> {os.readlink(file_path)}"


# ============================================================================
# Level 5: Custom Node Check
# ============================================================================

class TestCustomNodes:
    """Check custom nodes are installed."""

    def test_custom_nodes_dir_exists(self, models_dir):
        """Custom nodes directory should exist."""
        custom_nodes_dir = models_dir.parent / "custom_nodes"
        if not custom_nodes_dir.exists():
            custom_nodes_dir = Path("/comfyui/custom_nodes")
        if not custom_nodes_dir.exists():
            pytest.skip("Custom nodes directory not found")

    @pytest.mark.parametrize("node_name", REQUIRED_CUSTOM_NODES)
    def test_custom_node_installed(self, node_name, models_dir):
        """Required custom nodes should be installed."""
        custom_nodes_dir = models_dir.parent / "custom_nodes"
        if not custom_nodes_dir.exists():
            custom_nodes_dir = Path("/comfyui/custom_nodes")
        if not custom_nodes_dir.exists():
            pytest.skip("Custom nodes directory not found")
        node_path = custom_nodes_dir / node_name
        assert node_path.exists(), f"Custom node not found: {node_path}"
        assert (node_path / "__init__.py").exists(), f"Missing __init__.py: {node_path}"
