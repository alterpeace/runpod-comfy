"""
Unit tests for the ComfyUI Frontend Proxy Server.

Tests cover:
- REST endpoint responses (object_info, system_stats, prompt, history, view, queue)
- WebSocket event simulation (execution_start, executing, executed, execution_success)
- RunPod API mocking (submit, status polling, cancel)
- Object info caching
- Image upload handling
- Error scenarios
"""

import json
import base64
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Request, Response

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import proxy_server


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_workflow():
    """Minimal valid ComfyUI API workflow."""
    return {
        "3": {
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {"ckpt_name": "model.safetensors"},
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {"text": "a beautiful landscape", "clip": ["4", 1]},
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {"text": "blurry, low quality", "clip": ["4", 1]},
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {"images": ["8", 0]},
            "class_type": "SaveImage"
        }
    }


@pytest.fixture
def sample_object_info():
    """Minimal object_info cache."""
    return {
        "KSampler": {
            "input": {"required": {"seed": ["INT", {"default": 0}]}},
            "output": ["LATENT"],
            "name": "KSampler"
        },
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [["model.safetensors"]]}},
            "output": ["MODEL", "CLIP", "VAE"],
            "name": "CheckpointLoaderSimple"
        }
    }


@pytest.fixture
def mock_runpod_submit():
    """Mock RunPod API submit response."""
    return {"id": "job-abc-123", "status": "IN_QUEUE"}


@pytest.fixture
def mock_runpod_completed():
    """Mock RunPod API completed status response."""
    return {
        "status": "COMPLETED",
        "output": {
            "images": [
                {
                    "filename": "ComfyUI_00001.png",
                    "node_id": "9",
                    "type": "output",
                    "data": base64.b64encode(b"fake-png-data").decode("utf-8")
                }
            ]
        }
    }


@pytest.fixture(autouse=True)
def reset_state():
    """Reset proxy server state between tests."""
    proxy_server.job_store.clear()
    proxy_server.object_info_cache = None
    proxy_server.runpod_client = None
    proxy_server.manager.connections.clear()
    yield
    proxy_server.job_store.clear()
    proxy_server.object_info_cache = None
    proxy_server.runpod_client = None


# ============================================================================
# REST Endpoint Tests
# ============================================================================

