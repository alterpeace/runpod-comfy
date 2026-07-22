"""
Tests for RunPod lifecycle management tools.

These tests verify the basic structure and functionality of the lifecycle
management CLI tools without making actual API calls.
"""

import sys
import os
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add parent directory to path to import lifecycle modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lifecycle'))


class TestPodManager:
    """Test PodManager class."""
    
    @patch('runpod_pods.runpod')
    def test_pod_manager_init_with_api_key(self, mock_runpod):
        """Test PodManager initialization with API key."""
        from runpod_pods import PodManager
        
        manager = PodManager(api_key="test_key")
        assert manager.api_key == "test_key"
        assert mock_runpod.api_key == "test_key"
    
    @patch.dict(os.environ, {'RUNPOD_API_KEY': 'env_key'})
    @patch('runpod_pods.runpod')
    def test_pod_manager_init_from_env(self, mock_runpod):
        """Test PodManager initialization from environment."""
        from runpod_pods import PodManager
        
        manager = PodManager()
        assert manager.api_key == "env_key"
    
    @patch.dict(os.environ, {}, clear=True)
    @patch('runpod_pods.runpod')
    def test_pod_manager_init_no_key_exits(self, mock_runpod):
        """Test PodManager exits when no API key is provided."""
        from runpod_pods import PodManager
        
        with pytest.raises(SystemExit):
            PodManager()
    
    @patch('runpod_pods.runpod')
    def test_create_pod_with_minimal_config(self, mock_runpod):
        """Test creating a pod with minimal configuration."""
        from runpod_pods import PodManager
        
        mock_runpod.create_pod.return_value = {
            'id': 'pod123',
            'desiredStatus': 'RUNNING',
            'machine': {'gpuDisplayName': 'RTX A4000'}
        }
        
        manager = PodManager(api_key="test_key")
        
        # Mock input to auto-confirm
        with patch('builtins.input', return_value='yes'):
            result = manager.create_pod(
                name="test-pod",
                gpu_type="RTX A4000",
                image="test/image:latest",
                spot=True
            )
        
        assert result['id'] == 'pod123'
        assert mock_runpod.create_pod.called
    
    @patch('runpod_pods.runpod')
    def test_create_pod_cancelled(self, mock_runpod):
        """Test creating a pod can be cancelled."""
        from runpod_pods import PodManager
        
        manager = PodManager(api_key="test_key")
        
        # Mock input to cancel
        with patch('builtins.input', return_value='no'):
            result = manager.create_pod(
                name="test-pod",
                gpu_type="RTX A4000",
                image="test/image:latest",
                spot=True
            )
        
        assert result['status'] == 'cancelled'
        assert not mock_runpod.create_pod.called
    
    @patch('runpod_pods.runpod')
    def test_terminate_pod(self, mock_runpod):
        """Test terminating a pod."""
        from runpod_pods import PodManager
        
        mock_runpod.terminate_pod.return_value = {'status': 'terminated'}
        
        manager = PodManager(api_key="test_key")
        
        with patch('builtins.input', return_value='yes'):
            result = manager.terminate_pod("pod123")
        
        assert mock_runpod.terminate_pod.called
        mock_runpod.terminate_pod.assert_called_with("pod123")
    
    @patch('runpod_pods.runpod')
    def test_list_pods(self, mock_runpod):
        """Test listing pods."""
        from runpod_pods import PodManager
        
        mock_runpod.get_pods.return_value = [
            {
                'id': 'pod1',
                'name': 'test-pod-1',
                'desiredStatus': 'RUNNING',
                'machine': {'gpuDisplayName': 'RTX A4000', 'costPerHr': 0.40}
            },
            {
                'id': 'pod2',
                'name': 'test-pod-2',
                'desiredStatus': 'STOPPED',
                'machine': {'gpuDisplayName': 'RTX 4090', 'costPerHr': 0.60}
            }
        ]
        
        manager = PodManager(api_key="test_key")
        result = manager.list_pods(json_output=True)
        
        assert len(result) == 2
        assert result[0]['name'] == 'test-pod-1'
        assert result[1]['name'] == 'test-pod-2'
    
    @patch('runpod_pods.runpod')
    def test_estimate_cost(self, mock_runpod):
        """Test cost estimation."""
        from runpod_pods import PodManager
        
        manager = PodManager(api_key="test_key")
        
        # Test known GPU types
        assert manager._estimate_cost("RTX A4000", spot=True) == 0.40
        assert manager._estimate_cost("RTX A4000", spot=False) == 0.80
        assert manager._estimate_cost("RTX 4090", spot=True) == 0.60
        
        # Test unknown GPU type (should return default)
        assert manager._estimate_cost("Unknown GPU", spot=True) == 0.50


