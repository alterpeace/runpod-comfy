"""
ComfyUI Frontend Proxy Server

Translates between the official ComfyUI Frontend (Vue.js, node-based UI) and
the RunPod Serverless API (job queue). The frontend expects a live ComfyUI
server with HTTP REST + WebSocket; RunPod Serverless exposes a submit/poll
job API. This proxy bridges the gap.

Architecture:
    ComfyUI Frontend (:5173) -> Vite dev proxy -> Proxy Server (:8188) -> RunPod API

The proxy implements:
  - REST endpoints: /object_info, /system_stats, /prompt, /history, /view, /upload/image
  - WebSocket endpoint: /ws (simulates execution events by polling RunPod status)

Usage:
    python src/proxy_server.py                    # start on :8188
    python src/proxy_server.py --port 9000        # custom port
    python src/proxy_server.py --debug            # verbose logging
    python src/proxy_server.py --backend local    # passthrough to local ComfyUI

Environment variables (see .env.example):
    RUNPOD_ENDPOINT_ID   - RunPod serverless endpoint ID
    RUNPOD_API_KEY       - RunPod API key
    PROXY_PORT           - Port to listen on (default: 8188)
    OBJECT_INFO_CACHE    - Path to cached object_info JSON
    PROXY_POLL_INTERVAL  - Seconds between status polls (default: 2)
    PROXY_UPLOAD_DIR     - Directory for uploaded images
    PROXY_DEBUG          - Enable verbose logging (default: false)
"""

import os
import sys
import json
import time
import uuid
import base64
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, Set
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import httpx
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File,
    Query, HTTPException, Request,
)
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logger = logging.getLogger("proxy_server")

# ============================================================================
# Configuration
# ============================================================================

def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

def get_env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default

def get_env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off", ""):
        return False if val else default
    return default

RUNPOD_ENDPOINT_ID = get_env("RUNPOD_ENDPOINT_ID", "")
RUNPOD_API_KEY = get_env("RUNPOD_API_KEY", "")
PROXY_PORT = get_env_int("PROXY_PORT", 8188)
OBJECT_INFO_CACHE = get_env("OBJECT_INFO_CACHE", "config/object_info_cache.json")
PROXY_POLL_INTERVAL = get_env_int("PROXY_POLL_INTERVAL", 2)
PROXY_UPLOAD_DIR = get_env("PROXY_UPLOAD_DIR", "./.local/input")
PROXY_DEBUG = get_env_bool("PROXY_DEBUG", False)

RUNPOD_API_BASE = get_env("RUNPOD_API_BASE", "https://api.runpod.ai/v2")

# ============================================================================
# State
# ============================================================================

# Maps prompt_id -> {job_id, status, workflow, output, submitted_at, completed_at}
job_store: Dict[str, Dict[str, Any]] = {}

# Cached object_info loaded from file
object_info_cache: Optional[dict] = None

# ============================================================================
# Logging
# ============================================================================

def setup_logging(debug: bool = False):
    level = logging.DEBUG if (debug or PROXY_DEBUG) else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

def dlog(msg: str):
    """Debug log for proxy translations."""
    if PROXY_DEBUG:
        logger.debug(f"[PROXY] {msg}")

# ============================================================================
# RunPod API Client
# ============================================================================

class RunPodClient:
    """Async client for RunPod Serverless API."""

    def __init__(self, endpoint_id: str, api_key: str):
        self.endpoint_id = endpoint_id
        self.api_key = api_key
        self.base_url = f"{RUNPOD_API_BASE}/{endpoint_id}"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        return self._client

    async def submit_job(self, workflow: dict, input_images: Optional[dict] = None) -> dict:
        """Submit a workflow to the RunPod serverless endpoint."""
        client = await self.get_client()
        payload: Dict[str, Any] = {"input": {"workflow": workflow}}
        if input_images:
            payload["input"]["input_images"] = input_images

        dlog(f"POST {self.base_url}/run - {len(workflow)} nodes")
        resp = await client.post(f"{self.base_url}/run", json=payload)
        resp.raise_for_status()
        data = resp.json()
        dlog(f"  -> job_id={data.get('id')}, status={data.get('status')}")
        return data

    async def get_status(self, job_id: str) -> dict:
        """Poll job status."""
        client = await self.get_client()
        dlog(f"GET {self.base_url}/status/{job_id}")
        resp = await client.get(f"{self.base_url}/status/{job_id}")
        resp.raise_for_status()
        return resp.json()

    async def cancel_job(self, job_id: str) -> dict:
        """Cancel a job."""
        client = await self.get_client()
        dlog(f"POST {self.base_url}/cancel/{job_id}")
        resp = await client.post(f"{self.base_url}/cancel/{job_id}")
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


