"""
Unit tests for RunPod serverless handler functions.

Tests cover:
- Input validation with valid and invalid payloads
- Workflow execution flow with mocked ComfyUI client
- Error handling for various failure scenarios
- Cleanup functionality
"""

import pytest
import base64
import json
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import tempfile
import shutil

# Import handler functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from handler import (
    handler,
    validate_workflow,
    upload_images,
    execute_workflow,
    get_outputs,
    cleanup_temp_files,
    process_outputs,
    initialize_comfyui,
    ValidationError,
    HandlerError
)


class TestValidateWorkflow:
    """Tests for workflow validation function."""
    
    def test_validate_workflow_valid(self):
        """Test validation passes for valid workflow."""
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"}
            },
            "2": {
                "class_type": "KSampler",
                "inputs": {"model": ["1", 0]}
            }
        }
        
        result = validate_workflow(workflow)
        assert result == workflow
    
    def test_validate_workflow_none(self):
        """Test validation fails for None workflow."""
        with pytest.raises(ValidationError, match="Workflow is required"):
            validate_workflow(None)
    
    def test_validate_workflow_not_dict(self):
        """Test validation fails for non-dictionary workflow."""
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_workflow("not a dict")
        
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_workflow([1, 2, 3])
    
    def test_validate_workflow_empty(self):
        """Test validation fails for empty workflow."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_workflow({})
    
    def test_validate_workflow_no_nodes(self):
        """Test validation fails for workflow without numeric node keys."""
        workflow = {
            "not_a_node": {"class_type": "Test", "inputs": {}}
        }
        with pytest.raises(ValidationError, match="must contain at least one node"):
            validate_workflow(workflow)
    
    def test_validate_workflow_node_not_dict(self):
        """Test validation fails when node is not a dictionary."""
        workflow = {
            "1": "not a dict"
        }
        with pytest.raises(ValidationError, match="Node 1 must be a dictionary"):
            validate_workflow(workflow)
    
    def test_validate_workflow_missing_class_type(self):
        """Test validation fails when node missing class_type."""
        workflow = {
            "1": {
                "inputs": {}
            }
        }
        with pytest.raises(ValidationError, match="missing required field 'class_type'"):
            validate_workflow(workflow)
    
    def test_validate_workflow_missing_inputs(self):
        """Test validation fails when node missing inputs."""
        workflow = {
            "1": {
                "class_type": "Test"
            }
        }
        with pytest.raises(ValidationError, match="missing required field 'inputs'"):
            validate_workflow(workflow)


class TestUploadImages:
    """Tests for image upload function."""
    
    @patch('handler.comfyui_client')
    def test_upload_images_none(self, mock_client):
        """Test upload with no images returns empty dict."""
        result = upload_images(None)
        assert result == {}
        mock_client.upload_image.assert_not_called()
    
    @patch('handler.comfyui_client')
    def test_upload_images_empty(self, mock_client):
        """Test upload with empty dict returns empty dict."""
        result = upload_images({})
        assert result == {}
        mock_client.upload_image.assert_not_called()
    
    @patch('handler.comfyui_client')
    def test_upload_images_valid(self, mock_client):
        """Test successful image upload."""
        # Create test image data
        test_data = b"fake image data"
        encoded = base64.b64encode(test_data).decode('utf-8')
        
        images = {
            "test.png": encoded
        }
        
        mock_client.upload_image.return_value = {"name": "test.png"}
        
        result = upload_images(images)
        
        assert result == {"test.png": "test.png"}
        mock_client.upload_image.assert_called_once()
        
        # Verify the call arguments
        call_args = mock_client.upload_image.call_args
        assert call_args[1]['filename'] == "test.png"
        assert call_args[1]['overwrite'] is True
    
    @patch('handler.comfyui_client')
    def test_upload_images_with_data_url(self, mock_client):
        """Test upload with data URL prefix."""
        test_data = b"fake image data"
        encoded = base64.b64encode(test_data).decode('utf-8')
        data_url = f"data:image/png;base64,{encoded}"
        
        images = {
            "test.png": data_url
        }
        
        mock_client.upload_image.return_value = {"name": "test.png"}
        
        result = upload_images(images)
        
        assert result == {"test.png": "test.png"}
        mock_client.upload_image.assert_called_once()
    
    @patch('handler.comfyui_client')
    def test_upload_images_multiple(self, mock_client):
        """Test uploading multiple images."""
        test_data = b"fake image data"
        encoded = base64.b64encode(test_data).decode('utf-8')
        
        images = {
            "test1.png": encoded,
            "test2.png": encoded
        }
        
        mock_client.upload_image.side_effect = [
            {"name": "test1.png"},
            {"name": "test2.png"}
        ]
        
        result = upload_images(images)
        
        assert result == {"test1.png": "test1.png", "test2.png": "test2.png"}
        assert mock_client.upload_image.call_count == 2
    
    def test_upload_images_not_dict(self):
        """Test upload fails with non-dict input."""
        with pytest.raises(ValidationError, match="must be a dictionary"):
            upload_images("not a dict")
    
    def test_upload_images_invalid_data(self):
        """Test upload fails with invalid base64 data."""
        images = {
            "test.png": "not valid base64!!!"
        }
        
        with pytest.raises(HandlerError, match="Failed to upload image"):
            upload_images(images)
    
    @patch('handler.comfyui_client')
    def test_upload_images_upload_failure(self, mock_client):
        """Test handling of upload failure."""
        test_data = b"fake image data"
        encoded = base64.b64encode(test_data).decode('utf-8')
        
        images = {
            "test.png": encoded
        }
        
        mock_client.upload_image.side_effect = Exception("Upload failed")
        
        with pytest.raises(HandlerError, match="Failed to upload image test.png"):
            upload_images(images)


class TestExecuteWorkflow:
    """Tests for workflow execution function."""
    
    @patch('handler.comfyui_client')
    def test_execute_workflow_success(self, mock_client):
        """Test successful workflow execution."""
        workflow = {
            "1": {"class_type": "Test", "inputs": {}}
        }
        
        mock_client.queue_prompt.return_value = "prompt-123"
        mock_client.wait_for_completion.return_value = {
            "outputs": {"1": {"images": []}}
        }
        
        result = execute_workflow(workflow)
        
        assert result == "prompt-123"
        mock_client.queue_prompt.assert_called_once_with(workflow)
        mock_client.wait_for_completion.assert_called_once()
    
    @patch('handler.comfyui_client')
    def test_execute_workflow_custom_timeout(self, mock_client):
        """Test workflow execution with custom timeout."""
        workflow = {
            "1": {"class_type": "Test", "inputs": {}}
        }
        
        mock_client.queue_prompt.return_value = "prompt-123"
        mock_client.wait_for_completion.return_value = {
            "outputs": {"1": {"images": []}}
        }
        
        result = execute_workflow(workflow, timeout=600)
        
        assert result == "prompt-123"
        
        # Verify timeout was passed
        call_args = mock_client.wait_for_completion.call_args
        assert call_args[1]['max_wait_time'] == 600
    
    @patch('handler.comfyui_client')
    def test_execute_workflow_queue_failure(self, mock_client):
        """Test handling of queue failure."""
        from comfyui_client import ComfyUIWorkflowError
        
        workflow = {
            "1": {"class_type": "Test", "inputs": {}}
        }
        
        mock_client.queue_prompt.side_effect = ComfyUIWorkflowError("Queue failed")
        
        with pytest.raises(HandlerError, match="Workflow execution failed"):
            execute_workflow(workflow)
    
    @patch('handler.comfyui_client')
    def test_execute_workflow_execution_failure(self, mock_client):
        """Test handling of execution failure."""
        from comfyui_client import ComfyUIWorkflowError
        
        workflow = {
            "1": {"class_type": "Test", "inputs": {}}
        }
        
        mock_client.queue_prompt.return_value = "prompt-123"
        mock_client.wait_for_completion.side_effect = ComfyUIWorkflowError(
            "Execution failed"
        )
        
        with pytest.raises(HandlerError, match="Workflow execution failed"):
            execute_workflow(workflow)
    
    @patch('handler.comfyui_client')
    def test_execute_workflow_connection_error(self, mock_client):
        """Test handling of connection error."""
        from comfyui_client import ComfyUIConnectionError
        
        workflow = {
            "1": {"class_type": "Test", "inputs": {}}
        }
        
        mock_client.queue_prompt.side_effect = ComfyUIConnectionError(
            "Connection failed"
        )
        
        with pytest.raises(HandlerError, match="Connection to ComfyUI failed"):
            execute_workflow(workflow)


class TestGetOutputs:
    """Tests for output retrieval function."""
    
    @patch('handler.comfyui_client')
    def test_get_outputs_success(self, mock_client):
        """Test successful output retrieval."""
        outputs = [
            {
                'filename': 'output1.png',
                'data': b'image data',
                'type': 'output',
                'node_id': '1'
            }
        ]
        
        mock_client.get_outputs.return_value = outputs
        
        result = get_outputs("prompt-123")
        
        assert result == outputs
        mock_client.get_outputs.assert_called_once_with("prompt-123")
    
    @patch('handler.comfyui_client')
    def test_get_outputs_failure(self, mock_client):
        """Test handling of output retrieval failure."""
        from comfyui_client import ComfyUIWorkflowError
        
        mock_client.get_outputs.side_effect = ComfyUIWorkflowError(
            "No outputs found"
        )
        
        with pytest.raises(HandlerError, match="Failed to retrieve outputs"):
            get_outputs("prompt-123")


class TestCleanupTempFiles:
    """Tests for cleanup function."""
    
    @patch('handler.COMFYUI_PATH', '/tmp/test_comfyui')
    def test_cleanup_temp_files(self):
        """Test cleanup removes temporary files."""
        # Create temporary directory structure
        temp_base = Path('/tmp/test_comfyui')
        temp_dir = temp_base / 'temp'
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Create test files
        test_file = temp_dir / 'test.txt'
        test_file.write_text('test')
        
        test_subdir = temp_dir / 'subdir'
        test_subdir.mkdir()
        (test_subdir / 'nested.txt').write_text('nested')
        
        # Run cleanup
        cleanup_temp_files()
        
        # Verify files were removed
        assert not test_file.exists()
        assert not test_subdir.exists()
        
        # Cleanup test directory
        shutil.rmtree(temp_base, ignore_errors=True)
    
    @patch('handler.COMFYUI_PATH', '/nonexistent/path')
    def test_cleanup_temp_files_no_dir(self):
        """Test cleanup handles missing directory gracefully."""
        # Should not raise exception
        cleanup_temp_files()


class TestProcessOutputs:
    """Tests for output processing function."""
    
    @patch('handler.STORAGE_TYPE', 'response')
    def test_process_outputs_response_mode(self):
        """Test output processing in response mode."""
        outputs = [
            {
                'filename': 'output1.png',
                'data': b'image data',
                'type': 'output',
                'node_id': '1'
            }
        ]
        
        result = process_outputs(outputs)
        
        assert len(result) == 1
        assert result[0]['filename'] == 'output1.png'
        assert result[0]['encoding'] == 'base64'
        assert 'data' in result[0]
        
        # Verify base64 encoding
        decoded = base64.b64decode(result[0]['data'])
        assert decoded == b'image data'
    
    @patch('handler.STORAGE_TYPE', 'volume')
    @patch('handler.VOLUME_OUTPUT_PATH')
    def test_process_outputs_volume_mode(self, mock_path):
        """Test output processing in volume mode."""
        # Create temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_path.__str__ = Mock(return_value=tmpdir)
            mock_path.__truediv__ = lambda self, other: Path(tmpdir) / other
            
            # Mock VOLUME_OUTPUT_PATH to return our temp dir
            with patch('handler.VOLUME_OUTPUT_PATH', tmpdir):
                outputs = [
                    {
                        'filename': 'output1.png',
                        'data': b'image data',
                        'type': 'output',
                        'node_id': '1'
                    }
                ]
                
                result = process_outputs(outputs)
                
                assert len(result) == 1
                assert result[0]['filename'] == 'output1.png'
                assert 'path' in result[0]
                
                # Verify file was written
                output_file = Path(result[0]['path'])
                assert output_file.exists()
                assert output_file.read_bytes() == b'image data'


class TestHandler:
    """Tests for main handler function."""
    
    @patch('handler.initialize_comfyui')
    @patch('handler.comfyui_client')
    @patch('handler.cleanup_temp_files')
    def test_handler_success(self, mock_cleanup, mock_client, mock_init):
        """Test successful job processing."""
        mock_init.return_value = True
        mock_client.queue_prompt.return_value = "prompt-123"
        mock_client.wait_for_completion.return_value = {
            "outputs": {"1": {"images": []}}
        }
        mock_client.get_outputs.return_value = [
            {
                'filename': 'output.png',
                'data': b'image data',
                'type': 'output',
                'node_id': '1'
            }
        ]
        
        job = {
            'id': 'job-123',
            'input': {
                'workflow': {
                    "1": {"class_type": "Test", "inputs": {}}
                }
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        assert 'output' in result
        assert 'images' in result['output']
        assert result['output']['prompt_id'] == "prompt-123"
        assert result['metadata']['job_id'] == 'job-123'
        assert result['metadata']['output_count'] == 1
        
        mock_init.assert_called_once()
        mock_cleanup.assert_called()
    
    @patch('handler.initialize_comfyui')
    def test_handler_validation_error(self, mock_init):
        """Test handler with validation error."""
        mock_init.return_value = True
        
        job = {
            'id': 'job-123',
            'input': {
                'workflow': None  # Invalid workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'VALIDATION_ERROR'
        assert result['error']['type'] == 'ValidationError'
        assert 'Workflow is required' in result['error']['message']
    
    @patch('handler.initialize_comfyui')
    def test_handler_invalid_input(self, mock_init):
        """Test handler with invalid input structure."""
        mock_init.return_value = True
        
        job = {
            'id': 'job-123',
            'input': "not a dict"
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'VALIDATION_ERROR'
    
    @patch('handler.initialize_comfyui')
    @patch('handler.comfyui_client')
    def test_handler_execution_error(self, mock_client, mock_init):
        """Test handler with execution error."""
        from comfyui_client import ComfyUIWorkflowError
        
        mock_init.return_value = True
        mock_client.queue_prompt.side_effect = ComfyUIWorkflowError("Execution failed")
        
        job = {
            'id': 'job-123',
            'input': {
                'workflow': {
                    "1": {"class_type": "Test", "inputs": {}}
                }
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'HANDLER_ERROR'
        assert 'Workflow execution failed' in result['error']['message']
    
    @patch('handler.initialize_comfyui')
    @patch('handler.comfyui_client')
    @patch('handler.cleanup_temp_files')
    def test_handler_with_input_images(self, mock_cleanup, mock_client, mock_init):
        """Test handler with input images."""
        mock_init.return_value = True
        mock_client.upload_image.return_value = {"name": "test.png"}
        mock_client.queue_prompt.return_value = "prompt-123"
        mock_client.wait_for_completion.return_value = {
            "outputs": {"1": {"images": []}}
        }
        mock_client.get_outputs.return_value = []
        
        test_data = b"fake image"
        encoded = base64.b64encode(test_data).decode('utf-8')
        
        job = {
            'id': 'job-123',
            'input': {
                'workflow': {
                    "1": {"class_type": "Test", "inputs": {}}
                },
                'input_images': {
                    'test.png': encoded
                }
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        mock_client.upload_image.assert_called_once()
    
    @patch('handler.initialize_comfyui')
    @patch('handler.comfyui_client')
    @patch('handler.cleanup_temp_files')
    def test_handler_with_custom_timeout(self, mock_cleanup, mock_client, mock_init):
        """Test handler with custom timeout."""
        mock_init.return_value = True
        mock_client.queue_prompt.return_value = "prompt-123"
        mock_client.wait_for_completion.return_value = {
            "outputs": {"1": {"images": []}}
        }
        mock_client.get_outputs.return_value = []
        
        job = {
            'id': 'job-123',
            'input': {
                'workflow': {
                    "1": {"class_type": "Test", "inputs": {}}
                },
                'timeout': 600
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        
        # Verify custom timeout was used
        call_args = mock_client.wait_for_completion.call_args
        assert call_args[1]['max_wait_time'] == 600
    
    @patch('handler.initialize_comfyui')
    @patch('handler.cleanup_temp_files')
    def test_handler_cleanup_always_runs(self, mock_cleanup, mock_init):
        """Test that cleanup runs even on error."""
        mock_init.side_effect = Exception("Init failed")
        
        job = {
            'id': 'job-123',
            'input': {
                'workflow': {
                    "1": {"class_type": "Test", "inputs": {}}
                }
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        # Cleanup should be called in finally block
        mock_cleanup.assert_called()


class TestInitializeComfyUI:
    """Tests for ComfyUI initialization function."""
    
    @patch('handler.comfyui_client')
    def test_initialize_comfyui_already_running(self, mock_client):
        """Test initialization when ComfyUI is already running."""
        mock_client.health_check.return_value = True
        
        result = initialize_comfyui()
        
        assert result is True
        mock_client.health_check.assert_called_once()
    
    @patch('handler.comfyui_client', None)
    @patch('handler.ComfyUIClient')
    def test_initialize_comfyui_creates_client(self, mock_client_class):
        """Test that client is created if not exists."""
        mock_instance = Mock()
        mock_instance.health_check.return_value = True
        mock_client_class.return_value = mock_instance
        
        # Reset global client
        import handler
        handler.comfyui_client = None
        
        result = initialize_comfyui()
        
        assert result is True
        mock_client_class.assert_called_once()
