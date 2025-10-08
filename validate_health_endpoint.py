#!/usr/bin/env python3

"""
Validation script for the enhanced health endpoint
This script tests the health endpoint functionality without running the full service
"""

import json
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock

def mock_environment():
    """Set up mock environment for testing"""
    # Mock environment variables
    os.environ.update({
        'DOWNLOADS_DIR': '/tmp/test_downloads',
        'LOGS_DIR': '/tmp/test_logs',
        'API_KEY_FILE': '/tmp/test_api_key.txt',
        'PORT': '8000',
        'YTDL_MAX_RETRIES': '3',
        'YTDL_RETRY_DELAY': '1',
        'YTDLP_UPDATE_INTERVAL': '86400',
        'CLEANUP_INTERVAL': '3600',
        'FILE_MAX_AGE': '604800'
    })
    
    # Create test directories
    os.makedirs('/tmp/test_downloads', exist_ok=True)
    os.makedirs('/tmp/test_logs', exist_ok=True)
    
    # Create test API key file
    with open('/tmp/test_api_key.txt', 'w') as f:
        f.write('test_api_key_12345')

def test_health_endpoint_structure():
    """Test the health endpoint response structure"""
    print("Testing health endpoint response structure...")
    
    try:
        # Mock the required modules and variables
        with patch('yt_dlp.version.__version__', '2025.5.22'), \
             patch('subprocess.run') as mock_subprocess, \
             patch('os.statvfs') as mock_statvfs, \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.cpu_percent') as mock_cpu, \
             patch('psutil.Process') as mock_process, \
             patch('socket.gethostbyname') as mock_dns, \
             patch('urllib.request.urlopen') as mock_http:
            
            # Configure mocks
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = b'ffmpeg version 6.1.1'
            
            # Mock disk usage
            mock_statvfs_result = MagicMock()
            mock_statvfs_result.f_frsize = 4096
            mock_statvfs_result.f_bavail = 1000000  # Available blocks
            mock_statvfs_result.f_blocks = 2000000  # Total blocks
            mock_statvfs.return_value = mock_statvfs_result
            
            # Mock memory
            mock_memory_result = MagicMock()
            mock_memory_result.total = 4 * 1024**3  # 4GB
            mock_memory_result.available = 2 * 1024**3  # 2GB
            mock_memory_result.percent = 50.0
            mock_memory_result.free = 2 * 1024**3  # 2GB
            mock_memory.return_value = mock_memory_result
            
            # Mock CPU
            mock_cpu.return_value = 25.5
            
            # Mock process
            mock_process_instance = MagicMock()
            mock_process_instance.pid = 12345
            mock_process_instance.memory_info.return_value.rss = 100 * 1024**2  # 100MB
            mock_process_instance.cpu_percent.return_value = 5.2
            mock_process_instance.num_threads.return_value = 8
            mock_process_instance.open_files.return_value = []
            mock_process_instance.connections.return_value = []
            mock_process.return_value = mock_process_instance
            
            # Import and test the health check function
            sys.path.insert(0, '.')
            
            # Mock the global variables that would be set by the main module
            import download_service
            download_service.DOWNLOADS_DIR = '/tmp/test_downloads'
            download_service.LOGS_DIR = '/tmp/test_logs'
            download_service.API_KEY_FILE = '/tmp/test_api_key.txt'
            download_service.PORT = 8000
            download_service.YTDL_MAX_RETRIES = 3
            download_service.YTDL_RETRY_DELAY = 1
            download_service.YTDLP_UPDATE_INTERVAL = 86400
            download_service.CLEANUP_INTERVAL = 3600
            download_service.FILE_MAX_AGE = 604800
            download_service.last_update_check = 0
            download_service.last_update_status = None
            download_service.validated_config = {
                'YTDL_SERVICE_API_KEY': None,
                'DOWNLOADS_DIR': '/tmp/test_downloads',
                'LOGS_DIR': '/tmp/test_logs',
                'API_KEY_FILE': '/tmp/test_api_key.txt',
                'PORT': '8000'
            }
            
            # Import asyncio to run the async function
            import asyncio
            
            # Run the health check
            result = asyncio.run(download_service.health_check())
            
            # Validate response structure
            required_fields = [
                'status', 'container_health', 'system_info', 'directories',
                'disk_usage', 'system_resources', 'process_health',
                'network_health', 'configuration', 'timestamp'
            ]
            
            for field in required_fields:
                if field not in result:
                    print(f"❌ Missing required field: {field}")
                    return False
                else:
                    print(f"✅ Found required field: {field}")
            
            # Validate container_health structure
            container_health_fields = [
                'ffmpeg_available', 'ytdlp_available', 'ytdlp_functional',
                'api_key_accessible', 'downloads_dir_accessible',
                'logs_dir_accessible', 'disk_space_ok', 'network_connectivity',
                'dns_resolution'
            ]
            
            for field in container_health_fields:
                if field not in result['container_health']:
                    print(f"❌ Missing container_health field: {field}")
                    return False
                else:
                    print(f"✅ Found container_health field: {field}")
            
            # Validate status values
            valid_statuses = ['healthy', 'degraded', 'unhealthy']
            if result['status'] not in valid_statuses:
                print(f"❌ Invalid status: {result['status']}")
                return False
            else:
                print(f"✅ Valid status: {result['status']}")
            
            # Print sample response
            print("\n📋 Sample health response:")
            print(json.dumps(result, indent=2, default=str)[:1000] + "...")
            
            return True
            
    except Exception as e:
        print(f"❌ Health endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_health_check_script_syntax():
    """Test that the health check script has valid syntax"""
    print("\nTesting health check script syntax...")
    
    try:
        import subprocess
        result = subprocess.run(
            ['bash', '-n', 'health_check.sh'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Health check script syntax is valid")
            return True
        else:
            print(f"❌ Health check script syntax error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Could not test script syntax: {e}")
        return False

def cleanup_test_environment():
    """Clean up test files and directories"""
    try:
        import shutil
        for path in ['/tmp/test_downloads', '/tmp/test_logs', '/tmp/test_api_key.txt']:
            if os.path.exists(path):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        print("🧹 Cleaned up test environment")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

def main():
    """Run all validation tests"""
    print("=== Health Monitoring Validation ===")
    
    # Set up test environment
    mock_environment()
    
    tests_passed = 0
    total_tests = 2
    
    # Run tests
    if test_health_check_script_syntax():
        tests_passed += 1
    
    if test_health_endpoint_structure():
        tests_passed += 1
    
    # Clean up
    cleanup_test_environment()
    
    # Report results
    print(f"\n=== Results: {tests_passed}/{total_tests} tests passed ===")
    
    if tests_passed == total_tests:
        print("🎉 All validation tests passed!")
        return 0
    else:
        print("❌ Some validation tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())