#!/bin/bash

# Docker Compose Integration Tests
# This script validates Docker Compose deployment functionality

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_PROJECT="ytdl-test"
SERVICE_NAME="ytdl-service"
TEST_API_KEY="compose-test-key-67890"
COMPOSE_FILE="docker-compose.yml"
OVERRIDE_FILE="docker-compose.test.yml"

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
    print_status "Cleaning up Docker Compose test resources..."
    docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE down -v --remove-orphans 2>/dev/null || true
    rm -f $OVERRIDE_FILE
    rm -rf ./test-compose-downloads ./test-compose-logs 2>/dev/null || true
}

# Function to create test override file
create_test_override() {
    print_status "Creating test Docker Compose override..."
    
    cat > $OVERRIDE_FILE << EOF
version: '3.8'
services:
  ytdl-service:
    container_name: ${COMPOSE_PROJECT}-${SERVICE_NAME}
    ports:
      - "8002:8000"
    volumes:
      - ./test-compose-downloads:/opt/ytdl_service/downloads
      - ./test-compose-logs:/var/log
    environment:
      - YTDL_SERVICE_API_KEY=$TEST_API_KEY
      - YTDL_SERVICE_URL=http://localhost:8000
      - PORT=8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s
EOF
}

# Function to wait for compose service
wait_for_compose_service() {
    local max_attempts=30
    local attempt=1
    
    print_status "Waiting for Docker Compose service to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE ps | grep -q "Up (healthy)"; then
            print_status "Docker Compose service is ready and healthy!"
            return 0
        elif docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE ps | grep -q "Up"; then
            print_status "Service is up, waiting for health check..."
        fi
        
        echo -n "."
        sleep 3
        attempt=$((attempt + 1))
    done
    
    print_error "Docker Compose service failed to become healthy"
    return 1
}

# Function to test compose service functionality
test_compose_service() {
    print_status "Testing Docker Compose service functionality..."
    
    # Test health endpoint
    response=$(curl -s "http://localhost:8002/health")
    if echo "$response" | grep -q "status.*ok"; then
        print_status "✓ Health endpoint accessible via Compose"
    else
        print_error "✗ Health endpoint failed via Compose"
        return 1
    fi
    
    # Test API functionality
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8002/download" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $TEST_API_KEY" \
        -d '{"url": "invalid-url"}')
    
    if [ "$status_code" = "400" ] || [ "$status_code" = "422" ]; then
        print_status "✓ API endpoint accessible via Compose"
    else
        print_error "✗ API endpoint failed via Compose (status: $status_code)"
        return 1
    fi
    
    print_status "Compose service functionality tests passed!"
}

# Function to test compose volume mounts
test_compose_volumes() {
    print_status "Testing Docker Compose volume mounts..."
    
    # Create test directories
    mkdir -p ./test-compose-downloads ./test-compose-logs
    
    # Test file creation in mounted volumes
    container_name="${COMPOSE_PROJECT}-${SERVICE_NAME}"
    docker exec $container_name touch "/opt/ytdl_service/downloads/compose-test.txt"
    
    if [ -f "./test-compose-downloads/compose-test.txt" ]; then
        print_status "✓ Compose downloads volume mount working"
        rm -f "./test-compose-downloads/compose-test.txt"
    else
        print_error "✗ Compose downloads volume mount failed"
        return 1
    fi
    
    print_status "Compose volume tests passed!"
}

# Function to test compose networking
test_compose_networking() {
    print_status "Testing Docker Compose networking..."
    
    # Get container network information
    container_name="${COMPOSE_PROJECT}-${SERVICE_NAME}"
    network_info=$(docker inspect $container_name --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
    
    if [ -n "$network_info" ]; then
        print_status "✓ Container has network connectivity (IP: $network_info)"
    else
        print_error "✗ Container network configuration failed"
        return 1
    fi
    
    # Test internal connectivity
    if docker exec $container_name curl -s -f "http://localhost:8000/health" > /dev/null; then
        print_status "✓ Internal service connectivity working"
    else
        print_error "✗ Internal service connectivity failed"
        return 1
    fi
    
    print_status "Compose networking tests passed!"
}

# Function to test compose scaling
test_compose_scaling() {
    print_status "Testing Docker Compose scaling capabilities..."
    
    # Note: For this test, we'll verify the compose file supports scaling
    # but won't actually scale since our service uses a specific port
    
    # Check if compose file is properly configured for scaling
    if grep -q "container_name" $OVERRIDE_FILE; then
        print_warning "Service has fixed container name - scaling would require removing container_name"
    fi
    
    # Test compose configuration validation
    if docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE config > /dev/null 2>&1; then
        print_status "✓ Compose configuration is valid"
    else
        print_error "✗ Compose configuration validation failed"
        return 1
    fi
    
    print_status "Compose scaling tests completed!"
}

# Function to test compose logs
test_compose_logs() {
    print_status "Testing Docker Compose logging..."
    
    # Check if logs are accessible
    logs=$(docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE logs --tail=10 $SERVICE_NAME 2>/dev/null)
    
    if [ -n "$logs" ]; then
        print_status "✓ Compose logs accessible"
        echo "Recent log entries:"
        echo "$logs" | tail -3
    else
        print_warning "No logs found or logs not accessible"
    fi
    
    # Check log files in mounted volume
    if [ -d "./test-compose-logs" ] && [ "$(ls -A ./test-compose-logs 2>/dev/null)" ]; then
        print_status "✓ Log files created in mounted volume"
    else
        print_warning "No log files found in mounted volume"
    fi
    
    print_status "Compose logging tests completed!"
}

# Function to test compose restart behavior
test_compose_restart() {
    print_status "Testing Docker Compose restart behavior..."
    
    # Restart the service
    docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE restart $SERVICE_NAME
    
    # Wait for service to be ready again
    sleep 10
    
    # Test if service is still functional after restart
    if curl -s -f "http://localhost:8002/health" > /dev/null; then
        print_status "✓ Service functional after restart"
    else
        print_error "✗ Service failed after restart"
        return 1
    fi
    
    print_status "Compose restart tests passed!"
}

# Main test execution
main() {
    print_status "Starting Docker Compose integration tests..."
    
    # Trap cleanup on exit
    trap cleanup EXIT
    
    # Check if Docker and Docker Compose are available
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running or not accessible"
        exit 1
    fi
    
    if ! docker-compose --version > /dev/null 2>&1; then
        print_error "Docker Compose is not installed or not accessible"
        exit 1
    fi
    
    # Check if main compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        print_error "Docker Compose file '$COMPOSE_FILE' not found"
        exit 1
    fi
    
    # Cleanup any existing resources
    cleanup
    
    # Create test override file
    create_test_override
    
    # Start services
    print_status "Starting Docker Compose services..."
    docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE up -d
    
    # Wait for services to be ready
    if ! wait_for_compose_service; then
        print_error "Docker Compose services failed to start"
        docker-compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE -f $OVERRIDE_FILE logs
        exit 1
    fi
    
    # Run integration tests
    test_compose_service
    test_compose_volumes
    test_compose_networking
    test_compose_scaling
    test_compose_logs
    test_compose_restart
    
    print_status "All Docker Compose integration tests passed! ✓"
}

# Run main function
main "$@"