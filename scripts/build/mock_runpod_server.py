#!/usr/bin/env python3
"""
Mock RunPod Serverless API Server

Simulates the RunPod serverless API endpoints locally so you can test the
full frontend → proxy → "serverless" → ComfyUI stack without any cloud costs
or RunPod endpoint. The mock server accepts the same API calls as real RunPod
but routes them to a local ComfyUI instance.

This lets you:
  - Test the proxy server's protocol translation
  - Test the frontend's WebSocket event handling
  - Test workflow submission end-to-end
  - All on your local machine, 0 cloud cost

Architecture:
    Frontend (:5173) → Proxy (:8188) → Mock RunPod (:8080) → Local ComfyUI (:8188)

    Wait — that's a port conflict. Use different ports:
    Frontend (:5173) → Proxy (:8188) → Mock RunPod (:9090) → Local ComfyUI (:8188)

    Actually, local ComfyUI runs in Docker on :8188. The proxy also wants :8188.
    So we need to run the proxy on a different port when testing locally:

    Docker ComfyUI (:8188) ← Mock RunPod (:9090) ← Proxy (:8189) ← Frontend (:5173)

Usage:
    # 1. Start local ComfyUI in Docker
    ./scripts/build/run_local.sh

    # 2. Start mock RunPod server (routes to Docker ComfyUI on :8188)
    python scripts/build/mock_runpod_server.py

    # 3. Start proxy pointing at mock server
    RUNPOD_API_BASE=http://127.0.0.1:9090/v2 \
    RUNPOD_ENDPOINT_ID=local-test \
    RUNPOD_API_KEY=mock-key \
    PROXY_PORT=8189 \
    python src/proxy_server.py

    # 4. Start frontend pointing at proxy
    cd frontend && DEV_SERVER_COMFYUI_URL=http://127.0.0.1:8189 npm run dev

    # 5. Open http://localhost:5173

Or use the one-command script:
    ./scripts/build/frontend.sh --mock
"""

import asyncio
import json
import time
import uuid
import argparse
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logger = logging.getLogger("mock_runpod")

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_PORT = 9090
DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"

# ============================================================================
# State
# ============================================================================

# Maps job_id → {status, workflow, prompt_id, submitted_at, completed_at, output, error}
jobs: Dict[str, Dict[str, Any]] = {}

# Maps prompt_id → job_id (for looking up ComfyUI history)
prompt_to_job: Dict[str, str] = {}

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Mock RunPod Serverless API",
    description="Simulates RunPod serverless endpoints locally for testing",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# ComfyUI Client (async)
# ============================================================================

comfyui_url: str = DEFAULT_COMFYUI_URL
http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    return http_client


# ============================================================================
# RunPod API Endpoints (Mock)
# ============================================================================

@app.post("/v2/{endpoint_id}/run")
async def submit_job(endpoint_id: str, request: Request):
    """
    Mock RunPod POST /v2/{endpoint_id}/run
    Submits workflow to local ComfyUI and returns a job_id.
    """
    body = await request.json()
    job_input = body.get("input", {})
    workflow = job_input.get("workflow", {})
    input_images = job_input.get("input_images", {})

    if not workflow:
        raise HTTPException(status_code=400, detail="No workflow in input")

    job_id = str(uuid.uuid4())
    prompt_id = None

    logger.info(f"POST /run — job_id={job_id}, {len(workflow)} nodes")

    # Upload input images to ComfyUI if provided
    client = await get_http_client()
    if input_images:
        import base64
        for filename, img_b64 in input_images.items():
            try:
                img_bytes = base64.b64decode(img_b64)
                resp = await client.post(
                    f"{comfyui_url}/upload/image",
                    files={"image": (filename, img_bytes, "image/png")},
                    params={"overwrite": "true"},
                )
                logger.info(f"  Uploaded {filename} to ComfyUI")
            except Exception as e:
                logger.warning(f"  Failed to upload {filename}: {e}")

    # Submit to ComfyUI
    try:
        resp = await client.post(
            f"{comfyui_url}/prompt",
            json={"prompt": workflow},
        )
        resp.raise_for_status()
        data = resp.json()
        prompt_id = data.get("prompt_id")
        logger.info(f"  ComfyUI prompt_id={prompt_id}")
    except httpx.ConnectError:
        logger.error(f"  Cannot connect to ComfyUI at {comfyui_url}")
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to ComfyUI at {comfyui_url}. Is Docker running? ./scripts/build/run_local.sh"
        )
    except Exception as e:
        logger.error(f"  ComfyUI error: {e}")
        raise HTTPException(status_code=502, detail=f"ComfyUI error: {e}")

    # Store job
    jobs[job_id] = {
        "status": "IN_QUEUE",
        "workflow": workflow,
        "prompt_id": prompt_id,
        "submitted_at": datetime.now().isoformat(),
        "completed_at": None,
        "output": None,
        "error": None,
        "delay_time": None,
        "execution_time": None,
    }
    prompt_to_job[prompt_id] = job_id

    # Start background task to poll ComfyUI and update status
    asyncio.create_task(poll_comfyui(job_id, prompt_id))

    return {"id": job_id, "status": "IN_QUEUE"}


