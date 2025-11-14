#!/bin/bash
# Build and push Docker image for Family Link Auth addon

# Configuration
DOCKER_USER="${DOCKER_USER:-noiwid}"
IMAGE_NAME="familylink-auth"
VERSION=$(grep '"version":' config.json | sed 's/.*"version": "\(.*\)".*/\1/')

echo "Building Family Link Auth Docker image..."
echo "Version: $VERSION"

# Build for amd64
docker build \
  --platform linux/amd64 \
  -t ${DOCKER_USER}/${IMAGE_NAME}:${VERSION}-amd64 \
  -t ${DOCKER_USER}/${IMAGE_NAME}:latest-amd64 \
  .

# Build for arm64
docker build \
  --platform linux/arm64 \
  -t ${DOCKER_USER}/${IMAGE_NAME}:${VERSION}-arm64 \
  -t ${DOCKER_USER}/${IMAGE_NAME}:latest-arm64 \
  .

echo "Images built successfully!"
echo ""
echo "To push to Docker Hub:"
echo "  docker push ${DOCKER_USER}/${IMAGE_NAME}:${VERSION}-amd64"
echo "  docker push ${DOCKER_USER}/${IMAGE_NAME}:${VERSION}-arm64"
echo "  docker push ${DOCKER_USER}/${IMAGE_NAME}:latest-amd64"
echo "  docker push ${DOCKER_USER}/${IMAGE_NAME}:latest-arm64"
echo ""
echo "Then create multi-arch manifest:"
echo "  docker manifest create ${DOCKER_USER}/${IMAGE_NAME}:${VERSION} \\"
echo "    ${DOCKER_USER}/${IMAGE_NAME}:${VERSION}-amd64 \\"
echo "    ${DOCKER_USER}/${IMAGE_NAME}:${VERSION}-arm64"
echo "  docker manifest push ${DOCKER_USER}/${IMAGE_NAME}:${VERSION}"
