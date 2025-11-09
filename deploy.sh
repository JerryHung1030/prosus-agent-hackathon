#!/bin/bash

# HomePilot Nginx Deployment Script
# This script deploys the application with Nginx reverse proxy

set -e  # Exit on any error

echo "🚀 HomePilot Nginx Deployment"
echo "=============================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "ℹ $1"
}

# Check if docker compose is available
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

print_success "Docker is installed"

# Check if .env file exists
if [ ! -f .env ]; then
    print_warning ".env file not found. Make sure to create one with required environment variables."
    echo "Required variables: OPENAI_API_KEY, GOOGLE_MAPS_API_KEY"
fi

# Stop existing containers
print_info "Stopping existing containers..."
docker compose down -v 2>/dev/null || true
print_success "Containers stopped"

# Build and start services
print_info "Building and starting services..."
docker compose up --build -d

# Wait for services to be ready
print_info "Waiting for services to start..."
sleep 5

# Check if containers are running
print_info "Checking container status..."
if docker compose ps | grep -q "nginx.*Up"; then
    print_success "Nginx is running"
else
    print_error "Nginx failed to start"
    docker compose logs nginx
    exit 1
fi

if docker compose ps | grep -q "backend.*Up"; then
    print_success "Backend is running"
else
    print_error "Backend failed to start"
    docker compose logs backend
    exit 1
fi

# Test health endpoint
print_info "Testing backend health endpoint..."
sleep 2
if curl -sf http://localhost/api/health > /dev/null 2>&1; then
    print_success "Backend health check passed"
else
    print_warning "Backend health check failed (might still be starting up)"
fi

# Get the server's public IP (if available)
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "localhost")

echo ""
echo "=============================="
print_success "Deployment Complete!"
echo "=============================="
echo ""
echo "📍 Access your application at:"
echo "   http://localhost/"
if [ "$PUBLIC_IP" != "localhost" ]; then
    echo "   http://$PUBLIC_IP/"
fi
echo ""
echo "🔍 Useful commands:"
echo "   View logs:        docker compose logs -f"
echo "   Stop services:    docker compose down"
echo "   Restart:          docker compose restart"
echo "   Check status:     docker compose ps"
echo ""
echo "🧪 Test endpoints:"
echo "   Health:           curl http://localhost/api/health"
echo "   Listings:         curl http://localhost/api/listings?limit=5"
echo ""
echo "📊 Monitor logs:"
echo "   Nginx:            docker compose logs -f nginx"
echo "   Backend:          docker compose logs -f backend"
echo ""

# Open browser if possible (Linux with xdg-open or macOS with open)
if command -v xdg-open &> /dev/null; then
    read -p "Open browser now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        xdg-open "http://localhost/" &>/dev/null &
    fi
elif command -v open &> /dev/null; then
    read -p "Open browser now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        open "http://localhost/" &>/dev/null &
    fi
fi
