# Docker Deployment Examples

## Overview

This document provides practical examples for different Docker deployment scenarios of the YouTube Download Service. Each example includes complete configuration files and deployment commands.

## Example 1: Basic Development Setup

### Files Structure
```
ytdl-service/
├── docker-compose.yml
├── .env
├── downloads/
├── logs/
└── config/
```

### .env File
```bash
# Basic development configuration
YTDL_SERVICE_URL=http://localhost:8000
YTDL_SERVICE_API_KEY=dev-api-key-12345
PORT=8000
DEBUG=true
LOG_LEVEL=DEBUG

# Development-friendly settings
YTDL_MAX_RETRIES=2
FILE_MAX_AGE=3600
CLEANUP_INTERVAL=1800
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  ytdl-service:
    build: .
    container_name: ytdl-dev
    ports:
      - "8000:8000"
    volumes:
      - ./downloads:/opt/ytdl_service/downloads
      - ./logs:/var/log
      - ./config:/opt/ytdl_service/config
    environment:
      - YTDL_SERVICE_URL=${YTDL_SERVICE_URL}
      - YTDL_SERVICE_API_KEY=${YTDL_SERVICE_API_KEY}
      - PORT=${PORT}
      - DEBUG=${DEBUG}
      - LOG_LEVEL=${LOG_LEVEL}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Deployment Commands
```bash
# Setup
mkdir -p downloads logs config
cp .env.example .env
# Edit .env with your settings

# Deploy
docker-compose up -d

# Monitor
docker-compose logs -f ytdl-service

# Stop
docker-compose down
```

## Example 2: Production Deployment

### Files Structure
```
/opt/ytdl-service/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.production
├── nginx/
│   └── ytdl.conf
└── data/
    ├── downloads/
    ├── logs/
    └── config/
```

### .env.production
```bash
# Production configuration
YTDL_SERVICE_URL=https://ytdl.yourdomain.com
YTDL_SERVICE_API_KEY=super-secure-production-key-here
PORT=8000
DEBUG=false
LOG_LEVEL=INFO

# Production optimized settings
YTDL_MAX_RETRIES=5
YTDL_RETRY_DELAY=2
FILE_MAX_AGE=172800  # 48 hours
CLEANUP_INTERVAL=3600  # 1 hour

# Resource paths
DOWNLOADS_DIR=/opt/ytdl_service/downloads
LOGS_DIR=/var/log
API_KEY_FILE=/opt/ytdl_service/config/api_key.txt
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  ytdl-service:
    image: ytdl-service:latest
    container_name: ytdl-prod
    restart: unless-stopped
    volumes:
      - /opt/ytdl-service/data/downloads:/opt/ytdl_service/downloads
      - /opt/ytdl-service/data/logs:/var/log
      - /opt/ytdl-service/data/config:/opt/ytdl_service/config
    environment:
      - YTDL_SERVICE_URL=${YTDL_SERVICE_URL}
      - YTDL_SERVICE_API_KEY=${YTDL_SERVICE_API_KEY}
      - PORT=${PORT}
      - DEBUG=${DEBUG}
      - LOG_LEVEL=${LOG_LEVEL}
      - YTDL_MAX_RETRIES=${YTDL_MAX_RETRIES}
      - FILE_MAX_AGE=${FILE_MAX_AGE}
    networks:
      - ytdl-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  ytdl-network:
    driver: bridge
```

### docker-compose.prod.yml
```yaml
version: '3.8'

services:
  ytdl-service:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.5'
        reservations:
          memory: 1G
          cpus: '0.5'
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:rw,size=1G
    volumes:
      - /opt/ytdl-service/data/downloads:/opt/ytdl_service/downloads
      - /opt/ytdl-service/data/logs:/var/log
      - /opt/ytdl-service/data/config:/opt/ytdl_service/config:ro

  nginx:
    image: nginx:alpine
    container_name: ytdl-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/ytdl.conf:/etc/nginx/conf.d/default.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    networks:
      - ytdl-network
    depends_on:
      - ytdl-service
    restart: unless-stopped
