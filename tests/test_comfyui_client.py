"""
Unit tests for ComfyUI API Client

Tests workflow submission, status checking, image upload/download,
and error handling scenarios with mocked API responses.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import requests
from comfyui_client import (
    ComfyUIClient,
    ComfyUIError,
    ComfyUIConnectionError,
    ComfyUIWorkflowError
)


@pytest.fixture
def client():
    """Create a ComfyUI client instance for testing"""
    return ComfyUIClient(
        base_url="http://test.local:8188",
        timeout=10,
        max_retries=2,
        retry_delay=0.1
    )


@pytest.fixture
def sample_workflow():
    """Sample ComfyUI workflow for testing"""
    return {
        "1": {
            "inputs": {
                "ckpt_name": "model.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {
                "text": "a beautiful landscape"
            },
            "class_type": "CLIPTextEncode"
        }
    }


class TestComfyUIClientInit:
    """Test client initialization"""
    
    def test_init_default_values(self):
        """Test client initializes with default values"""
        client = ComfyUIClient()
        assert client.base_url == "http://127.0.0.1:8188"
        assert client.timeout == 300
        assert client.max_retries == 3
        assert client.client_id is not None
    
    def test_init_custom_values(self):
        """Test client initializes with custom values"""
        client = ComfyUIClient(
            base_url="http://custom:9999",
            timeout=60,
            max_retries=5
        )
        assert client.base_url == "http://custom:9999"
        assert client.timeout == 60
        assert client.max_retries == 5
    
    def test_base_url_trailing_slash_removed(self):
        """Test trailing slash is removed from base URL"""
        client = ComfyUIClient(base_url="http://test.local:8188/")
        assert client.base_url == "http://test.local:8188"


class TestQueuePrompt:
    """Test workflow submission"""
    
    def test_queue_prompt_success(self, client, sample_workflow):
        """Test successful workflow submission"""
        mock_response = Mock()
        mock_response.json.return_value = {"prompt_id": "test-prompt-123"}
        mock_response.status_code = 200
        
        with patch.object(client, '_make_request', return_value=mock_response):
            prompt_id = client.queue_prompt(sample_workflow)
            
            assert prompt_id == "test-prompt-123"
            client._make_request.assert_called_once()
            call_args = client._make_request.call_args
            assert call_args[0][0] == 'POST'
            assert call_args[0][1] == '/prompt'
    
    def test_queue_prompt_invalid_response(self, client, sample_workflow):
        """Test workflow submission with invalid response"""
        mock_response = Mock()
        mock_response.json.return_value = {"error": "something went wrong"}
        
        with patch.object(client, '_make_request', return_value=mock_response):
            with pytest.raises(ComfyUIWorkflowError, match="Invalid response"):
                client.queue_prompt(sample_workflow)
    
    def test_queue_prompt_json_decode_error(self, client, sample_workflow):
        """Test workflow submission with JSON decode error"""
        mock_response = Mock()
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError(
            "Invalid JSON", "", 0
        )
        
        with patch.object(client, '_make_request', return_value=mock_response):
            with pytest.raises(ComfyUIWorkflowError, match="Invalid JSON response"):
                client.queue_prompt(sample_workflow)
    
    def test_queue_prompt_connection_error(self, client, sample_workflow):
        """Test workflow submission with connection error"""
        with patch.object(
            client,
            '_make_request',
            side_effect=ComfyUIConnectionError("Connection failed")
        ):
            with pytest.raises(ComfyUIConnectionError):
                client.queue_prompt(sample_workflow)


class TestGetHistory:
    """Test execution status checking"""
    
    def test_get_history_success(self, client):
        """Test successful history retrieval"""
        prompt_id = "test-prompt-123"
        mock_history = {
            prompt_id: {
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "output_00001.png",
                                "subfolder": "",
                                "type": "output"
                            }
                        ]
                    }
                }
            }
        }
        
        mock_response = Mock()
        mock_response.json.return_value = mock_history
        
        with patch.object(client, '_make_request', return_value=mock_response):
            history = client.get_history(prompt_id)
            
            assert "outputs" in history
            assert "9" in history["outputs"]
            client._make_request.assert_called_once_with('GET', f'/history/{prompt_id}')
    
    def test_get_history_not_found(self, client):
        """Test history retrieval when prompt not found"""
        mock_response = Mock()
        mock_response.json.return_value = {}
        
        with patch.object(client, '_make_request', return_value=mock_response):
            history = client.get_history("nonexistent-prompt")
            
            assert history == {}
    
    def test_get_history_connection_error(self, client):
        """Test history retrieval with connection error"""
        with patch.object(
            client,
            '_make_request',
            side_effect=ComfyUIConnectionError("Connection failed")
        ):
            with pytest.raises(ComfyUIConnectionError):
                client.get_history("test-prompt-123")


class TestWaitForCompletion:
    """Test waiting for workflow completion"""
    
    def test_wait_for_completion_success(self, client):
        """Test successful wait for completion"""
        prompt_id = "test-prompt-123"
        completed_history = {
            "outputs": {
                "9": {
                    "images": [{"filename": "output.png"}]
                }
            }
        }
        
        with patch.object(client, 'get_history', return_value=completed_history):
            result = client.wait_for_completion(prompt_id, poll_interval=0.1)
            
            assert "outputs" in result
    
    def test_wait_for_completion_timeout(self, client):
        """Test wait for completion with timeout"""
        prompt_id = "test-prompt-123"
        
        with patch.object(client, 'get_history', return_value={}):
            with pytest.raises(ComfyUIWorkflowError, match="timed out"):
                client.wait_for_completion(
                    prompt_id,
                    poll_interval=0.1,
                    max_wait_time=0.3
                )
    
    def test_wait_for_completion_error(self, client):
        """Test wait for completion with execution error"""
        prompt_id = "test-prompt-123"
        error_history = {
            "status": {
                "completed": False,
                "messages": ["Node execution failed"]
            }
        }
        
        with patch.object(client, 'get_history', return_value=error_history):
            with pytest.raises(ComfyUIWorkflowError, match="execution failed"):
                client.wait_for_completion(prompt_id, poll_interval=0.1)


class TestGetImage:
    """Test image download"""
    
    def test_get_image_success(self, client):
        """Test successful image download"""
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        
        with patch.object(client, '_make_request', return_value=mock_response):
            image_data = client.get_image("output.png")
            
            assert image_data == b"fake_image_data"
            call_args = client._make_request.call_args
            assert call_args[0][0] == 'GET'
            assert call_args[0][1] == '/view'
    
    def test_get_image_with_subfolder(self, client):
        """Test image download with subfolder"""
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        
        with patch.object(client, '_make_request', return_value=mock_response):
            image_data = client.get_image(
                "output.png",
                subfolder="temp",
                folder_type="temp"
            )
            
            assert image_data == b"fake_image_data"
            call_args = client._make_request.call_args
            params = call_args[1]['params']
            assert params['subfolder'] == "temp"
            assert params['type'] == "temp"
    
    def test_get_image_connection_error(self, client):
        """Test image download with connection error"""
        with patch.object(
            client,
            '_make_request',
            side_effect=ComfyUIConnectionError("Connection failed")
        ):
            with pytest.raises(ComfyUIConnectionError):
                client.get_image("output.png")


class TestUploadImage:
    """Test image upload"""
    
    def test_upload_image_success(self, client):
        """Test successful image upload"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "name": "uploaded.png",
            "subfolder": ""
        }
        
        image_data = b"fake_image_data"
        
        with patch.object(client, '_make_request', return_value=mock_response):
            result = client.upload_image(image_data, "test.png")
            
            assert result["name"] == "uploaded.png"
            call_args = client._make_request.call_args
            assert call_args[0][0] == 'POST'
            assert call_args[0][1] == '/upload/image'
            assert 'files' in call_args[1]
    
    def test_upload_image_with_subfolder(self, client):
        """Test image upload with subfolder"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "name": "uploaded.png",
            "subfolder": "custom"
        }
        
        image_data = b"fake_image_data"
        
        with patch.object(client, '_make_request', return_value=mock_response):
            result = client.upload_image(
                image_data,
                "test.png",
                subfolder="custom",
                overwrite=False
            )
            
            assert result["subfolder"] == "custom"
            call_args = client._make_request.call_args
            data = call_args[1]['data']
            assert data['subfolder'] == "custom"
            assert data['overwrite'] == "false"
    
    def test_upload_image_connection_error(self, client):
        """Test image upload with connection error"""
        with patch.object(
            client,
            '_make_request',
            side_effect=ComfyUIConnectionError("Connection failed")
        ):
            with pytest.raises(ComfyUIConnectionError):
                client.upload_image(b"data", "test.png")


class TestGetOutputs:
    """Test retrieving all outputs from a workflow"""
    
    def test_get_outputs_success(self, client):
        """Test successful output retrieval"""
        prompt_id = "test-prompt-123"
        mock_history = {
            "outputs": {
                "9": {
                    "images": [
                        {
                            "filename": "output_00001.png",
                            "subfolder": "",
                            "type": "output"
                        },
                        {
                            "filename": "output_00002.png",
                            "subfolder": "temp",
                            "type": "temp"
                        }
                    ]
                }
            }
        }
        
        with patch.object(client, 'get_history', return_value=mock_history):
            with patch.object(client, 'get_image', return_value=b"image_data"):
                outputs = client.get_outputs(prompt_id)
                
                assert len(outputs) == 2
                assert outputs[0]['filename'] == "output_00001.png"
                assert outputs[0]['data'] == b"image_data"
                assert outputs[1]['filename'] == "output_00002.png"
                assert outputs[1]['subfolder'] == "temp"
    
    def test_get_outputs_no_outputs(self, client):
        """Test output retrieval when no outputs exist"""
        with patch.object(client, 'get_history', return_value={}):
            with pytest.raises(ComfyUIWorkflowError, match="No outputs found"):
                client.get_outputs("test-prompt-123")
    
    def test_get_outputs_download_error(self, client):
        """Test output retrieval with download error"""
        mock_history = {
            "outputs": {
                "9": {
                    "images": [
                        {
                            "filename": "output.png",
                            "subfolder": "",
                            "type": "output"
                        }
                    ]
                }
            }
        }
        
        with patch.object(client, 'get_history', return_value=mock_history):
            with patch.object(
                client,
                'get_image',
                side_effect=ComfyUIConnectionError("Download failed")
            ):
                with pytest.raises(ComfyUIConnectionError):
                    client.get_outputs("test-prompt-123")


class TestMakeRequest:
    """Test HTTP request handling with retries"""
    
    def test_make_request_success(self, client):
        """Test successful HTTP request"""
        mock_response = Mock()
        mock_response.status_code = 200
        
        with patch.object(client.session, 'request', return_value=mock_response):
            response = client._make_request('GET', '/test')
            
            assert response.status_code == 200
    
    def test_make_request_retry_success(self, client):
        """Test request succeeds after retry"""
        mock_response = Mock()
        mock_response.status_code = 200
        
        # First call fails, second succeeds
        with patch.object(
            client.session,
            'request',
            side_effect=[
                requests.exceptions.ConnectionError("Failed"),
                mock_response
            ]
        ):
            response = client._make_request('GET', '/test')
            
            assert response.status_code == 200
            assert client.session.request.call_count == 2
    
    def test_make_request_all_retries_fail(self, client):
        """Test request fails after all retries"""
        with patch.object(
            client.session,
            'request',
            side_effect=requests.exceptions.ConnectionError("Failed")
        ):
            with pytest.raises(ComfyUIConnectionError, match="Failed to connect"):
                client._make_request('GET', '/test')
            
            # Should retry max_retries times
            assert client.session.request.call_count == client.max_retries
    
    def test_make_request_http_error(self, client):
        """Test request with HTTP error status"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "Server error"
        )
        
        with patch.object(client.session, 'request', return_value=mock_response):
            with pytest.raises(ComfyUIConnectionError):
                client._make_request('GET', '/test')


class TestHealthCheck:
    """Test server health check"""
    
    def test_health_check_success(self, client):
        """Test successful health check"""
        mock_response = Mock()
        mock_response.status_code = 200
        
        with patch.object(client, '_make_request', return_value=mock_response):
            assert client.health_check() is True
    
    def test_health_check_failure(self, client):
        """Test failed health check"""
        with patch.object(
            client,
            '_make_request',
            side_effect=ComfyUIConnectionError("Connection failed")
        ):
            assert client.health_check() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