runpod_client: Optional[RunPodClient] = None

def get_runpod_client() -> RunPodClient:
    global runpod_client
    if runpod_client is None:
        if not RUNPOD_ENDPOINT_ID:
            raise HTTPException(status_code=500, detail="RUNPOD_ENDPOINT_ID not configured")
        if not RUNPOD_API_KEY:
            raise HTTPException(status_code=500, detail="RUNPOD_API_KEY not configured")
        runpod_client = RunPodClient(RUNPOD_ENDPOINT_ID, RUNPOD_API_KEY)
    return runpod_client

# ============================================================================
# Object Info Cache
# ============================================================================

def load_object_info() -> dict:
    """Load cached object_info from file."""
    global object_info_cache
    if object_info_cache is not None:
        return object_info_cache

    cache_path = Path(OBJECT_INFO_CACHE)
    if cache_path.exists():
        with open(cache_path, "r") as f:
            object_info_cache = json.load(f)
        logger.info(f"Loaded object_info cache: {len(object_info_cache)} nodes from {cache_path}")
        return object_info_cache

    logger.warning(f"object_info cache not found at {cache_path}")
    logger.warning("Run: python scripts/build/fetch_object_info.py --source local|runpod")
    object_info_cache = {}
    return object_info_cache

# ============================================================================
# WebSocket Event Manager
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self):
        self.connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)
        dlog(f"WebSocket connected ({len(self.connections)} total)")

    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)
        dlog(f"WebSocket disconnected ({len(self.connections)} total)")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSocket clients."""
        text = json.dumps(message)
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        self.connections -= dead

manager = ConnectionManager()

async def poll_and_emit_events(prompt_id: str):
    """
    Background task: poll RunPod job status and emit WebSocket events
    that simulate ComfyUI execution progress.
    """
    job_entry = job_store.get(prompt_id)
    if not job_entry:
        return

    job_id = job_entry["job_id"]
    client = get_runpod_client()

    # Emit execution_start
    await manager.broadcast({
        "type": "execution_start",
        "data": {"prompt_id": prompt_id}
    })
    dlog(f"WS -> execution_start {{prompt_id: {prompt_id}}}")

    # Emit execution_cached (empty - no cache info from serverless)
    await manager.broadcast({
        "type": "execution_cached",
        "data": {"prompt_id": prompt_id, "nodes": []}
    })

    last_status = None
    start_time = time.time()

    while True:
        try:
            status_data = await client.get_status(job_id)
            status = status_data.get("status", "UNKNOWN")

            if status != last_status:
                dlog(f"Polling status... {status} (elapsed: {time.time()-start_time:.1f}s)")
                last_status = status

            if status == "IN_QUEUE":
                await manager.broadcast({
                    "type": "progress",
                    "data": {
                        "prompt_id": prompt_id,
                        "value": 0,
                        "max": 1,
                        "status": "queued",
                    }
                })

            elif status == "IN_PROGRESS":
                await manager.broadcast({
                    "type": "executing",
                    "data": {"prompt_id": prompt_id, "node": None}
                })

            elif status == "COMPLETED":
                output = status_data.get("output", {})
                job_entry["status"] = "COMPLETED"
                job_entry["output"] = output
                job_entry["completed_at"] = datetime.now().isoformat()

                images = output.get("images", [])
                for img in images:
                    node_id = img.get("node_id", "unknown")
                    filename = img.get("filename", "output.png")
                    await manager.broadcast({
                        "type": "executed",
                        "data": {
                            "prompt_id": prompt_id,
                            "node": str(node_id),
                            "output": {
                                "images": [{
                                    "filename": filename,
                                    "subfolder": img.get("subfolder", ""),
                                    "type": img.get("type", "output"),
                                }]
                            }
                        }
                    })
                    dlog(f"WS -> executed {{prompt_id: {prompt_id}, node: {node_id}}}")

                await manager.broadcast({
                    "type": "execution_success",
                    "data": {"prompt_id": prompt_id}
                })
                dlog(f"WS -> execution_success {{prompt_id: {prompt_id}}}")
                return

            elif status in ("FAILED", "CANCELLED", "ERROR", "TIMED_OUT"):
                job_entry["status"] = status
                job_entry["error"] = status_data.get("error", "Unknown error")
                job_entry["completed_at"] = datetime.now().isoformat()

                error_msg = status_data.get("error", f"Job {status}")
                await manager.broadcast({
                    "type": "execution_error",
                    "data": {
                        "prompt_id": prompt_id,
                        "exception_type": status,
                        "exception_message": str(error_msg),
                    }
                })
                dlog(f"WS -> execution_error {{prompt_id: {prompt_id}, error: {error_msg}}}")
                return

        except Exception as e:
            logger.error(f"Error polling job {job_id}: {e}")
            await manager.broadcast({
                "type": "execution_error",
                "data": {
                    "prompt_id": prompt_id,
                    "exception_type": "ProxyError",
                    "exception_message": str(e),
                }
            })
            return

        await asyncio.sleep(PROXY_POLL_INTERVAL)

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="ComfyUI Frontend Proxy",
    description="Translates ComfyUI Frontend API calls to RunPod Serverless API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------------
# ComfyUI REST API Endpoints
# ----------------------------------------------------------------------------

@app.get("/")
async def root():
    """Root endpoint - returns basic info."""
    return {
        "status": "ok",
        "proxy": "ComfyUI Frontend Proxy",
        "backend": "runpod" if RUNPOD_ENDPOINT_ID else "not-configured",
        "endpoint_id": RUNPOD_ENDPOINT_ID or "(not set)",
        "websocket": "/ws",
    }

@app.get("/object_info")
async def get_object_info():
    """Return cached object_info for node palette rendering."""
    cache = load_object_info()
    return JSONResponse(cache)

@app.get("/object_info/{node_class}")
async def get_object_info_node(node_class: str):
    """Return object_info for a specific node class."""
    cache = load_object_info()
    if node_class in cache:
        return JSONResponse({node_class: cache[node_class]})
    raise HTTPException(status_code=404, detail=f"Node class '{node_class}' not found")

@app.get("/system_stats")
async def system_stats():
    """Return synthetic system stats (frontend expects this)."""
    return {
        "system": {
            "os": "runpod-serverless-proxy",
            "ram_total": 0,
            "ram_free": 0,
            "comfyui_version": "0.0.0-proxy",
            "python_version": sys.version.split()[0],
        },
        "devices": [
            {
                "name": "RunPod Serverless (remote)",
                "type": "GPU",
                "index": 0,
                "vram_total": 0,
                "vram_free": 0,
                "torch_vram_total": 0,
                "torch_vram_free": 0,
            }
        ],
    }

@app.get("/prompt")
async def get_prompt_info():
    """Return empty prompt info (frontend uses this for queue display)."""
    active = [j for j in job_store.values()
              if j["status"] not in ("COMPLETED", "FAILED", "CANCELLED")]
    return {
        "node_errors": {},
        "exec_info": {
            "queue_remaining": len(active),
        }
    }

@app.post("/prompt")
async def submit_prompt(request: Request):
    """
    Submit a workflow for execution.
    Translates to: POST https://api.runpod.ai/v2/{endpoint_id}/run
    """
    body = await request.json()
    workflow = body.get("prompt", body)
    client_data = body.get("client_id", str(uuid.uuid4()))

    if not workflow or not isinstance(workflow, dict):
        raise HTTPException(status_code=400, detail="Invalid workflow: must be a non-empty dict")

    dlog(f"POST /prompt - {len(workflow)} nodes, client_id={client_data}")

    # Check for uploaded images that need to be included
    input_images = {}
    upload_dir = Path(PROXY_UPLOAD_DIR)
    if upload_dir.exists():
        for img_file in upload_dir.iterdir():
            if img_file.is_file() and img_file.suffix in (".png", ".jpg", ".jpeg", ".webp"):
                with open(img_file, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                input_images[img_file.name] = img_b64

    client = get_runpod_client()
    try:
        result = await client.submit_job(
            workflow, input_images=input_images if input_images else None
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"RunPod API error: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail=f"RunPod API error: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to submit job: {e}")

    job_id = result.get("id")
    if not job_id:
        raise HTTPException(status_code=502, detail=f"RunPod did not return job ID: {result}")

    prompt_id = str(uuid.uuid4())

    job_store[prompt_id] = {
        "job_id": job_id,
        "status": result.get("status", "IN_QUEUE"),
        "workflow": workflow,
        "output": None,
        "submitted_at": datetime.now().isoformat(),
        "completed_at": None,
        "client_id": client_data,
    }

    dlog(f"  -> job_id={job_id}, prompt_id={prompt_id}")

    asyncio.create_task(poll_and_emit_events(prompt_id))

    return {"prompt_id": prompt_id, "number": len(job_store)}

@app.get("/history")
async def get_history():
    """Return all completed jobs in ComfyUI history format."""
    history = {}
    for prompt_id, job in job_store.items():
        if job["status"] == "COMPLETED" and job.get("output"):
            history[prompt_id] = _translate_history_entry(prompt_id, job)
    return JSONResponse(history)

@app.get("/history/{prompt_id}")
async def get_history_prompt(prompt_id: str):
    """Return history for a specific prompt. Polls RunPod if still pending."""
    job = job_store.get(prompt_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown prompt_id: {prompt_id}")

    if job["status"] not in ("COMPLETED", "FAILED", "CANCELLED"):
        client = get_runpod_client()
        try:
            status_data = await client.get_status(job["job_id"])
            status = status_data.get("status", "UNKNOWN")
            job["status"] = status
            if status == "COMPLETED":
                job["output"] = status_data.get("output", {})
                job["completed_at"] = datetime.now().isoformat()
            elif status in ("FAILED", "CANCELLED", "ERROR", "TIMED_OUT"):
                job["error"] = status_data.get("error", "Unknown error")
        except Exception as e:
            logger.error(f"Error polling job {job['job_id']}: {e}")

    if job["status"] == "COMPLETED" and job.get("output"):
        return JSONResponse({prompt_id: _translate_history_entry(prompt_id, job)})
    elif job["status"] in ("FAILED", "CANCELLED", "ERROR", "TIMED_OUT"):
        return JSONResponse({prompt_id: {"status": job["status"], "error": job.get("error", "")}})
    else:
        return JSONResponse({})

def _translate_history_entry(prompt_id: str, job: dict) -> dict:
    """Translate RunPod output to ComfyUI history format."""
    output = job.get("output", {})
    images = output.get("images", [])

    outputs_by_node: Dict[str, dict] = {}
    for img in images:
        node_id = str(img.get("node_id", "unknown"))
        if node_id not in outputs_by_node:
            outputs_by_node[node_id] = {"images": []}
        outputs_by_node[node_id]["images"].append({
            "filename": img.get("filename", "output.png"),
            "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output"),
        })

    return {
        "prompt": job.get("workflow", []),
        "outputs": outputs_by_node,
        "status": {
            "status_str": job["status"],
            "completed": True,
            "messages": [],
        },
        "meta": {
            "prompt_id": prompt_id,
            "job_id": job["job_id"],
        }
    }

@app.get("/view")
async def view_image(
    filename: str = Query(...),
    subfolder: str = Query(""),
    type: str = Query("output"),
    preview: Optional[str] = Query(None),
):
    """
    Serve an image to the frontend.
    In serverless mode, images are returned as base64 in the job output.
    We store them temporarily and serve them here.
    """
    for prompt_id, job in job_store.items():
        if job.get("output"):
            for img in job["output"].get("images", []):
                if img.get("filename") == filename:
                    if img.get("data"):
                        img_bytes = base64.b64decode(img["data"])
                        return Response(content=img_bytes, media_type="image/png")
                    if img.get("url"):
                        return JSONResponse(
                            {"url": img["url"]},
                            status_code=302,
                            headers={"Location": img["url"]}
                        )

    local_path = Path(PROXY_UPLOAD_DIR) / filename
    if local_path.exists():
        return FileResponse(str(local_path), media_type="image/png")

    raise HTTPException(status_code=404, detail=f"Image not found: {filename}")

@app.post("/upload/image")
async def upload_image(
    image: UploadFile = File(...),
    overwrite: bool = Query(False),
    type: str = Query("input"),
):
    """
    Upload an image for use in img2img workflows.
    Stored locally and included as base64 in the next job payload.
    """
    upload_dir = Path(PROXY_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = image.filename or "upload.png"
    file_path = upload_dir / filename

    if file_path.exists() and not overwrite:
        return {"name": filename, "subfolder": "", "type": type}

    content = await image.read()
    with open(file_path, "wb") as f:
        f.write(content)

    dlog(f"Uploaded image: {filename} ({len(content)} bytes)")

    return {
        "name": filename,
        "subfolder": "",
        "type": type,
    }

@app.get("/queue")
async def get_queue():
    """Return synthetic queue info."""
    running = [
        {"prompt_id": pid, "number": i + 1, "batch_size": 1}
        for i, (pid, j) in enumerate(job_store.items())
        if j["status"] == "IN_PROGRESS"
    ]
    pending = [
        {"prompt_id": pid, "number": i + 1, "batch_size": 1}
        for i, (pid, j) in enumerate(job_store.items())
        if j["status"] == "IN_QUEUE"
    ]

    return {
        "queue_running": running,
        "queue_pending": pending,
    }

@app.post("/queue")
async def cancel_queue(request: Request):
    """Cancel a job."""
    body = await request.json()
    prompt_id = body.get("prompt_id", "")

    job = job_store.get(prompt_id)
    if not job:
        return {"error": "Unknown prompt_id"}

    client = get_runpod_client()
    try:
        await client.cancel_job(job["job_id"])
        job["status"] = "CANCELLED"
        dlog(f"Cancelled job {job['job_id']} (prompt_id={prompt_id})")
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")

    return {"success": True}

@app.get("/api/userdata")
async def get_userdata():
    """Return empty user data (frontend expects this)."""
    return JSONResponse({})

@app.get("/api/extensions")
async def get_extensions():
    """Return empty extensions list."""
    return JSONResponse([])

@app.get("/api/settings")
async def get_settings():
    """Return minimal settings."""
    return JSONResponse({})

@app.post("/api/settings")
async def set_settings():
    """No-op settings update."""
    return JSONResponse({"status": "ok"})

@app.get("/api/upload/metadata")
async def get_upload_metadata():
    """Return empty upload metadata."""
    return JSONResponse({})

# ----------------------------------------------------------------------------
# WebSocket Endpoint
# ----------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint that simulates ComfyUI execution events.
    The frontend connects here and listens for execution_start, executing,
    executed, execution_success, execution_error messages.
    """
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            dlog(f"WS recv: {data}")
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        dlog(f"WS error: {e}")
        manager.disconnect(ws)