```

### nginx/ytdl.conf
```nginx
upstream ytdl_backend {
    server ytdl-service:8000;
}

server {
    listen 80;
    server_name ytdl.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ytdl.yourdomain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    client_max_body_size 100M;

    location / {
        proxy_pass http://ytdl_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    location /health {
        proxy_pass http://ytdl_backend/health;
        access_log off;
    }
}
```

### Deployment Commands
```bash
# Setup production environment
sudo mkdir -p /opt/ytdl-service/data/{downloads,logs,config}
sudo chown -R 1000:1000 /opt/ytdl-service/data
cp .env.example .env.production
# Edit .env.production with production settings

# Deploy with production overrides
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d

# Monitor
docker-compose logs -f

# Update deployment
docker-compose pull
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d
```

## Example 3: Multi-Instance Load Balanced Setup

### docker-compose.yml
```yaml
version: '3.8'

services:
  ytdl-service:
    image: ytdl-service:latest
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 1G
          cpus: '0.8'
    volumes:
      - ytdl-downloads:/opt/ytdl_service/downloads
      - ytdl-logs:/var/log
      - ytdl-config:/opt/ytdl_service/config
    environment:
      - YTDL_SERVICE_URL=http://localhost:8000
      - YTDL_SERVICE_API_KEY=${YTDL_SERVICE_API_KEY}
    networks:
      - ytdl-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  load-balancer:
    image: nginx:alpine
    ports:
      - "8000:80"
    volumes:
      - ./nginx-lb.conf:/etc/nginx/nginx.conf:ro
    networks:
      - ytdl-network
    depends_on:
      - ytdl-service

volumes:
  ytdl-downloads:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nfs-server,rw
      device: ":/data/ytdl/downloads"
  ytdl-logs:
    driver: local
  ytdl-config:
    driver: local

networks:
  ytdl-network:
    driver: overlay
```

### nginx-lb.conf
```nginx
events {
    worker_connections 1024;
}

