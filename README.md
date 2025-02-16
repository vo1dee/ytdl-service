# YouTube Download Service

A FastAPI-based service for downloading YouTube videos with API key authentication.

## Features

- 🔒 Secure API key authentication
- 📹 Download YouTube videos in various formats
- 🚀 Fast downloads using yt-dlp
- 📝 Detailed logging
- 🔍 Health check endpoint
- 🌐 CORS support
- 🗑️ File management (download & delete)

## Prerequisites

- Python 3.8 or higher
- Linux/Unix system (for service deployment)
- Sufficient disk space for downloads

## Installation

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
   ExecStart=/path/to/your/venv/bin/python /path/to/your/youtube-download-service/download_service.py

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

## Development

### Local Setup
```bash
# Clone and setup
git clone [your-repo-url]
cd youtube-download-service
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run service
python download_service.py
```

### Running Tests
```bash
pytest
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License
 
 MIT