#!/bin/bash

# Master Test Script for Docker Containerization
# This script runs all testing and validation scripts for the containerized YouTube Download Service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="ytdl-service"
CONTAINER_NAME="ytdl-service-test-suite"
API_KEY="test-suite-api-key-$(date +%s)"
TEST_PORT="8003"

# Function to print colored output
print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to cleanup all test resources
cleanup_all() {
    print_status "Cleaning up all test resources..."
    
    # Stop and remove test containers
    docker stop $CONTAINER_NAME 2>/dev/null || true
    docker rm $CONTAINER_NAME 2>/dev/null || true
    
    # Clean up Docker Compose test resources
    docker-compose -p ytdl-test down -v --remove-orphans 2>/dev/null || true
    
    # Remove test directories
    rm -rf ./test-* 2>/dev/null || true
    rm -f docker-compose.test.yml 2>/dev/null || true
    rm -f performance_report.txt 2>/dev/null || true
    
    print_status "Cleanup completed"
}

# Function to check prerequisites
check_prerequisites() {
    print_header "CHECKING PREREQUISITES"
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running or not accessible"
        exit 1
    fi
    print_status "✓ Docker is running"
    
    # Check if Docker Compose is available
    if ! docker-compose --version > /dev/null 2>&1; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    print_status "✓ Docker Compose is available"
    
    # Check if Python 3 is available
    if ! python3 --version > /dev/null 2>&1; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    print_status "✓ Python 3 is available"
    
    # Check if required Python packages are available
    python3 -c "import requests, docker, psutil, numpy, matplotlib" 2>/dev/null || {
        print_warning "Some Python packages may be missing. Installing..."
        pip3 install requests docker psutil numpy matplotlib 2>/dev/null || {
            print_warning "Could not install Python packages. Some tests may fail."
        }
    }
    print_status "✓ Python dependencies checked"
    
    # Check if curl is available
    if ! command -v curl &> /dev/null; then
        print_error "curl is not installed"
        exit 1
    fi
    print_status "✓ curl is available"
    
    # Check if bc is available (for calculations)
    if ! command -v bc &> /dev/null; then
        print_warning "bc is not installed - some calculations may be skipped"
    else
        print_status "✓ bc is available"
    fi
    
    # Check if Docker image exists
    if ! docker image inspect $IMAGE_NAME > /dev/null 2>&1; then
        print_error "Docker image '$IMAGE_NAME' not found"
        print_status "Please build the image first with: docker build -t $IMAGE_NAME ."
        exit 1
    fi
    print_status "✓ Docker image '$IMAGE_NAME' exists"
    
    # Check if main compose file exists
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found"
        exit 1
    fi
    print_status "✓ docker-compose.yml exists"
    
    print_status "All prerequisites satisfied!"
}

# Function to make test scripts executable
setup_test_scripts() {
    print_header "SETTING UP TEST SCRIPTS"
    
    chmod +x test-container.sh
    chmod +x test-docker-compose.sh
    chmod +x test-volume-mounts.sh
    chmod +x test-api-endpoints.py
    chmod +x test-performance.py
    
    print_status "All test scripts are now executable"
}

# Function to run container functionality tests
run_container_tests() {
    print_header "RUNNING CONTAINER FUNCTIONALITY TESTS"
    
    if ./test-container.sh; then
        print_status "✓ Container functionality tests PASSED"
        return 0
    else
        print_error "✗ Container functionality tests FAILED"
        return 1
    fi
}

# Function to run Docker Compose integration tests
run_compose_tests() {
    print_header "RUNNING DOCKER COMPOSE INTEGRATION TESTS"
    
    if ./test-docker-compose.sh; then
        print_status "✓ Docker Compose integration tests PASSED"
        return 0
    else
        print_error "✗ Docker Compose integration tests FAILED"
        return 1
    fi
}

# Function to run volume mount validation tests
run_volume_tests() {
    print_header "RUNNING VOLUME MOUNT VALIDATION TESTS"
    
    if ./test-volume-mounts.sh; then
        print_status "✓ Volume mount validation tests PASSED"
        return 0
    else
        print_error "✗ Volume mount validation tests FAILED"
        return 1
    fi
}

# Function to run API endpoint tests
run_api_tests() {
    print_header "RUNNING API ENDPOINT TESTS"
    
    # Start a test container for API testing
    print_status "Starting container for API testing..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p $TEST_PORT:8000 \
        -e YTDL_SERVICE_API_KEY="$API_KEY" \
        -e PORT=8000 \
        $IMAGE_NAME
    
    # Wait for container to be ready
    sleep 10
    
    # Run API tests
    if python3 test-api-endpoints.py --url "http://localhost:$TEST_PORT" --api-key "$API_KEY" --wait 5; then
        print_status "✓ API endpoint tests PASSED"
        docker stop $CONTAINER_NAME
        docker rm $CONTAINER_NAME
        return 0
    else
        print_error "✗ API endpoint tests FAILED"
        docker logs $CONTAINER_NAME
        docker stop $CONTAINER_NAME
        docker rm $CONTAINER_NAME
        return 1
    fi
}