async def poll_comfyui(job_id: str, prompt_id: str):
    """Background task: poll ComfyUI for completion and update job status."""
    client = await get_http_client()
    start_time = time.time()

    # Simulate cold start delay (configurable)
    await asyncio.sleep(0.5)  # 500ms "cold start"

    jobs[job_id]["status"] = "IN_PROGRESS"
    jobs[job_id]["delay_time"] = int((time.time() - start_time) * 1000)

    while True:
        try:
            resp = await client.get(f"{comfyui_url}/history/{prompt_id}")
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                # Job completed
                prompt_history = history[prompt_id]
                status_info = prompt_history.get("status", {})

                # Extract outputs
                outputs = prompt_history.get("outputs", {})
                images = []
                for node_id, node_output in outputs.items():
                    for img in node_output.get("images", []):
                        # Fetch the actual image data from ComfyUI
                        img_filename = img.get("filename", "output.png")
                        img_subfolder = img.get("subfolder", "")
                        img_type = img.get("type", "output")

                        # Get image as base64
                        try:
                            img_resp = await client.get(
                                f"{comfyui_url}/view",
                                params={
                                    "filename": img_filename,
                                    "subfolder": img_subfolder,
                                    "type": img_type,
                                },
                            )
                            if img_resp.status_code == 200:
                                import base64
                                img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
                                images.append({
                                    "filename": img_filename,
                                    "node_id": node_id,
                                    "type": img_type,
                                    "data": img_b64,
                                })
                        except Exception as e:
                            logger.warning(f"  Failed to fetch image {img_filename}: {e}")
                            images.append({
                                "filename": img_filename,
                                "node_id": node_id,
                                "type": img_type,
                            })

                jobs[job_id]["status"] = "COMPLETED"
                jobs[job_id]["output"] = {
                    "status": "success",
                    "output": {
                        "images": images,
                        "prompt_id": prompt_id,
                    },
                    "metadata": {
                        "job_id": job_id,
                        "prompt_id": prompt_id,
                        "execution_time": round(time.time() - start_time, 2),
                    }
                }
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                jobs[job_id]["execution_time"] = int((time.time() - start_time) * 1000)

                logger.info(f"  Job {job_id} COMPLETED — {len(images)} images, {time.time()-start_time:.1f}s")
                return

        except Exception as e:
            logger.error(f"  Error polling ComfyUI for {prompt_id}: {e}")

        await asyncio.sleep(1)


@app.get("/v2/{endpoint_id}/status/{job_id}")
async def get_status(endpoint_id: str, job_id: str):
    """Mock RunPod GET /v2/{endpoint_id}/status/{job_id}"""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    response = {
        "id": job_id,
        "status": job["status"],
    }

    if job["delay_time"] is not None:
        response["delayTime"] = job["delay_time"]
    if job["execution_time"] is not None:
        response["executionTime"] = job["execution_time"]

    if job["status"] == "COMPLETED":
        response["output"] = job["output"]
    elif job["status"] in ("FAILED", "CANCELLED"):
        response["error"] = job.get("error", "Unknown error")

    return JSONResponse(response)


@app.post("/v2/{endpoint_id}/cancel/{job_id}")
async def cancel_job(endpoint_id: str, job_id: str):
    """Mock RunPod POST /v2/{endpoint_id}/cancel/{job_id}"""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Try to cancel in ComfyUI
    client = await get_http_client()
    prompt_id = job.get("prompt_id")
    if prompt_id:
        try:
            await client.post(f"{comfyui_url}/queue", json={"cancel": [prompt_id]})
        except Exception:
            pass

    job["status"] = "CANCELLED"
    logger.info(f"  Job {job_id} CANCELLED")
    return {"cancelled": True}


