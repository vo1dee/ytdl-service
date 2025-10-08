#!/bin/bash

# Test Container Functionality Script
# This script validates the Docker container functionality for the YouTube Download Service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="ytdl-service-test"
IMAGE_NAME="ytdl-service"
TEST_PORT="8001"
API_KEY="test-api-key-12345"
DOWNLOADS_DIR="./test-downloads"
LOGS_DIR="./test-logs"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to cleanup test resources
cleanup() {
    print_status "Cleaning up test resources..."
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    rm -rf $DOWNLOADS_DIR $LOGS_DIR 2>/dev/null || true
}

# Function to wait for service to be ready
wait_for_service() {
    local max_attempts=30
    local attempt=1
    
    print_status "Waiting for service to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://localhost:$TEST_PORT/health" > /dev/null 2>&1; then
            print_status "Service is ready!"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "Service failed to start within expected time"
    return 1
}

# Function to test API endpoints
test_api_endpoints() {
    print_status "Testing API endpoints..."
    
    # Test health endpoint
    print_status "Testing health endpoint..."
    response=$(curl -s "http://localhost:$TEST_PORT/health")
    if echo "$response" | grep -q "status.*ok"; then
        print_status "✓ Health endpoint working"
    else
        print_error "✗ Health endpoint failed"
        return 1
    fi
    
    # Test API key validation
    print_status "Testing API key validation..."
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$TEST_PORT/download" \
        -H "Content-Type: application/json" \
        -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}')
    
    if [ "$status_code" = "401" ]; then
        print_status "✓ API key validation working (unauthorized without key)"
    else
        print_error "✗ API key validation failed (expected 401, got $status_code)"
        return 1
    fi
    
    # Test with valid API key
    print_status "Testing with valid API key..."
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$TEST_PORT/download" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $API_KEY" \
        -d '{"url": "invalid-url"}')
    
    if [ "$status_code" = "400" ] || [ "$status_code" = "422" ]; then
        print_status "✓ API accepts valid key (rejected invalid URL as expected)"
    else
        print_error "✗ API key acceptance failed (expected 400/422, got $status_code)"
        return 1
    fi
    
    print_status "All API endpoint tests passed!"
}

# Function to test volume mounts
test_volume_mounts() {
    print_status "Testing volume mounts..."
    
    # Check if downloads directory is mounted
    if docker exec $CONTAINER_NAME test -d "/opt/ytdl_service/downloads"; then
        print_status "✓ Downloads directory exists in container"
    else
        print_error "✗ Downloads directory not found in container"
        return 1
    fi
    
    # Check if logs directory is mounted
    if docker exec $CONTAINER_NAME test -d "/var/log"; then
        print_status "✓ Logs directory exists in container"
    else
        print_error "✗ Logs directory not found in container"
        return 1
    fi
    
    # Test file creation in downloads directory
    docker exec $CONTAINER_NAME touch "/opt/ytdl_service/downloads/test-file.txt"
    if [ -f "$DOWNLOADS_DIR/test-file.txt" ]; then
        print_status "✓ Downloads volume mount working (file created on host)"
        rm -f "$DOWNLOADS_DIR/test-file.txt"
    else
        print_error "✗ Downloads volume mount failed"
        return 1
    fi
    
    print_status "Volume mount tests passed!"
}

# Function to test container security
test_container_security() {
    print_status "Testing container security..."
    
    # Check if running as non-root user
    user_info=$(docker exec $CONTAINER_NAME id)
    if echo "$user_info" | grep -q "uid=1000(ytdl)"; then
        print_status "✓ Container running as non-root user (ytdl)"
    else
        print_warning "Container user info: $user_info"
        print_error "✗ Container not running as expected non-root user"
        return 1
    fi
    
    # Check file permissions
    perms=$(docker exec $CONTAINER_NAME stat -c "%a" "/opt/ytdl_service/downloads")
    if [ "$perms" = "755" ] || [ "$perms" = "775" ]; then
        print_status "✓ Downloads directory has appropriate permissions ($perms)"
    else
        print_warning "Downloads directory permissions: $perms"
    fi
    
    print_status "Container security tests passed!"
}

# Function to test container resource usage
test_resource_usage() {
    print_status "Testing container resource usage..."
    
    # Get container stats
    stats=$(docker stats $CONTAINER_NAME --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}")
    print_status "Container resource usage:"
    echo "$stats"
    
    # Check if container is responsive under load
    print_status "Testing service responsiveness..."
    for i in {1..5}; do
        response_time=$(curl -s -w "%{time_total}" -o /dev/null "http://localhost:$TEST_PORT/health")
        if (( $(echo "$response_time < 2.0" | bc -l) )); then
            print_status "✓ Response $i: ${response_time}s (good)"
        else
            print_warning "Response $i: ${response_time}s (slow)"
        fi
    done
    
    print_status "Resource usage tests completed!"
}

# Main test execution
main() {
    print_status "Starting container functionality tests..."
    
    # Trap cleanup on exit
    trap cleanup EXIT
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running or not accessible"
        exit 1
    fi
    
    # Check if image exists
    if ! docker image inspect $IMAGE_NAME > /dev/null 2>&1; then
        print_error "Docker image '$IMAGE_NAME' not found. Please build it first with: docker build -t $IMAGE_NAME ."
        exit 1
    fi
    
    # Create test directories
    mkdir -p $DOWNLOADS_DIR $LOGS_DIR
    
    # Stop and remove any existing test container
    cleanup
    
    # Run the container
    print_status "Starting test container..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p $TEST_PORT:8000 \
        -v "$(pwd)/$DOWNLOADS_DIR:/opt/ytdl_service/downloads" \
        -v "$(pwd)/$LOGS_DIR:/var/log" \
        -e YTDL_SERVICE_API_KEY="$API_KEY" \
        -e PORT=8000 \
        $IMAGE_NAME
    
    # Wait for service to be ready
    if ! wait_for_service; then
        print_error "Service failed to start"
        docker logs $CONTAINER_NAME
        exit 1
    fi
    
    # Run tests
    test_api_endpoints
    test_volume_mounts
    test_container_security
    test_resource_usage
    
    print_status "All container functionality tests passed! ✓"
}

# Check if bc is available for floating point comparison
if ! command -v bc &> /dev/null; then
    print_warning "bc command not found, skipping response time validation"
fi

# Run main function
main "$@"