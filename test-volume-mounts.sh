#!/bin/bash

# Volume Mount Validation Tests
# This script validates Docker volume mount functionality for the YouTube Download Service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="ytdl-volume-test"
IMAGE_NAME="ytdl-service"
TEST_DOWNLOADS_DIR="./test-volume-downloads"
TEST_LOGS_DIR="./test-volume-logs"
TEST_CONFIG_DIR="./test-volume-config"

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
    print_status "Cleaning up volume test resources..."
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    rm -rf $TEST_DOWNLOADS_DIR $TEST_LOGS_DIR $TEST_CONFIG_DIR 2>/dev/null || true
}

# Function to create test directories
setup_test_directories() {
    print_status "Setting up test directories..."
    
    mkdir -p $TEST_DOWNLOADS_DIR $TEST_LOGS_DIR $TEST_CONFIG_DIR
    
    # Create some test files on host
    echo "Host test file for downloads" > "$TEST_DOWNLOADS_DIR/host-test.txt"
    echo "Host test file for logs" > "$TEST_LOGS_DIR/host-log.txt"
    echo "test-api-key-volume-123" > "$TEST_CONFIG_DIR/api_key.txt"
    
    # Set appropriate permissions
    chmod 755 $TEST_DOWNLOADS_DIR $TEST_LOGS_DIR $TEST_CONFIG_DIR
    chmod 644 "$TEST_DOWNLOADS_DIR/host-test.txt"
    chmod 644 "$TEST_LOGS_DIR/host-log.txt"
    chmod 600 "$TEST_CONFIG_DIR/api_key.txt"
    
    print_status "Test directories created with initial files"
}

# Function to start container with volume mounts
start_container_with_volumes() {
    print_status "Starting container with volume mounts..."
    
    docker run -d \
        --name $CONTAINER_NAME \
        -v "$(pwd)/$TEST_DOWNLOADS_DIR:/opt/ytdl_service/downloads" \
        -v "$(pwd)/$TEST_LOGS_DIR:/var/log" \
        -v "$(pwd)/$TEST_CONFIG_DIR:/opt/ytdl_service/config" \
        -e YTDL_SERVICE_API_KEY="volume-test-key" \
        -e PORT=8000 \
        $IMAGE_NAME
    
    # Wait for container to start
    sleep 5
    
    if docker ps | grep -q $CONTAINER_NAME; then
        print_status "Container started successfully"
    else
        print_error "Container failed to start"
        docker logs $CONTAINER_NAME
        return 1
    fi
}

# Function to test downloads volume mount
test_downloads_volume() {
    print_status "Testing downloads volume mount..."
    
    # Test 1: Check if host file is visible in container
    if docker exec $CONTAINER_NAME test -f "/opt/ytdl_service/downloads/host-test.txt"; then
        print_status "✓ Host file visible in container downloads directory"
    else
        print_error "✗ Host file not visible in container"
        return 1
    fi
    
    # Test 2: Create file in container, check if visible on host
    docker exec $CONTAINER_NAME touch "/opt/ytdl_service/downloads/container-created.txt"
    docker exec $CONTAINER_NAME sh -c 'echo "Created from container" > /opt/ytdl_service/downloads/container-created.txt'
    
    if [ -f "$TEST_DOWNLOADS_DIR/container-created.txt" ]; then
        content=$(cat "$TEST_DOWNLOADS_DIR/container-created.txt")
        if [ "$content" = "Created from container" ]; then
            print_status "✓ Container-created file visible on host with correct content"
        else
            print_error "✗ Container-created file has incorrect content: $content"
            return 1
        fi
    else
        print_error "✗ Container-created file not visible on host"
        return 1
    fi
    
    # Test 3: Test file permissions
    host_perms=$(stat -c "%a" "$TEST_DOWNLOADS_DIR/container-created.txt")
    container_perms=$(docker exec $CONTAINER_NAME stat -c "%a" "/opt/ytdl_service/downloads/container-created.txt")
    
    if [ "$host_perms" = "$container_perms" ]; then
        print_status "✓ File permissions consistent between host and container ($host_perms)"
    else
        print_warning "File permissions differ: host=$host_perms, container=$container_perms"
    fi
    
    # Test 4: Test directory ownership in container
    owner_info=$(docker exec $CONTAINER_NAME stat -c "%U:%G" "/opt/ytdl_service/downloads")
    if echo "$owner_info" | grep -q "ytdl:ytdl"; then
        print_status "✓ Downloads directory owned by correct user (ytdl:ytdl)"
    else
        print_warning "Downloads directory ownership: $owner_info"
    fi
    
    print_status "Downloads volume tests completed"
}

