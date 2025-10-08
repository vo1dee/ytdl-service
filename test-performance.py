#!/usr/bin/env python3
"""
Performance Testing Script for Containerized YouTube Download Service
This script performs comprehensive performance testing of the containerized service.
"""

import requests
import time
import threading
import statistics
import json
import sys
import argparse
import psutil
import docker
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
import matplotlib.pyplot as plt
import numpy as np


class PerformanceTester:
    def __init__(self, base_url: str, api_key: str, container_name: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.container_name = container_name
        self.docker_client = None
        self.container = None
        
        # Initialize Docker client if container name provided
        if container_name:
            try:
                self.docker_client = docker.from_env()
                self.container = self.docker_client.containers.get(container_name)
            except Exception as e:
                print(f"Warning: Could not connect to Docker container: {e}")
        
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'X-API-Key': api_key
        })
        
        self.results = {
            'response_times': [],
            'throughput_tests': [],
            'resource_usage': [],
            'concurrent_tests': [],
            'stress_tests': []
        }

    def log_result(self, test_type: str, data: Dict[Any, Any]):
        """Log test result"""
        self.results[test_type].append(data)
        print(f"✓ {test_type}: {data}")

    def get_container_stats(self) -> Dict[str, Any]:
        """Get container resource usage statistics"""
        if not self.container:
            return {}
        
        try:
            stats = self.container.stats(stream=False)
            
            # Calculate CPU percentage
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * \
                             len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            
            # Calculate memory usage
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100.0
            
            # Network I/O
            network_rx = 0
            network_tx = 0
            if 'networks' in stats:
                for interface in stats['networks'].values():
                    network_rx += interface['rx_bytes']
                    network_tx += interface['tx_bytes']
            
            # Block I/O
            block_read = 0
            block_write = 0
            if 'blkio_stats' in stats and 'io_service_bytes_recursive' in stats['blkio_stats']:
                for entry in stats['blkio_stats']['io_service_bytes_recursive']:
                    if entry['op'] == 'Read':
                        block_read += entry['value']
                    elif entry['op'] == 'Write':
                        block_write += entry['value']
            
            return {
                'cpu_percent': round(cpu_percent, 2),
                'memory_usage_mb': round(memory_usage / 1024 / 1024, 2),
                'memory_percent': round(memory_percent, 2),
                'network_rx_mb': round(network_rx / 1024 / 1024, 2),
                'network_tx_mb': round(network_tx / 1024 / 1024, 2),
                'block_read_mb': round(block_read / 1024 / 1024, 2),
                'block_write_mb': round(block_write / 1024 / 1024, 2),
                'timestamp': time.time()
            }
        except Exception as e:
            print(f"Error getting container stats: {e}")
            return {}

    def test_response_times(self, num_requests: int = 100) -> Dict[str, Any]:
        """Test API response times"""
        print(f"\n🔍 Testing response times with {num_requests} requests...")
        
        response_times = []
        errors = 0
        
        for i in range(num_requests):
            try:
                start_time = time.time()
                response = self.session.get(f"{self.base_url}/health", timeout=30)
                end_time = time.time()
                
                if response.status_code == 200:
                    response_times.append(end_time - start_time)
                else:
                    errors += 1
                    
            except Exception as e:
                errors += 1
                print(f"Request {i+1} failed: {e}")
            
            if (i + 1) % 10 == 0:
                print(f"Completed {i+1}/{num_requests} requests...")
        
        if response_times:
            result = {
                'total_requests': num_requests,
                'successful_requests': len(response_times),
                'errors': errors,
                'min_time': min(response_times),
                'max_time': max(response_times),
                'avg_time': statistics.mean(response_times),
                'median_time': statistics.median(response_times),
                'p95_time': np.percentile(response_times, 95),
                'p99_time': np.percentile(response_times, 99),
                'std_dev': statistics.stdev(response_times) if len(response_times) > 1 else 0
            }
            
            self.log_result('response_times', result)
            return result
        else:
            print("❌ No successful requests completed")
            return {}

    def test_throughput(self, duration_seconds: int = 60) -> Dict[str, Any]:
        """Test API throughput over time"""
        print(f"\n🚀 Testing throughput for {duration_seconds} seconds...")
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        request_count = 0
        errors = 0
        response_times = []
        
        while time.time() < end_time:
            try:
                req_start = time.time()
                response = self.session.get(f"{self.base_url}/health", timeout=10)
                req_end = time.time()
                
                if response.status_code == 200:
                    request_count += 1
                    response_times.append(req_end - req_start)
                else:
                    errors += 1
                    
            except Exception as e:
                errors += 1
            
            # Brief pause to prevent overwhelming
            time.sleep(0.01)
        
        actual_duration = time.time() - start_time
        throughput = request_count / actual_duration
        
        result = {
            'duration_seconds': actual_duration,
            'total_requests': request_count,
            'errors': errors,
            'requests_per_second': throughput,
            'avg_response_time': statistics.mean(response_times) if response_times else 0,
            'error_rate': (errors / (request_count + errors)) * 100 if (request_count + errors) > 0 else 0
        }
        
        self.log_result('throughput_tests', result)
        return result

    def test_concurrent_requests(self, num_threads: int = 10, requests_per_thread: int = 20) -> Dict[str, Any]:
        """Test concurrent request handling"""
        print(f"\n🔄 Testing concurrent requests: {num_threads} threads, {requests_per_thread} requests each...")
        
        def make_requests(thread_id: int) -> Tuple[int, int, List[float]]:
            """Make requests in a single thread"""
            successful = 0
            errors = 0
            times = []
            
            for i in range(requests_per_thread):
                try:
                    start_time = time.time()
                    response = self.session.get(f"{self.base_url}/health", timeout=30)
                    end_time = time.time()
                    
                    if response.status_code == 200:
                        successful += 1
                        times.append(end_time - start_time)
                    else:
                        errors += 1
                        
                except Exception as e:
                    errors += 1
            
            return successful, errors, times
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(make_requests, i) for i in range(num_threads)]
            
            total_successful = 0
            total_errors = 0
            all_times = []
            
            for future in as_completed(futures):
                successful, errors, times = future.result()
                total_successful += successful
                total_errors += errors
                all_times.extend(times)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        result = {
            'num_threads': num_threads,
            'requests_per_thread': requests_per_thread,
            'total_requests': num_threads * requests_per_thread,
            'successful_requests': total_successful,
            'errors': total_errors,
            'duration_seconds': total_duration,
            'requests_per_second': total_successful / total_duration,
            'avg_response_time': statistics.mean(all_times) if all_times else 0,
            'max_response_time': max(all_times) if all_times else 0,
            'error_rate': (total_errors / (total_successful + total_errors)) * 100 if (total_successful + total_errors) > 0 else 0
        }
        
        self.log_result('concurrent_tests', result)
        return result

    def test_resource_usage_under_load(self, duration_seconds: int = 30) -> Dict[str, Any]:
        """Monitor resource usage under load"""
        print(f"\n📊 Monitoring resource usage under load for {duration_seconds} seconds...")
        
        if not self.container:
            print("⚠️  Container monitoring not available")
            return {}
        
        resource_samples = []
        
        def collect_stats():
            """Collect resource statistics"""
            end_time = time.time() + duration_seconds
            while time.time() < end_time:
                stats = self.get_container_stats()
                if stats:
                    resource_samples.append(stats)
                time.sleep(1)
        
        def generate_load():
            """Generate API load"""
            end_time = time.time() + duration_seconds
            while time.time() < end_time:
                try:
                    self.session.get(f"{self.base_url}/health", timeout=5)
                    self.session.get(f"{self.base_url}/files", timeout=5)
                except:
                    pass
                time.sleep(0.1)
        
        # Start monitoring and load generation
        monitor_thread = threading.Thread(target=collect_stats)
        load_thread = threading.Thread(target=generate_load)
        
        monitor_thread.start()
        load_thread.start()
        
        monitor_thread.join()
        load_thread.join()
        
        if resource_samples:
            cpu_values = [s['cpu_percent'] for s in resource_samples]
            memory_values = [s['memory_usage_mb'] for s in resource_samples]
            
            result = {
                'duration_seconds': duration_seconds,
                'samples_collected': len(resource_samples),
                'cpu_avg': statistics.mean(cpu_values),
                'cpu_max': max(cpu_values),
                'cpu_min': min(cpu_values),
                'memory_avg_mb': statistics.mean(memory_values),
                'memory_max_mb': max(memory_values),
                'memory_min_mb': min(memory_values),
                'network_rx_total_mb': resource_samples[-1]['network_rx_mb'] - resource_samples[0]['network_rx_mb'],
                'network_tx_total_mb': resource_samples[-1]['network_tx_mb'] - resource_samples[0]['network_tx_mb']
            }
            
            self.log_result('resource_usage', result)
            return result
        else:
            print("❌ No resource samples collected")
            return {}

    def test_stress_limits(self) -> Dict[str, Any]:
        """Test service under stress conditions"""
        print(f"\n💥 Running stress test...")
        
        # Gradually increase load and measure breaking point
        thread_counts = [1, 5, 10, 20, 50, 100]
        results = []
        
        for thread_count in thread_counts:
            print(f"Testing with {thread_count} concurrent threads...")
            
            def stress_worker():
                """Worker function for stress testing"""
                success_count = 0
                error_count = 0
                
                for _ in range(10):  # 10 requests per thread
                    try:
                        response = self.session.get(f"{self.base_url}/health", timeout=10)
                        if response.status_code == 200:
                            success_count += 1
                        else:
                            error_count += 1
                    except:
                        error_count += 1
                
                return success_count, error_count
            
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [executor.submit(stress_worker) for _ in range(thread_count)]
                
                total_success = 0
                total_errors = 0
                
                for future in as_completed(futures):
                    success, errors = future.result()
                    total_success += success
                    total_errors += errors
            
            end_time = time.time()
            duration = end_time - start_time
            
            error_rate = (total_errors / (total_success + total_errors)) * 100 if (total_success + total_errors) > 0 else 100
            
            thread_result = {
                'thread_count': thread_count,
                'total_requests': total_success + total_errors,
                'successful_requests': total_success,
                'errors': total_errors,
                'error_rate': error_rate,
                'duration_seconds': duration,
                'requests_per_second': (total_success + total_errors) / duration
            }
            
            results.append(thread_result)
            
            # Stop if error rate becomes too high
            if error_rate > 50:
                print(f"Stopping stress test at {thread_count} threads due to high error rate ({error_rate:.1f}%)")
                break
            
            time.sleep(2)  # Brief pause between tests
        
        stress_result = {
            'test_results': results,
            'max_stable_threads': max([r['thread_count'] for r in results if r['error_rate'] < 10], default=0),
            'breaking_point_threads': next((r['thread_count'] for r in results if r['error_rate'] > 25), None)
        }
        
        self.log_result('stress_tests', stress_result)
        return stress_result

    def generate_report(self) -> str:
        """Generate performance test report"""
        report = []
        report.append("=" * 80)
        report.append("PERFORMANCE TEST REPORT")
        report.append("=" * 80)
        report.append(f"Test Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Service URL: {self.base_url}")
        report.append(f"Container: {self.container_name or 'Not monitored'}")
        report.append("")
        
        # Response Times Summary
        if self.results['response_times']:
            rt = self.results['response_times'][0]
            report.append("📈 RESPONSE TIMES")
            report.append("-" * 40)
            report.append(f"Total Requests: {rt['total_requests']}")
            report.append(f"Successful: {rt['successful_requests']}")
            report.append(f"Average: {rt['avg_time']:.3f}s")
            report.append(f"Median: {rt['median_time']:.3f}s")
            report.append(f"95th Percentile: {rt['p95_time']:.3f}s")
            report.append(f"99th Percentile: {rt['p99_time']:.3f}s")
            report.append(f"Min/Max: {rt['min_time']:.3f}s / {rt['max_time']:.3f}s")
            report.append("")
        
        # Throughput Summary
        if self.results['throughput_tests']:
            th = self.results['throughput_tests'][0]
            report.append("🚀 THROUGHPUT")
            report.append("-" * 40)
            report.append(f"Duration: {th['duration_seconds']:.1f}s")
            report.append(f"Requests/Second: {th['requests_per_second']:.2f}")
            report.append(f"Total Requests: {th['total_requests']}")
            report.append(f"Error Rate: {th['error_rate']:.2f}%")
            report.append("")
        
        # Concurrent Requests Summary
        if self.results['concurrent_tests']:
            ct = self.results['concurrent_tests'][0]
            report.append("🔄 CONCURRENT REQUESTS")
            report.append("-" * 40)
            report.append(f"Threads: {ct['num_threads']}")
            report.append(f"Requests per Thread: {ct['requests_per_thread']}")
            report.append(f"Success Rate: {100 - ct['error_rate']:.1f}%")
            report.append(f"Throughput: {ct['requests_per_second']:.2f} req/s")
            report.append(f"Avg Response Time: {ct['avg_response_time']:.3f}s")
            report.append("")
        
        # Resource Usage Summary
        if self.results['resource_usage']:
            ru = self.results['resource_usage'][0]
            report.append("📊 RESOURCE USAGE")
            report.append("-" * 40)
            report.append(f"CPU Average: {ru['cpu_avg']:.1f}%")
            report.append(f"CPU Peak: {ru['cpu_max']:.1f}%")
            report.append(f"Memory Average: {ru['memory_avg_mb']:.1f} MB")
            report.append(f"Memory Peak: {ru['memory_max_mb']:.1f} MB")
            report.append(f"Network RX: {ru['network_rx_total_mb']:.2f} MB")
            report.append(f"Network TX: {ru['network_tx_total_mb']:.2f} MB")
            report.append("")
        
        # Stress Test Summary
        if self.results['stress_tests']:
            st = self.results['stress_tests'][0]
            report.append("💥 STRESS TEST")
            report.append("-" * 40)
            report.append(f"Max Stable Threads: {st['max_stable_threads']}")
            report.append(f"Breaking Point: {st['breaking_point_threads'] or 'Not reached'}")
            report.append("")
        
        # Performance Recommendations
        report.append("💡 RECOMMENDATIONS")
        report.append("-" * 40)
        
        if self.results['response_times']:
            rt = self.results['response_times'][0]
            if rt['avg_time'] > 1.0:
                report.append("⚠️  Average response time > 1s - consider optimization")
            if rt['p95_time'] > 2.0:
                report.append("⚠️  95th percentile > 2s - investigate slow requests")
        
        if self.results['resource_usage']:
            ru = self.results['resource_usage'][0]
            if ru['cpu_avg'] > 80:
                report.append("⚠️  High CPU usage - consider scaling or optimization")
            if ru['memory_avg_mb'] > 1000:
                report.append("⚠️  High memory usage - monitor for memory leaks")
        
        if self.results['concurrent_tests']:
            ct = self.results['concurrent_tests'][0]
            if ct['error_rate'] > 5:
                report.append("⚠️  High error rate under concurrency - investigate bottlenecks")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)

    def run_all_tests(self):
        """Run all performance tests"""
        print("🏁 Starting comprehensive performance tests...")
        
        # Basic response time test
        self.test_response_times(100)
        
        # Throughput test
        self.test_throughput(30)
        
        # Concurrent request test
        self.test_concurrent_requests(10, 20)
        
        # Resource usage monitoring
        self.test_resource_usage_under_load(30)
        
        # Stress test
        self.test_stress_limits()
        
        # Generate and display report
        report = self.generate_report()
        print("\n" + report)
        
        # Save report to file
        with open('performance_report.txt', 'w') as f:
            f.write(report)
        
        print(f"\n📄 Full report saved to: performance_report.txt")


def main():
    parser = argparse.ArgumentParser(description='Performance test for containerized YouTube Download Service')
    parser.add_argument('--url', default='http://localhost:8000',
                       help='Base URL of the service (default: http://localhost:8000)')
    parser.add_argument('--api-key', required=True,
                       help='API key for authentication')
    parser.add_argument('--container', 
                       help='Docker container name for resource monitoring')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick tests with reduced duration/requests')
    
    args = parser.parse_args()
    
    tester = PerformanceTester(args.url, args.api_key, args.container)
    
    try:
        if args.quick:
            print("🏃 Running quick performance tests...")
            tester.test_response_times(20)
            tester.test_throughput(10)
            tester.test_concurrent_requests(5, 10)
        else:
            tester.run_all_tests()
        
        print("\n🎉 Performance testing completed!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Performance tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error during performance testing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()