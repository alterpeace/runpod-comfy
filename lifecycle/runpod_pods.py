#!/usr/bin/env python3
"""
RunPod Pods Lifecycle Management CLI

Manage RunPod Pods (persistent servers) with commands for create, start, stop,
terminate, status, and list operations.

WARNING: Stopping a pod does NOT stop billing! You must TERMINATE to stop charges.
"""

import argparse
import json
import os
import sys
from typing import Optional, Dict, Any

try:
    import runpod
except ImportError:
    print("ERROR: runpod SDK not installed. Install with: uv add runpod")
    sys.exit(1)


class PodManager:
    """Manage RunPod Pods lifecycle operations."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize pod manager with API key."""
        self.api_key = api_key or os.environ.get("RUNPOD_API_KEY")
        if not self.api_key:
            print("ERROR: RUNPOD_API_KEY not found in environment or arguments")
            print("Set it with: export RUNPOD_API_KEY=your_key_here")
            sys.exit(1)
        
        runpod.api_key = self.api_key
    
    def create_pod(
        self,
        name: str,
        gpu_type: str,
        image: str,
        spot: bool = True,
        volume_id: Optional[str] = None,
        volume_mount_path: str = "/runpod-volume",
        env_vars: Optional[Dict[str, str]] = None,
        ports: Optional[str] = None,
        json_output: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new RunPod pod.
        
        Args:
            name: Pod name
            gpu_type: GPU type (e.g., "RTX A4000", "RTX 4090")
            image: Docker image URL
            spot: Use spot instance (cheaper but can be interrupted)
            volume_id: Network volume ID to attach
            volume_mount_path: Where to mount the volume
            env_vars: Environment variables dict
            ports: Comma-separated ports to expose (e.g., "8188/http,22/tcp")
            json_output: Output as JSON
        
        Returns:
            Pod creation response
        """
        # Estimate costs
        instance_type = "spot" if spot else "on-demand"
        estimated_hourly = self._estimate_cost(gpu_type, spot)
        
        if not json_output:
            print(f"\n{'='*60}")
            print(f"Creating Pod: {name}")
            print(f"{'='*60}")
            print(f"GPU Type: {gpu_type}")
            print(f"Instance Type: {instance_type}")
            print(f"Image: {image}")
            print(f"Estimated Cost: ${estimated_hourly:.2f}/hour")
            print(f"Daily (24h): ${estimated_hourly * 24:.2f}")
            print(f"Monthly (30d): ${estimated_hourly * 24 * 30:.2f}")
            print(f"\n⚠️  WARNING: Stopping a pod does NOT stop billing!")
            print(f"⚠️  You must TERMINATE the pod to stop charges.")
            print(f"{'='*60}\n")
            
            confirm = input("Continue? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return {"status": "cancelled"}
        
        # Prepare pod configuration
        pod_config = {
            "name": name,
            "imageName": image,
            "gpuTypeId": gpu_type,
            "cloudType": "SECURE" if spot else "COMMUNITY",
            "volumeInGb": 50,  # Container disk size
        }
        
        # Add network volume if specified
        if volume_id:
            pod_config["volumeMountPath"] = volume_mount_path
            pod_config["networkVolumeId"] = volume_id
        
        # Add environment variables
        if env_vars:
            pod_config["env"] = [{"key": k, "value": v} for k, v in env_vars.items()]
        
        # Add ports
        if ports:
            port_list = []
            for port_spec in ports.split(","):
                port_spec = port_spec.strip()
                if "/" in port_spec:
                    port, protocol = port_spec.split("/")
                    port_list.append({
                        "port": int(port),
                        "protocol": protocol.upper()
                    })
            pod_config["ports"] = port_list
        
        try:
            # Create pod using RunPod API
            response = runpod.create_pod(**pod_config)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"\n✅ Pod created successfully!")
                print(f"Pod ID: {response.get('id', 'N/A')}")
                print(f"Status: {response.get('desiredStatus', 'N/A')}")
                if 'machine' in response:
                    print(f"Machine: {response['machine'].get('gpuDisplayName', 'N/A')}")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"\n❌ Error creating pod: {e}")
            return {"error": str(e)}
    
    def start_pod(self, pod_id: str, json_output: bool = False) -> Dict[str, Any]:
        """Start a stopped pod."""
        if not json_output:
            print(f"Starting pod: {pod_id}")
            print("⚠️  Billing will resume when pod starts.")
        
        try:
            response = runpod.start_pod(pod_id)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"✅ Pod start initiated")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error starting pod: {e}")
            return {"error": str(e)}
    
    def stop_pod(self, pod_id: str, json_output: bool = False) -> Dict[str, Any]:
        """
        Stop a running pod.
        
        WARNING: This does NOT stop billing! Use terminate to stop charges.
        """
        if not json_output:
            print(f"\n{'='*60}")
            print(f"⚠️  WARNING: STOPPING DOES NOT STOP BILLING!")
            print(f"{'='*60}")
            print(f"Stopping a pod pauses it but you continue to be charged.")
            print(f"To stop billing, use 'terminate' instead.")
            print(f"{'='*60}\n")
            
            confirm = input("Continue with stop? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return {"status": "cancelled"}
        
        try:
            response = runpod.stop_pod(pod_id)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"✅ Pod stop initiated")
                print(f"⚠️  Remember: You are still being charged!")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error stopping pod: {e}")
            return {"error": str(e)}
    
    def terminate_pod(self, pod_id: str, json_output: bool = False) -> Dict[str, Any]:
        """
        Terminate (delete) a pod. This stops billing.
        
        Network volumes remain intact and can be reattached to new pods.
        """
        if not json_output:
            print(f"\n{'='*60}")
            print(f"Terminating Pod: {pod_id}")
            print(f"{'='*60}")
            print(f"This will DELETE the pod and STOP billing.")
            print(f"Network volumes will remain intact.")
            print(f"{'='*60}\n")
            
            confirm = input("Continue? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return {"status": "cancelled"}
        
        try:
            response = runpod.terminate_pod(pod_id)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"✅ Pod terminated successfully")
                print(f"Billing has stopped for this pod.")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error terminating pod: {e}")
            return {"error": str(e)}
    
    def get_pod_status(self, pod_id: str, json_output: bool = False) -> Dict[str, Any]:
        """Get detailed status of a pod."""
        try:
            response = runpod.get_pod(pod_id)
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Pod Status: {pod_id}")
                print(f"{'='*60}")
                print(f"Name: {response.get('name', 'N/A')}")
                print(f"Status: {response.get('desiredStatus', 'N/A')}")
                print(f"Runtime: {response.get('runtime', {}).get('uptimeInSeconds', 0) / 3600:.2f} hours")
                
                if 'machine' in response:
                    machine = response['machine']
                    print(f"GPU: {machine.get('gpuDisplayName', 'N/A')}")
                    print(f"Cost/hour: ${machine.get('costPerHr', 0):.2f}")
                
                if 'networkVolume' in response:
                    vol = response['networkVolume']
                    print(f"Volume: {vol.get('name', 'N/A')} ({vol.get('size', 0)} GB)")
                
                print(f"{'='*60}\n")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error getting pod status: {e}")
            return {"error": str(e)}
    
    def list_pods(self, json_output: bool = False) -> list:
        """List all pods."""
        try:
            response = runpod.get_pods()
            
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Your RunPod Pods")
                print(f"{'='*60}\n")
                
                if not response:
                    print("No pods found.")
                else:
                    for pod in response:
                        status = pod.get('desiredStatus', 'UNKNOWN')
                        name = pod.get('name', 'N/A')
                        pod_id = pod.get('id', 'N/A')
                        gpu = pod.get('machine', {}).get('gpuDisplayName', 'N/A')
                        cost = pod.get('machine', {}).get('costPerHr', 0)
                        
                        print(f"Pod: {name}")
                        print(f"  ID: {pod_id}")
                        print(f"  Status: {status}")
                        print(f"  GPU: {gpu}")
                        print(f"  Cost: ${cost:.2f}/hour")
                        print()
                
                print(f"{'='*60}\n")
            
            return response
        
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"❌ Error listing pods: {e}")
            return []
    
    def _estimate_cost(self, gpu_type: str, spot: bool) -> float:
        """Estimate hourly cost for a GPU type."""
        # Rough estimates (actual prices vary)
        gpu_costs = {
            "RTX A4000": 0.40 if spot else 0.80,
            "RTX 4090": 0.60 if spot else 1.20,
            "RTX A5000": 0.50 if spot else 1.00,
            "RTX A6000": 0.70 if spot else 1.40,
            "A100 40GB": 1.50 if spot else 3.00,
            "A100 80GB": 2.00 if spot else 4.00,
        }
        
        return gpu_costs.get(gpu_type, 0.50 if spot else 1.00)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RunPod Pods Lifecycle Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a spot instance pod
  python runpod_pods.py create --name comfyui-dev --gpu "RTX A4000" --spot \\
      --image ghcr.io/user/comfyui-serverless:latest

  # Create with network volume
  python runpod_pods.py create --name comfyui-dev --gpu "RTX A4000" \\
      --volume-id abc123 --spot

  # Check pod status
  python runpod_pods.py status --pod-id xyz789

  # List all pods
  python runpod_pods.py list

  # Terminate pod (stops billing)
  python runpod_pods.py terminate --pod-id xyz789

  # JSON output for scripting
  python runpod_pods.py list --json
        """
    )
    
    parser.add_argument("--api-key", help="RunPod API key (or set RUNPOD_API_KEY env var)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new pod")
    create_parser.add_argument("--name", required=True, help="Pod name")
    create_parser.add_argument("--gpu", required=True, help="GPU type (e.g., 'RTX A4000')")
    create_parser.add_argument("--image", required=True, help="Docker image URL")
    create_parser.add_argument("--spot", action="store_true", help="Use spot instance (cheaper)")
    create_parser.add_argument("--volume-id", help="Network volume ID to attach")
    create_parser.add_argument("--volume-mount", default="/runpod-volume", help="Volume mount path")
    create_parser.add_argument("--env", action="append", help="Environment variable (KEY=VALUE)")
    create_parser.add_argument("--ports", help="Ports to expose (e.g., '8188/http,22/tcp')")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start a stopped pod")
    start_parser.add_argument("--pod-id", required=True, help="Pod ID")
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop a running pod (billing continues!)")
    stop_parser.add_argument("--pod-id", required=True, help="Pod ID")
    
    # Terminate command
    term_parser = subparsers.add_parser("terminate", help="Terminate pod (stops billing)")
    term_parser.add_argument("--pod-id", required=True, help="Pod ID")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get pod status")
    status_parser.add_argument("--pod-id", required=True, help="Pod ID")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all pods")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Initialize manager
    manager = PodManager(api_key=args.api_key)
    
    # Execute command
    if args.command == "create":
        env_vars = {}
        if args.env:
            for env_pair in args.env:
                if "=" in env_pair:
                    key, value = env_pair.split("=", 1)
                    env_vars[key] = value
        
        manager.create_pod(
            name=args.name,
            gpu_type=args.gpu,
            image=args.image,
            spot=args.spot,
            volume_id=args.volume_id,
            volume_mount_path=args.volume_mount,
            env_vars=env_vars if env_vars else None,
            ports=args.ports,
            json_output=args.json
        )
    
    elif args.command == "start":
        manager.start_pod(args.pod_id, json_output=args.json)
    
    elif args.command == "stop":
        manager.stop_pod(args.pod_id, json_output=args.json)
    
    elif args.command == "terminate":
        manager.terminate_pod(args.pod_id, json_output=args.json)
    
    elif args.command == "status":
        manager.get_pod_status(args.pod_id, json_output=args.json)
    
    elif args.command == "list":
        manager.list_pods(json_output=args.json)


if __name__ == "__main__":
    main()
