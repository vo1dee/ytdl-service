#!/usr/bin/env python3
"""
API Endpoint Testing Script for Containerized YouTube Download Service
This script performs comprehensive API testing within the container environment.
"""

import requests
import json
import time
import sys
import os
from typing import Dict, Any, Optional
import argparse


class APITester:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'X-API-Key': api_key
        })
        self.test_results = []

    def log_test(self, test_name: str, success: bool, message: str = ""):
        """Log test result"""
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {test_name}")
        if message:
            print(f"    {message}")
        
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message
        })

    def test_health_endpoint(self) -> bool:
        """Test the health check endpoint"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'ok':
                    self.log_test("Health Endpoint", True, f"Response: {data}")
                    return True
                else:
                    self.log_test("Health Endpoint", False, f"Invalid status: {data}")
                    return False
            else:
                self.log_test("Health Endpoint", False, f"Status code: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Health Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_authentication(self) -> bool:
        """Test API authentication"""
        # Test without API key
        try:
            response = requests.post(
                f"{self.base_url}/download",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                timeout=10
            )
            
            if response.status_code == 401:
                self.log_test("Authentication - No Key", True, "Correctly rejected request without API key")
            else:
                self.log_test("Authentication - No Key", False, f"Expected 401, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Authentication - No Key", False, f"Exception: {str(e)}")
            return False

        # Test with invalid API key
        try:
            response = requests.post(
                f"{self.base_url}/download",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                headers={'X-API-Key': 'invalid-key', 'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 401:
                self.log_test("Authentication - Invalid Key", True, "Correctly rejected invalid API key")
            else:
                self.log_test("Authentication - Invalid Key", False, f"Expected 401, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Authentication - Invalid Key", False, f"Exception: {str(e)}")
            return False

        # Test with valid API key (should get validation error for invalid URL)
        try:
            response = self.session.post(
                f"{self.base_url}/download",
                json={"url": "invalid-url"},
                timeout=10
            )
            
            if response.status_code in [400, 422]:
                self.log_test("Authentication - Valid Key", True, "Valid API key accepted")
                return True
            else:
                self.log_test("Authentication - Valid Key", False, f"Unexpected status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Authentication - Valid Key", False, f"Exception: {str(e)}")
            return False

    def test_download_endpoint_validation(self) -> bool:
        """Test download endpoint input validation"""
        test_cases = [
            {
                "name": "Missing URL",
                "data": {},
                "expected_status": [400, 422]
            },
            {
                "name": "Empty URL",
                "data": {"url": ""},
                "expected_status": [400, 422]
            },
            {
                "name": "Invalid URL Format",
                "data": {"url": "not-a-url"},
                "expected_status": [400, 422]
            },
            {
                "name": "Non-YouTube URL",
                "data": {"url": "https://example.com"},
                "expected_status": [400, 422]
            }
        ]

        all_passed = True
        for case in test_cases:
            try:
                response = self.session.post(
                    f"{self.base_url}/download",
                    json=case["data"],
                    timeout=10
                )
                
                if response.status_code in case["expected_status"]:
                    self.log_test(f"Validation - {case['name']}", True, 
                                f"Status: {response.status_code}")
                else:
                    self.log_test(f"Validation - {case['name']}", False, 
                                f"Expected {case['expected_status']}, got {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Validation - {case['name']}", False, f"Exception: {str(e)}")
                all_passed = False

        return all_passed

    def test_files_endpoint(self) -> bool:
        """Test files listing endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/files", timeout=10)
            
            if response.status_code == 200:
                files = response.json()
                if isinstance(files, list):
                    self.log_test("Files Endpoint", True, f"Found {len(files)} files")
                    return True
                else:
                    self.log_test("Files Endpoint", False, "Response is not a list")
                    return False
            else:
                self.log_test("Files Endpoint", False, f"Status code: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Files Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_file_download_endpoint(self) -> bool:
        """Test individual file download endpoint"""
        try:
            # First get list of files
            response = self.session.get(f"{self.base_url}/files", timeout=10)
            if response.status_code != 200:
                self.log_test("File Download - List Files", False, "Could not get file list")
                return False

            files = response.json()
            
            if not files:
                # Test with non-existent file
                response = self.session.get(f"{self.base_url}/files/nonexistent.mp4", timeout=10)
                if response.status_code == 404:
                    self.log_test("File Download - Non-existent", True, "Correctly returned 404 for non-existent file")
                    return True
                else:
                    self.log_test("File Download - Non-existent", False, f"Expected 404, got {response.status_code}")
                    return False
            else:
                # Test with existing file
                filename = files[0]
                response = self.session.get(f"{self.base_url}/files/{filename}", timeout=10)
                if response.status_code == 200:
                    self.log_test("File Download - Existing", True, f"Successfully accessed {filename}")
                    return True
                else:
                    self.log_test("File Download - Existing", False, f"Status: {response.status_code}")
                    return False
                    
        except Exception as e:
            self.log_test("File Download", False, f"Exception: {str(e)}")
            return False

    def test_cors_headers(self) -> bool:
        """Test CORS headers if present"""
        try:
            response = requests.options(f"{self.base_url}/health", timeout=10)
            
            # CORS headers are optional, so we just check if the OPTIONS method is handled
            if response.status_code in [200, 204, 405]:
                cors_headers = {
                    'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
                    'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
                    'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers')
                }
                
                if any(cors_headers.values()):
                    self.log_test("CORS Headers", True, f"CORS configured: {cors_headers}")
                else:
                    self.log_test("CORS Headers", True, "No CORS headers (may be intentional)")
                return True
            else:
                self.log_test("CORS Headers", False, f"OPTIONS request failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("CORS Headers", False, f"Exception: {str(e)}")
            return False

    def test_response_times(self) -> bool:
        """Test API response times"""
        endpoints = [
            ("/health", "GET"),
            ("/files", "GET")
        ]
        
        all_passed = True
        for endpoint, method in endpoints:
            try:
                start_time = time.time()
                
                if method == "GET":
                    response = self.session.get(f"{self.base_url}{endpoint}", timeout=10)
                else:
                    response = self.session.post(f"{self.base_url}{endpoint}", timeout=10)
                
                response_time = time.time() - start_time
                
                if response_time < 2.0:  # 2 second threshold
                    self.log_test(f"Response Time - {endpoint}", True, 
                                f"{response_time:.3f}s (good)")
                else:
                    self.log_test(f"Response Time - {endpoint}", False, 
                                f"{response_time:.3f}s (slow)")
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Response Time - {endpoint}", False, f"Exception: {str(e)}")
                all_passed = False

        return all_passed

    def run_all_tests(self) -> bool:
        """Run all API tests"""
        print(f"Starting API endpoint tests for {self.base_url}")
        print("=" * 60)
        
        tests = [
            self.test_health_endpoint,
            self.test_authentication,
            self.test_download_endpoint_validation,
            self.test_files_endpoint,
            self.test_file_download_endpoint,
            self.test_cors_headers,
            self.test_response_times
        ]
        
        all_passed = True
        for test in tests:
            try:
                if not test():
                    all_passed = False
            except Exception as e:
                print(f"Test {test.__name__} failed with exception: {e}")
                all_passed = False
            print()  # Add spacing between test groups
        
        return all_passed

    def print_summary(self):
        """Print test summary"""
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for result in self.test_results if result['success'])
        total = len(self.test_results)
        
        print(f"Total tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success rate: {(passed/total)*100:.1f}%")
        
        if total - passed > 0:
            print("\nFailed tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['message']}")


def main():
    parser = argparse.ArgumentParser(description='Test API endpoints for containerized YouTube Download Service')
    parser.add_argument('--url', default='http://localhost:8000', 
                       help='Base URL of the service (default: http://localhost:8000)')
    parser.add_argument('--api-key', required=True,
                       help='API key for authentication')
    parser.add_argument('--wait', type=int, default=0,
                       help='Wait time in seconds before starting tests')
    
    args = parser.parse_args()
    
    if args.wait > 0:
        print(f"Waiting {args.wait} seconds before starting tests...")
        time.sleep(args.wait)
    
    tester = APITester(args.url, args.api_key)
    
    try:
        success = tester.run_all_tests()
        tester.print_summary()
        
        if success:
            print("\n🎉 All API tests passed!")
            sys.exit(0)
        else:
            print("\n❌ Some API tests failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()