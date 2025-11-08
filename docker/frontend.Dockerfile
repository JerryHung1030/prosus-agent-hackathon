# syntax=docker/dockerfile:1

FROM node:20-slim as base

WORKDIR /app

# Install dependencies
COPY frontend/package.json ./
COPY frontend/package-lock.json ./
RUN npm install

# Copy source
COPY frontend/ ./

# Build the production bundle
RUN npm run build

EXPOSE 5173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
