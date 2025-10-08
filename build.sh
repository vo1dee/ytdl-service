#!/bin/bash

# YouTube Download Service - Docker Build Script
# This script builds the Docker image with proper tagging

set -e  # Exit on any error

# Configuration
IMAGE_NAME="ytdl-service"
DEFAULT_TAG="latest"
BUILD_CONTEXT="."

# Parse command line arguments
TAG=${1:-$DEFAULT_TAG}
DOCKERFILE=${2:-"Dockerfile"}

echo "Building YouTube Download Service Docker image..."
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "Dockerfile: ${DOCKERFILE}"
echo "Build Context: ${BUILD_CONTEXT}"
echo ""

# Check if Dockerfile exists
if [ ! -f "$DOCKERFILE" ]; then
    echo "Error: Dockerfile '$DOCKERFILE' not found!"
    exit 1
fi

# Build the Docker image
echo "Starting Docker build..."
docker build \
    --tag "${IMAGE_NAME}:${TAG}" \
    --tag "${IMAGE_NAME}:latest" \
    --file "$DOCKERFILE" \
    "$BUILD_CONTEXT"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build completed successfully!"
    echo "Image: ${IMAGE_NAME}:${TAG}"
    echo ""
    echo "To run the container, use:"
    echo "  ./run.sh"
    echo ""
    echo "To view available images:"
    echo "  docker images | grep ${IMAGE_NAME}"
else
    echo ""
    echo "❌ Build failed!"
    exit 1
fi