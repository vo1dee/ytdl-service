# Environment Variables Documentation

This document describes all environment variables used by the YouTube Download Service.

## Configuration Files

- **`.env.example`**: Template file with all available environment variables and their descriptions
- **`docker-compose.override.yml.example`**: Template for Docker Compose development overrides

## Environment Variables

### Required Variables

Currently, there are no strictly required environment variables. All variables have sensible defaults for container deployment.

### Optional Variables

#### Service Configuration

- **`YTDL_SERVICE_URL`**: Service URL for internal communication (used by Telegram bot)
  - Default: `http://localhost:8000`
  - Example: `http://ytdl-service:8000`
  - Validation: Must start with `http://` or `https://`

- **`YTDL_SERVICE_API_KEY`**: API key for service authentication
  - Default: Auto-generated if not provided
  - Example: `your-secure-api-key-here`
  - Validation: Must be at least 8 characters if provided
  - Note: If not provided, a random key will be generated and stored in `API_KEY_FILE`

- **`PORT`**: Port for the FastAPI service
  - Default: `8000`
  - Example: `8080`
  - Validation: Must be a valid port number (1-65535)

#### Download Configuration

- **`YTDL_MAX_RETRIES`**: Number of retry attempts for failed downloads
  - Default: `3`
  - Example: `5`
  - Validation: Must be between 1 and 10

- **`YTDL_RETRY_DELAY`**: Delay between retry attempts (in seconds)
  - Default: `1`
  - Example: `2`
  - Validation: Must be between 0 and 60 seconds

#### Directory Configuration

- **`DOWNLOADS_DIR`**: Downloads directory path inside container
  - Default: `/opt/ytdl_service/downloads`
  - Example: `/app/downloads`
  - Validation: Must be an absolute path
  - Note: This is the container path, not the host path

- **`LOGS_DIR`**: Logs directory path inside container
  - Default: `/var/log`
  - Example: `/app/logs`
  - Validation: Must be an absolute path
  - Note: This is the container path, not the host path

- **`API_KEY_FILE`**: API key file path inside container
  - Default: `/opt/ytdl_service/config/api_key.txt`
  - Example: `/app/config/api_key.txt`
  - Validation: Must be an absolute path
  - Note: Used for persistent API key storage

#### Maintenance Configuration

- **`YTDLP_UPDATE_INTERVAL`**: yt-dlp update check interval (in seconds)
  - Default: `86400` (24 hours)
  - Example: `3600` (1 hour)
  - Validation: Must be at least 3600 seconds (1 hour)

- **`CLEANUP_INTERVAL`**: File cleanup interval (in seconds)
  - Default: `3600` (1 hour)
  - Example: `1800` (30 minutes)
  - Validation: Must be at least 300 seconds (5 minutes)

- **`FILE_MAX_AGE`**: Maximum age for downloaded files before cleanup (in seconds)
  - Default: `86400` (24 hours)
  - Example: `7200` (2 hours)
  - Validation: Must be at least 3600 seconds (1 hour)

#### Telegram Bot Configuration (Optional)

- **`TELEGRAM_BOT_TOKEN`**: Telegram bot token
  - Default: None (Telegram bot disabled)
  - Example: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
  - Validation: Must be in format `number:string` if provided

- **`TELEGRAM_ERROR_CHAT_ID`**: Chat ID for error reporting
  - Default: None
  - Example: `-1001234567890`
  - Validation: Must be a valid chat ID (number, can be negative)

#### Advanced Configuration

- **`DEBUG`**: Debug mode
  - Default: `false`
  - Example: `true`
  - Validation: Must be `true`, `false`, `1`, `0`, `yes`, or `no`

- **`LOG_LEVEL`**: Log level
  - Default: `INFO`
  - Example: `DEBUG`
  - Validation: Must be `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`

## Docker Compose Specific Variables

These variables are used in the `docker-compose.yml` and override files:

- **`EXTERNAL_PORT`**: External port mapping for Docker Compose
  - Default: `8000`
  - Example: `8080`
  - Note: This is used in the `ports` section of docker-compose.yml

- **`DOWNLOADS_HOST_PATH`**: Host path for downloads volume
  - Default: `./downloads`
  - Example: `/home/user/ytdl-downloads`

- **`LOGS_HOST_PATH`**: Host path for logs volume
  - Default: `./logs`
  - Example: `/home/user/ytdl-logs`

- **`CONFIG_HOST_PATH`**: Host path for config volume
  - Default: `./config`
  - Example: `/home/user/ytdl-config`

## Configuration Validation

The application includes automatic configuration validation on startup:

1. **Validation**: All environment variables are validated according to their rules
2. **Defaults**: Missing optional variables are set to their default values
3. **Errors**: Invalid values cause the application to exit with an error message
4. **Warnings**: Non-critical issues (like directory permissions) generate warnings
5. **Logging**: Configuration summary is logged on startup

### Validation Features

- **Type checking**: Ensures numeric values are valid numbers
- **Range validation**: Checks that values are within acceptable ranges
- **Path validation**: Verifies that paths are absolute (for container paths)
- **Directory creation**: Attempts to create required directories
- **Permission checking**: Warns about permission issues

## Usage Examples

### Basic Setup

```bash
# Copy the example file
cp .env.example .env

# Edit the file with your values
nano .env
```

### Development Setup

```bash
# Copy the override example
cp docker-compose.override.yml.example docker-compose.override.yml

# Edit for development settings
nano docker-compose.override.yml

# Start with development settings
docker-compose up -d
```

### Production Setup

```bash
# Set environment variables directly
export YTDL_SERVICE_API_KEY="your-secure-production-key"
export YTDL_MAX_RETRIES=5
export FILE_MAX_AGE=172800  # 48 hours

# Or use a production .env file
cp .env.example .env.production
# Edit .env.production with production values
docker-compose --env-file .env.production up -d
```

## Troubleshooting

### Configuration Validation Errors

If you see configuration validation errors on startup:

1. Check the error message for specific validation failures
2. Verify environment variable values match the validation rules
3. Ensure directory paths are absolute (start with `/`)
4. Check that numeric values are within acceptable ranges

### Permission Warnings

If you see permission warnings:

1. Ensure the container has write access to mounted volumes
2. Check that the user running the container has appropriate permissions
3. Consider using Docker volume mounts instead of bind mounts for better permission handling

### Common Issues

- **Port conflicts**: Change `PORT` or `EXTERNAL_PORT` if port 8000 is in use
- **Directory permissions**: Ensure mounted directories are writable by the container user
- **API key issues**: Let the system auto-generate the API key or provide a secure one
- **Telegram bot not working**: Verify `TELEGRAM_BOT_TOKEN` format and permissions