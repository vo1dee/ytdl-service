# Volume Management and Backup Guide

## Overview

This guide covers volume management strategies, backup procedures, and data recovery for the YouTube Download Service Docker deployment. Proper volume management ensures data persistence, enables easy backups, and facilitates disaster recovery.

## Volume Structure

### Default Volume Layout

```
Host System:
├── downloads/              # Downloaded video files
├── logs/                   # Application and system logs
└── config/                 # Configuration files (optional)
    └── api_key.txt

Container Paths:
├── /opt/ytdl_service/downloads/    # Mounted from ./downloads
├── /var/log/                       # Mounted from ./logs
└── /opt/ytdl_service/              # Mounted from ./config (optional)
```

### Volume Types

#### 1. Downloads Volume
- **Purpose**: Store downloaded video files
- **Size**: Variable (depends on usage)
- **Backup Priority**: High
- **Retention**: Based on usage policy

#### 2. Logs Volume
- **Purpose**: Application logs and system logs
- **Size**: Moderate (with log rotation)
- **Backup Priority**: Medium
- **Retention**: 30-90 days typical

#### 3. Configuration Volume
- **Purpose**: API keys and configuration files
- **Size**: Small (< 1MB)
- **Backup Priority**: Critical
- **Retention**: Permanent

## Volume Configuration

### Docker Run Configuration

```bash
# Basic volume mounts
docker run -d \
  --name ytdl-service \
  -v $(pwd)/downloads:/opt/ytdl_service/downloads \
  -v $(pwd)/logs:/var/log \
  -v $(pwd)/config:/opt/ytdl_service/config \
  ytdl-service:latest

# With specific volume drivers
docker run -d \
  --name ytdl-service \
  -v ytdl-downloads:/opt/ytdl_service/downloads \
  -v ytdl-logs:/var/log \
  ytdl-service:latest
```

### Docker Compose Configuration

```yaml
version: '3.8'
services:
  ytdl-service:
    image: ytdl-service:latest
    volumes:
      # Bind mounts (recommended for easy access)
      - ./downloads:/opt/ytdl_service/downloads
      - ./logs:/var/log
      - ./config:/opt/ytdl_service/config
      
      # Named volumes (recommended for production)
      # - ytdl-downloads:/opt/ytdl_service/downloads
      # - ytdl-logs:/var/log
      # - ytdl-config:/opt/ytdl_service/config

# Named volumes definition
volumes:
  ytdl-downloads:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/ytdl/downloads
  ytdl-logs:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/ytdl/logs
  ytdl-config:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/ytdl/config
```

### Production Volume Configuration

```yaml
# Production-ready volume configuration
version: '3.8'
services:
  ytdl-service:
    image: ytdl-service:latest
    volumes:
      - type: bind
        source: /data/ytdl/downloads
        target: /opt/ytdl_service/downloads
        bind:
          propagation: rprivate
      - type: bind
        source: /data/ytdl/logs
        target: /var/log
        bind:
          propagation: rprivate
      - type: bind
        source: /data/ytdl/config
        target: /opt/ytdl_service/config
        read_only: true
```

## Backup Strategies

### 1. Simple File-Based Backup

#### Daily Backup Script

```bash
#!/bin/bash
# backup-daily.sh - Daily backup script

BACKUP_DIR="/backup/ytdl-service"
DATE=$(date +%Y%m%d)
RETENTION_DAYS=30

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup downloads (incremental)
rsync -av --link-dest="$BACKUP_DIR/latest" \
  ./downloads/ "$BACKUP_DIR/$DATE/downloads/"

# Backup logs
tar -czf "$BACKUP_DIR/$DATE/logs-$DATE.tar.gz" ./logs/

# Backup configuration
cp -r ./config/ "$BACKUP_DIR/$DATE/config/"

# Update latest symlink
rm -f "$BACKUP_DIR/latest"
ln -s "$DATE" "$BACKUP_DIR/latest"

# Cleanup old backups
find "$BACKUP_DIR" -maxdepth 1 -type d -name "20*" -mtime +$RETENTION_DAYS -exec rm -rf {} \;

echo "Backup completed: $BACKUP_DIR/$DATE"
```

#### Weekly Full Backup

