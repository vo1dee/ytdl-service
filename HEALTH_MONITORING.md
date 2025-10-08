# Container Health Monitoring

This document describes the comprehensive health monitoring system implemented for the YouTube Download Service container.

## Overview

The health monitoring system provides multi-layered health checks to ensure the container and service are operating correctly. It includes both automated Docker health checks and detailed API-based health reporting.

## Components

### 1. Health Check Script (`health_check.sh`)

A comprehensive bash script that performs various health checks suitable for Docker HEALTHCHECK instructions and manual validation.

#### Usage

```bash
# Quick health check (for Docker HEALTHCHECK)
./health_check.sh --quick

# Comprehensive health check with detailed output
./health_check.sh --verbose

# Show help
./health_check.sh --help
```

#### Features

- **Service Response Check**: Validates FastAPI service is responding
- **Dependency Validation**: Checks Python3, FFmpeg, yt-dlp, and FastAPI availability
- **Disk Space Monitoring**: Monitors disk usage for downloads and logs directories
- **Directory Permissions**: Validates read/write access to required directories
- **System Resources**: Monitors memory usage and system load
- **Process Health**: Checks if required processes are running

### 2. Enhanced Health API Endpoint (`/health`)

The FastAPI service provides a comprehensive health endpoint that returns detailed health information in JSON format.

#### Endpoint Details

- **URL**: `GET /health`
- **Authentication**: None required (public endpoint)
- **Response Format**: JSON

#### Response Structure

```json
{
  "status": "healthy|degraded|unhealthy",
  "container_health": {
    "ffmpeg_available": true,
    "ytdlp_available": true,
    "ytdlp_functional": true,
    "api_key_accessible": true,
    "downloads_dir_accessible": true,
    "logs_dir_accessible": true,
    "disk_space_ok": true,
    "network_connectivity": true,
    "dns_resolution": true
  },
  "system_info": {
    "yt_dlp_version": "2025.5.22",
    "ffmpeg_version": "6.1.1",
    "python_version": "3.11.2",
    "last_update_check": "2025-10-08T18:00:00",
    "uptime_seconds": 3600
  },
  "directories": {
    "downloads_dir": "/opt/ytdl_service/downloads",
    "logs_dir": "/var/log",
    "downloads_dir_exists": true,
    "downloads_dir_writeable": true,
    "downloads_dir_readable": true,
    "logs_dir_exists": true,
    "logs_dir_writeable": true
  },
  "disk_usage": {
    "downloads": {
      "total_gb": 100.0,
      "used_gb": 45.2,
      "free_gb": 54.8,
      "usage_percent": 45.2,
      "available_mb": 56115.2
    },
    "logs": {
      "total_gb": 100.0,
      "used_gb": 2.1,
      "free_gb": 97.9,
      "usage_percent": 2.1,
      "available_mb": 100249.6
    }
  },
  "system_resources": {
    "memory": {
      "total_gb": 4.0,
      "available_gb": 2.5,
      "used_percent": 37.5,
      "free_gb": 2.5
    },
    "cpu": {
      "usage_percent": 15.2,
      "count": 4,
      "load_average": [0.5, 0.3, 0.2]
    },
    "process": {
      "pid": 1234,
      "memory_mb": 125.4,
      "cpu_percent": 2.1,
      "threads": 8,
      "open_files": 12,
      "connections": 3
    }
  },
  "process_health": {
    "current_process": {
      "pid": 1234,
      "running": true
    },
    "telegram_bot": {
      "pid": 1235,
      "running": true
    }
  },
  "network_health": {
    "dns_resolution": true,
    "http_connectivity": true
  },
  "configuration": {
    "port": 8000,
    "max_retries": 3,
    "retry_delay": 1,
    "api_key_source": "file"
  },
  "timestamp": "2025-10-08T18:30:00"
}
```

## Health Status Levels

### Healthy
All critical and non-critical checks pass. The service is fully operational.

### Degraded
Critical checks pass but some non-critical checks fail. The service is operational but may have reduced functionality.

**Critical Checks:**
- FFmpeg availability
- yt-dlp availability
- Downloads directory accessibility
- Disk space availability

### Unhealthy
One or more critical checks fail. The service may not function correctly.

