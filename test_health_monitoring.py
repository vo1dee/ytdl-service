#!/usr/bin/env python3

"""
Test script for container health monitoring functionality
This script validates the enhanced health check features
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
from pathlib import Path

def test_health_check_script():
    """Test the health check script functionality"""
    print("Testing health check script...")
    
    # Test quick health check
    try:
        result = subprocess.run(
            ["./health_check.sh", "--quick"],
            capture_output=True,
            text=True,
            timeout=30
        )
        print(f"Quick health check exit code: {result.returncode}")
        if result.stdout:
            print(f"Quick health check output: {result.stdout[:200]}...")
        if result.stderr:
            print(f"Quick health check errors: {result.stderr[:200]}...")
    except subprocess.TimeoutExpired:
        print("Quick health check timed out")
    except Exception as e:
        print(f"Quick health check failed: {e}")
    
    # Test verbose health check
    try:
        result = subprocess.run(
            ["./health_check.sh", "--verbose"],
            capture_output=True,
            text=True,
            timeout=60
        )
        print(f"Verbose health check exit code: {result.returncode}")
        if result.stdout:
            print(f"Verbose health check output: {result.stdout[:500]}...")
    except subprocess.TimeoutExpired:
        print("Verbose health check timed out")
    except Exception as e:
        print(f"Verbose health check failed: {e}")

def test_dependency_checks():
    """Test dependency availability checks"""
    print("\nTesting dependency checks...")
    
    # Test FFmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        print(f"FFmpeg available: {result.returncode == 0}")
        if result.returncode == 0:
            version_line = result.stdout.decode().split('\n')[0]
            print(f"FFmpeg version: {version_line}")
    except Exception as e:
        print(f"FFmpeg check failed: {e}")
    
    # Test yt-dlp
    try:
        import yt_dlp
        print(f"yt-dlp available: True")
        print(f"yt-dlp version: {yt_dlp.version.__version__}")
    except ImportError:
        print("yt-dlp not available")
    except Exception as e:
        print(f"yt-dlp check failed: {e}")
    
    # Test psutil
    try:
        import psutil
        print(f"psutil available: True")
        print(f"psutil version: {psutil.__version__}")
    except ImportError:
        print("psutil not available")
    except Exception as e:
        print(f"psutil check failed: {e}")

def test_disk_space_monitoring():
    """Test disk space monitoring functionality"""
    print("\nTesting disk space monitoring...")
    
    # Create temporary directory to test
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            statvfs = os.statvfs(temp_dir)
            free_bytes = statvfs.f_frsize * statvfs.f_bavail
            total_bytes = statvfs.f_frsize * statvfs.f_blocks
            used_bytes = total_bytes - free_bytes
            
            usage_info = {
                "total_gb": round(total_bytes / (1024**3), 2),
                "used_gb": round(used_bytes / (1024**3), 2),
                "free_gb": round(free_bytes / (1024**3), 2),
                "usage_percent": round((used_bytes / total_bytes) * 100, 1)
            }
            
            print(f"Disk space monitoring working: {json.dumps(usage_info, indent=2)}")
        except Exception as e:
            print(f"Disk space monitoring failed: {e}")

def test_directory_permissions():
    """Test directory permission checks"""
    print("\nTesting directory permission checks...")
    
    # Test with temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir) / "test_downloads"
        test_dir.mkdir()
        
        # Test read/write permissions
        readable = os.access(test_dir, os.R_OK)
        writable = os.access(test_dir, os.W_OK)
        exists = os.path.exists(test_dir)
        
        print(f"Directory exists: {exists}")
        print(f"Directory readable: {readable}")
        print(f"Directory writable: {writable}")
        
        # Test file creation
        try:
            test_file = test_dir / "test.txt"
            test_file.write_text("test")
            print(f"File creation successful: {test_file.exists()}")
            test_file.unlink()
        except Exception as e:
            print(f"File creation failed: {e}")

def test_system_resources():
    """Test system resource monitoring"""
    print("\nTesting system resource monitoring...")
    
    try:
        import psutil
        
        # Memory info
        memory = psutil.virtual_memory()
        print(f"Memory total: {round(memory.total / (1024**3), 2)} GB")
        print(f"Memory available: {round(memory.available / (1024**3), 2)} GB")
        print(f"Memory usage: {memory.percent}%")
        
        # CPU info
        cpu_percent = psutil.cpu_percent(interval=1)
        print(f"CPU usage: {cpu_percent}%")
        print(f"CPU count: {psutil.cpu_count()}")
        
        # Process info
        current_process = psutil.Process()
        print(f"Current process PID: {current_process.pid}")
        print(f"Process memory: {round(current_process.memory_info().rss / (1024**2), 2)} MB")
        
    except ImportError:
        print("psutil not available for system resource monitoring")
    except Exception as e:
        print(f"System resource monitoring failed: {e}")

def test_network_connectivity():
    """Test network connectivity checks"""
    print("\nTesting network connectivity...")
    
    try:
        import socket
        import urllib.request
        
        # Test DNS resolution
        try:
            socket.gethostbyname('www.youtube.com')
            print("DNS resolution: OK")
        except Exception as e:
            print(f"DNS resolution failed: {e}")
        
        # Test HTTP connectivity
        try:
            urllib.request.urlopen('https://www.youtube.com', timeout=5)
            print("HTTP connectivity: OK")
        except Exception as e:
            print(f"HTTP connectivity failed: {e}")
            
    except Exception as e:
        print(f"Network connectivity test failed: {e}")

def main():
    """Run all health monitoring tests"""
    print("=== Container Health Monitoring Test Suite ===")
    print(f"Running tests at: {os.getcwd()}")
    print()
    
    # Check if health check script exists
    if not os.path.exists("health_check.sh"):
        print("ERROR: health_check.sh not found in current directory")
        return 1
    
    # Run all tests
    test_health_check_script()
    test_dependency_checks()
    test_disk_space_monitoring()
    test_directory_permissions()
    test_system_resources()
    test_network_connectivity()
    
    print("\n=== Test Suite Completed ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())