```bash
#!/bin/bash
# backup-weekly.sh - Weekly full backup script

BACKUP_DIR="/backup/ytdl-service/weekly"
DATE=$(date +%Y%m%d)

# Create compressed archive
tar -czf "$BACKUP_DIR/ytdl-full-$DATE.tar.gz" \
  --exclude='./logs/*.log' \
  ./downloads/ ./config/

# Cleanup old weekly backups (keep 8 weeks)
find "$BACKUP_DIR" -name "ytdl-full-*.tar.gz" -mtime +56 -delete

echo "Weekly backup completed: $BACKUP_DIR/ytdl-full-$DATE.tar.gz"
```

### 2. Docker Volume Backup

#### Backup Named Volumes

```bash
#!/bin/bash
# backup-volumes.sh - Backup Docker volumes

BACKUP_DIR="/backup/docker-volumes"
DATE=$(date +%Y%m%d-%H%M%S)

# Backup downloads volume
docker run --rm \
  -v ytdl-downloads:/data \
  -v "$BACKUP_DIR:/backup" \
  alpine tar -czf "/backup/downloads-$DATE.tar.gz" -C /data .

# Backup logs volume
docker run --rm \
  -v ytdl-logs:/data \
  -v "$BACKUP_DIR:/backup" \
  alpine tar -czf "/backup/logs-$DATE.tar.gz" -C /data .

# Backup config volume
docker run --rm \
  -v ytdl-config:/data \
  -v "$BACKUP_DIR:/backup" \
  alpine tar -czf "/backup/config-$DATE.tar.gz" -C /data .

echo "Volume backup completed: $BACKUP_DIR/*-$DATE.tar.gz"
```

### 3. Automated Backup with Cron

```bash
# Add to crontab (crontab -e)

# Daily backup at 2 AM
0 2 * * * /path/to/backup-daily.sh >> /var/log/ytdl-backup.log 2>&1

# Weekly backup on Sunday at 3 AM
0 3 * * 0 /path/to/backup-weekly.sh >> /var/log/ytdl-backup.log 2>&1

# Monthly cleanup on first day of month at 4 AM
0 4 1 * * /path/to/cleanup-old-backups.sh >> /var/log/ytdl-backup.log 2>&1
```

### 4. Cloud Backup Integration

#### AWS S3 Backup

```bash
#!/bin/bash
# backup-s3.sh - Backup to AWS S3

S3_BUCKET="your-backup-bucket"
DATE=$(date +%Y%m%d)

# Create local backup
./backup-daily.sh

# Sync to S3
aws s3 sync "/backup/ytdl-service/$DATE" "s3://$S3_BUCKET/ytdl-service/$DATE/"

# Cleanup old S3 backups (keep 90 days)
aws s3 ls "s3://$S3_BUCKET/ytdl-service/" | \
  awk '{print $2}' | \
  while read -r folder; do
    folder_date=$(echo "$folder" | tr -d '/')
    if [[ $(date -d "$folder_date" +%s 2>/dev/null) -lt $(date -d "90 days ago" +%s) ]]; then
      aws s3 rm "s3://$S3_BUCKET/ytdl-service/$folder" --recursive
    fi
  done
```

#### Google Cloud Storage Backup

```bash
#!/bin/bash
# backup-gcs.sh - Backup to Google Cloud Storage

GCS_BUCKET="your-backup-bucket"
DATE=$(date +%Y%m%d)

# Create local backup
./backup-daily.sh

# Upload to GCS
gsutil -m rsync -r -d "/backup/ytdl-service/$DATE" "gs://$GCS_BUCKET/ytdl-service/$DATE/"

# Cleanup old GCS backups
gsutil ls "gs://$GCS_BUCKET/ytdl-service/" | \
  grep -E "gs://$GCS_BUCKET/ytdl-service/[0-9]{8}/" | \
  while read -r folder; do
    folder_date=$(basename "$folder")
    if [[ $(date -d "$folder_date" +%s 2>/dev/null) -lt $(date -d "90 days ago" +%s) ]]; then
      gsutil -m rm -r "$folder"
    fi
  done
```

## Data Recovery

### 1. Restore from File Backup

#### Restore Downloads

