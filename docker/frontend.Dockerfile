# syntax=docker/dockerfile:1

FROM node:20-slim as builder

WORKDIR /app

# Install dependencies
COPY frontend/package.json ./
COPY frontend/package-lock.json ./
RUN npm ci

# Copy source
COPY frontend/ ./

# Build argument for API URL
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Build the production bundle
RUN npm run build

# Production stage - use nginx to serve static files
FROM nginx:alpine

# Copy built frontend from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Nginx runs as default, no need for CMD
