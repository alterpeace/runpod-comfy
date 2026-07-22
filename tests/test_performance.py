"""
Performance tests for handler execution.

Tests cold start timing, warm start timing, and performance characteristics.
"""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from io import BytesIO
from PIL import Image

from handler import handler


@pytest.fixture
def sample_workflow():
    """Load sample workflow"""
    workflow_path = Path(__file__).parent.parent / 'examples' / 'text_to_image_simple.json'
    with open(workflow_path) as f:
        return json.load(f)


@pytest.fixture
def mock_comfyui_client():
    """Mock ComfyUI client for performance testing"""
    with patch('handler.comfyui_client') as mock_client:
        mock_client.health_check.return_value = True
        mock_client.queue_prompt.return_value = 'test-prompt-perf'
        
        # Simulate realistic timing
        def wait_with_delay(*args, **kwargs):
            time.sleep(0.1)  # Simulate processing time
            return {
                'outputs': {
                    '9': {
                        'images': [
                            {
                                'filename': 'output.png',
                                'subfolder': '',
                                'type': 'output'
                            }
                        ]
                    }
                }
            }
        
        mock_client.wait_for_completion.side_effect = wait_with_delay
        
        # Mock output
        test_image = Image.new('RGB', (512, 512), color='blue')
        buffer = BytesIO()
        test_image.save(buffer, format='PNG')
        image_data = buffer.getvalue()
        
        mock_client.get_outputs.return_value = [
            {
                'filename': 'output.png',
                'subfolder': '',
                'type': 'output',
                'data': image_data,
                'node_id': '9'
            }
        ]
        
        yield mock_client