# Function to run performance tests
run_performance_tests() {
    print_header "RUNNING PERFORMANCE TESTS"
    
    # Start a test container for performance testing
    print_status "Starting container for performance testing..."
    docker run -d \
        --name $CONTAINER_NAME \
        -p $TEST_PORT:8000 \
        -e YTDL_SERVICE_API_KEY="$API_KEY" \
        -e PORT=8000 \
        $IMAGE_NAME
    
    # Wait for container to be ready
    sleep 10
    
    # Run performance tests (quick mode for CI/automated testing)
    if python3 test-performance.py --url "http://localhost:$TEST_PORT" --api-key "$API_KEY" --container "$CONTAINER_NAME" --quick; then
        print_status "✓ Performance tests PASSED"
        docker stop $CONTAINER_NAME
        docker rm $CONTAINER_NAME
        return 0
    else
        print_error "✗ Performance tests FAILED"
        docker logs $CONTAINER_NAME
        docker stop $CONTAINER_NAME
        docker rm $CONTAINER_NAME
        return 1
    fi
}

# Function to generate test summary
generate_summary() {
    print_header "TEST EXECUTION SUMMARY"
    
    local total_tests=5
    local passed_tests=0
    
    echo "Test Results:"
    echo "============="
    
    if [ "${test_results[container]}" = "PASS" ]; then
        echo "✓ Container Functionality Tests: PASSED"
        ((passed_tests++))
    else
        echo "✗ Container Functionality Tests: FAILED"
    fi
    
    if [ "${test_results[compose]}" = "PASS" ]; then
        echo "✓ Docker Compose Integration Tests: PASSED"
        ((passed_tests++))
    else
        echo "✗ Docker Compose Integration Tests: FAILED"
    fi
    
    if [ "${test_results[volume]}" = "PASS" ]; then
        echo "✓ Volume Mount Validation Tests: PASSED"
        ((passed_tests++))
    else
        echo "✗ Volume Mount Validation Tests: FAILED"
    fi
    
    if [ "${test_results[api]}" = "PASS" ]; then
        echo "✓ API Endpoint Tests: PASSED"
        ((passed_tests++))
    else
        echo "✗ API Endpoint Tests: FAILED"
    fi
    
    if [ "${test_results[performance]}" = "PASS" ]; then
        echo "✓ Performance Tests: PASSED"
        ((passed_tests++))
    else
        echo "✗ Performance Tests: FAILED"
    fi
    
    echo ""
    echo "Summary: $passed_tests/$total_tests tests passed"
    
    if [ $passed_tests -eq $total_tests ]; then
        print_status "🎉 ALL TESTS PASSED! The containerized service is ready for deployment."
        return 0
    else
        print_error "❌ Some tests failed. Please review the output above and fix issues before deployment."
        return 1
    fi
}

# Main execution function
main() {
    print_header "DOCKER CONTAINERIZATION TEST SUITE"
    echo "This script will run comprehensive tests for the containerized YouTube Download Service"
    echo ""
    
    # Trap cleanup on exit
    trap cleanup_all EXIT
    
    # Initialize test results array
    declare -A test_results
    
    # Check prerequisites
    check_prerequisites
    
    # Setup test scripts
    setup_test_scripts
    
    # Clean up any existing test resources
    cleanup_all
    
    echo ""
    print_status "Starting test execution..."
    echo ""
    
    # Run all test suites
    if run_container_tests; then
        test_results[container]="PASS"
    else
        test_results[container]="FAIL"
    fi
    
    echo ""
    
    if run_compose_tests; then
        test_results[compose]="PASS"
    else
        test_results[compose]="FAIL"
    fi
    
    echo ""
    
    if run_volume_tests; then
        test_results[volume]="PASS"
    else
        test_results[volume]="FAIL"
    fi
    
    echo ""
    
    if run_api_tests; then
        test_results[api]="PASS"
    else
        test_results[api]="FAIL"
    fi
    
    echo ""
    
    if run_performance_tests; then
        test_results[performance]="PASS"
    else
        test_results[performance]="FAIL"
    fi
    
    echo ""
    
    # Generate summary
    generate_summary
}

# Parse command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --quick        Run quick tests only (reduced duration)"
        echo "  --container    Run container tests only"
        echo "  --compose      Run Docker Compose tests only"
        echo "  --volume       Run volume mount tests only"
        echo "  --api          Run API endpoint tests only"
        echo "  --performance  Run performance tests only"
        echo ""
        echo "Examples:"
        echo "  $0                    # Run all tests"
        echo "  $0 --quick           # Run quick version of all tests"
        echo "  $0 --container       # Run only container functionality tests"
        exit 0
        ;;
    --quick)
        print_status "Running quick test suite..."
        # Set environment variable for quick tests
        export QUICK_TESTS=1
        ;;
    --container)
        check_prerequisites
        setup_test_scripts
        cleanup_all
        run_container_tests
        exit $?
        ;;
    --compose)
        check_prerequisites
        setup_test_scripts
        cleanup_all
        run_compose_tests
        exit $?
        ;;
    --volume)
        check_prerequisites
        setup_test_scripts
        cleanup_all
        run_volume_tests
        exit $?
        ;;
    --api)
        check_prerequisites
        setup_test_scripts
        cleanup_all
        run_api_tests
        exit $?
        ;;
    --performance)
        check_prerequisites
        setup_test_scripts
        cleanup_all
        run_performance_tests
        exit $?
        ;;
    "")
        # No arguments, run all tests
        ;;
    *)
        print_error "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac

# Run main function
main "$@"