# Function to test logs volume mount
test_logs_volume() {
    print_status "Testing logs volume mount..."
    
    # Test 1: Check if host log file is visible in container
    if docker exec $CONTAINER_NAME test -f "/var/log/host-log.txt"; then
        print_status "✓ Host log file visible in container"
    else
        print_error "✗ Host log file not visible in container"
        return 1
    fi
    
    # Test 2: Create log file in container
    docker exec $CONTAINER_NAME sh -c 'echo "Container log entry" > /var/log/container.log'
    docker exec $CONTAINER_NAME sh -c 'echo "$(date): Test log message" >> /var/log/container.log'
    
    if [ -f "$TEST_LOGS_DIR/container.log" ]; then
        if grep -q "Test log message" "$TEST_LOGS_DIR/container.log"; then
            print_status "✓ Container log file created and accessible on host"
        else
            print_error "✗ Container log file missing expected content"
            return 1
        fi
    else
        print_error "✗ Container log file not visible on host"
        return 1
    fi
    
    # Test 3: Test log rotation simulation
    docker exec $CONTAINER_NAME sh -c 'for i in {1..100}; do echo "Log line $i" >> /var/log/container.log; done'
    
    line_count=$(wc -l < "$TEST_LOGS_DIR/container.log")
    if [ "$line_count" -gt 100 ]; then
        print_status "✓ Log file writing performance acceptable ($line_count lines)"
    else
        print_warning "Log file has fewer lines than expected: $line_count"
    fi
    
    print_status "Logs volume tests completed"
}

# Function to test config volume mount
test_config_volume() {
    print_status "Testing config volume mount..."
    
    # Test 1: Check if API key file is accessible
    if docker exec $CONTAINER_NAME test -f "/opt/ytdl_service/config/api_key.txt"; then
        api_key_content=$(docker exec $CONTAINER_NAME cat "/opt/ytdl_service/config/api_key.txt")
        if [ "$api_key_content" = "test-api-key-volume-123" ]; then
            print_status "✓ Config file accessible with correct content"
        else
            print_error "✗ Config file has incorrect content: $api_key_content"
            return 1
        fi
    else
        print_error "✗ Config file not accessible in container"
        return 1
    fi
    
    # Test 2: Test config file permissions
    config_perms=$(docker exec $CONTAINER_NAME stat -c "%a" "/opt/ytdl_service/config/api_key.txt")
    if [ "$config_perms" = "600" ]; then
        print_status "✓ Config file has secure permissions (600)"
    else
        print_warning "Config file permissions: $config_perms (expected 600)"
    fi
    
    # Test 3: Create new config file from container
    docker exec $CONTAINER_NAME sh -c 'echo "container_setting=true" > /opt/ytdl_service/config/app.conf'
    
    if [ -f "$TEST_CONFIG_DIR/app.conf" ]; then
        if grep -q "container_setting=true" "$TEST_CONFIG_DIR/app.conf"; then
            print_status "✓ Container can create config files accessible on host"
        else
            print_error "✗ Config file content mismatch"
            return 1
        fi
    else
        print_error "✗ Container-created config file not visible on host"
        return 1
    fi
    
    print_status "Config volume tests completed"
}

# Function to test volume persistence
test_volume_persistence() {
    print_status "Testing volume persistence across container restarts..."
    
    # Create test files
    docker exec $CONTAINER_NAME touch "/opt/ytdl_service/downloads/persistence-test.txt"
    docker exec $CONTAINER_NAME sh -c 'echo "Persistence test" > /opt/ytdl_service/downloads/persistence-test.txt'
    
    # Stop container
    docker stop $CONTAINER_NAME
    
    # Verify files still exist on host
    if [ -f "$TEST_DOWNLOADS_DIR/persistence-test.txt" ]; then
        print_status "✓ Files persist on host after container stop"
    else
        print_error "✗ Files lost after container stop"
        return 1
    fi
    
    # Start container again
    docker start $CONTAINER_NAME
    sleep 3
    
    # Check if files are still accessible in new container instance
    if docker exec $CONTAINER_NAME test -f "/opt/ytdl_service/downloads/persistence-test.txt"; then
        content=$(docker exec $CONTAINER_NAME cat "/opt/ytdl_service/downloads/persistence-test.txt")
        if [ "$content" = "Persistence test" ]; then
            print_status "✓ Files accessible in restarted container with correct content"
        else
            print_error "✗ File content changed after restart: $content"
            return 1
        fi
    else
        print_error "✗ Files not accessible in restarted container"
        return 1
    fi
    
    print_status "Volume persistence tests completed"
}

