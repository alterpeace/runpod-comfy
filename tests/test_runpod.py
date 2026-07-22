#!/usr/bin/env python3
"""
RunPod Endpoint Testing Script

Tests a deployed RunPod serverless endpoint with ComfyUI workflows.
"""

import os
import sys
import json
import time
import base64
import argparse
import requests
from pathlib import Path
from typing import Dict, Any, Optional


class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def load_workflow(workflow_path: str) -> Dict[str, Any]:
    """Load workflow JSON from file"""
    try:
        with open(workflow_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"{Colors.RED}Error: Workflow file not found: {workflow_path}{Colors.NC}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"{Colors.RED}Error: Invalid JSON in workflow file: {e}{Colors.NC}")
        sys.exit(1)


def load_image_base64(image_path: str) -> str:
    """Load image and encode as base64"""
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        return base64.b64encode(image_data).decode('utf-8')
    except FileNotFoundError:
        print(f"{Colors.RED}Error: Image file not found: {image_path}{Colors.NC}")
        sys.exit(1)


def invoke_endpoint(
    endpoint_id: str,
    api_key: str,
    workflow: Dict[str, Any],
    input_images: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None
) -> Dict[str, Any]:
    """
    Invoke RunPod serverless endpoint with workflow.
    
    Args:
        endpoint_id: RunPod endpoint ID
        api_key: RunPod API key
        workflow: ComfyUI workflow JSON
        input_images: Optional dict of filename -> base64 image data
        timeout: Optional custom timeout in seconds
        
    Returns:
        Response from endpoint
    """
    url = f"https://api.runpod.ai/v2/{endpoint_id}/runsync"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "input": {
            "workflow": workflow
        }
    }
    
    if input_images:
        payload["input"]["input_images"] = input_images
    
    if timeout:
        payload["input"]["timeout"] = timeout
    
    print(f"{Colors.BLUE}Invoking endpoint: {endpoint_id}{Colors.NC}")
    print(f"{Colors.BLUE}Workflow nodes: {len(workflow)}{Colors.NC}")
    if input_images:
        print(f"{Colors.BLUE}Input images: {len(input_images)}{Colors.NC}")
    print()
    
    start_time = time.time()
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=600)
        response.raise_for_status()
        
        elapsed = time.time() - start_time
        print(f"{Colors.GREEN}✓ Request completed in {elapsed:.2f}s{Colors.NC}")
        
        return response.json()
        
    except requests.exceptions.Timeout:
        print(f"{Colors.RED}Error: Request timed out{Colors.NC}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"{Colors.RED}Error: Request failed: {e}{Colors.NC}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"{Colors.YELLOW}Response: {e.response.text}{Colors.NC}")
        sys.exit(1)


