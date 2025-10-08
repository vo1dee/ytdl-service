# Testing and Validation Guide

This document describes the comprehensive testing suite for the containerized YouTube Download Service.

## Overview

The testing suite includes multiple scripts that validate different aspects of the containerized service:

- **Container Functionality Tests** - Validates basic container operations
- **Docker Compose Integration Tests** - Tests orchestrated deployment
- **API Endpoint Tests** - Comprehensive API testing within container environment
- **Volume Mount Validation** - Tests persistent storage functionality
- **Performance Tests** - Measures service performance under various loads

## Prerequisites

Before running the tests, ensure you have:

- Docker and Docker Compose installed and running
- Python 3 with required packages (`requests`, `docker`, `psutil`, `numpy`, `matplotlib`)
- `curl` command available
- `bc` command (optional, for calculations)
- The Docker image built: `docker build -t ytdl-service .`

## Quick Start

Run all tests with a single command:

```bash
./run-all-tests.sh
```

For a faster test run with reduced duration:

```bash
./run-all-tests.sh --quick
```

## Individual Test Scripts

### 1. Container Functionality Tests

```bash
./test-container.sh
```

**What it tests:**
- Container startup and health
- API endpoint accessibility
- Volume mount functionality
- Container security (non-root user)
- Resource usage monitoring

**Requirements:** Docker image `ytdl-service` must exist

### 2. Docker Compose Integration Tests

```bash
./test-docker-compose.sh
```

**What it tests:**
- Docker Compose service orchestration
- Service networking and connectivity
- Volume mounts in Compose environment
- Health checks and restart behavior
- Logging functionality

**Requirements:** `docker-compose.yml` file must exist

### 3. API Endpoint Tests

```bash
python3 test-api-endpoints.py --url http://localhost:8000 --api-key YOUR_API_KEY
```

**What it tests:**
- Health endpoint functionality
- Authentication and authorization
- Input validation for download requests
- File listing and download endpoints
- CORS headers (if configured)
- Response time performance

**Options:**
- `--url`: Service URL (default: http://localhost:8000)
- `--api-key`: API key for authentication (required)
- `--wait`: Wait time before starting tests

### 4. Volume Mount Validation Tests

```bash
./test-volume-mounts.sh
```

**What it tests:**
- Downloads directory volume mount
- Logs directory volume mount
- Config directory volume mount
- File persistence across container restarts
- File permissions and ownership
- Performance of volume operations
- Edge cases (special characters, large files)

### 5. Performance Tests

```bash
python3 test-performance.py --url http://localhost:8000 --api-key YOUR_API_KEY --container CONTAINER_NAME
```

**What it tests:**
- Response time analysis
- Throughput measurement
- Concurrent request handling
- Resource usage under load
- Stress testing with increasing load

**Options:**
- `--url`: Service URL (default: http://localhost:8000)
- `--api-key`: API key for authentication (required)
- `--container`: Docker container name for resource monitoring
- `--quick`: Run reduced tests for faster execution

## Test Results and Reports

### Console Output

All tests provide real-time console output with:
- ✓ Green checkmarks for passed tests
- ✗ Red X marks for failed tests
- ⚠️ Yellow warnings for non-critical issues
- Detailed error messages and debugging information

### Performance Report

The performance tests generate a detailed report saved to `performance_report.txt` containing:
- Response time statistics (min, max, average, percentiles)
- Throughput measurements
- Resource usage analysis
- Stress test results
- Performance recommendations

### Exit Codes

All scripts return appropriate exit codes:
- `0`: All tests passed
- `1`: One or more tests failed

## Running Specific Test Categories

Use the master script with specific options:

```bash
# Run only container tests
./run-all-tests.sh --container

# Run only Docker Compose tests
./run-all-tests.sh --compose

# Run only volume tests
./run-all-tests.sh --volume

# Run only API tests
./run-all-tests.sh --api

# Run only performance tests
./run-all-tests.sh --performance
```

## Troubleshooting

### Common Issues

1. **Docker image not found**
   ```bash
   docker build -t ytdl-service .
   ```

2. **Permission denied on scripts**
   ```bash
   chmod +x *.sh *.py
   ```

3. **Python packages missing**
   ```bash
   pip3 install requests docker psutil numpy matplotlib
   ```

4. **Port conflicts**
   - Tests use ports 8001, 8002, 8003 for testing
   - Ensure these ports are available

### Test Failures

If tests fail:

1. **Check Docker logs**
   ```bash
   docker logs CONTAINER_NAME
   ```

2. **Verify service health**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Check volume mounts**
   ```bash
   docker inspect CONTAINER_NAME
   ```

4. **Review test output** for specific error messages

### Performance Issues

If performance tests show poor results:

1. **Check system resources**
   ```bash
   docker stats
   ```

2. **Review container configuration**
   - Memory limits
   - CPU constraints
   - Volume mount performance

3. **Optimize application settings**
   - Increase worker processes
   - Tune timeout values
   - Optimize database queries

## Continuous Integration

For CI/CD pipelines, use:

```bash
# Quick tests suitable for CI
./run-all-tests.sh --quick

# Or run specific critical tests
./test-container.sh && ./test-api-endpoints.py --url http://localhost:8000 --api-key test-key
```

## Test Coverage

The testing suite covers:

- ✅ Container build and startup
- ✅ Service health and availability
- ✅ API authentication and authorization
- ✅ Volume persistence and permissions
- ✅ Network connectivity
- ✅ Resource usage and performance
- ✅ Concurrent request handling
- ✅ Error handling and recovery
- ✅ Docker Compose orchestration
- ✅ Security best practices

## Contributing

When adding new tests:

1. Follow the existing naming convention: `test-*.sh` or `test-*.py`
2. Include proper error handling and cleanup
3. Add colored output for better readability
4. Update this documentation
5. Ensure tests are idempotent and can run multiple times

## Support

For issues with the testing suite:

1. Check the troubleshooting section above
2. Review individual test script output
3. Verify all prerequisites are met
4. Check Docker and system logs for additional context