# Function to test volume performance
test_volume_performance() {
    print_status "Testing volume mount performance..."
    
    # Test write performance
    start_time=$(date +%s.%N)
    docker exec $CONTAINER_NAME sh -c 'for i in {1..1000}; do echo "Performance test line $i" >> /opt/ytdl_service/downloads/perf-test.txt; done'
    end_time=$(date +%s.%N)
    
    write_time=$(echo "$end_time - $start_time" | bc -l)
    print_status "Write performance: 1000 lines in ${write_time}s"
    
    # Test read performance
    start_time=$(date +%s.%N)
    docker exec $CONTAINER_NAME wc -l "/opt/ytdl_service/downloads/perf-test.txt" > /dev/null
    end_time=$(date +%s.%N)
    
    read_time=$(echo "$end_time - $start_time" | bc -l)
    print_status "Read performance: file read in ${read_time}s"
    
    # Verify file size
    file_size=$(docker exec $CONTAINER_NAME stat -c "%s" "/opt/ytdl_service/downloads/perf-test.txt")
    host_file_size=$(stat -c "%s" "$TEST_DOWNLOADS_DIR/perf-test.txt")
    
    if [ "$file_size" = "$host_file_size" ]; then
        print_status "✓ File sizes match between container and host ($file_size bytes)"
    else
        print_error "✗ File size mismatch: container=$file_size, host=$host_file_size"
        return 1
    fi
    
    print_status "Volume performance tests completed"
}

# Function to test volume mount edge cases
test_volume_edge_cases() {
    print_status "Testing volume mount edge cases..."
    
    # Test 1: Special characters in filenames
    docker exec $CONTAINER_NAME touch "/opt/ytdl_service/downloads/file with spaces.txt"
    docker exec $CONTAINER_NAME touch "/opt/ytdl_service/downloads/file-with-special-chars_@#$.txt"
    
    if [ -f "$TEST_DOWNLOADS_DIR/file with spaces.txt" ] && [ -f "$TEST_DOWNLOADS_DIR/file-with-special-chars_@#$.txt" ]; then
        print_status "✓ Special characters in filenames handled correctly"
    else
        print_error "✗ Special characters in filenames not handled properly"
        return 1
    fi
    
    # Test 2: Subdirectory creation
    docker exec $CONTAINER_NAME mkdir -p "/opt/ytdl_service/downloads/subdir/nested"
    docker exec $CONTAINER_NAME touch "/opt/ytdl_service/downloads/subdir/nested/test.txt"
    
    if [ -f "$TEST_DOWNLOADS_DIR/subdir/nested/test.txt" ]; then
        print_status "✓ Subdirectory creation works correctly"
    else
        print_error "✗ Subdirectory creation failed"
        return 1
    fi
    
    # Test 3: Large file handling (create a 10MB file)
    docker exec $CONTAINER_NAME dd if=/dev/zero of="/opt/ytdl_service/downloads/large-file.bin" bs=1M count=10 2>/dev/null
    
    if [ -f "$TEST_DOWNLOADS_DIR/large-file.bin" ]; then
        host_size=$(stat -c "%s" "$TEST_DOWNLOADS_DIR/large-file.bin")
        expected_size=$((10 * 1024 * 1024))
        if [ "$host_size" = "$expected_size" ]; then
            print_status "✓ Large file handling works correctly (10MB)"
        else
            print_error "✗ Large file size mismatch: expected=$expected_size, actual=$host_size"
            return 1
        fi
    else
        print_error "✗ Large file not created on host"
        return 1
    fi
    
    print_status "Volume edge case tests completed"
}

# Main test execution
main() {
    print_status "Starting volume mount validation tests..."
    
    # Trap cleanup on exit
    trap cleanup EXIT
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running or not accessible"
        exit 1
    fi
    
    # Check if image exists
    if ! docker image inspect $IMAGE_NAME > /dev/null 2>&1; then
        print_error "Docker image '$IMAGE_NAME' not found. Please build it first."
        exit 1
    fi
    
    # Check if bc is available for performance calculations
    if ! command -v bc &> /dev/null; then
        print_warning "bc command not found, skipping performance time calculations"
    fi
    
    # Cleanup any existing resources
    cleanup
    
    # Setup test environment
    setup_test_directories
    start_container_with_volumes
    
    # Run volume tests
    test_downloads_volume
    test_logs_volume
    test_config_volume
    test_volume_persistence
    test_volume_performance
    test_volume_edge_cases
    
    print_status "All volume mount validation tests passed! ✓"
}

# Run main function
main "$@"