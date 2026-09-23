# ==============================================================================
# Multi-Stage Dockerfile for React/Vite Frontend
# Stage 1: Build static assets using Node.js
# Stage 2: Serve high-performance static build with Nginx
# ==============================================================================

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Cache package dependencies layer
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@11.19.0 --activate && pnpm install --frozen-lockfile

# Copy source code and build production bundle
COPY . .
RUN pnpm run build

# Stage 2: Production Nginx Server
FROM nginx:1.25-alpine

# Copy custom Nginx configuration with reverse proxy & SPA fallback
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled frontend assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Run nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
