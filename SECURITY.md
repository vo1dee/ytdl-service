# Security Guide for YouTube Download Service

This document outlines the security features and best practices implemented in the YouTube Download Service containerization.

## Security Features Implemented

### 1. Non-Root User Execution

The container runs as a dedicated non-root user (`ytdl:ytdl`) with UID/GID 1001:1001.

**Benefits:**
- Prevents privilege escalation attacks
- Limits potential damage from container breakouts
- Follows principle of least privilege

**Implementation:**
```dockerfile
# Create non-root user with specific UID/GID
RUN groupadd -g ${APP_USER_GID} ytdl && \
    useradd -u ${APP_USER_UID} -g ${APP_USER_GID} -r -d /opt/ytdl_service -s /sbin/nologin ytdl

# Switch to non-root user
USER ytdl
```

### 2. File System Security

#### Restrictive Permissions
- Application directories: `750` (owner: read/write/execute, group: read/execute)
- Configuration files: `600` (owner: read/write only)
- Secret files: `600` (owner: read/write only)
- Executable scripts: `750` (owner: read/write/execute, group: read/execute)

#### Directory Structure
```
/opt/ytdl_service/
├── downloads/          # 755 - Downloaded files
├── app/               # 750 - Application code
├── config/            # 700 - Configuration and secrets
├── secrets/           # 700 - Mounted secrets (production)
└── logs/              # 755 - Log files
```

### 3. Secret Management

#### Multiple Secret Sources (Priority Order)
1. **Docker Secrets** (Recommended for production)
   ```bash
   echo "your-api-key" | docker secret create ytdl_api_key -
   ```

2. **Mounted Secret Files**
   ```bash
   mkdir -p ./secrets
   echo "your-api-key" > ./secrets/api_key
   chmod 600 ./secrets/api_key
   ```

3. **Environment Variables** (Development only)
   ```bash
   export YTDL_SERVICE_API_KEY="your-api-key"
   ```

4. **Auto-generation** (Fallback)
   - Generates cryptographically secure 48-character key
   - Uses `secrets.token_urlsafe(36)` for enhanced security

#### API Key Security Features
- Minimum 32-character length validation
- Atomic file operations for key storage
- Automatic environment variable clearing after use
- Key rotation script included
- Backup and recovery mechanisms

### 4. Container Security Hardening

#### Multi-Stage Build Security
```dockerfile
# Builder stage with dedicated build user
FROM python:3.11-slim-bullseye AS builder
RUN groupadd -g ${BUILD_USER_GID} builduser && \
    useradd -u ${BUILD_USER_UID} -g ${BUILD_USER_GID} -m -s /bin/bash builduser
USER builduser

# Runtime stage with minimal attack surface
FROM python:3.11-slim-bullseye AS runtime
# Install only runtime dependencies
# Remove build tools and unnecessary packages
```

#### Security Labels and Metadata
```dockerfile
LABEL security.scan="enabled" \
      security.non-root="true" \
      security.readonly-rootfs="partial"
```

### 5. Process Security

#### Resource Limits
- File descriptors: 1024
- Processes: 100
- Memory: 1GB
- Core dumps: Disabled

#### Signal Handling
- Uses `dumb-init` as PID 1 for proper signal handling
- Graceful shutdown with SIGTERM handling
- Process monitoring and restart capabilities

### 6. Network Security

#### Port Configuration
- Only exposes necessary port (8000)
- Validates port ranges (1024-65535, no privileged ports)
- Network isolation with custom bridge networks

#### TLS/SSL Recommendations
- Use reverse proxy (nginx, traefik) for TLS termination
- Internal HTTP communication only
- Certificate management at infrastructure level

### 7. Logging Security

#### Log Sanitization
- Automatic removal of sensitive data patterns
- API keys, tokens, passwords redacted
- Configurable sanitization patterns

#### Secure Log Rotation
```bash
# Logs rotated daily, compressed, 30-day retention
# Proper ownership and permissions maintained
# Secure backup and cleanup procedures
```

## Security Scanning and Monitoring

### 1. Vulnerability Scanning

#### Using Dockerfile.security
```bash
# Build security-enhanced image
docker build -f Dockerfile.security -t ytdl-service:security .

# Run security scan
docker run --rm ytdl-service:security /opt/ytdl_service/security-scan.sh
```

#### Scanning Tools Included
- **Lynis**: System security auditing
- **chkrootkit**: Rootkit detection
- **rkhunter**: Rootkit hunter
- **AIDE**: File integrity monitoring

### 2. Runtime Security Monitoring

#### Security Status Monitoring
```bash
# Check security status
docker exec ytdl-service cat /opt/ytdl_service/security-status.txt

# Run security checks
docker exec ytdl-service /opt/ytdl_service/security-scan.sh
```