## Docker Integration

### Dockerfile Health Check

The Dockerfile includes a HEALTHCHECK instruction that uses the health check script:

```dockerfile
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=3 \
    CMD /opt/ytdl_service/health_check.sh --quick || exit 1
```

### Docker Compose Health Check

The docker-compose.yml file configures health checking:

```yaml
healthcheck:
  test: ["CMD", "/opt/ytdl_service/health_check.sh", "--quick"]
  interval: 30s
  timeout: 15s
  retries: 3
  start_period: 45s
```

## Monitoring Thresholds

### Disk Space
- **Warning**: 90% usage
- **Critical**: 95% usage (for logs), 90% (for downloads)

### System Resources
- **Memory**: Monitored but no automatic failure
- **CPU**: Load average threshold of 10.0 (warning only)
- **Process**: Automatic failure if main process not running

### Network
- **DNS Resolution**: Must resolve www.youtube.com
- **HTTP Connectivity**: Must connect to https://www.youtube.com

## Usage Examples

### Check Container Health Status

```bash
# Using Docker
docker exec ytdl-service /opt/ytdl_service/health_check.sh --verbose

# Using curl to API endpoint
curl http://localhost:8000/health | jq .

# Check Docker health status
docker inspect ytdl-service --format='{{.State.Health.Status}}'
```

### Monitor Health in Scripts

```bash
#!/bin/bash
# Simple health monitoring script

if docker exec ytdl-service /opt/ytdl_service/health_check.sh --quick; then
    echo "Container is healthy"
else
    echo "Container is unhealthy - checking details..."
    docker exec ytdl-service /opt/ytdl_service/health_check.sh --verbose
fi
```

### Health Check Automation

```bash
# Add to crontab for periodic health checks
*/5 * * * * docker exec ytdl-service /opt/ytdl_service/health_check.sh --quick || echo "Health check failed at $(date)" >> /var/log/health_failures.log
```

## Troubleshooting

### Common Issues

1. **FFmpeg Not Available**
   - Ensure FFmpeg is installed in the container
   - Check PATH environment variable

2. **Directory Permission Issues**
   - Verify volume mounts are correct
   - Check directory ownership (should be ytdl:ytdl)
   - Ensure host directories exist and are writable

3. **Disk Space Issues**
   - Clean up old downloads using the cleanup endpoint
   - Increase disk space or add volume cleanup
   - Check log rotation configuration

4. **Network Connectivity Issues**
   - Verify DNS resolution works
   - Check firewall rules
   - Ensure internet connectivity

### Debug Commands

```bash
# Check container logs
docker logs ytdl-service

# Execute interactive shell in container
docker exec -it ytdl-service /bin/bash

# Check health endpoint directly
docker exec ytdl-service curl -f http://localhost:8000/health

# Run comprehensive health check
docker exec ytdl-service /opt/ytdl_service/health_check.sh --verbose
```

## Integration with Monitoring Systems

### Prometheus Metrics

The health endpoint can be scraped by Prometheus for monitoring:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'ytdl-service'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/health'
    scrape_interval: 30s
```

### Alerting

Set up alerts based on health status:

```yaml
# Alert when service is unhealthy
- alert: YTDLServiceUnhealthy
  expr: ytdl_service_health_status != 1
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "YTDL Service is unhealthy"
```

## Dependencies

The health monitoring system requires:

- **bash**: For health check script
- **curl**: For HTTP connectivity tests
- **psutil**: For system resource monitoring (Python package)
- **ffmpeg**: For video processing capability validation
- **yt-dlp**: For download functionality validation

## Configuration

Health monitoring behavior can be configured through environment variables:

```bash
# Health check thresholds
HEALTH_DISK_THRESHOLD=90          # Disk usage warning threshold (%)
HEALTH_RESPONSE_TIMEOUT=10        # HTTP response timeout (seconds)
HEALTH_MAX_LOAD_AVERAGE=10.0      # System load threshold

# Monitoring intervals (configured in Docker/compose)
HEALTH_CHECK_INTERVAL=30s         # How often to run health checks
HEALTH_CHECK_TIMEOUT=15s          # Health check timeout
HEALTH_CHECK_RETRIES=3            # Number of retries before marking unhealthy
```