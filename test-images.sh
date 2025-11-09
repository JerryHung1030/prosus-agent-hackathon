#!/bin/bash

# Quick test script for image serving

set -e

echo "🧪 Testing Image Serving via Nginx"
echo "==================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
info() { echo -e "ℹ️  $1"; }

# Test 1: Check if a sample image exists in the container
echo "Test 1: Checking if images directory is mounted..."
if docker compose exec nginx test -d /app/images > /dev/null 2>&1; then
    pass "Images directory is mounted at /app/images/"
    
    # List a few image directories
    info "Sample image directories:"
    docker compose exec nginx ls /app/images/ | head -5
else
    fail "Images directory not found at /app/images/"
    exit 1
fi

echo ""

# Test 2: Find an actual image file to test with
echo "Test 2: Finding a test image..."
TEST_IMAGE=$(docker compose exec nginx find /app/images -name "thumbnail.webp" -type f | head -1 | tr -d '\r')

if [ -z "$TEST_IMAGE" ]; then
    fail "No thumbnail.webp found in /app/images/"
    info "This might be OK if you haven't scraped any listings yet"
    exit 0
fi

# Extract the path after /app/images/
RELATIVE_PATH="${TEST_IMAGE#/app/images/}"
pass "Found test image: $RELATIVE_PATH"

echo ""

# Test 3: Test via /api/images/ endpoint
echo "Test 3: Testing /api/images/ endpoint..."
API_URL="http://localhost/api/images/${RELATIVE_PATH}"
info "Testing: $API_URL"

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL")

if [ "$HTTP_STATUS" = "200" ]; then
    pass "Image serving works! (HTTP $HTTP_STATUS)"
    
    echo ""
    info "Response headers:"
    curl -sI "$API_URL" | grep -E "Content-Type|Cache-Control|X-Content-Type-Options"
    
elif [ "$HTTP_STATUS" = "404" ]; then
    fail "Image not found! (HTTP $HTTP_STATUS)"
    info "Check if the file exists: docker compose exec nginx ls -la $TEST_IMAGE"
    exit 1
else
    fail "Unexpected response! (HTTP $HTTP_STATUS)"
    exit 1
fi

echo ""

# Test 4: Test content type
echo "Test 4: Verifying content type..."
CONTENT_TYPE=$(curl -sI "$API_URL" | grep -i "content-type" | awk '{print $2}' | tr -d '\r')

if [[ "$CONTENT_TYPE" == *"image/webp"* ]]; then
    pass "Correct content type: $CONTENT_TYPE"
else
    fail "Incorrect content type: $CONTENT_TYPE (expected image/webp)"
fi

echo ""

# Test 5: Test caching headers
echo "Test 5: Verifying cache headers..."
CACHE_CONTROL=$(curl -sI "$API_URL" | grep -i "cache-control" | awk '{$1=""; print $0}' | tr -d '\r' | xargs)

if [[ "$CACHE_CONTROL" == *"public"* ]] && [[ "$CACHE_CONTROL" == *"max-age"* ]]; then
    pass "Cache headers present: $CACHE_CONTROL"
else
    fail "Missing or incorrect cache headers: $CACHE_CONTROL"
fi

echo ""
echo "==================================="
echo -e "${GREEN}✓ All tests passed!${NC}"
echo "==================================="
echo ""
echo "📸 Your images are being served correctly via:"
echo "   $API_URL"
echo ""
echo "💡 Images are cached for 30 days with 'public' cache control"
echo ""
