"""
Unit tests for the debug_workflow.py script.

Tests cover:
- Workflow validation (valid, invalid, edge cases)
- Node graph visualization
- Input patching (--set-input parsing and application)
- Output extraction (local and RunPod formats)
- Node validation against object_info cache
"""

import json
import base64
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Import the debug_workflow module
import importlib.util

spec = importlib.util.spec_from_file_location(
    "debug_workflow",
    Path(__file__).parent.parent / "scripts" / "debug_workflow.py"
)
debug_workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(debug_workflow)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_workflow():
    """Load the example text_to_image workflow."""
    workflow_path = Path(__file__).parent.parent / "examples" / "text_to_image_simple.json"
    with open(workflow_path) as f:
        return json.load(f)


@pytest.fixture
def sample_object_info():
    """Minimal object_info cache."""
    return {
        "KSampler": {"input": {"required": {"seed": ["INT", {"default": 0}]}}, "name": "KSampler"},
        "CheckpointLoaderSimple": {"input": {"required": {}}, "name": "CheckpointLoaderSimple"},
        "EmptyLatentImage": {"input": {"required": {}}, "name": "EmptyLatentImage"},
        "CLIPTextEncode": {"input": {"required": {}}, "name": "CLIPTextEncode"},
        "VAEDecode": {"input": {"required": {}}, "name": "VAEDecode"},
        "SaveImage": {"input": {"required": {}}, "name": "SaveImage"},
    }


# ============================================================================
# Workflow Validation Tests
# ============================================================================

class TestValidateWorkflow:
    """Tests for validate_workflow function."""

    def test_valid_workflow(self, sample_workflow):
        is_valid, errors = debug_workflow.validate_workflow(sample_workflow)
        assert is_valid is True
        assert errors == []

    def test_empty_workflow(self):
        is_valid, errors = debug_workflow.validate_workflow({})
        assert is_valid is False
        assert "cannot be empty" in errors[0]

    def test_not_dict(self):
        is_valid, errors = debug_workflow.validate_workflow("not a dict")
        assert is_valid is False
        assert "must be a dictionary" in errors[0]

    def test_not_dict_list(self):
        is_valid, errors = debug_workflow.validate_workflow([1, 2, 3])
        assert is_valid is False
        assert "must be a dictionary" in errors[0]

    def test_no_numeric_keys(self):
        workflow = {"not_a_node": {"class_type": "Test", "inputs": {}}}
        is_valid, errors = debug_workflow.validate_workflow(workflow)
        assert is_valid is False
        assert "at least one node" in errors[0]

    def test_missing_class_type(self):
        workflow = {"1": {"inputs": {}}}
        is_valid, errors = debug_workflow.validate_workflow(workflow)
        assert is_valid is False
        assert any("class_type" in e for e in errors)

    def test_missing_inputs(self):
        workflow = {"1": {"class_type": "Test"}}
        is_valid, errors = debug_workflow.validate_workflow(workflow)
        assert is_valid is False
        assert any("inputs" in e for e in errors)

    def test_node_not_dict(self):
        workflow = {"1": "not a dict"}
        is_valid, errors = debug_workflow.validate_workflow(workflow)
        assert is_valid is False
        assert any("must be a dictionary" in e for e in errors)

    def test_invalid_reference(self):
        workflow = {
            "1": {
                "class_type": "Test",
                "inputs": {"model": ["99", 0]}  # node 99 doesn't exist
            }
        }
        is_valid, errors = debug_workflow.validate_workflow(workflow)
        assert is_valid is False
        assert any("references node" in e for e in errors)

    def test_valid_reference(self):
        workflow = {
            "1": {"class_type": "Source", "inputs": {}},
            "2": {"class_type": "Consumer", "inputs": {"src": ["1", 0]}}
        }
        is_valid, errors = debug_workflow.validate_workflow(workflow)
        assert is_valid is True


# ============================================================================
# Node Cache Validation Tests
# ============================================================================

class TestValidateNodesAgainstCache:
    """Tests for validate_nodes_against_cache function."""

    def test_all_nodes_in_cache(self, sample_workflow, sample_object_info, tmp_path):
        cache_file = tmp_path / "cache.json"
        with open(cache_file, "w") as f:
            json.dump(sample_object_info, f)

        warnings = debug_workflow.validate_nodes_against_cache(
            sample_workflow, str(cache_file)
        )
        assert warnings == []

    def test_unknown_node_in_cache(self, tmp_path):
        workflow = {"1": {"class_type": "UnknownNode", "inputs": {}}}
        cache = {"KnownNode": {"name": "KnownNode"}}
        cache_file = tmp_path / "cache.json"
        with open(cache_file, "w") as f:
            json.dump(cache, f)

        warnings = debug_workflow.validate_nodes_against_cache(
            workflow, str(cache_file)
        )
        assert len(warnings) == 1
        assert "UnknownNode" in warnings[0]

    def test_missing_cache_file(self, tmp_path):
        workflow = {"1": {"class_type": "Test", "inputs": {}}}
        warnings = debug_workflow.validate_nodes_against_cache(
            workflow, str(tmp_path / "nonexistent.json")
        )
        assert len(warnings) == 1
        assert "not found" in warnings[0]


