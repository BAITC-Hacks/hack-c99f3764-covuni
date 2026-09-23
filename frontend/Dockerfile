# ==============================================================================
# Single-Stage Lightweight Nginx Container
# Pure Vanilla HTML/JS + Tailwind CDN (Zero Node.js build overhead)
# ==============================================================================

FROM nginx:alpine

# Remove default static files
RUN rm -rf /usr/share/nginx/html/*

# Copy custom Nginx configuration with reverse proxy & SPA fallback
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy static frontend files (index.html, assets, scripts)
COPY . /usr/share/nginx/html

# Expose HTTP port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