# ----------------------------------------------------------------------------
# Health & Debug
# ----------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "backend": "runpod" if RUNPOD_ENDPOINT_ID else "not-configured",
        "endpoint_id": RUNPOD_ENDPOINT_ID or "(not set)",
        "jobs": len(job_store),
        "connections": len(manager.connections),
    }

@app.get("/debug/jobs")
async def debug_jobs():
    """Debug endpoint: list all jobs."""
    return JSONResponse({
        pid: {
            "job_id": j["job_id"],
            "status": j["status"],
            "submitted_at": j["submitted_at"],
            "completed_at": j.get("completed_at"),
            "has_output": bool(j.get("output")),
        }
        for pid, j in job_store.items()
    })

# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ComfyUI Frontend Proxy Server - translates ComfyUI API to RunPod Serverless"
    )
    parser.add_argument("--port", type=int, default=PROXY_PORT,
                        help=f"Port to listen on (default: {PROXY_PORT})")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    setup_logging(args.debug)

    if not RUNPOD_ENDPOINT_ID:
        logger.warning("RUNPOD_ENDPOINT_ID not set - proxy will fail on /prompt submissions")
        logger.warning("Set it in .env: RUNPOD_ENDPOINT_ID=your-endpoint-id")
    if not RUNPOD_API_KEY:
        logger.warning("RUNPOD_API_KEY not set - proxy will fail on /prompt submissions")
        logger.warning("Set it in .env: RUNPOD_API_KEY=your-api-key")

    cache_path = Path(OBJECT_INFO_CACHE)
    if not cache_path.exists():
        logger.warning(f"object_info cache not found at {cache_path}")
        logger.warning("Node palette will be empty. Run: python scripts/build/fetch_object_info.py --source local")
    else:
        logger.info(f"object_info cache: {cache_path}")

    Path(PROXY_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting ComfyUI Frontend Proxy on http://{args.host}:{args.port}")
    logger.info(f"  Backend: RunPod Serverless (endpoint: {RUNPOD_ENDPOINT_ID or 'NOT SET'})")
    logger.info(f"  WebSocket: ws://{args.host}:{args.port}/ws")
    logger.info(f"  Debug: {'ON' if (args.debug or PROXY_DEBUG) else 'OFF'}")
    logger.info(f"  Frontend: open http://localhost:5173 (after starting frontend dev server)")

    uvicorn.run(
        "proxy_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="debug" if (args.debug or PROXY_DEBUG) else "info",
    )

if __name__ == "__main__":
    main()