# ============================================================================
# Input Patching Tests
# ============================================================================

class TestParseSetInput:
    """Tests for parse_set_input function."""

    def test_parse_equals_format(self):
        node_id, field, value = debug_workflow.parse_set_input("6.text=hello world")
        assert node_id == "6"
        assert field == "text"
        assert value == "hello world"

    def test_parse_space_format(self):
        node_id, field, value = debug_workflow.parse_set_input("3.seed 999")
        assert node_id == "3"
        assert field == "seed"
        assert value == 999  # parsed as int

    def test_parse_float_value(self):
        node_id, field, value = debug_workflow.parse_set_input("3.cfg=7.5")
        assert node_id == "3"
        assert field == "cfg"
        assert value == 7.5

    def test_parse_int_value(self):
        node_id, field, value = debug_workflow.parse_set_input("3.steps=30")
        assert node_id == "3"
        assert field == "steps"
        assert value == 30

    def test_parse_string_value(self):
        node_id, field, value = debug_workflow.parse_set_input("6.text=a beautiful landscape")
        assert node_id == "6"
        assert field == "text"
        assert value == "a beautiful landscape"

    def test_parse_no_dot_raises(self):
        with pytest.raises(ValueError, match="Invalid --set-input"):
            debug_workflow.parse_set_input("invalid")

    def test_parse_no_separator_raises(self):
        with pytest.raises(ValueError, match="Invalid --set-input format"):
            debug_workflow.parse_set_input("6.text")


class TestApplyInputPatches:
    """Tests for apply_input_patches function."""

    def test_apply_single_patch(self, sample_workflow):
        patches = ["6.text=a cat sitting on a chair"]
        debug_workflow.apply_input_patches(sample_workflow, patches)
        assert sample_workflow["6"]["inputs"]["text"] == "a cat sitting on a chair"

    def test_apply_multiple_patches(self, sample_workflow):
        patches = ["6.text=a cat", "3.seed=999", "3.steps=30"]
        debug_workflow.apply_input_patches(sample_workflow, patches)
        assert sample_workflow["6"]["inputs"]["text"] == "a cat"
        assert sample_workflow["3"]["inputs"]["seed"] == 999
        assert sample_workflow["3"]["inputs"]["steps"] == 30

    def test_apply_patch_to_nonexistent_node(self, sample_workflow):
        patches = ["99.text=hello"]
        # Should not crash, just print a warning
        debug_workflow.apply_input_patches(sample_workflow, patches)
        # Workflow unchanged
        assert "99" not in sample_workflow

    def test_apply_patch_creates_inputs_if_missing(self):
        workflow = {"1": {"class_type": "Test"}}
        patches = ["1.new_field=value"]
        debug_workflow.apply_input_patches(workflow, patches)
        assert workflow["1"]["inputs"]["new_field"] == "value"


# ============================================================================
# Output Extraction Tests
# ============================================================================

class TestExtractOutputs:
    """Tests for extract_outputs function."""

    def test_extract_local_format(self, tmp_path):
        result = {
            "outputs": {
                "9": {"images": [{"filename": "out.png", "type": "output"}]}
            }
        }
        images = debug_workflow.extract_outputs(result, "local", None, verbose=False)
        assert len(images) == 1
        assert images[0]["filename"] == "out.png"
        assert images[0]["node_id"] == "9"

    def test_extract_runpod_format(self):
        result = {
            "output": {
                "images": [
                    {"filename": "out.png", "node_id": "9", "data": "base64data"}
                ]
            }
        }
        images = debug_workflow.extract_outputs(result, "runpod", None, verbose=False)
        assert len(images) == 1
        assert images[0]["filename"] == "out.png"
        assert images[0]["data"] == "base64data"

    def test_extract_and_save_to_disk(self, tmp_path):
        img_bytes = b"\x89PNG fake png"
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        result = {
            "output": {
                "images": [
                    {"filename": "test.png", "node_id": "9", "data": img_b64}
                ]
            }
        }
        output_dir = str(tmp_path / "outputs")
        images = debug_workflow.extract_outputs(result, "runpod", output_dir, verbose=False)

        saved_file = Path(output_dir) / "test.png"
        assert saved_file.exists()
        assert saved_file.read_bytes() == img_bytes

    def test_extract_empty_output(self):
        result = {"output": {"images": []}}
        images = debug_workflow.extract_outputs(result, "runpod", None, verbose=False)
        assert images == []


# ============================================================================
# Node Graph Tests
# ============================================================================

class TestPrintNodeGraph:
    """Tests for print_node_graph function."""

    def test_print_graph_does_not_crash(self, sample_workflow, capsys):
        debug_workflow.print_node_graph(sample_workflow)
        captured = capsys.readouterr()
        assert "Node Graph" in captured.out
        assert "KSampler" in captured.out
        assert "CheckpointLoaderSimple" in captured.out

    def test_print_graph_shows_references(self, capsys):
        workflow = {
            "1": {"class_type": "Source", "inputs": {}},
            "2": {"class_type": "Consumer", "inputs": {"src": ["1", 0]}}
        }
        debug_workflow.print_node_graph(workflow)
        captured = capsys.readouterr()
        assert "← [1:0]" in captured.out
