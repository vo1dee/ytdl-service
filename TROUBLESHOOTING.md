# Docker Troubleshooting Guide

## Common Issues and Solutions

### Container Startup Issues

#### Issue: Container fails to start

**Symptoms:**
- Container exits immediately after starting
- Error messages in container logs
- Health check failures

**Diagnosis:**
```bash
# Check container logs
docker logs ytdl-service

# Check container status
docker ps -a

# Inspect container configuration
docker inspect ytdl-service
```

**Common Causes and Solutions:**

1. **Missing environment variables**
   ```bash
   # Check if required environment variables are set
   docker exec ytdl-service env | grep YTDL
   
   # Solution: Set required environment variables
   docker run -e YTDL_SERVICE_URL=http://localhost:8000 ytdl-service
   ```

2. **Port conflicts**
   ```bash
   # Check if port is already in use
   netstat -tulpn | grep :8000
   
   # Solution: Use different port
   docker run -p 8001:8000 ytdl-service
   ```

3. **Volume mount permissions**
   ```bash
   # Check volume permissions
   ls -la downloads/ logs/
   
   # Solution: Fix permissions
   sudo chown -R 1000:1000 downloads/ logs/
   chmod -R 755 downloads/ logs/
   ```

#### Issue: Permission denied errors

**Symptoms:**
- Cannot write to mounted volumes
- API key file creation fails
- Log file creation fails

**Solution:**
```bash
# Create directories with correct permissions
mkdir -p downloads logs config
sudo chown -R 1000:1000 downloads logs config
chmod -R 755 downloads logs config

# Or run with user mapping
docker run --user $(id -u):$(id -g) ytdl-service
```

### Network and Connectivity Issues

#### Issue: Cannot access the API

**Symptoms:**
- Connection refused errors
- Timeout when accessing http://localhost:8000
- Health check endpoint not responding

**Diagnosis:**
```bash
# Check if container is running
docker ps | grep ytdl-service

# Check port mapping
docker port ytdl-service

# Test network connectivity
docker exec ytdl-service curl -f http://localhost:8000/health
```

**Solutions:**

1. **Container not running**
   ```bash
   # Start the container
   docker start ytdl-service
   
   # Or restart if it's stuck
   docker restart ytdl-service
   ```

2. **Port mapping issues**
   ```bash
   # Check current port mapping
   docker port ytdl-service
   
   # Recreate with correct port mapping
   docker stop ytdl-service
   docker rm ytdl-service
   docker run -p 8000:8000 ytdl-service
   ```

3. **Firewall blocking access**
   ```bash
   # Check firewall rules (Ubuntu/Debian)
   sudo ufw status
   
   # Allow port if needed
   sudo ufw allow 8000
   ```

#### Issue: Service communication failures

**Symptoms:**
- Telegram bot cannot reach FastAPI service
- Internal service discovery fails
- API calls return connection errors

**Solutions:**

1. **Docker Compose networking**
   ```bash
   # Check network configuration
   docker-compose ps
   docker network ls
   
   # Use service names for internal communication
   # In docker-compose.yml, use: http://ytdl-service:8000
   ```

2. **Custom network setup**
   ```bash
   # Create custom network
   docker network create ytdl-network
   
   # Run containers on same network
   docker run --network ytdl-network ytdl-service
   ```

### Download and Processing Issues

#### Issue: Downloads fail or timeout

**Symptoms:**
- Download requests return errors
- Videos fail to process
- yt-dlp errors in logs

**Diagnosis:**
```bash
# Check container logs for yt-dlp errors
docker logs ytdl-service | grep -i error

# Test yt-dlp directly in container
docker exec -it ytdl-service yt-dlp --version
docker exec -it ytdl-service yt-dlp "https://www.youtube.com/watch?v=test"
```

**Solutions:**

1. **Update yt-dlp**
   ```bash
   # Rebuild container with latest yt-dlp
   docker build --no-cache -t ytdl-service .
   ```

2. **Network connectivity issues**
   ```bash
   # Test internet connectivity from container
   docker exec ytdl-service ping -c 3 google.com
   docker exec ytdl-service curl -I https://www.youtube.com
   ```

3. **Insufficient disk space**
   ```bash
   # Check available disk space
   docker exec ytdl-service df -h /opt/ytdl_service/downloads
   
   # Clean up old downloads if needed
   docker exec ytdl-service find /opt/ytdl_service/downloads -type f -mtime +7 -delete
   ```

#### Issue: FFmpeg processing errors

**Symptoms:**
- Video conversion fails
- Audio extraction errors
- Format-specific processing issues

**Solutions:**

1. **Check FFmpeg installation**
   ```bash
   # Verify FFmpeg is available
   docker exec ytdl-service ffmpeg -version
   
   # Test FFmpeg functionality
   docker exec ytdl-service ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -f null -
   ```

2. **Memory and resource limits**
   ```bash
   # Increase container memory limits
   docker run --memory=4g --memory-swap=4g ytdl-service
   ```

### Storage and Volume Issues

#### Issue: Volume mounts not working

**Symptoms:**
- Downloaded files not visible on host
- Logs not persisting between restarts
- Configuration changes not saved

**Diagnosis:**
```bash
# Check volume mounts
docker inspect ytdl-service | grep -A 10 "Mounts"

# Verify files in container
docker exec ytdl-service ls -la /opt/ytdl_service/downloads
docker exec ytdl-service ls -la /var/log
```

**Solutions:**

1. **Absolute paths for volumes**
   ```bash
   # Use absolute paths for volume mounts
   docker run -v /full/path/to/downloads:/opt/ytdl_service/downloads ytdl-service
   ```