def save_outputs(outputs: list, output_dir: str) -> None:
    """Save output images to directory"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for i, output in enumerate(outputs):
        filename = output.get('filename', f'output_{i}.png')
        
        # Handle different storage types
        if 'data' in output:
            # Base64 encoded data
            image_data = base64.b64decode(output['data'])
            file_path = output_path / filename
            file_path.write_bytes(image_data)
            print(f"{Colors.GREEN}✓ Saved: {file_path}{Colors.NC}")
            
        elif 'url' in output:
            # S3 URL
            print(f"{Colors.GREEN}✓ S3 URL: {output['url']}{Colors.NC}")
            
        elif 'path' in output:
            # Volume path
            print(f"{Colors.GREEN}✓ Volume path: {output['path']}{Colors.NC}")


def main():
    parser = argparse.ArgumentParser(
        description='Test RunPod serverless endpoint with ComfyUI workflows'
    )
    parser.add_argument(
        '--endpoint-id',
        help='RunPod endpoint ID (or set RUNPOD_ENDPOINT_ID env var)'
    )
    parser.add_argument(
        '--api-key',
        help='RunPod API key (or set RUNPOD_API_KEY env var)'
    )
    parser.add_argument(
        '--workflow',
        default='examples/text_to_image_simple.json',
        help='Path to workflow JSON file (default: examples/text_to_image_simple.json)'
    )
    parser.add_argument(
        '--input-image',
        help='Path to input image file (for image-to-image workflows)'
    )
    parser.add_argument(
        '--input-image-name',
        default='input_image.png',
        help='Name for input image in workflow (default: input_image.png)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        help='Custom timeout in seconds'
    )
    parser.add_argument(
        '--output-dir',
        default='test_outputs',
        help='Directory to save output images (default: test_outputs)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print full response JSON'
    )
    
    args = parser.parse_args()
    
    # Get endpoint ID and API key
    endpoint_id = args.endpoint_id or os.environ.get('RUNPOD_ENDPOINT_ID')
    api_key = args.api_key or os.environ.get('RUNPOD_API_KEY')
    
    if not endpoint_id:
        print(f"{Colors.RED}Error: Endpoint ID required{Colors.NC}")
        print("Provide via --endpoint-id or RUNPOD_ENDPOINT_ID env var")
        sys.exit(1)
    
    if not api_key:
        print(f"{Colors.RED}Error: API key required{Colors.NC}")
        print("Provide via --api-key or RUNPOD_API_KEY env var")
        sys.exit(1)
    
    print(f"{Colors.BLUE}=== RunPod Endpoint Testing ==={Colors.NC}")
    print()
    
    # Load workflow
    workflow = load_workflow(args.workflow)
    print(f"{Colors.GREEN}✓ Loaded workflow: {args.workflow}{Colors.NC}")
    
    # Load input image if provided
    input_images = None
    if args.input_image:
        image_data = load_image_base64(args.input_image)
        input_images = {args.input_image_name: image_data}
        print(f"{Colors.GREEN}✓ Loaded input image: {args.input_image}{Colors.NC}")
    
    print()
    
    # Invoke endpoint
    response = invoke_endpoint(
        endpoint_id=endpoint_id,
        api_key=api_key,
        workflow=workflow,
        input_images=input_images,
        timeout=args.timeout
    )
    
    print()
    
    # Check response status
    if response.get('status') == 'COMPLETED':
        output = response.get('output', {})
        
        if output.get('status') == 'success':
            print(f"{Colors.GREEN}✓ Workflow executed successfully{Colors.NC}")
            print()
            
            # Print metadata
            metadata = output.get('metadata', {})
            print(f"{Colors.BLUE}Metadata:{Colors.NC}")
            print(f"  Job ID: {metadata.get('job_id')}")
            print(f"  Prompt ID: {metadata.get('prompt_id')}")
            print(f"  Execution time: {metadata.get('execution_time')}s")
            print(f"  Node count: {metadata.get('node_count')}")
            print(f"  Output count: {metadata.get('output_count')}")
            print(f"  Storage type: {metadata.get('storage_type')}")
            print()
            
            # Save outputs
            images = output.get('output', {}).get('images', [])
            if images:
                print(f"{Colors.BLUE}Saving {len(images)} output(s):{Colors.NC}")
                save_outputs(images, args.output_dir)
            else:
                print(f"{Colors.YELLOW}No output images found{Colors.NC}")
            
        else:
            print(f"{Colors.RED}✗ Workflow execution failed{Colors.NC}")
            error = output.get('error', {})
            print(f"{Colors.RED}Error: {error.get('message')}{Colors.NC}")
            print(f"Code: {error.get('code')}")
            print(f"Type: {error.get('type')}")
            sys.exit(1)
    
    elif response.get('status') == 'FAILED':
        print(f"{Colors.RED}✗ Endpoint execution failed{Colors.NC}")
        print(f"{Colors.RED}Error: {response.get('error')}{Colors.NC}")
        sys.exit(1)
    
    else:
        print(f"{Colors.YELLOW}Unexpected status: {response.get('status')}{Colors.NC}")
    
    # Print full response if verbose
    if args.verbose:
        print()
        print(f"{Colors.BLUE}Full response:{Colors.NC}")
        print(json.dumps(response, indent=2))
    
    print()
    print(f"{Colors.GREEN}=== Test completed ==={Colors.NC}")


if __name__ == '__main__':
    main()
