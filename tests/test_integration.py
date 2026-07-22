"""
Integration tests for complete workflow execution.

Tests the full handler workflow from input to output, including:
- Complete workflow execution
- Input image handling
- Output retrieval and storage
- Error scenarios
"""

import json
import base64
import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO
from PIL import Image

# Import handler components
from handler import (
    handler,
    initialize_comfyui,
    validate_workflow,
    upload_images,
    execute_workflow,
    get_outputs,
    process_outputs,
    cleanup_temp_files,
    ValidationError,
    HandlerError
)


@pytest.fixture
def sample_workflow():
    """Load sample text-to-image workflow"""
    workflow_path = Path(__file__).parent.parent / 'examples' / 'text_to_image_simple.json'
    with open(workflow_path) as f:
        return json.load(f)


@pytest.fixture
def sample_img2img_workflow():
    """Load sample image-to-image workflow"""
    workflow_path = Path(__file__).parent.parent / 'examples' / 'image_to_image.json'
    with open(workflow_path) as f:
        return json.load(f)


@pytest.fixture
def sample_image_base64():
    """Create a sample image encoded as base64"""
    # Create a simple test image
    img = Image.new('RGB', (512, 512), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()
    return base64.b64encode(image_bytes).decode('utf-8')


@pytest.fixture
def mock_comfyui_client():
    """Mock ComfyUI client for testing"""
    with patch('handler.comfyui_client') as mock_client:
        # Mock health check
        mock_client.health_check.return_value = True
        
        # Mock queue_prompt
        mock_client.queue_prompt.return_value = 'test-prompt-123'
        
        # Mock wait_for_completion
        mock_client.wait_for_completion.return_value = {
            'outputs': {
                '9': {
                    'images': [
                        {
                            'filename': 'ComfyUI_00001.png',
                            'subfolder': '',
                            'type': 'output'
                        }
                    ]
                }
            }
        }
        
        # Mock get_outputs
        test_image = Image.new('RGB', (512, 512), color='blue')
        buffer = BytesIO()
        test_image.save(buffer, format='PNG')
        image_data = buffer.getvalue()
        
        mock_client.get_outputs.return_value = [
            {
                'filename': 'ComfyUI_00001.png',
                'subfolder': '',
                'type': 'output',
                'data': image_data,
                'node_id': '9'
            }
        ]
        
        # Mock upload_image
        mock_client.upload_image.return_value = {
            'name': 'input_image.png',
            'subfolder': ''
        }
        
        yield mock_client


class TestCompleteWorkflowExecution:
    """Test complete workflow execution from input to output"""
    
    def test_text_to_image_workflow_success(self, sample_workflow, mock_comfyui_client):
        """Test successful text-to-image workflow execution"""
        job = {
            'id': 'test-job-001',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        assert 'output' in result
        assert 'images' in result['output']
        assert len(result['output']['images']) > 0
        assert result['output']['prompt_id'] == 'test-prompt-123'
        
        # Check metadata
        metadata = result['metadata']
        assert metadata['job_id'] == 'test-job-001'
        assert metadata['prompt_id'] == 'test-prompt-123'
        assert 'execution_time' in metadata
        assert metadata['node_count'] == len(sample_workflow)
        assert metadata['output_count'] > 0
    
    def test_image_to_image_workflow_success(
        self,
        sample_img2img_workflow,
        sample_image_base64,
        mock_comfyui_client
    ):
        """Test successful image-to-image workflow execution"""
        job = {
            'id': 'test-job-002',
            'input': {
                'workflow': sample_img2img_workflow,
                'input_images': {
                    'input_image.png': sample_image_base64
                }
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        assert 'output' in result
        assert 'images' in result['output']
        
        # Verify image upload was called
        mock_comfyui_client.upload_image.assert_called_once()
    
    def test_workflow_with_custom_timeout(self, sample_workflow, mock_comfyui_client):
        """Test workflow execution with custom timeout"""
        job = {
            'id': 'test-job-003',
            'input': {
                'workflow': sample_workflow,
                'timeout': 600
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        
        # Verify wait_for_completion was called with custom timeout
        mock_comfyui_client.wait_for_completion.assert_called_once()
        call_kwargs = mock_comfyui_client.wait_for_completion.call_args[1]
        assert call_kwargs.get('max_wait_time') == 600
    
    def test_workflow_output_base64_encoding(self, sample_workflow, mock_comfyui_client):
        """Test that outputs are properly base64 encoded"""
        job = {
            'id': 'test-job-004',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        with patch('handler.STORAGE_TYPE', 'response'):
            result = handler(job)
        
        assert result['status'] == 'success'
        
        # Check that images have base64 data
        for image in result['output']['images']:
            assert 'data' in image
            assert 'encoding' in image
            assert image['encoding'] == 'base64'
            
            # Verify it's valid base64
            try:
                base64.b64decode(image['data'])
            except Exception:
                pytest.fail("Invalid base64 encoding")
    
    def test_workflow_validation_error(self, mock_comfyui_client):
        """Test workflow validation error handling"""
        job = {
            'id': 'test-job-005',
            'input': {
                'workflow': None  # Invalid workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'VALIDATION_ERROR'
        assert 'Workflow is required' in result['error']['message']
    
    def test_workflow_execution_error(self, sample_workflow, mock_comfyui_client):
        """Test workflow execution error handling"""
        # Mock execution failure
        from comfyui_client import ComfyUIWorkflowError
        mock_comfyui_client.wait_for_completion.side_effect = ComfyUIWorkflowError(
            "Node execution failed"
        )
        
        job = {
            'id': 'test-job-006',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'HANDLER_ERROR'
        assert 'Node execution failed' in result['error']['message']
    
    def test_multiple_output_images(self, sample_workflow, mock_comfyui_client):
        """Test handling of multiple output images"""
        # Mock multiple outputs
        test_image = Image.new('RGB', (512, 512), color='green')
        buffer = BytesIO()
        test_image.save(buffer, format='PNG')
        image_data = buffer.getvalue()
        
        mock_comfyui_client.get_outputs.return_value = [
            {
                'filename': f'output_{i}.png',
                'subfolder': '',
                'type': 'output',
                'data': image_data,
                'node_id': str(i)
            }
            for i in range(3)
        ]
        
        job = {
            'id': 'test-job-007',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        assert len(result['output']['images']) == 3
        assert result['metadata']['output_count'] == 3


class TestStorageIntegration:
    """Test different storage backend integrations"""
    
    def test_volume_storage(self, sample_workflow, mock_comfyui_client, tmp_path):
        """Test saving outputs to volume storage"""
        job = {
            'id': 'test-job-008',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        with patch('handler.STORAGE_TYPE', 'volume'):
            with patch('handler.VOLUME_OUTPUT_PATH', str(tmp_path)):
                result = handler(job)
        
        assert result['status'] == 'success'
        
        # Check that files were saved
        for image in result['output']['images']:
            assert 'path' in image
            assert Path(image['path']).exists()
    
    @patch('handler.S3_AVAILABLE', True)
    @patch('handler.s3_client')
    def test_s3_storage(self, mock_s3_client, sample_workflow, mock_comfyui_client):
        """Test uploading outputs to S3 storage"""
        # Mock S3 upload
        mock_s3_client.upload_file.return_value = {
            'key': 'outputs/test-prompt-123/ComfyUI_00001.png',
            'url': 'https://s3.example.com/bucket/outputs/test-prompt-123/ComfyUI_00001.png',
            'bucket': 'test-bucket',
            'size': 12345,
            'content_type': 'image/png'
        }
        
        job = {
            'id': 'test-job-009',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        with patch('handler.STORAGE_TYPE', 's3'):
            result = handler(job)
        
        assert result['status'] == 'success'
        
        # Check that S3 URLs are returned
        for image in result['output']['images']:
            assert 'url' in image
            assert 'bucket' in image
            assert 's3_key' in image
            assert image['url'].startswith('https://')


class TestErrorScenarios:
    """Test various error scenarios"""
    
    def test_invalid_job_input_type(self, mock_comfyui_client):
        """Test error when job input is not a dictionary"""
        job = {
            'id': 'test-job-010',
            'input': "invalid"  # Should be dict
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'VALIDATION_ERROR'
    
    def test_empty_workflow(self, mock_comfyui_client):
        """Test error when workflow is empty"""
        job = {
            'id': 'test-job-011',
            'input': {
                'workflow': {}
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'VALIDATION_ERROR'
    
    def test_invalid_workflow_structure(self, mock_comfyui_client):
        """Test error when workflow has invalid structure"""
        job = {
            'id': 'test-job-012',
            'input': {
                'workflow': {
                    '1': {
                        # Missing 'class_type' and 'inputs'
                        'invalid': 'structure'
                    }
                }
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'VALIDATION_ERROR'
    
    def test_invalid_input_image_format(self, sample_img2img_workflow, mock_comfyui_client):
        """Test error when input image is not base64"""
        job = {
            'id': 'test-job-013',
            'input': {
                'workflow': sample_img2img_workflow,
                'input_images': {
                    'input_image.png': 12345  # Should be string
                }
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'HANDLER_ERROR'
    
    def test_comfyui_connection_error(self, sample_workflow, mock_comfyui_client):
        """Test error when ComfyUI connection fails"""
        from comfyui_client import ComfyUIConnectionError
        mock_comfyui_client.queue_prompt.side_effect = ComfyUIConnectionError(
            "Connection refused"
        )
        
        job = {
            'id': 'test-job-014',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert result['error']['code'] == 'HANDLER_ERROR'
        assert 'Connection refused' in result['error']['message']
    
    def test_timeout_error(self, sample_workflow, mock_comfyui_client):
        """Test error when workflow execution times out"""
        from comfyui_client import ComfyUIWorkflowError
        mock_comfyui_client.wait_for_completion.side_effect = ComfyUIWorkflowError(
            "Workflow execution timed out after 300 seconds"
        )
        
        job = {
            'id': 'test-job-015',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'error'
        assert 'timed out' in result['error']['message'].lower()


class TestCleanup:
    """Test cleanup functionality"""
    
    def test_cleanup_on_success(self, sample_workflow, mock_comfyui_client, tmp_path):
        """Test that cleanup is called on successful execution"""
        with patch('handler.cleanup_temp_files') as mock_cleanup:
            job = {
                'id': 'test-job-016',
                'input': {
                    'workflow': sample_workflow
                }
            }
            
            result = handler(job)
            
            assert result['status'] == 'success'
            # Cleanup should be called at least once (in handler and finally block)
            assert mock_cleanup.call_count >= 1
    
    def test_cleanup_on_error(self, sample_workflow, mock_comfyui_client):
        """Test that cleanup is called even on error"""
        from comfyui_client import ComfyUIWorkflowError
        mock_comfyui_client.wait_for_completion.side_effect = ComfyUIWorkflowError(
            "Test error"
        )
        
        with patch('handler.cleanup_temp_files') as mock_cleanup:
            job = {
                'id': 'test-job-017',
                'input': {
                    'workflow': sample_workflow
                }
            }
            
            result = handler(job)
            
            assert result['status'] == 'error'
            # Cleanup should still be called in finally block
            assert mock_cleanup.call_count >= 1