http {
    upstream ytdl_cluster {
        least_conn;
        server ytdl-service:8000 max_fails=3 fail_timeout=30s;
    }

    server {
        listen 80;
        
        location / {
            proxy_pass http://ytdl_cluster;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
        
        location /health {
            proxy_pass http://ytdl_cluster/health;
            access_log off;
        }
    }
}
```

## Example 4: Docker Swarm Deployment

### docker-stack.yml
```yaml
version: '3.8'

services:
  ytdl-service:
    image: ytdl-service:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
        order: start-first
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
      placement:
        constraints:
          - node.role == worker
    volumes:
      - ytdl-downloads:/opt/ytdl_service/downloads
      - ytdl-logs:/var/log
    environment:
      - YTDL_SERVICE_URL=http://ytdl-service:8000
      - YTDL_SERVICE_API_KEY_FILE=/run/secrets/ytdl_api_key
    secrets:
      - ytdl_api_key
    networks:
      - ytdl-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  traefik:
    image: traefik:v2.9
    command:
      - --api.dashboard=true
      - --providers.docker.swarmMode=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - ytdl-network
    deploy:
      placement:
        constraints:
          - node.role == manager
      labels:
        - traefik.enable=true
        - traefik.http.routers.ytdl.rule=Host(`ytdl.yourdomain.com`)
        - traefik.http.routers.ytdl.entrypoints=websecure
        - traefik.http.routers.ytdl.tls=true
        - traefik.http.services.ytdl.loadbalancer.server.port=8000

volumes:
  ytdl-downloads:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nfs-server,rw
      device: ":/data/ytdl/downloads"
  ytdl-logs:
    driver: local

networks:
  ytdl-network:
    driver: overlay
    attachable: true

secrets:
  ytdl_api_key:
    external: true
```

### Deployment Commands
```bash
# Create secret
echo "your-secure-api-key" | docker secret create ytdl_api_key -

# Deploy stack
docker stack deploy -c docker-stack.yml ytdl

# Monitor
docker service ls
docker service logs ytdl_ytdl-service

# Scale
docker service scale ytdl_ytdl-service=5

# Update
docker service update --image ytdl-service:v2.0.0 ytdl_ytdl-service
```

## Example 5: Kubernetes Deployment

### namespace.yaml
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ytdl-service
```

### configmap.yaml
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ytdl-config
  namespace: ytdl-service
data:
  YTDL_SERVICE_URL: "http://ytdl-service:8000"
  PORT: "8000"
  DEBUG: "false"
  LOG_LEVEL: "INFO"
  YTDL_MAX_RETRIES: "5"
  FILE_MAX_AGE: "172800"
```

### secret.yaml
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ytdl-secrets
  namespace: ytdl-service
type: Opaque
data:
  api-key: eW91ci1zZWN1cmUtYXBpLWtleQ==  # base64 encoded
```

### deployment.yaml
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ytdl-service
  namespace: ytdl-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ytdl-service
  template:
    metadata:
      labels:
        app: ytdl-service
    spec:
      containers:
      - name: ytdl-service
        image: ytdl-service:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: ytdl-config
        env:
        - name: YTDL_SERVICE_API_KEY
          valueFrom:
            secretKeyRef:
              name: ytdl-secrets
              key: api-key
        volumeMounts:
        - name: downloads
          mountPath: /opt/ytdl_service/downloads
        - name: logs
          mountPath: /var/log
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
      volumes:
      - name: downloads
        persistentVolumeClaim:
          claimName: ytdl-downloads-pvc
      - name: logs
        persistentVolumeClaim:
          claimName: ytdl-logs-pvc
```

### service.yaml
```yaml
apiVersion: v1
kind: Service
metadata:
  name: ytdl-service
  namespace: ytdl-service
spec:
  selector:
    app: ytdl-service
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

### ingress.yaml
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ytdl-ingress
  namespace: ytdl-service
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - ytdl.yourdomain.com
    secretName: ytdl-tls
  rules:
  - host: ytdl.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ytdl-service
            port:
              number: 8000
```

### Deployment Commands
```bash
# Deploy to Kubernetes
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml

# Monitor
kubectl get pods -n ytdl-service
kubectl logs -f deployment/ytdl-service -n ytdl-service

# Scale
kubectl scale deployment ytdl-service --replicas=5 -n ytdl-service
```

## Example 6: Development with Hot Reload

### docker-compose.dev.yml
```yaml
version: '3.8'

services:
  ytdl-service:
    build:
      context: .
      dockerfile: Dockerfile.dev
    container_name: ytdl-dev
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      - ./downloads:/opt/ytdl_service/downloads
      - ./logs:/var/log
    environment:
      - YTDL_SERVICE_URL=http://localhost:8000
      - DEBUG=true
      - LOG_LEVEL=DEBUG
      - PYTHONPATH=/app
    command: ["python", "-m", "uvicorn", "download_service:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    restart: unless-stopped
```

### Dockerfile.dev
```dockerfile
FROM python:3.11-slim-bullseye

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install development dependencies
RUN pip install watchdog

# Create non-root user
RUN useradd --create-home --shell /bin/bash ytdl

# Create directories
RUN mkdir -p /opt/ytdl_service/downloads /var/log
RUN chown -R ytdl:ytdl /opt/ytdl_service /var/log /app

USER ytdl

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "download_service:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

## Common Configuration Patterns

### Environment Variable Precedence
1. Docker Compose override files
2. Docker Compose main file
3. .env file
4. System environment variables
5. Application defaults

### Volume Mount Strategies
```yaml
# Bind mounts (development)
volumes:
  - ./downloads:/opt/ytdl_service/downloads

# Named volumes (production)
volumes:
  - ytdl-downloads:/opt/ytdl_service/downloads

# NFS volumes (distributed)
volumes:
  ytdl-downloads:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nfs-server,rw
      device: ":/data/ytdl/downloads"
```

### Health Check Patterns
```yaml
# Basic health check
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3

# Advanced health check with custom script
healthcheck:
  test: ["CMD", "/app/health-check.sh"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

For more deployment scenarios and troubleshooting, see the [Docker Deployment Guide](DOCKER_DEPLOYMENT.md) and [Troubleshooting Guide](TROUBLESHOOTING.md).