class TestColdStartPerformance:
    """Test cold start performance characteristics"""
    
    def test_cold_start_timing(self, sample_workflow, mock_comfyui_client):
        """Test cold start execution time"""
        job = {
            'id': 'perf-cold-001',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        start_time = time.time()
        result = handler(job)
        elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        
        # Cold start should complete reasonably fast (with mocked ComfyUI)
        assert elapsed < 5.0, f"Cold start took {elapsed:.2f}s, expected < 5s"
        
        # Check reported execution time
        assert 'execution_time' in result['metadata']
        assert result['metadata']['execution_time'] < 5.0
    
    def test_initialization_overhead(self, sample_workflow, mock_comfyui_client):
        """Test initialization overhead"""
        # First call - includes initialization
        job1 = {
            'id': 'perf-cold-002',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        start1 = time.time()
        result1 = handler(job1)
        time1 = time.time() - start1
        
        assert result1['status'] == 'success'
        
        # Initialization should be fast with mocked client
        assert time1 < 5.0


class TestWarmStartPerformance:
    """Test warm start performance characteristics"""
    
    def test_warm_start_timing(self, sample_workflow, mock_comfyui_client):
        """Test warm start execution time"""
        # First call to warm up
        job1 = {
            'id': 'perf-warm-001',
            'input': {
                'workflow': sample_workflow
            }
        }
        handler(job1)
        
        # Second call - warm start
        job2 = {
            'id': 'perf-warm-002',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        start_time = time.time()
        result = handler(job2)
        elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        
        # Warm start should be fast
        assert elapsed < 3.0, f"Warm start took {elapsed:.2f}s, expected < 3s"
    
    def test_consecutive_executions(self, sample_workflow, mock_comfyui_client):
        """Test performance of consecutive executions"""
        execution_times = []
        
        for i in range(5):
            job = {
                'id': f'perf-warm-{i:03d}',
                'input': {
                    'workflow': sample_workflow
                }
            }
            
            start_time = time.time()
            result = handler(job)
            elapsed = time.time() - start_time
            
            assert result['status'] == 'success'
            execution_times.append(elapsed)
        
        # All executions should be reasonably fast
        for i, exec_time in enumerate(execution_times):
            assert exec_time < 3.0, f"Execution {i} took {exec_time:.2f}s"
        
        # Average should be good
        avg_time = sum(execution_times) / len(execution_times)
        assert avg_time < 2.0, f"Average execution time {avg_time:.2f}s"


class TestWorkflowComplexity:
    """Test performance with different workflow complexities"""
    
    def test_simple_workflow_performance(self, sample_workflow, mock_comfyui_client):
        """Test performance with simple workflow"""
        job = {
            'id': 'perf-simple-001',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        start_time = time.time()
        result = handler(job)
        elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        assert elapsed < 3.0
    
    def test_complex_workflow_performance(self, mock_comfyui_client):
        """Test performance with complex workflow (many nodes)"""
        # Create a workflow with many nodes
        complex_workflow = {}
        for i in range(50):
            complex_workflow[str(i)] = {
                'class_type': 'TestNode',
                'inputs': {
                    'value': i
                }
            }
        
        job = {
            'id': 'perf-complex-001',
            'input': {
                'workflow': complex_workflow
            }
        }
        
        start_time = time.time()
        result = handler(job)
        elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        
        # Complex workflow should still complete reasonably fast
        assert elapsed < 5.0, f"Complex workflow took {elapsed:.2f}s"
        
        # Check node count in metadata
        assert result['metadata']['node_count'] == 50
    
    def test_workflow_with_multiple_outputs(self, mock_comfyui_client):
        """Test performance with workflow generating multiple outputs"""
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
            for i in range(10)
        ]
        
        workflow = {
            '1': {
                'class_type': 'TestNode',
                'inputs': {}
            }
        }
        
        job = {
            'id': 'perf-multi-001',
            'input': {
                'workflow': workflow
            }
        }
        
        start_time = time.time()
        result = handler(job)
        elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        assert len(result['output']['images']) == 10
        
        # Should handle multiple outputs efficiently
        assert elapsed < 5.0


class TestMemoryEfficiency:
    """Test memory efficiency of handler"""
    
    def test_large_image_handling(self, sample_workflow, mock_comfyui_client):
        """Test handling of large output images"""
        # Create a large image (4K resolution)
        large_image = Image.new('RGB', (3840, 2160), color='red')
        buffer = BytesIO()
        large_image.save(buffer, format='PNG')
        large_image_data = buffer.getvalue()
        
        mock_comfyui_client.get_outputs.return_value = [
            {
                'filename': 'large_output.png',
                'subfolder': '',
                'type': 'output',
                'data': large_image_data,
                'node_id': '9'
            }
        ]
        
        job = {
            'id': 'perf-large-001',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        start_time = time.time()
        result = handler(job)
        elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        
        # Should handle large images without significant slowdown
        assert elapsed < 5.0
    
    def test_multiple_large_images(self, sample_workflow, mock_comfyui_client):
        """Test handling of multiple large output images"""
        # Create multiple large images
        large_image = Image.new('RGB', (2048, 2048), color='blue')
        buffer = BytesIO()
        large_image.save(buffer, format='PNG')
        large_image_data = buffer.getvalue()
        
        mock_comfyui_client.get_outputs.return_value = [
            {
                'filename': f'large_output_{i}.png',
                'subfolder': '',
                'type': 'output',
                'data': large_image_data,
                'node_id': str(i)
            }
            for i in range(5)
        ]
        
        job = {
            'id': 'perf-multi-large-001',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        start_time = time.time()
        result = handler(job)
        elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        assert len(result['output']['images']) == 5
        
        # Should handle multiple large images efficiently
        assert elapsed < 10.0


class TestTimeoutHandling:
    """Test timeout handling performance"""
    
    def test_custom_timeout_respected(self, sample_workflow, mock_comfyui_client):
        """Test that custom timeout is properly passed through"""
        job = {
            'id': 'perf-timeout-001',
            'input': {
                'workflow': sample_workflow,
                'timeout': 600
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        
        # Verify timeout was passed to wait_for_completion
        mock_comfyui_client.wait_for_completion.assert_called_once()
        call_kwargs = mock_comfyui_client.wait_for_completion.call_args[1]
        assert call_kwargs.get('max_wait_time') == 600
    
    def test_default_timeout_used(self, sample_workflow, mock_comfyui_client):
        """Test that default timeout is used when not specified"""
        job = {
            'id': 'perf-timeout-002',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        with patch('handler.TIMEOUT', 300):
            result = handler(job)
        
        assert result['status'] == 'success'
        
        # Verify default timeout was used
        mock_comfyui_client.wait_for_completion.assert_called_once()
        call_kwargs = mock_comfyui_client.wait_for_completion.call_args[1]
        assert call_kwargs.get('max_wait_time') == 300


class TestMetadataAccuracy:
    """Test accuracy of performance metadata"""
    
    def test_execution_time_accuracy(self, sample_workflow, mock_comfyui_client):
        """Test that reported execution time is accurate"""
        job = {
            'id': 'perf-meta-001',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        start_time = time.time()
        result = handler(job)
        actual_elapsed = time.time() - start_time
        
        assert result['status'] == 'success'
        
        reported_time = result['metadata']['execution_time']
        
        # Reported time should be close to actual time (within 0.5s)
        assert abs(reported_time - actual_elapsed) < 0.5
    
    def test_metadata_completeness(self, sample_workflow, mock_comfyui_client):
        """Test that all performance metadata is included"""
        job = {
            'id': 'perf-meta-002',
            'input': {
                'workflow': sample_workflow
            }
        }
        
        result = handler(job)
        
        assert result['status'] == 'success'
        
        metadata = result['metadata']
        
        # Check all expected metadata fields
        assert 'job_id' in metadata
        assert 'prompt_id' in metadata
        assert 'execution_time' in metadata
        assert 'node_count' in metadata
        assert 'output_count' in metadata
        assert 'storage_type' in metadata
        
        # Check types
        assert isinstance(metadata['execution_time'], (int, float))
        assert isinstance(metadata['node_count'], int)
        assert isinstance(metadata['output_count'], int)
