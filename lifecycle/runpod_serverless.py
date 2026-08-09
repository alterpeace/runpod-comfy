#!/usr/bin/env python3
"""
RunPod Serverless Endpoint Management CLI

Manage RunPod Serverless endpoints with commands for create, update, delete,
invoke, status, and list operations.
"""

import argparse
import json
import os
import sys
import time
from typing import Optional, Dict, Any

try:
    import runpod
except ImportError:
    print("ERROR: runpod SDK not installed. Install with: uv add runpod")
    sys.exit(1)


class ServerlessManager:
    """Manage RunPod Serverless endpoint operations."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize serverless manager with API key."""
        self.api_key = api_key or os.environ.get("RUNPOD_API_KEY")
        if not self.api_key:
            print("ERROR: RUNPOD_API_KEY not found in environment or arguments")
            print("Set it with: export RUNPOD_API_KEY=your_key_here")
            sys.exit(1)
        
        runpod.api_key = self.api_key
    
    def create_endpoint(
        self,
        name: str,
        gpu_type: str,
        image: str,
        min_workers: int = 0,
        max_workers: int = 3,
        idle_timeout: int = 5,
        volume_id: Optional[str] = None,
        volume_mount_path: str = "/runpod-volume",
        env_vars: Optional[Dict[str, str]] = None,
        json_output: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new serverless endpoint.
        
        Args:
            name: Endpoint name
            gpu_type: GPU type (e.g., "RTX A4000", "RTX 4090")
            image: Docker image URL
            min_workers: Minimum workers (0 = scale to zero)
            max_workers: Maximum workers for auto-scaling
            idle_timeout: Minutes before scaling down idle workers
            volume_id: Network volume ID to attach
            volume_mount_path: Where to mount the volume
            env_vars: Environment variables dict
            json_output: Output as JSON
        
        Returns:
            Endpoint creation response
        """
        # Estimate costs
        estimated_per_execution = self._estimate_execution_cost(gpu_type)
        
        if not json_output:
            print(f"\n{'='*60}")
            print(f"Creating Serverless Endpoint: {name}")
            print(f"{'='*60}")
            print(f"GPU Type: {gpu_type}")
            print(f"Image: {image}")
            print(f"Workers: {min_workers} min, {max_workers} max")
            print(f"Idle Timeout: {idle_timeout} minutes")
            print(f"\nEstimated Cost:")
            print(f"  Per execution (1 min): ~${estimated_per_execution:.4f}")
            print(f"  Per hour (60 exec): ~${estimated_per_execution * 60:.2f}")
            print(f"  Per day (1440 exec): ~${estimated_per_execution * 1440:.2f}")
            print(f"\n💡 Serverless = Pay only for execution time")
            print(f"{'='*60}\n")
            
            confirm = input("Continue? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return {"status": "cancelled"}
        
        # Prepare endpoint configuration
        endpoint_config = {
            "name": name,
            "imageName": image,
            "gpuTypeId": gpu_type,
            "scalerType": "QUEUE_DELAY",
            "scalerValue": idle_timeout,
            "workersMin": min_workers,
            "workersMax": max_workers,
        }
        
        # Add network volume if specified
        if volume_id:
            endpoint_config["volumeMountPath"] = volume_mount_path
            endpoint_config["networkVolumeId"] = volume_id
        
        # Add environment variables
        if env_vars:
            endpoint_config["env"] = [{"key": k, "value": v} for k, v in env_vars.items()]
        
        try:
            # Create endpoint using RunPod API
            response = runpod.create_endpoint(**endpoint_config)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"\n✅ Endpoint created successfully!")
                print(f"Endpoint ID: {response.get('id', 'N/A')}")
                print(f"Status: {response.get('status', 'N/A')}")
                print(f"\nInvoke with:")
                print(f"  python runpod_serverless.py invoke --endpoint-id {response.get('id', 'N/A')} --workflow workflow.json")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"\n❌ Error creating endpoint: {e}")
            return {"error": str(e)}
    
    def update_endpoint(
        self,
        endpoint_id: str,
        min_workers: Optional[int] = None,
        max_workers: Optional[int] = None,
        idle_timeout: Optional[int] = None,
        json_output: bool = False
    ) -> Dict[str, Any]:
        """Update endpoint configuration."""
        if not json_output:
            print(f"Updating endpoint: {endpoint_id}")
        
        update_config = {}
        if min_workers is not None:
            update_config["workersMin"] = min_workers
        if max_workers is not None:
            update_config["workersMax"] = max_workers
        if idle_timeout is not None:
            update_config["scalerValue"] = idle_timeout
        
        try:
            response = runpod.update_endpoint(endpoint_id, **update_config)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"✅ Endpoint updated successfully")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error updating endpoint: {e}")
            return {"error": str(e)}
    
    def delete_endpoint(self, endpoint_id: str, json_output: bool = False) -> Dict[str, Any]:
        """Delete a serverless endpoint."""
        if not json_output:
            print(f"\n{'='*60}")
            print(f"Deleting Endpoint: {endpoint_id}")
            print(f"{'='*60}")
            print(f"This will permanently delete the endpoint.")
            print(f"{'='*60}\n")
            
            confirm = input("Continue? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return {"status": "cancelled"}
        
        try:
            response = runpod.delete_endpoint(endpoint_id)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"✅ Endpoint deleted successfully")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error deleting endpoint: {e}")
            return {"error": str(e)}
    
    def invoke_endpoint(
        self,
        endpoint_id: str,
        workflow_file: Optional[str] = None,
        workflow_json: Optional[str] = None,
        wait: bool = False,
        timeout: int = 300,
        json_output: bool = False
    ) -> Dict[str, Any]:
        """
        Invoke a serverless endpoint with a workflow.
        
        Args:
            endpoint_id: Endpoint ID
            workflow_file: Path to workflow JSON file
            workflow_json: Workflow JSON string
            wait: Wait for completion
            timeout: Timeout in seconds (if wait=True)
            json_output: Output as JSON
        
        Returns:
            Job response
        """
        # Load workflow
        if workflow_file:
            with open(workflow_file, 'r') as f:
                workflow = json.load(f)
        elif workflow_json:
            workflow = json.loads(workflow_json)
        else:
            if not json_output:
                print("ERROR: Must provide --workflow or --workflow-json")
            return {"error": "No workflow provided"}
        
        if not json_output:
            print(f"Invoking endpoint: {endpoint_id}")
            if wait:
                print(f"Waiting for completion (timeout: {timeout}s)...")
        
        try:
            # Submit job
            endpoint = runpod.Endpoint(endpoint_id)
            job = endpoint.run({"input": {"workflow": workflow}})
            
            if not json_output:
                print(f"Job ID: {job.job_id}")
            
            if wait:
                # Poll for completion
                start_time = time.time()
                while True:
                    status = job.status()
                    
                    if status in ["COMPLETED", "FAILED"]:
                        result = job.output()
                        
                        if json_output:
                            print(json.dumps(result, indent=2))
                        else:
                            print(f"\n✅ Job completed")
                            print(f"Status: {status}")
                            print(f"Output: {json.dumps(result, indent=2)}")
                        
                        return result
                    
                    if time.time() - start_time > timeout:
                        if json_output:
                            print(json.dumps({"error": "Timeout"}, indent=2))
                        else:
                            print(f"\n❌ Timeout waiting for job")
                        return {"error": "Timeout"}
                    
                    if not json_output:
                        print(f"Status: {status}... ", end="\r")
                    
                    time.sleep(2)
            else:
                result = {"job_id": job.job_id, "status": "SUBMITTED"}
                
                if json_output:
                    print(json.dumps(result, indent=2))
                else:
                    print(f"✅ Job submitted")
                    print(f"Check status with: python runpod_serverless.py status --job-id {job.job_id}")
                
                return result
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error invoking endpoint: {e}")
            return {"error": str(e)}
    
    def get_job_status(self, endpoint_id: str, job_id: str, json_output: bool = False) -> Dict[str, Any]:
        """Get the status of a specific job via the RunPod REST API."""
        import urllib.request
        import urllib.error

        url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                response = json.loads(resp.read().decode())

            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Job Status: {job_id}")
                print(f"{'='*60}")
                print(f"Status: {response.get('status', 'N/A')}")
                if response.get('delayTime') is not None:
                    print(f"Queue delay: {response['delayTime']/1000:.1f}s")
                if response.get('executionTime') is not None:
                    print(f"Execution time: {response['executionTime']/1000:.1f}s")
                if response.get('error'):
                    print(f"Error: {response['error']}")
                output = response.get('output')
                if output is not None:
                    rendered = json.dumps(output, indent=2)
                    print(f"Output: {rendered[:2000]}")
                print(f"{'='*60}\n")

            return response

        except urllib.error.HTTPError as e:
            result = {"error": f"HTTP {e.code}: {e.read().decode()[:500]}"}
        except Exception as e:
            result = {"error": str(e)}

        if json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"❌ Error getting job status: {result['error']}")
        return result

    def get_endpoint_status(self, endpoint_id: str, json_output: bool = False) -> Dict[str, Any]:
        """Get endpoint status and metrics."""
        try:
            # runpod SDK v1.7+ only has get_endpoints() (plural), not get_endpoint()
            all_endpoints = runpod.get_endpoints()
            response = None
            for ep in all_endpoints:
                if ep.get("id") == endpoint_id:
                    response = ep
                    break
            if response is None:
                response = {"error": f"Endpoint {endpoint_id} not found"}
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Endpoint Status: {endpoint_id}")
                print(f"{'='*60}")
                print(f"Name: {response.get('name', 'N/A')}")
                print(f"Status: {response.get('status', 'N/A')}")
                print(f"Workers: {response.get('workersMin', 0)} min, {response.get('workersMax', 0)} max")
                print(f"Active Workers: {response.get('workersRunning', 0)}")
                print(f"GPU: {response.get('gpuTypeId', 'N/A')}")
                print(f"{'='*60}\n")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error getting endpoint status: {e}")
            return {"error": str(e)}
    
    def list_endpoints(self, json_output: bool = False) -> list:
        """List all serverless endpoints."""
        try:
            response = runpod.get_endpoints()
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Your RunPod Serverless Endpoints")
                print(f"{'='*60}\n")
                
                if not response:
                    print("No endpoints found.")
                else:
                    for endpoint in response:
                        name = endpoint.get('name', 'N/A')
                        endpoint_id = endpoint.get('id', 'N/A')
                        status = endpoint.get('status', 'UNKNOWN')
                        gpu = endpoint.get('gpuTypeId', 'N/A')
                        workers = endpoint.get('workersRunning', 0)
                        
                        print(f"Endpoint: {name}")
                        print(f"  ID: {endpoint_id}")
                        print(f"  Status: {status}")
                        print(f"  GPU: {gpu}")
                        print(f"  Active Workers: {workers}")
                        print()
                
                print(f"{'='*60}\n")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error listing endpoints: {e}")
            return []
    
    def _estimate_execution_cost(self, gpu_type: str) -> float:
        """Estimate cost per minute of execution."""
        # Rough estimates (actual prices vary)
        gpu_costs_per_min = {
            "RTX A4000": 0.01,
            "RTX 4090": 0.015,
            "RTX A5000": 0.012,
            "RTX A6000": 0.018,
            "A100 40GB": 0.025,
            "A100 80GB": 0.033,
        }
        
        return gpu_costs_per_min.get(gpu_type, 0.01)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RunPod Serverless Endpoint Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a serverless endpoint
  python runpod_serverless.py create --name comfyui-api --gpu "RTX A4000" \\
      --image ghcr.io/user/comfyui-serverless:latest

  # Create with network volume
  python runpod_serverless.py create --name comfyui-api --gpu "RTX A4000" \\
      --image ghcr.io/user/comfyui-serverless:latest --volume-id abc123

  # Invoke endpoint with workflow
  python runpod_serverless.py invoke --endpoint-id xyz789 \\
      --workflow examples/text_to_image_simple.json

  # Invoke and wait for completion
  python runpod_serverless.py invoke --endpoint-id xyz789 \\
      --workflow workflow.json --wait

  # Check endpoint status
  python runpod_serverless.py status --endpoint-id xyz789

  # List all endpoints
  python runpod_serverless.py list

  # Delete endpoint
  python runpod_serverless.py delete --endpoint-id xyz789

  # JSON output for scripting
  python runpod_serverless.py list --json
        """
    )
    
    parser.add_argument("--api-key", help="RunPod API key (or set RUNPOD_API_KEY env var)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new endpoint")
    create_parser.add_argument("--name", required=True, help="Endpoint name")
    create_parser.add_argument("--gpu", required=True, help="GPU type (e.g., 'RTX A4000')")
    create_parser.add_argument("--image", required=True, help="Docker image URL")
    create_parser.add_argument("--min-workers", type=int, default=0, help="Minimum workers (default: 0)")
    create_parser.add_argument("--max-workers", type=int, default=3, help="Maximum workers (default: 3)")
    create_parser.add_argument("--idle-timeout", type=int, default=5, help="Idle timeout in minutes (default: 5)")
    create_parser.add_argument("--volume-id", help="Network volume ID to attach")
    create_parser.add_argument("--volume-mount", default="/runpod-volume", help="Volume mount path")
    create_parser.add_argument("--env", action="append", help="Environment variable (KEY=VALUE)")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update endpoint configuration")
    update_parser.add_argument("--endpoint-id", required=True, help="Endpoint ID")
    update_parser.add_argument("--min-workers", type=int, help="Minimum workers")
    update_parser.add_argument("--max-workers", type=int, help="Maximum workers")
    update_parser.add_argument("--idle-timeout", type=int, help="Idle timeout in minutes")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete an endpoint")
    delete_parser.add_argument("--endpoint-id", required=True, help="Endpoint ID")
    
    # Invoke command
    invoke_parser = subparsers.add_parser("invoke", help="Invoke endpoint with workflow")
    invoke_parser.add_argument("--endpoint-id", required=True, help="Endpoint ID")
    invoke_parser.add_argument("--workflow", help="Path to workflow JSON file")
    invoke_parser.add_argument("--workflow-json", help="Workflow JSON string")
    invoke_parser.add_argument("--wait", action="store_true", help="Wait for completion")
    invoke_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get endpoint status, or job status with --job-id")
    status_parser.add_argument("--endpoint-id", required=True, help="Endpoint ID")
    status_parser.add_argument("--job-id", help="Job ID (returns job status instead of endpoint status)")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all endpoints")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Initialize manager
    manager = ServerlessManager(api_key=args.api_key)
    
    # Execute command
    if args.command == "create":
        env_vars = {}
        if args.env:
            for env_pair in args.env:
                if "=" in env_pair:
                    key, value = env_pair.split("=", 1)
                    env_vars[key] = value
        
        manager.create_endpoint(
            name=args.name,
            gpu_type=args.gpu,
            image=args.image,
            min_workers=args.min_workers,
            max_workers=args.max_workers,
            idle_timeout=args.idle_timeout,
            volume_id=args.volume_id,
            volume_mount_path=args.volume_mount,
            env_vars=env_vars if env_vars else None,
            json_output=args.json
        )
    
    elif args.command == "update":
        manager.update_endpoint(
            endpoint_id=args.endpoint_id,
            min_workers=args.min_workers,
            max_workers=args.max_workers,
            idle_timeout=args.idle_timeout,
            json_output=args.json
        )
    
    elif args.command == "delete":
        manager.delete_endpoint(args.endpoint_id, json_output=args.json)
    
    elif args.command == "invoke":
        manager.invoke_endpoint(
            endpoint_id=args.endpoint_id,
            workflow_file=args.workflow,
            workflow_json=args.workflow_json,
            wait=args.wait,
            timeout=args.timeout,
            json_output=args.json
        )
    
    elif args.command == "status":
        if getattr(args, "job_id", None):
            manager.get_job_status(args.endpoint_id, args.job_id, json_output=args.json)
        else:
            manager.get_endpoint_status(args.endpoint_id, json_output=args.json)
    
    elif args.command == "list":
        manager.list_endpoints(json_output=args.json)


if __name__ == "__main__":
    main()