2. **SELinux context (RHEL/CentOS)**
   ```bash
   # Add SELinux context for volumes
   docker run -v /path/to/downloads:/opt/ytdl_service/downloads:Z ytdl-service
   ```

#### Issue: Disk space issues

**Symptoms:**
- Downloads fail with "No space left on device"
- Container becomes unresponsive
- Log files grow too large

**Solutions:**

1. **Monitor disk usage**
   ```bash
   # Check disk usage
   docker exec ytdl-service df -h
   
   # Check largest files
   docker exec ytdl-service du -sh /opt/ytdl_service/downloads/* | sort -hr
   ```

2. **Implement cleanup strategies**
   ```bash
   # Clean old downloads (older than 7 days)
   docker exec ytdl-service find /opt/ytdl_service/downloads -type f -mtime +7 -delete
   
   # Rotate logs
   docker exec ytdl-service logrotate /etc/logrotate.conf
   ```

### Performance Issues

#### Issue: Slow download speeds

**Symptoms:**
- Downloads take much longer than expected
- High CPU usage during downloads
- Memory usage spikes

**Solutions:**

1. **Resource allocation**
   ```bash
   # Increase CPU and memory limits
   docker run --cpus=2.0 --memory=4g ytdl-service
   ```

2. **Concurrent download limits**
   ```bash
   # Limit concurrent downloads via environment
   docker run -e YTDL_MAX_CONCURRENT=2 ytdl-service
   ```

#### Issue: High memory usage

**Symptoms:**
- Container killed by OOM killer
- System becomes unresponsive
- Memory usage continuously increases

**Solutions:**

1. **Set memory limits**
   ```bash
   # Set appropriate memory limits
   docker run --memory=2g --memory-swap=2g ytdl-service
   ```

2. **Monitor memory usage**
   ```bash
   # Monitor container memory usage
   docker stats ytdl-service
   
   # Check for memory leaks
   docker exec ytdl-service ps aux --sort=-%mem
   ```

### Docker Compose Issues

#### Issue: Services fail to communicate

**Symptoms:**
- Service discovery failures
- Connection refused between services
- Network isolation issues

**Solutions:**

1. **Check service names**
   ```yaml
   # Use service names for internal communication
   environment:
     - YTDL_SERVICE_URL=http://ytdl-service:8000
   ```

2. **Network configuration**
   ```bash
   # Check Docker Compose networks
   docker-compose ps
   docker network ls | grep ytdl
   
   # Recreate network if needed
   docker-compose down
   docker-compose up -d
   ```

#### Issue: Environment variable conflicts

**Symptoms:**
- Configuration not applied correctly
- Services use wrong settings
- Inconsistent behavior

**Solutions:**

1. **Check environment precedence**
   ```bash
   # Environment variables override order:
   # 1. docker-compose.override.yml
   # 2. docker-compose.yml
   # 3. .env file
   # 4. Dockerfile ENV
   ```

2. **Validate environment variables**
   ```bash
   # Check effective environment variables
   docker-compose config
   docker exec ytdl-service env | sort
   ```

## Debugging Tools and Commands

### Container Inspection

```bash
# Get detailed container information
docker inspect ytdl-service

# Check container processes
docker exec ytdl-service ps aux

# Monitor resource usage
docker stats ytdl-service

# Access container shell
docker exec -it ytdl-service /bin/bash
```

### Log Analysis

```bash
# View container logs
docker logs ytdl-service

# Follow logs in real-time
docker logs -f ytdl-service

# View logs with timestamps
docker logs -t ytdl-service

# View last N lines
docker logs --tail 50 ytdl-service

# Filter logs by time
docker logs --since "2025-01-08T10:00:00" ytdl-service
```

### Network Debugging

```bash
# Test network connectivity
docker exec ytdl-service ping google.com
docker exec ytdl-service curl -I http://localhost:8000/health

# Check listening ports
docker exec ytdl-service netstat -tulpn

# Test DNS resolution
docker exec ytdl-service nslookup google.com
```

### Performance Monitoring

```bash
# Monitor system resources
docker exec ytdl-service top
docker exec ytdl-service htop

# Check disk I/O
docker exec ytdl-service iostat -x 1

# Monitor network traffic
docker exec ytdl-service iftop
```

## Getting Help

### Log Collection for Support

```bash
# Collect comprehensive logs
mkdir -p debug-logs
docker logs ytdl-service > debug-logs/container.log
docker inspect ytdl-service > debug-logs/inspect.json
docker-compose config > debug-logs/compose-config.yml
docker exec ytdl-service env > debug-logs/environment.txt
```

### Health Check Script

```bash
#!/bin/bash
# health-check.sh - Comprehensive health check

echo "=== Container Status ==="
docker ps | grep ytdl-service

echo "=== Health Check Endpoint ==="
curl -f http://localhost:8000/health || echo "Health check failed"

echo "=== Resource Usage ==="
docker stats --no-stream ytdl-service

echo "=== Recent Logs ==="
docker logs --tail 20 ytdl-service

echo "=== Volume Mounts ==="
docker inspect ytdl-service | grep -A 10 "Mounts"
```

### Common Error Messages

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `bind: address already in use` | Port conflict | Use different port or stop conflicting service |
| `permission denied` | Volume permission issues | Fix directory permissions |
| `no space left on device` | Disk full | Clean up downloads or increase disk space |
| `connection refused` | Service not running | Check container status and restart if needed |
| `network not found` | Docker network issues | Recreate Docker network |
| `image not found` | Image not built | Build image with `./build.sh` |

For additional support, check the project documentation or create an issue with the debug logs collected above.