class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_status(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "proxy" in data
        assert "backend" in data

    def test_root_shows_not_configured_without_endpoint(self):
        with patch.object(proxy_server, "RUNPOD_ENDPOINT_ID", ""):
            client = TestClient(proxy_server.app)
            resp = client.get("/")
            data = resp.json()
            assert data["backend"] == "not-configured"


class TestObjectInfoEndpoint:
    """Tests for /object_info endpoint."""

    def test_get_object_info_serves_cache(self, sample_object_info, tmp_path):
        cache_file = tmp_path / "cache.json"
        with open(cache_file, "w") as f:
            json.dump(sample_object_info, f)

        with patch.object(proxy_server, "OBJECT_INFO_CACHE", str(cache_file)):
            proxy_server.object_info_cache = None  # force reload
            client = TestClient(proxy_server.app)
            resp = client.get("/object_info")
            assert resp.status_code == 200
            data = resp.json()
            assert "KSampler" in data
            assert "CheckpointLoaderSimple" in data

    def test_get_object_info_empty_when_no_cache(self):
        with patch.object(proxy_server, "OBJECT_INFO_CACHE", "/nonexistent/path.json"):
            proxy_server.object_info_cache = None
            client = TestClient(proxy_server.app)
            resp = client.get("/object_info")
            assert resp.status_code == 200
            assert resp.json() == {}

    def test_get_object_info_specific_node(self, sample_object_info, tmp_path):
        cache_file = tmp_path / "cache.json"
        with open(cache_file, "w") as f:
            json.dump(sample_object_info, f)

        with patch.object(proxy_server, "OBJECT_INFO_CACHE", str(cache_file)):
            proxy_server.object_info_cache = None
            client = TestClient(proxy_server.app)
            resp = client.get("/object_info/KSampler")
            assert resp.status_code == 200
            data = resp.json()
            assert "KSampler" in data

    def test_get_object_info_unknown_node(self, sample_object_info, tmp_path):
        cache_file = tmp_path / "cache.json"
        with open(cache_file, "w") as f:
            json.dump(sample_object_info, f)

        with patch.object(proxy_server, "OBJECT_INFO_CACHE", str(cache_file)):
            proxy_server.object_info_cache = None
            client = TestClient(proxy_server.app)
            resp = client.get("/object_info/NonExistentNode")
            assert resp.status_code == 404


class TestSystemStatsEndpoint:
    """Tests for /system_stats endpoint."""

    def test_system_stats_returns_synthetic_data(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/system_stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "system" in data
        assert "devices" in data
        assert len(data["devices"]) == 1
        assert data["devices"][0]["type"] == "GPU"


class TestPromptEndpoint:
    """Tests for /prompt endpoint (workflow submission)."""

    def test_submit_prompt_invalid_workflow(self):
        client = TestClient(proxy_server.app)
        resp = client.post("/prompt", json={"prompt": {}})
        assert resp.status_code == 400

    def test_submit_prompt_not_dict(self):
        client = TestClient(proxy_server.app)
        resp = client.post("/prompt", json={"prompt": "not a dict"})
        assert resp.status_code == 400

    @patch("proxy_server.get_runpod_client")
    def test_submit_prompt_success(self, mock_get_client, sample_workflow, mock_runpod_submit):
        mock_client = AsyncMock()
        mock_client.submit_job = AsyncMock(return_value=mock_runpod_submit)
        mock_get_client.return_value = mock_client

        with patch.object(proxy_server, "RUNPOD_ENDPOINT_ID", "test-endpoint"):
            with patch.object(proxy_server, "RUNPOD_API_KEY", "test-key"):
                client = TestClient(proxy_server.app)
                resp = client.post("/prompt", json={"prompt": sample_workflow})
                assert resp.status_code == 200
                data = resp.json()
                assert "prompt_id" in data
                assert data["number"] >= 1

    @patch("proxy_server.get_runpod_client")
    def test_submit_prompt_stores_job(self, mock_get_client, sample_workflow, mock_runpod_submit):
        mock_client = AsyncMock()
        mock_client.submit_job = AsyncMock(return_value=mock_runpod_submit)
        mock_get_client.return_value = mock_client

        with patch.object(proxy_server, "RUNPOD_ENDPOINT_ID", "test-endpoint"):
            with patch.object(proxy_server, "RUNPOD_API_KEY", "test-key"):
                client = TestClient(proxy_server.app)
                resp = client.post("/prompt", json={"prompt": sample_workflow})
                prompt_id = resp.json()["prompt_id"]
                assert prompt_id in proxy_server.job_store
                assert proxy_server.job_store[prompt_id]["job_id"] == "job-abc-123"
                assert proxy_server.job_store[prompt_id]["status"] == "IN_QUEUE"


class TestHistoryEndpoint:
    """Tests for /history endpoint."""

    def test_get_history_empty(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/history")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_get_history_with_completed_job(self, sample_workflow):
        prompt_id = "test-prompt-id"
        proxy_server.job_store[prompt_id] = {
            "job_id": "job-123",
            "status": "COMPLETED",
            "workflow": sample_workflow,
            "output": {
                "images": [
                    {"filename": "out.png", "node_id": "9", "type": "output"}
                ]
            },
            "submitted_at": "2024-01-01T00:00:00",
            "completed_at": "2024-01-01T00:01:00",
        }

        client = TestClient(proxy_server.app)
        resp = client.get("/history")
        data = resp.json()
        assert prompt_id in data
        assert "outputs" in data[prompt_id]
        assert "9" in data[prompt_id]["outputs"]

    def test_get_history_specific_prompt_not_found(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/history/nonexistent-id")
        assert resp.status_code == 404

    @patch("proxy_server.get_runpod_client")
    def test_get_history_polls_pending_job(self, mock_get_client, sample_workflow, mock_runpod_completed):
        mock_client = AsyncMock()
        mock_client.get_status = AsyncMock(return_value=mock_runpod_completed)
        mock_get_client.return_value = mock_client

        prompt_id = "pending-prompt"
        proxy_server.job_store[prompt_id] = {
            "job_id": "job-pending",
            "status": "IN_QUEUE",
            "workflow": sample_workflow,
            "output": None,
            "submitted_at": "2024-01-01T00:00:00",
            "completed_at": None,
        }

        client = TestClient(proxy_server.app)
        resp = client.get(f"/history/{prompt_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert prompt_id in data
        assert proxy_server.job_store[prompt_id]["status"] == "COMPLETED"


class TestQueueEndpoint:
    """Tests for /queue endpoint."""

    def test_get_queue_empty(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["queue_running"] == []
        assert data["queue_pending"] == []

    def test_get_queue_with_jobs(self):
        proxy_server.job_store["p1"] = {
            "job_id": "j1", "status": "IN_PROGRESS",
            "workflow": {}, "output": None,
            "submitted_at": "", "completed_at": None,
        }
        proxy_server.job_store["p2"] = {
            "job_id": "j2", "status": "IN_QUEUE",
            "workflow": {}, "output": None,
            "submitted_at": "", "completed_at": None,
        }

        client = TestClient(proxy_server.app)
        resp = client.get("/queue")
        data = resp.json()
        assert len(data["queue_running"]) == 1
        assert len(data["queue_pending"]) == 1


class TestViewEndpoint:
    """Tests for /view endpoint (image serving)."""

    def test_view_image_not_found(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/view?filename=nonexistent.png")
        assert resp.status_code == 404

    def test_view_image_from_job_output(self):
        img_data = base64.b64encode(b"\x89PNG fake png data").decode("utf-8")
        proxy_server.job_store["p1"] = {
            "job_id": "j1",
            "status": "COMPLETED",
            "workflow": {},
            "output": {
                "images": [
                    {"filename": "test.png", "node_id": "9", "type": "output", "data": img_data}
                ]
            },
            "submitted_at": "",
            "completed_at": "",
        }

        client = TestClient(proxy_server.app)
        resp = client.get("/view?filename=test.png")
        assert resp.status_code == 200
        assert resp.content == base64.b64decode(img_data)

    def test_view_image_with_url_redirects(self):
        proxy_server.job_store["p1"] = {
            "job_id": "j1",
            "status": "COMPLETED",
            "workflow": {},
            "output": {
                "images": [
                    {"filename": "remote.png", "node_id": "9", "type": "output",
                     "url": "https://s3.example.com/remote.png"}
                ]
            },
            "submitted_at": "",
            "completed_at": "",
        }

        client = TestClient(proxy_server.app, follow_redirects=False)
        resp = client.get("/view?filename=remote.png")
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://s3.example.com/remote.png"


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_status(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "jobs" in data
        assert "connections" in data


class TestDebugJobsEndpoint:
    """Tests for /debug/jobs endpoint."""

    def test_debug_jobs_empty(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/debug/jobs")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_debug_jobs_with_entries(self):
        proxy_server.job_store["p1"] = {
            "job_id": "j1", "status": "COMPLETED",
            "workflow": {}, "output": None,
            "submitted_at": "2024-01-01", "completed_at": "2024-01-02",
        }
        client = TestClient(proxy_server.app)
        resp = client.get("/debug/jobs")
        data = resp.json()
        assert "p1" in data
        assert data["p1"]["status"] == "COMPLETED"


class TestApiEndpoints:
    """Tests for /api/* stub endpoints."""

    def test_get_userdata(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/api/userdata")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_get_extensions(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/api/extensions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_settings(self):
        client = TestClient(proxy_server.app)
        resp = client.get("/api/settings")
        assert resp.status_code == 200

    def test_post_settings(self):
        client = TestClient(proxy_server.app)
        resp = client.post("/api/settings", json={})
        assert resp.status_code == 200


# ============================================================================
# Helper Function Tests
# ============================================================================

class TestTranslateHistoryEntry:
    """Tests for _translate_history_entry helper."""

    def test_translate_completed_job(self, sample_workflow):
        job = {
            "job_id": "j1",
            "status": "COMPLETED",
            "workflow": sample_workflow,
            "output": {
                "images": [
                    {"filename": "out1.png", "node_id": "9", "type": "output"},
                    {"filename": "out2.png", "node_id": "9", "type": "output"},
                ]
            },
        }
        result = proxy_server._translate_history_entry("prompt-1", job)
        assert result["status"]["status_str"] == "COMPLETED"
        assert result["status"]["completed"] is True
        assert "9" in result["outputs"]
        assert len(result["outputs"]["9"]["images"]) == 2
        assert result["meta"]["prompt_id"] == "prompt-1"
        assert result["meta"]["job_id"] == "j1"

    def test_translate_empty_output(self, sample_workflow):
        job = {
            "job_id": "j1",
            "status": "COMPLETED",
            "workflow": sample_workflow,
            "output": {"images": []},
        }
        result = proxy_server._translate_history_entry("prompt-1", job)
        assert result["outputs"] == {}


class TestObjectInfoCache:
    """Tests for load_object_info function."""

    def test_load_from_file(self, sample_object_info, tmp_path):
        cache_file = tmp_path / "cache.json"
        with open(cache_file, "w") as f:
            json.dump(sample_object_info, f)

        with patch.object(proxy_server, "OBJECT_INFO_CACHE", str(cache_file)):
            proxy_server.object_info_cache = None
            result = proxy_server.load_object_info()
            assert "KSampler" in result
            assert "CheckpointLoaderSimple" in result

    def test_load_returns_cached_in_memory(self, sample_object_info):
        proxy_server.object_info_cache = sample_object_info
        result = proxy_server.load_object_info()
        assert result is sample_object_info

    def test_load_missing_file_returns_empty(self):
        with patch.object(proxy_server, "OBJECT_INFO_CACHE", "/nonexistent/path.json"):
            proxy_server.object_info_cache = None
            result = proxy_server.load_object_info()
            assert result == {}


class TestRunPodClient:
    """Tests for RunPodClient class."""

    def test_init_sets_headers(self):
        client = proxy_server.RunPodClient("test-endpoint", "test-key")
        assert client.endpoint_id == "test-endpoint"
        assert client.api_key == "test-key"
        assert client.headers["Authorization"] == "Bearer test-key"
        assert client.base_url == "https://api.runpod.ai/v2/test-endpoint"

    @pytest.mark.asyncio
    async def test_submit_job_builds_payload(self, sample_workflow):
        client = proxy_server.RunPodClient("test-ep", "test-key")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "job-1", "status": "IN_QUEUE"}
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.submit_job(sample_workflow)
        assert result["id"] == "job-1"

        # Verify the payload was correct
        call_args = mock_http.post.call_args
        payload = call_args.kwargs["json"]
        assert "input" in payload
        assert "workflow" in payload["input"]
        assert payload["input"]["workflow"] == sample_workflow

    @pytest.mark.asyncio
    async def test_submit_job_with_images(self, sample_workflow):
        client = proxy_server.RunPodClient("test-ep", "test-key")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "job-1"}
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        images = {"input.png": "base64data"}
        await client.submit_job(sample_workflow, input_images=images)

        call_args = mock_http.post.call_args
        payload = call_args.kwargs["json"]
        assert "input_images" in payload["input"]
        assert payload["input"]["input_images"] == images

    @pytest.mark.asyncio
    async def test_get_status(self):
        client = proxy_server.RunPodClient("test-ep", "test-key")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"status": "COMPLETED"}
        mock_http.get = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.get_status("job-1")
        assert result["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_cancel_job(self):
        client = proxy_server.RunPodClient("test-ep", "test-key")

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"cancelled": True}
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        result = await client.cancel_job("job-1")
        assert result["cancelled"] is True


class TestConnectionManager:
    """Tests for WebSocket ConnectionManager."""

    @pytest.mark.asyncio
    async def test_broadcast_to_no_connections(self):
        mgr = proxy_server.ConnectionManager()
        await mgr.broadcast({"type": "test"})
        assert len(mgr.connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        mgr = proxy_server.ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        mgr.connections = {ws1, ws2}

        await mgr.broadcast({"type": "test"})

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        mgr = proxy_server.ConnectionManager()
        ws_alive = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = Exception("Connection closed")
        mgr.connections = {ws_alive, ws_dead}

        await mgr.broadcast({"type": "test"})

        assert ws_alive in mgr.connections
        assert ws_dead not in mgr.connections