class TestServerlessManager:
    """Test ServerlessManager class."""
    
    @patch('runpod_serverless.runpod')
    def test_serverless_manager_init(self, mock_runpod):
        """Test ServerlessManager initialization."""
        from runpod_serverless import ServerlessManager
        
        manager = ServerlessManager(api_key="test_key")
        assert manager.api_key == "test_key"
    
    @patch('runpod_serverless.runpod')
    def test_create_endpoint(self, mock_runpod):
        """Test creating a serverless endpoint."""
        from runpod_serverless import ServerlessManager
        
        mock_runpod.create_endpoint.return_value = {
            'id': 'endpoint123',
            'status': 'RUNNING'
        }
        
        manager = ServerlessManager(api_key="test_key")
        
        with patch('builtins.input', return_value='yes'):
            result = manager.create_endpoint(
                name="test-endpoint",
                gpu_type="RTX A4000",
                image="test/image:latest"
            )
        
        assert result['id'] == 'endpoint123'
        assert mock_runpod.create_endpoint.called
    
    @patch('runpod_serverless.runpod')
    def test_delete_endpoint(self, mock_runpod):
        """Test deleting an endpoint."""
        from runpod_serverless import ServerlessManager
        
        mock_runpod.delete_endpoint.return_value = {'status': 'deleted'}
        
        manager = ServerlessManager(api_key="test_key")
        
        with patch('builtins.input', return_value='yes'):
            result = manager.delete_endpoint("endpoint123")
        
        assert mock_runpod.delete_endpoint.called
    
    @patch('runpod_serverless.runpod')
    def test_list_endpoints(self, mock_runpod):
        """Test listing endpoints."""
        from runpod_serverless import ServerlessManager
        
        mock_runpod.get_endpoints.return_value = [
            {
                'id': 'ep1',
                'name': 'test-endpoint-1',
                'status': 'RUNNING',
                'gpuTypeId': 'RTX A4000',
                'workersRunning': 2
            }
        ]
        
        manager = ServerlessManager(api_key="test_key")
        result = manager.list_endpoints(json_output=True)
        
        assert len(result) == 1
        assert result[0]['name'] == 'test-endpoint-1'
    
    @patch('runpod_serverless.runpod')
    def test_invoke_endpoint_with_file(self, mock_runpod, tmp_path):
        """Test invoking endpoint with workflow file."""
        from runpod_serverless import ServerlessManager
        
        # Create a temporary workflow file
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"prompt": "test"}')
        
        # Mock endpoint and job
        mock_job = Mock()
        mock_job.job_id = "job123"
        mock_endpoint = Mock()
        mock_endpoint.run.return_value = mock_job
        
        mock_runpod.Endpoint.return_value = mock_endpoint
        
        manager = ServerlessManager(api_key="test_key")
        result = manager.invoke_endpoint(
            endpoint_id="endpoint123",
            workflow_file=str(workflow_file),
            json_output=True
        )
        
        assert result['job_id'] == 'job123'
        assert mock_endpoint.run.called
    
    @patch('runpod_serverless.runpod')
    def test_estimate_execution_cost(self, mock_runpod):
        """Test execution cost estimation."""
        from runpod_serverless import ServerlessManager
        
        manager = ServerlessManager(api_key="test_key")
        
        # Test known GPU types
        assert manager._estimate_execution_cost("RTX A4000") == 0.01
        assert manager._estimate_execution_cost("RTX 4090") == 0.015
        
        # Test unknown GPU type (should return default)
        assert manager._estimate_execution_cost("Unknown GPU") == 0.01


class TestCLIArguments:
    """Test CLI argument parsing."""
    
    @patch('runpod_pods.runpod')
    def test_pods_cli_create_command(self, mock_runpod):
        """Test pods CLI create command parsing."""
        from runpod_pods import main
        
        test_args = [
            'runpod_pods.py',
            'create',
            '--name', 'test-pod',
            '--gpu', 'RTX A4000',
            '--image', 'test/image:latest',
            '--spot'
        ]
        
        mock_runpod.create_pod.return_value = {'id': 'pod123'}
        
        with patch('sys.argv', test_args):
            with patch('builtins.input', return_value='yes'):
                # Should not raise an exception
                try:
                    main()
                except SystemExit:
                    pass  # Expected when command completes
    
    @patch('runpod_serverless.runpod')
    def test_serverless_cli_list_command(self, mock_runpod):
        """Test serverless CLI list command parsing."""
        from runpod_serverless import main
        
        test_args = [
            'runpod_serverless.py',
            'list',
            '--json'
        ]
        
        mock_runpod.get_endpoints.return_value = []
        
        with patch('sys.argv', test_args):
            # Should not raise an exception
            try:
                main()
            except SystemExit:
                pass  # Expected when command completes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
