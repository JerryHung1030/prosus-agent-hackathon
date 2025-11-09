#!/bin/bash

# Verification script for Nginx Reverse Proxy setup
# Tests that all components are working correctly

echo "🧪 HomePilot Nginx Verification"
echo "================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC} $1"; }
fail() { echo -e "${RED}✗ FAIL${NC} $1"; }
warn() { echo -e "${YELLOW}⚠ WARN${NC} $1"; }

TESTS_PASSED=0
TESTS_FAILED=0

# Test 1: Check if docker compose is running
echo "Test 1: Checking if containers are running..."
if docker compose ps | grep -q "nginx.*Up" && docker compose ps | grep -q "backend.*Up"; then
    pass "All containers are running"
    ((TESTS_PASSED++))
else
    fail "Some containers are not running"
    docker compose ps
    ((TESTS_FAILED++))
fi

# Test 2: Check if nginx config is valid
echo "Test 2: Validating nginx configuration..."
if docker compose exec nginx nginx -t 2>&1 | grep -q "successful"; then
    pass "Nginx configuration is valid"
    ((TESTS_PASSED++))
else
    fail "Nginx configuration has errors"
    docker compose exec nginx nginx -t
    ((TESTS_FAILED++))
fi

# Test 3: Test health endpoint
echo "Test 3: Testing health endpoint..."
if curl -sf http://localhost/api/health > /dev/null 2>&1; then
    pass "Health endpoint responding"
    ((TESTS_PASSED++))
else
    fail "Health endpoint not responding"
    ((TESTS_FAILED++))
fi

# Test 4: Test frontend is accessible
echo "Test 4: Testing frontend accessibility..."
if curl -sf http://localhost/ > /dev/null 2>&1; then
    pass "Frontend is accessible"
    ((TESTS_PASSED++))
else
    fail "Frontend is not accessible"
    ((TESTS_FAILED++))
fi

# Test 5: Test API proxy (listings endpoint)
echo "Test 5: Testing API proxy..."
if curl -sf http://localhost/api/listings?limit=1 > /dev/null 2>&1; then
    pass "API proxy is working"
    ((TESTS_PASSED++))
else
    warn "API proxy test inconclusive (might need data)"
fi

# Test 6: Check if backend is NOT exposed publicly
echo "Test 6: Verifying backend is internal only..."
if ! docker compose ps | grep -q "backend.*0.0.0.0:8000"; then
    pass "Backend is not exposed publicly"
    ((TESTS_PASSED++))
else
    warn "Backend might be exposed on port 8000"
fi

# Test 7: Check nginx is on port 80
echo "Test 7: Checking nginx port binding..."
if docker compose ps | grep -q "nginx.*0.0.0.0:80"; then
    pass "Nginx is exposed on port 80"
    ((TESTS_PASSED++))
else
    fail "Nginx is not on port 80"
    ((TESTS_FAILED++))
fi

# Test 8: Check if images directory is mounted
echo "Test 8: Verifying image directory mount..."
if docker compose exec nginx test -d /app/images > /dev/null 2>&1; then
    pass "Images directory is mounted"
    ((TESTS_PASSED++))
else
    fail "Images directory is not mounted"
    ((TESTS_FAILED++))
fi

# Test 9: Check gzip is enabled
echo "Test 9: Checking gzip compression..."
if curl -sI -H "Accept-Encoding: gzip" http://localhost/ | grep -q "Content-Encoding: gzip"; then
    pass "Gzip compression is enabled"
    ((TESTS_PASSED++))
else
    warn "Gzip compression might not be working (test inconclusive)"
fi

# Test 10: Check React Router fallback
echo "Test 10: Testing React Router fallback..."
if curl -sf http://localhost/some-random-route 2>&1 | grep -q "<!DOCTYPE html>"; then
    pass "React Router fallback is working"
    ((TESTS_PASSED++))
else
    warn "React Router fallback test inconclusive"
fi

echo ""
echo "================================"
echo "Test Results"
echo "================================"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All critical tests passed!${NC}"
    echo ""
    echo "🎉 Your application is ready!"
    echo ""
    echo "Access it at:"
    echo "  • http://localhost/"
    
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "")
    if [ -n "$PUBLIC_IP" ]; then
        echo "  • http://$PUBLIC_IP/"
    fi
    
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please check the logs:${NC}"
    echo "  docker compose logs -f"
    exit 1
fi