#### File Integrity Monitoring
```bash
# Initialize AIDE database
docker exec ytdl-service aide --init

# Check file integrity
docker exec ytdl-service aide --check
```

## Production Deployment Security

### 1. Docker Compose Security Configuration

Use the security-enhanced compose file:
```bash
docker-compose -f docker-compose.yml -f docker-compose.security.yml up -d
```

#### Security Features Enabled
- Read-only root filesystem (where possible)
- Dropped capabilities (ALL) with minimal additions
- Resource limits and reservations
- Custom network isolation
- Enhanced volume security options
- Comprehensive logging configuration

### 2. Secret Management Best Practices

#### For Production Environments
```bash
# Create Docker secrets
echo "$(openssl rand -base64 32)" | docker secret create ytdl_api_key -
echo "your-telegram-token" | docker secret create telegram_bot_token -

# Use in compose file
services:
  ytdl-service:
    secrets:
      - ytdl_api_key
      - telegram_bot_token
```

#### For Development Environments
```bash
# Use mounted secret files
mkdir -p ./secrets
echo "dev-api-key" > ./secrets/api_key
echo "dev-telegram-token" > ./secrets/telegram_token
chmod 600 ./secrets/*
```

### 3. Network Security

#### Reverse Proxy Configuration (nginx example)
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Security Maintenance

### 1. Regular Security Tasks

#### API Key Rotation
```bash
# Rotate API key (monthly recommended)
docker exec ytdl-service /opt/ytdl_service/rotate-api-key.sh
```

#### Log Sanitization
```bash
# Sanitize logs (weekly recommended)
docker exec ytdl-service /opt/ytdl_service/sanitize-logs.sh
```

#### Security Scanning
```bash
# Run comprehensive security scan (weekly recommended)
docker exec ytdl-service /opt/ytdl_service/security-scan.sh
```

### 2. Update Procedures

#### Container Updates
```bash
# Pull latest security updates
docker-compose pull

# Rebuild with security patches
docker-compose build --no-cache

# Deploy with zero-downtime
docker-compose up -d --force-recreate
```

#### Dependency Updates
```bash
# Update Python dependencies
pip-audit requirements.txt

# Update base image
docker pull python:3.11-slim-bullseye
```

## Security Incident Response

### 1. Incident Detection

#### Monitoring Indicators
- Unusual process activity
- Unexpected network connections
- File integrity violations
- Failed authentication attempts
- Resource usage anomalies

#### Log Analysis
```bash
# Check for security events
docker logs ytdl-service | grep -i "error\|warning\|security"

# Analyze access patterns
docker exec ytdl-service tail -f /var/log/access.log
```

### 2. Incident Response Procedures

#### Immediate Actions
1. Isolate the container: `docker network disconnect`
2. Preserve evidence: `docker commit` for forensic analysis
3. Rotate all secrets and API keys
4. Review and analyze logs
5. Patch and redeploy clean container

#### Recovery Steps
1. Identify and patch vulnerabilities
2. Rebuild container with security updates
3. Restore from clean backups
4. Implement additional monitoring
5. Update security procedures

## Compliance and Auditing

### 1. Security Compliance

#### Standards Alignment
- **CIS Docker Benchmark**: Container security best practices
- **NIST Cybersecurity Framework**: Risk management
- **OWASP Container Security**: Application security

#### Audit Trail
- All security events logged
- File integrity monitoring
- Access control logging
- Configuration change tracking

### 2. Security Documentation

#### Required Documentation
- Security architecture diagram
- Threat model and risk assessment
- Incident response procedures
- Security configuration baselines
- Regular security assessment reports

## Troubleshooting Security Issues

### Common Security Problems

#### Permission Denied Errors
```bash
# Check file permissions
docker exec ytdl-service ls -la /opt/ytdl_service/

# Fix permissions if needed
docker exec ytdl-service chmod 750 /opt/ytdl_service/app/
```

#### API Key Issues
```bash
# Check API key file
docker exec ytdl-service cat /opt/ytdl_service/config/api_key.txt

# Regenerate API key
docker exec ytdl-service /opt/ytdl_service/rotate-api-key.sh
```

#### Container Security Violations
```bash
# Check security status
docker exec ytdl-service /opt/ytdl_service/security-scan.sh

# Review security configuration
docker exec ytdl-service cat /opt/ytdl_service/security-status.txt
```

## Security Contact Information

For security-related issues or questions:
- Review this documentation first
- Check container logs for security events
- Run security scanning tools
- Follow incident response procedures
- Document and report security findings

---

**Note**: This security guide should be reviewed and updated regularly to address new threats and vulnerabilities. Security is an ongoing process, not a one-time configuration.