```bash
#!/bin/bash
# restore-downloads.sh - Restore downloads from backup

BACKUP_DATE="20250108"  # Specify backup date
BACKUP_DIR="/backup/ytdl-service"

# Stop service
docker-compose down

# Backup current data (safety)
mv ./downloads ./downloads.backup.$(date +%Y%m%d-%H%M%S)

# Restore from backup
rsync -av "$BACKUP_DIR/$BACKUP_DATE/downloads/" ./downloads/

# Fix permissions
sudo chown -R 1000:1000 ./downloads
chmod -R 755 ./downloads

# Start service
docker-compose up -d

echo "Downloads restored from $BACKUP_DATE"
```

#### Restore Configuration

```bash
#!/bin/bash
# restore-config.sh - Restore configuration from backup

BACKUP_DATE="20250108"
BACKUP_DIR="/backup/ytdl-service"

# Stop service
docker-compose down

# Backup current config
cp -r ./config ./config.backup.$(date +%Y%m%d-%H%M%S)

# Restore configuration
cp -r "$BACKUP_DIR/$BACKUP_DATE/config/" ./config/

# Fix permissions
sudo chown -R 1000:1000 ./config
chmod -R 644 ./config/*

# Start service
docker-compose up -d

echo "Configuration restored from $BACKUP_DATE"
```

### 2. Restore Docker Volumes

```bash
#!/bin/bash
# restore-volumes.sh - Restore Docker volumes from backup

BACKUP_FILE="/backup/docker-volumes/downloads-20250108-140000.tar.gz"

# Stop service
docker-compose down

# Restore volume
docker run --rm \
  -v ytdl-downloads:/data \
  -v "$(dirname "$BACKUP_FILE"):/backup" \
  alpine sh -c "cd /data && tar -xzf /backup/$(basename "$BACKUP_FILE")"

# Start service
docker-compose up -d

echo "Volume restored from $BACKUP_FILE"
```

### 3. Disaster Recovery Procedure

#### Complete System Recovery

```bash
#!/bin/bash
# disaster-recovery.sh - Complete system recovery

BACKUP_DATE="20250108"
BACKUP_DIR="/backup/ytdl-service"

echo "Starting disaster recovery for $BACKUP_DATE..."

# 1. Prepare directories
mkdir -p downloads logs config
sudo chown -R 1000:1000 downloads logs config

# 2. Restore downloads
echo "Restoring downloads..."
rsync -av "$BACKUP_DIR/$BACKUP_DATE/downloads/" ./downloads/

# 3. Restore configuration
echo "Restoring configuration..."
cp -r "$BACKUP_DIR/$BACKUP_DATE/config/" ./config/

# 4. Restore logs (optional)
echo "Restoring logs..."
tar -xzf "$BACKUP_DIR/$BACKUP_DATE/logs-$BACKUP_DATE.tar.gz" -C ./logs/

# 5. Fix permissions
sudo chown -R 1000:1000 downloads logs config
chmod -R 755 downloads logs
chmod -R 644 config/*

# 6. Start services
echo "Starting services..."
docker-compose up -d

# 7. Verify recovery
sleep 10
curl -f http://localhost:8000/health && echo "Recovery successful!" || echo "Recovery failed!"

echo "Disaster recovery completed"
```

## Monitoring and Maintenance

### 1. Disk Usage Monitoring

```bash
#!/bin/bash
# monitor-disk-usage.sh - Monitor volume disk usage

DOWNLOADS_DIR="./downloads"
LOGS_DIR="./logs"
THRESHOLD=80  # Alert threshold (%)

# Check downloads directory
DOWNLOADS_USAGE=$(df "$DOWNLOADS_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DOWNLOADS_USAGE" -gt "$THRESHOLD" ]; then
  echo "WARNING: Downloads directory is ${DOWNLOADS_USAGE}% full"
  # Send alert (email, Slack, etc.)
fi

# Check logs directory
LOGS_USAGE=$(df "$LOGS_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$LOGS_USAGE" -gt "$THRESHOLD" ]; then
  echo "WARNING: Logs directory is ${LOGS_USAGE}% full"
  # Send alert (email, Slack, etc.)
fi

# Show largest files
echo "Largest download files:"
du -sh "$DOWNLOADS_DIR"/* 2>/dev/null | sort -hr | head -10
```

### 2. Automated Cleanup

```bash
#!/bin/bash
# cleanup-old-files.sh - Automated cleanup of old files

DOWNLOADS_DIR="./downloads"
LOGS_DIR="./logs"
DOWNLOADS_RETENTION=30  # days
LOGS_RETENTION=7       # days

# Cleanup old downloads
echo "Cleaning up downloads older than $DOWNLOADS_RETENTION days..."
find "$DOWNLOADS_DIR" -type f -mtime +$DOWNLOADS_RETENTION -delete

# Cleanup old logs
echo "Cleaning up logs older than $LOGS_RETENTION days..."
find "$LOGS_DIR" -name "*.log" -mtime +$LOGS_RETENTION -delete

# Compress old logs
find "$LOGS_DIR" -name "*.log" -mtime +1 -exec gzip {} \;

echo "Cleanup completed"
```

### 3. Backup Verification

```bash
#!/bin/bash
# verify-backup.sh - Verify backup integrity

BACKUP_DIR="/backup/ytdl-service"
LATEST_BACKUP="$BACKUP_DIR/latest"

if [ ! -L "$LATEST_BACKUP" ]; then
  echo "ERROR: No latest backup found"
  exit 1
fi

BACKUP_DATE=$(readlink "$LATEST_BACKUP")
echo "Verifying backup: $BACKUP_DATE"

# Check backup completeness
if [ ! -d "$BACKUP_DIR/$BACKUP_DATE/downloads" ]; then
  echo "ERROR: Downloads backup missing"
  exit 1
fi

if [ ! -f "$BACKUP_DIR/$BACKUP_DATE/logs-$BACKUP_DATE.tar.gz" ]; then
  echo "ERROR: Logs backup missing"
  exit 1
fi

if [ ! -d "$BACKUP_DIR/$BACKUP_DATE/config" ]; then
  echo "ERROR: Config backup missing"
  exit 1
fi

# Verify archive integrity
tar -tzf "$BACKUP_DIR/$BACKUP_DATE/logs-$BACKUP_DATE.tar.gz" > /dev/null
if [ $? -ne 0 ]; then
  echo "ERROR: Logs archive is corrupted"
  exit 1
fi

echo "Backup verification successful"
```

## Best Practices

### 1. Volume Management

- Use named volumes for production deployments
- Implement proper backup strategies before going live
- Monitor disk usage regularly
- Set up automated cleanup for old files
- Use appropriate file permissions (1000:1000 for container user)

### 2. Backup Strategy

- Implement 3-2-1 backup rule (3 copies, 2 different media, 1 offsite)
- Test backup restoration regularly
- Automate backup processes with cron jobs
- Monitor backup job success/failure
- Document recovery procedures

### 3. Security Considerations

- Encrypt backups containing sensitive data
- Secure backup storage locations
- Limit access to backup files
- Regularly rotate backup encryption keys
- Audit backup access logs

### 4. Performance Optimization

- Use SSD storage for frequently accessed volumes
- Implement log rotation to prevent disk space issues
- Consider using compression for backup storage
- Monitor I/O performance on volume mounts
- Use appropriate Docker volume drivers for your storage backend

## Troubleshooting Volume Issues

### Common Problems

1. **Permission Denied**
   ```bash
   # Fix volume permissions
   sudo chown -R 1000:1000 downloads logs config
   chmod -R 755 downloads logs
   ```

2. **Volume Not Mounting**
   ```bash
   # Check volume configuration
   docker inspect ytdl-service | grep -A 10 "Mounts"
   
   # Recreate with absolute paths
   docker run -v /full/path/to/downloads:/opt/ytdl_service/downloads ytdl-service
   ```

3. **Backup Corruption**
   ```bash
   # Verify backup integrity
   tar -tzf backup-file.tar.gz
   
   # Use checksums for verification
   sha256sum backup-file.tar.gz > backup-file.tar.gz.sha256
   ```

4. **Insufficient Disk Space**
   ```bash
   # Check disk usage
   df -h
   du -sh downloads/* | sort -hr
   
   # Clean up old files
   find downloads -type f -mtime +30 -delete
   ```

For additional volume management support, refer to the main [Docker Deployment Guide](DOCKER_DEPLOYMENT.md) and [Troubleshooting Guide](TROUBLESHOOTING.md).