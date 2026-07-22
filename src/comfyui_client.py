"""
ComfyUI API Client Wrapper

This module provides a Python client for interacting with the ComfyUI API.
It handles workflow submission, status checking, image upload/download, and error handling.
"""

import uuid
import json
import time
import requests
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin
import logging

logger = logging.getLogger(__name__)


class ComfyUIError(Exception):
    """Base exception for ComfyUI client errors"""
    pass


class ComfyUIConnectionError(ComfyUIError):
    """Raised when connection to ComfyUI fails"""
    pass


class ComfyUIWorkflowError(ComfyUIError):
    """Raised when workflow execution fails"""
    pass


class ComfyUIClient:
    """
    Client for interacting with ComfyUI API.
    
    Provides methods for:
    - Submitting workflows for execution
    - Checking execution status
    - Uploading input images
    - Downloading generated images
    """
    
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: int = 2
    ):
        """
        Initialize ComfyUI client.
        
        Args:
            base_url: Base URL of ComfyUI server
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client_id = str(uuid.uuid4())
        self.session = requests.Session()
        
    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
            
        Raises:
            ComfyUIConnectionError: If connection fails after retries
        """
        url = urljoin(self.base_url, endpoint)
        kwargs.setdefault('timeout', self.timeout)
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e}")
        
        raise ComfyUIConnectionError(
            f"Failed to connect to ComfyUI at {url} after {self.max_retries} attempts: {last_error}"
        )
    
    def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """
        Submit a workflow to ComfyUI for execution.
        
        Args:
            workflow: ComfyUI workflow JSON structure
            
        Returns:
            prompt_id: Unique identifier for the queued workflow
            
        Raises:
            ComfyUIWorkflowError: If workflow submission fails
            ComfyUIConnectionError: If connection fails
        """
        try:
            payload = {
                "prompt": workflow,
                "client_id": self.client_id
            }
            
            response = self._make_request(
                'POST',
                '/prompt',
                json=payload
            )
            
            result = response.json()
            
            if 'prompt_id' not in result:
                raise ComfyUIWorkflowError(
                    f"Invalid response from ComfyUI: {result}"
                )
            
            prompt_id = result['prompt_id']
            logger.info(f"Workflow queued successfully with prompt_id: {prompt_id}")
            return prompt_id
            
        except requests.exceptions.JSONDecodeError as e:
            raise ComfyUIWorkflowError(f"Invalid JSON response: {e}")
        except KeyError as e:
            raise ComfyUIWorkflowError(f"Missing required field in workflow: {e}")
    
    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """
        Get execution history and status for a workflow.
        
        Args:
            prompt_id: Unique identifier of the workflow
            
        Returns:
            Dictionary containing execution history and outputs
            
        Raises:
            ComfyUIConnectionError: If connection fails
        """
        response = self._make_request(
            'GET',
            f'/history/{prompt_id}'
        )
        
        history = response.json()
        
        if prompt_id not in history:
            return {}
        
        return history[prompt_id]
    
    def wait_for_completion(
        self,
        prompt_id: str,
        poll_interval: int = 1,
        max_wait_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Wait for workflow execution to complete.
        
        Args:
            prompt_id: Unique identifier of the workflow
            poll_interval: Time between status checks in seconds
            max_wait_time: Maximum time to wait in seconds (None = no limit)
            
        Returns:
            Dictionary containing execution results
            
        Raises:
            ComfyUIWorkflowError: If workflow execution fails or times out
            ComfyUIConnectionError: If connection fails
        """
        start_time = time.time()
        
        while True:
            history = self.get_history(prompt_id)
            
            if history:
                # Check if execution completed
                if 'outputs' in history:
                    logger.info(f"Workflow {prompt_id} completed successfully")
                    return history
                
                # Check for errors
                if 'status' in history:
                    status = history['status']
                    if status.get('completed') is False:
                        error_msg = status.get('messages', [])
                        raise ComfyUIWorkflowError(
                            f"Workflow execution failed: {error_msg}"
                        )
            
            # Check timeout
            if max_wait_time:
                elapsed = time.time() - start_time
                if elapsed > max_wait_time:
                    raise ComfyUIWorkflowError(
                        f"Workflow execution timed out after {max_wait_time} seconds"
                    )
            
            time.sleep(poll_interval)
    
    def get_image(
        self,
        filename: str,
        subfolder: str = "",
        folder_type: str = "output"
    ) -> bytes:
        """
        Download a generated image from ComfyUI.
        
        Args:
            filename: Name of the image file
            subfolder: Subfolder path (if any)
            folder_type: Type of folder (output, input, temp)
            
        Returns:
            Image data as bytes
            
        Raises:
            ComfyUIConnectionError: If download fails
        """
        params = {
            'filename': filename,
            'subfolder': subfolder,
            'type': folder_type
        }
        
        response = self._make_request(
            'GET',
            '/view',
            params=params
        )
        
        logger.info(f"Downloaded image: {filename}")
        return response.content
    
    def upload_image(
        self,
        image_data: bytes,
        filename: str,
        subfolder: str = "",
        overwrite: bool = True
    ) -> Dict[str, Any]:
        """
        Upload an image to ComfyUI for use in workflows.
        
        Args:
            image_data: Image file data as bytes
            filename: Name for the uploaded file
            subfolder: Subfolder to upload to
            overwrite: Whether to overwrite existing file
            
        Returns:
            Dictionary containing upload result with 'name' and 'subfolder'
            
        Raises:
            ComfyUIConnectionError: If upload fails
        """
        files = {
            'image': (filename, image_data, 'image/png')
        }
        
        data = {
            'overwrite': str(overwrite).lower()
        }
        
        if subfolder:
            data['subfolder'] = subfolder
        
        response = self._make_request(
            'POST',
            '/upload/image',
            files=files,
            data=data
        )
        
        result = response.json()
        logger.info(f"Uploaded image: {filename}")
        return result
    
    def get_outputs(self, prompt_id: str) -> List[Dict[str, Any]]:
        """
        Get all output images from a completed workflow.
        
        Args:
            prompt_id: Unique identifier of the workflow
            
        Returns:
            List of dictionaries containing output information:
            - filename: Name of the output file
            - subfolder: Subfolder path
            - type: File type
            - data: Image data as bytes
            
        Raises:
            ComfyUIWorkflowError: If workflow hasn't completed
            ComfyUIConnectionError: If download fails
        """
        history = self.get_history(prompt_id)
        
        if not history or 'outputs' not in history:
            raise ComfyUIWorkflowError(
                f"No outputs found for prompt_id: {prompt_id}"
            )
        
        outputs = []
        
        for node_id, node_output in history['outputs'].items():
            if 'images' in node_output:
                for image_info in node_output['images']:
                    filename = image_info['filename']
                    subfolder = image_info.get('subfolder', '')
                    file_type = image_info.get('type', 'output')
                    
                    # Download the image
                    image_data = self.get_image(filename, subfolder, file_type)
                    
                    outputs.append({
                        'filename': filename,
                        'subfolder': subfolder,
                        'type': file_type,
                        'data': image_data,
                        'node_id': node_id
                    })
        
        logger.info(f"Retrieved {len(outputs)} output images for prompt {prompt_id}")
        return outputs
    
    def health_check(self) -> bool:
        """
        Check if ComfyUI server is responding.
        
        Returns:
            True if server is healthy, False otherwise
        """
        try:
            response = self._make_request('GET', '/')
            return response.status_code == 200
        except ComfyUIConnectionError:
            return False

    def free_memory(
        self,
        unload_models: bool = False,
        free_memory: bool = True
    ) -> bool:
        """
        Free VRAM/RAM and optionally unload models.
        
        This clears cached latent tensors and intermediate results that can
        cause corrupted outputs on subsequent runs. Call this before executing
        a new workflow to ensure fresh latent initialization.
        
        Args:
            unload_models: If True, unload all loaded models from memory.
                          Use sparingly as reloading models is slow.
            free_memory: If True, free all cached data from previous workflows.
                        This clears latent caches and intermediate tensors.
        
        Returns:
            True if memory was freed successfully, False otherwise
            
        Note:
            The /free endpoint was added to ComfyUI to handle memory management.
            POST /free with {"unload_models": bool, "free_memory": bool}
        """
        try:
            payload = {
                "unload_models": unload_models,
                "free_memory": free_memory
            }
            
            response = self._make_request(
                'POST',
                '/free',
                json=payload
            )
            
            logger.info(
                f"Memory freed (unload_models={unload_models}, "
                f"free_memory={free_memory})"
            )
            return True
            
        except ComfyUIConnectionError as e:
            # /free endpoint may not exist in older ComfyUI versions
            logger.warning(f"Failed to free memory (endpoint may not exist): {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error freeing memory: {e}")
            return False

    def clear_cache(self) -> bool:
        """
        Clear all cached data without unloading models.
        
        This is a convenience method that calls free_memory() with settings
        optimized for clearing latent caches while keeping models loaded.
        Use this between workflow runs to prevent corrupted outputs from
        stale cached tensors.
        
        Returns:
            True if cache was cleared successfully, False otherwise
        """
        return self.free_memory(unload_models=False, free_memory=True)

    def interrupt(self) -> bool:
        """
        Interrupt the currently running workflow.
        
        Returns:
            True if interrupt was sent successfully, False otherwise
        """
        try:
            response = self._make_request('POST', '/interrupt')
            logger.info("Workflow interrupted")
            return True
        except ComfyUIConnectionError as e:
            logger.warning(f"Failed to interrupt workflow: {e}")
            return False

    def clear_history(self, prompt_id: Optional[str] = None) -> bool:
        """
        Clear execution history to free memory.
        
        Args:
            prompt_id: If provided, clear only this prompt's history.
                      If None, clear all history.
        
        Returns:
            True if history was cleared successfully, False otherwise
        """
        try:
            if prompt_id:
                payload = {"delete": [prompt_id]}
            else:
                payload = {"clear": True}
            
            response = self._make_request(
                'POST',
                '/history',
                json=payload
            )
            
            logger.info(
                f"History cleared: {'prompt ' + prompt_id if prompt_id else 'all'}"
            )
            return True
            
        except ComfyUIConnectionError as e:
            logger.warning(f"Failed to clear history: {e}")
            return False
