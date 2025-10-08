# YouTube Download Service

A FastAPI-based service for downloading YouTube videos with API key authentication. Supports both traditional Python deployment and Docker containerization for easy deployment and scaling.

## Features

- 🔒 Secure API key authentication
- 📹 Download YouTube videos in various formats
- 🚀 Fast downloads using yt-dlp
- 📝 Detailed logging
- 🔍 Health check endpoint
- 🌐 CORS support
- 🗑️ File management (download & delete)
- 📦 List available files for download
- 🛠️ Graceful error handling and informative responses
- 🐳 Docker containerization support
- 📊 Health monitoring and metrics
- 🔄 Automatic cleanup and maintenance

## Prerequisites

### For Docker Deployment (Recommended)
- Docker Engine 20.10+ or Docker Desktop
- Docker Compose 2.0+
- At least 2GB available disk space

### For Traditional Python Deployment
- Python 3.8 or higher
- Linux/Unix system (for service deployment)
- Sufficient disk space for downloads

## Quick Start (Docker - Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/vo1dee/ytdl-service.git
   cd ytdl-service
   ```

2. Start with Docker Compose:
   ```bash
   # Copy environment template
   cp .env.example .env
   
   # Build and start the service
   docker-compose up -d
   
   # View logs
   docker-compose logs -f ytdl-service
   ```

3. Access the service:
   - API: http://localhost:8000
   - Health Check: http://localhost:8000/health
   - API Documentation: http://localhost:8000/docs

## Installation Options

### Option 1: Docker Deployment (Recommended)

See the [Docker Deployment Guide](DOCKER_DEPLOYMENT.md) for comprehensive Docker setup instructions, including:
- Basic development setup
- Production deployment with reverse proxy
- Multi-instance load balancing
- Docker Swarm and Kubernetes examples

### Option 2: Traditional Python Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/vo1dee/ytdl-service.git
   cd ytdl-service
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create required directories:
   ```bash
   sudo mkdir -p /opt/ytdl_service/downloads
   sudo mkdir -p /opt/ytdl_service/logs
   sudo chown -R $USER:$USER /opt/ytdl_service
   ```

## Creating a Systemd Service

To run the YouTube Download Service as a systemd service, create a service file:

1. Create and edit the service file:
   ```bash
   sudo nano /etc/systemd/system/ytdl_service.service
   ```

2. Add the following content to the file:
   ```ini
   [Unit]
   Description=YouTube Download Service
   After=network.target

   [Service]
   Type=simple
   User=your_username  # Replace with the user that should run the service
   ExecStart=/path/to/your/venv/bin/python /path/to/your/ytdl-service/download_service.py

   [Install]
   WantedBy=multi-user.target
   ```

3. Save and exit the editor.

4. Enable and start the service:
   ```bash
   sudo systemctl enable ytdl_service
   sudo systemctl start ytdl_service
   ```

5. Check the status of the service:
   ```bash
   sudo systemctl status ytdl_service
   ```

## API Endpoints

### Download Video
```http
POST /download
X-API-Key: your-api-key

{
  "url": "https://www.youtube.com/watch?v=...",
  "format": "best"  # optional
}
```

### Retrieve File
```http
GET /files/{filename}
X-API-Key: your-api-key
```

### List Files
```http
GET /files
X-API-Key: your-api-key
```

### Delete File
```http
DELETE /files/{filename}
X-API-Key: your-api-key
```

### Health Check
```http
GET /health
X-API-Key: your-api-key
```

## Security

- API key is auto-generated on first run
- Key location: `/opt/ytdl_service/api_key.txt`
- All endpoints require authentication
- CORS enabled for specified origins

## Logging

Service logs are stored in `/var/log/ytdl_service.log` with the following information:
- Timestamp
- Request method and path
- Response status and duration
- Download progress
- Error details (if any)

## Documentation

### Docker Deployment
- [Docker Deployment Guide](DOCKER_DEPLOYMENT.md) - Comprehensive Docker setup and deployment instructions
- [Docker Examples](DOCKER_EXAMPLES.md) - Practical examples for different deployment scenarios
- [Volume Management and Backup Guide](VOLUME_MANAGEMENT.md) - Data persistence and backup strategies
- [Troubleshooting Guide](TROUBLESHOOTING.md) - Common issues and solutions

### Configuration
- [Environment Variables](ENVIRONMENT_VARIABLES.md) - Complete configuration options
- [Health Monitoring](HEALTH_MONITORING.md) - Health check and monitoring setup

### iOS Compatibility
- [iOS Compatibility Guide](iOS_COMPATIBILITY.md) - iOS-specific download optimizations

## Management Scripts

The service includes several management scripts for easy operation:

```bash
# Build Docker image
./build.sh

# Run container
./run.sh

# Stop container
./stop.sh

# View logs
./logs.sh

# Health check
./health_check.sh
```

## Development

### Docker Development Setup
```bash
# Clone and setup
git clone https://github.com/vo1dee/ytdl-service.git
cd ytdl-service

# Start development environment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f ytdl-service
```

### Local Python Setup
```bash
# Clone and setup
git clone https://github.com/vo1dee/ytdl-service.git
cd ytdl-service
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run service
python download_service.py
```

```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT