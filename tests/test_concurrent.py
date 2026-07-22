"""
Concurrent job handling tests.

Tests the handler's ability to handle multiple concurrent requests
and maintain isolation between jobs.
"""

import json
import time
import pytest
import threading
from pathlib import Path
from unittest.mock import Mock, patch
from io import BytesIO
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

from handler import handler


@pytest.fixture
def sample_workflow():
    """Load sample workflow"""
    workflow_path = Path(__file__).parent.parent / 'examples' / 'text_to_image_simple.json'
    with open(workflow_path) as f:
        return json.load(f)


@pytest.fixture
def mock_comfyui_client():
    """Mock ComfyUI client for concurrent testing"""
    with patch('handler.comfyui_client') as mock_client:
        mock_client.health_check.return_value = True
        
        # Use a counter to generate unique prompt IDs
        counter = {'value': 0}
        lock = threading.Lock()
        
        def queue_prompt_with_id(workflow):
            with lock:
                counter['value'] += 1
                return f'test-prompt-{counter["value"]:03d}'
        
        mock_client.queue_prompt.side_effect = queue_prompt_with_id
        
        # Simulate realistic timing with some variation
        def wait_with_delay(prompt_id, max_wait_time=300, poll_interval=1):
            time.sleep(0.05 + (hash(prompt_id) % 10) * 0.01)  # 50-150ms
            return {
                'outputs': {
                    '9': {
                        'images': [
                            {
                                'filename': f'output_{prompt_id}.png',
                                'subfolder': '',
                                'type': 'output'
                            }
                        ]
                    }
                }
            }
        
        mock_client.wait_for_completion.side_effect = wait_with_delay
        
        # Mock output with unique data per call
        def get_outputs_unique(prompt_id):
            test_image = Image.new('RGB', (512, 512), color='blue')
            buffer = BytesIO()
            test_image.save(buffer, format='PNG')
            image_data = buffer.getvalue()
            
            return [
                {
                    'filename': f'output_{prompt_id}.png',
                    'subfolder': '',
                    'type': 'output',
                    'data': image_data,
                    'node_id': '9'
                }
            ]
        
        mock_client.get_outputs.side_effect = get_outputs_unique
        
        yield mock_client


class TestConcurrentExecution:
    """Test concurrent job execution"""
    
    def test_two_concurrent_jobs(self, sample_workflow, mock_comfyui_client):
        """Test handling two concurrent jobs"""
        jobs = [
            {
                'id': f'concurrent-001',
                'input': {'workflow': sample_workflow}
            },
            {
                'id': f'concurrent-002',
                'input': {'workflow': sample_workflow}
            }
        ]
        
        results = []
        
        def execute_job(job):
            return handler(job)
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        # Both jobs should succeed
        assert len(results) == 2
        for result in results:
            assert result['status'] == 'success'
        
        # Jobs should have different prompt IDs
        prompt_ids = [r['output']['prompt_id'] for r in results]
        assert len(set(prompt_ids)) == 2
    
    def test_multiple_concurrent_jobs(self, sample_workflow, mock_comfyui_client):
        """Test handling multiple concurrent jobs"""
        num_jobs = 5
        jobs = [
            {
                'id': f'concurrent-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(num_jobs)
        ]
        
        results = []
        
        def execute_job(job):
            return handler(job)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_jobs) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        elapsed = time.time() - start_time
        
        # All jobs should succeed
        assert len(results) == num_jobs
        for result in results:
            assert result['status'] == 'success'
        
        # Jobs should have unique prompt IDs
        prompt_ids = [r['output']['prompt_id'] for r in results]
        assert len(set(prompt_ids)) == num_jobs
        
        # Concurrent execution should be faster than sequential
        # (with mocked delays, should take ~150ms not 750ms)
        assert elapsed < 1.0
    
    def test_concurrent_jobs_with_different_workflows(self, mock_comfyui_client):
        """Test concurrent jobs with different workflow configurations"""
        workflows = [
            {
                '1': {'class_type': 'TestNode', 'inputs': {'value': i}}
            }
            for i in range(3)
        ]
        
        jobs = [
            {
                'id': f'concurrent-diff-{i:03d}',
                'input': {'workflow': workflow}
            }
            for i, workflow in enumerate(workflows)
        ]
        
        def execute_job(job):
            return handler(job)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        # All jobs should succeed
        assert len(results) == 3
        for result in results:
            assert result['status'] == 'success'


class TestJobIsolation:
    """Test isolation between concurrent jobs"""
    
    def test_job_metadata_isolation(self, sample_workflow, mock_comfyui_client):
        """Test that job metadata is properly isolated"""
        jobs = [
            {
                'id': f'isolation-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(3)
        ]
        
        def execute_job(job):
            return handler(job)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        # Each result should have correct job_id
        job_ids = {r['metadata']['job_id'] for r in results}
        assert len(job_ids) == 3
        assert all(f'isolation-{i:03d}' in job_ids for i in range(3))
    
    def test_output_isolation(self, sample_workflow, mock_comfyui_client):
        """Test that outputs are properly isolated between jobs"""
        jobs = [
            {
                'id': f'output-isolation-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(3)
        ]
        
        def execute_job(job):
            return handler(job)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        # Each result should have unique outputs
        for result in results:
            assert result['status'] == 'success'
            assert len(result['output']['images']) > 0
        
        # Filenames should be unique (based on prompt_id)
        all_filenames = []
        for result in results:
            for image in result['output']['images']:
                all_filenames.append(image['filename'])
        
        # All filenames should be unique
        assert len(all_filenames) == len(set(all_filenames))
    
    def test_error_isolation(self, sample_workflow, mock_comfyui_client):
        """Test that errors in one job don't affect others"""
        from comfyui_client import ComfyUIWorkflowError
        
        # Make one job fail
        call_count = {'value': 0}
        lock = threading.Lock()
        
        original_wait = mock_comfyui_client.wait_for_completion.side_effect
        
        def wait_with_selective_failure(prompt_id, max_wait_time=300, poll_interval=1):
            with lock:
                call_count['value'] += 1
                if call_count['value'] == 2:  # Fail the second call
                    raise ComfyUIWorkflowError("Simulated failure")
            return original_wait(prompt_id, max_wait_time, poll_interval)
        
        mock_comfyui_client.wait_for_completion.side_effect = wait_with_selective_failure
        
        jobs = [
            {
                'id': f'error-isolation-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(3)
        ]
        
        def execute_job(job):
            return handler(job)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        # Should have 2 successes and 1 failure
        successes = [r for r in results if r['status'] == 'success']
        failures = [r for r in results if r['status'] == 'error']
        
        assert len(successes) == 2
        assert len(failures) == 1


class TestConcurrentResourceManagement:
    """Test resource management under concurrent load"""
    
    def test_concurrent_cleanup(self, sample_workflow, mock_comfyui_client):
        """Test that cleanup works correctly with concurrent jobs"""
        cleanup_calls = []
        lock = threading.Lock()
        
        def track_cleanup():
            with lock:
                cleanup_calls.append(threading.current_thread().ident)
        
        with patch('handler.cleanup_temp_files', side_effect=track_cleanup) as mock_cleanup:
            
            jobs = [
                {
                    'id': f'cleanup-{i:03d}',
                    'input': {'workflow': sample_workflow}
                }
                for i in range(3)
            ]
            
            def execute_job(job):
                return handler(job)
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(execute_job, job) for job in jobs]
                results = [future.result() for future in as_completed(futures)]
            
            # All jobs should succeed
            for result in results:
                assert result['status'] == 'success'
            
            # Cleanup should be called for each job (at least once per job)
            assert len(cleanup_calls) >= 3
    
    def test_concurrent_storage_operations(self, sample_workflow, mock_comfyui_client, tmp_path):
        """Test concurrent storage operations don't conflict"""
        jobs = [
            {
                'id': f'storage-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(3)
        ]
        
        def execute_job(job):
            return handler(job)
        
        with patch('handler.STORAGE_TYPE', 'volume'):
            with patch('handler.VOLUME_OUTPUT_PATH', str(tmp_path)):
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(execute_job, job) for job in jobs]
                    results = [future.result() for future in as_completed(futures)]
        
        # All jobs should succeed
        for result in results:
            assert result['status'] == 'success'
        
        # All output files should exist
        for result in results:
            for image in result['output']['images']:
                assert Path(image['path']).exists()


class TestConcurrentPerformance:
    """Test performance characteristics under concurrent load"""
    
    def test_concurrent_throughput(self, sample_workflow, mock_comfyui_client):
        """Test throughput with concurrent jobs"""
        num_jobs = 10
        jobs = [
            {
                'id': f'throughput-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(num_jobs)
        ]
        
        def execute_job(job):
            return handler(job)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        elapsed = time.time() - start_time
        
        # All jobs should succeed
        assert len(results) == num_jobs
        for result in results:
            assert result['status'] == 'success'
        
        # Calculate throughput
        throughput = num_jobs / elapsed
        
        # With 5 workers and ~100ms per job, should process ~50 jobs/sec
        # With mocked delays, expect at least 5 jobs/sec
        assert throughput > 5.0, f"Throughput {throughput:.2f} jobs/sec is too low"
    
    def test_concurrent_scaling(self, sample_workflow, mock_comfyui_client):
        """Test that performance scales with worker count"""
        num_jobs = 10
        jobs = [
            {
                'id': f'scaling-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(num_jobs)
        ]
        
        def execute_jobs(max_workers):
            def execute_job(job):
                return handler(job)
            
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(execute_job, job) for job in jobs]
                results = [future.result() for future in as_completed(futures)]
            
            elapsed = time.time() - start_time
            return elapsed, results
        
        # Test with 1 worker
        time_1_worker, results_1 = execute_jobs(1)
        
        # Test with 5 workers
        time_5_workers, results_5 = execute_jobs(5)
        
        # Both should succeed
        assert all(r['status'] == 'success' for r in results_1)
        assert all(r['status'] == 'success' for r in results_5)
        
        # 5 workers should be faster than 1 worker
        # (not necessarily 5x due to overhead, but should be significantly faster)
        assert time_5_workers < time_1_worker * 0.8


class TestConcurrentEdgeCases:
    """Test edge cases in concurrent execution"""
    
    def test_rapid_sequential_jobs(self, sample_workflow, mock_comfyui_client):
        """Test rapid sequential job submission"""
        results = []
        
        for i in range(10):
            job = {
                'id': f'rapid-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            result = handler(job)
            results.append(result)
        
        # All jobs should succeed
        assert len(results) == 10
        for result in results:
            assert result['status'] == 'success'
        
        # All should have unique prompt IDs
        prompt_ids = [r['output']['prompt_id'] for r in results]
        assert len(set(prompt_ids)) == 10
    
    def test_mixed_success_and_failure(self, sample_workflow, mock_comfyui_client):
        """Test handling mixed success and failure scenarios"""
        from comfyui_client import ComfyUIWorkflowError
        
        # Make every other job fail
        call_count = {'value': 0}
        lock = threading.Lock()
        
        original_wait = mock_comfyui_client.wait_for_completion.side_effect
        
        def wait_with_alternating_failure(prompt_id, max_wait_time=300, poll_interval=1):
            with lock:
                call_count['value'] += 1
                should_fail = call_count['value'] % 2 == 0
            
            if should_fail:
                raise ComfyUIWorkflowError("Alternating failure")
            return original_wait(prompt_id, max_wait_time, poll_interval)
        
        mock_comfyui_client.wait_for_completion.side_effect = wait_with_alternating_failure
        
        jobs = [
            {
                'id': f'mixed-{i:03d}',
                'input': {'workflow': sample_workflow}
            }
            for i in range(6)
        ]
        
        def execute_job(job):
            return handler(job)
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(execute_job, job) for job in jobs]
            results = [future.result() for future in as_completed(futures)]
        
        # Should have 3 successes and 3 failures
        successes = [r for r in results if r['status'] == 'success']
        failures = [r for r in results if r['status'] == 'error']
        
        assert len(successes) == 3
        assert len(failures) == 3