@app.get("/v2/{endpoint_id}/health")
async def health_check(endpoint_id: str):
    """Mock health check."""
    return {"status": "healthy", "endpoint": endpoint_id, "jobs": len(jobs)}


# ============================================================================
# Debug Endpoints
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "Mock RunPod Serverless API",
        "comfyui_url": comfyui_url,
        "jobs": len(jobs),
        "endpoints": {
            "submit": "POST /v2/{endpoint_id}/run",
            "status": "GET /v2/{endpoint_id}/status/{job_id}",
            "cancel": "POST /v2/{endpoint_id}/cancel/{job_id}",
        }
    }

@app.get("/debug/jobs")
async def debug_jobs():
    """List all jobs for debugging."""
    return JSONResponse({
        jid: {
            "status": j["status"],
            "prompt_id": j.get("prompt_id"),
            "submitted_at": j["submitted_at"],
            "completed_at": j.get("completed_at"),
            "has_output": bool(j.get("output")),
        }
        for jid, j in jobs.items()
    })

@app.delete("/debug/jobs")
async def clear_jobs():
    """Clear all jobs (for testing)."""
    jobs.clear()
    prompt_to_job.clear()
    return {"cleared": True}

# ============================================================================
# Main
# ============================================================================

def main():
    global comfyui_url

    parser = argparse.ArgumentParser(
        description="Mock RunPod Serverless API — routes to local ComfyUI for testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Setup:
  1. Start local ComfyUI:  ./scripts/build/run_local.sh
  2. Start mock server:    python scripts/build/mock_runpod_server.py
  3. Start proxy:          RUNPOD_API_BASE=http://127.0.0.1:9090/v2 \\
                           RUNPOD_ENDPOINT_ID=local-test \\
                           RUNPOD_API_KEY=mock-key \\
                           PROXY_PORT=8189 \\
                           python src/proxy_server.py
  4. Start frontend:       cd frontend && DEV_SERVER_COMFYUI_URL=http://127.0.0.1:8189 npm run dev
  5. Open:                 http://localhost:5173

Or use the one-command script:
  ./scripts/build/frontend.sh --mock
        """
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--comfyui-url", default=DEFAULT_COMFYUI_URL,
                        help=f"Local ComfyUI URL (default: {DEFAULT_COMFYUI_URL})")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    comfyui_url = args.comfyui_url.rstrip("/")

    # Check if ComfyUI is reachable
    logger.info(f"Mock RunPod Server starting on http://{args.host}:{args.port}")
    logger.info(f"  ComfyUI backend: {comfyui_url}")

    import requests
    try:
        resp = requests.get(f"{comfyui_url}/system_stats", timeout=5)
        if resp.status_code == 200:
            logger.info("  ✓ ComfyUI is reachable")
        else:
            logger.warning(f"  ⚠ ComfyUI returned {resp.status_code}")
    except requests.exceptions.ConnectionError:
        logger.warning(f"  ⚠ Cannot connect to ComfyUI at {comfyui_url}")
        logger.warning("  Start it with: ./scripts/build/run_local.sh")
        logger.warning("  (The mock server will still start, but jobs will fail)")

    logger.info(f"  Endpoints:")
    logger.info(f"    POST   /v2/{{endpoint_id}}/run")
    logger.info(f"    GET    /v2/{{endpoint_id}}/status/{{job_id}}")
    logger.info(f"    POST   /v2/{{endpoint_id}}/cancel/{{job_id}}")
    logger.info(f"    GET    /debug/jobs  (list all jobs)")
    logger.info(f"    DELETE /debug/jobs  (clear all jobs)")
    logger.info("")
    logger.info("  To use with proxy:")
    logger.info(f"    RUNPOD_API_BASE=http://{args.host}:{args.port}/v2 \\")
    logger.info(f"    RUNPOD_ENDPOINT_ID=local-test \\")
    logger.info(f"    RUNPOD_API_KEY=mock-key \\")
    logger.info(f"    PROXY_PORT=8189 \\")
    logger.info(f"    python src/proxy_server.py")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="debug" if args.debug else "info",
    )


if __name__ == "__main__":
    main()
