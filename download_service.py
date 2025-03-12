from fastapi import FastAPI, HTTPException, Request, Depends, Security, BackgroundTasks
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS
import secrets
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator, HttpUrl
import yt_dlp
import os
import logging
from logging.handlers import RotatingFileHandler
import shutil
from datetime import datetime, timedelta
import time
from fastapi.responses import FileResponse
import mimetypes
import uuid
import hashlib
from typing import Optional, List, Dict, Any
import json
import asyncio
import subprocess
import platform
# For rate limiting - make sure these are installed from requirements.txt
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import aioredis

# Set up logging with log rotation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            '/var/log/ytdl_service.log', 
            maxBytes=10485760,  # 10MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ytdl_service')

# Configuration with environment variable support
class Config:
    API_KEY_FILE = os.environ.get("API_KEY_FILE", "/opt/ytdl_service/api_key.txt")
    DOWNLOADS_DIR = os.environ.get("DOWNLOADS_DIR", "/opt/ytdl_service/downloads")
    TEMP_DIR = os.environ.get("TEMP_DIR", "/opt/ytdl_service/temp")
    MAX_FILE_AGE_DAYS = int(os.environ.get("MAX_FILE_AGE_DAYS", "7"))
    MAX_STORAGE_GB = float(os.environ.get("MAX_STORAGE_GB", "10"))
    ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",") or ["*"]
    MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "3"))
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost")

config = Config()

# Create necessary directories
os.makedirs(config.DOWNLOADS_DIR, exist_ok=True)
os.makedirs(config.TEMP_DIR, exist_ok=True)

# Handle API key securely
def generate_api_key():
    return secrets.token_urlsafe(32)

def get_api_key_hash():
    if not os.path.exists(config.API_KEY_FILE):
        logger.warning("API Key file missing, generating a new one.")
        api_key = generate_api_key()
        with open(config.API_KEY_FILE, "w") as f:
            f.write(api_key)
        # Store a hash of the key for verification
        with open(f"{config.API_KEY_FILE}.hash", "w") as f:
            f.write(hashlib.sha256(api_key.encode()).hexdigest())
        return api_key
    else:
        with open(config.API_KEY_FILE) as f:
            return f.read().strip()

API_KEY = get_api_key_hash()
api_key_header = APIKeyHeader(name="X-API-Key")

# Track active downloads
active_downloads = {}
download_lock = asyncio.Lock()

app = FastAPI(title="YouTube Download Service", 
              description="A service to download and convert YouTube videos",
              version="1.0.0")

@app.on_event("startup")
async def startup():
    # Initialize Redis for rate limiting
    redis = await aioredis.from_url(config.REDIS_URL, encoding="utf8")
    await FastAPILimiter.init(redis)
    
    # Start cleanup task
    asyncio.create_task(periodic_cleanup())

@app.on_event("shutdown")
async def shutdown():
    # Clean up any temporary files
    if os.path.exists(config.TEMP_DIR):
        shutil.rmtree(config.TEMP_DIR)
        os.makedirs(config.TEMP_DIR, exist_ok=True)

async def verify_api_key(api_key_header: str = Security(api_key_header)):
    # Verify against stored hash
    with open(f"{config.API_KEY_FILE}.hash") as f:
        stored_hash = f.read().strip()
    
    if hashlib.sha256(api_key_header.encode()).hexdigest() != stored_hash:
        logger.warning(f"Invalid API key attempt from {request.client.host}")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid API key"
        )
    return api_key_header

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: HttpUrl
    format: str = 'best'
    convert_to: Optional[str] = 'mp4'
    audio_only: bool = False
    
    @validator('format')
    def validate_format(cls, v):
        allowed_formats = ['best', 'bestvideo', 'bestaudio', '1080p', '720p', '480p', '360p']
        if v not in allowed_formats and not v.startswith('bestvideo[height<='):
            raise ValueError(f"Format must be one of {allowed_formats} or bestvideo[height<=NNN]")
        return v
    
    @validator('convert_to')
    def validate_convert_to(cls, v):
        if v and v not in ['mp4', 'mkv', 'webm', 'mp3', 'aac', 'm4a', None]:
            raise ValueError("Conversion format must be mp4, mkv, webm, mp3, aac, m4a, or null")
        return v

class DownloadStatus(BaseModel):
    id: str
    url: str
    status: str
    progress: float = 0
    eta: Optional[int] = None
    file_path: Optional[str] = None
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

@app.middleware("http")
async def log_requests_and_errors(request: Request, call_next):
    """Middleware for logging requests and handling errors."""
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Sanitize URL for logging (remove query parameters)
    sanitized_url = str(request.url).split('?')[0]
    
    logger.info(f"Request {request_id} started: {request.method} {sanitized_url}")
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        logger.info(
            f"Request {request_id} completed: {request.method} {sanitized_url} "
            f"Status: {response.status_code}, Duration: {duration:.2f}s"
        )
        return response
    except Exception as e:
        logger.error(f"Request {request_id} failed: {sanitized_url} - Error: {str(e)}")
        raise

async def periodic_cleanup():
    """Periodically clean up old files and check storage usage"""
    while True:
        try:
            await cleanup_old_files()
            await check_storage_usage()
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
        
        await asyncio.sleep(3600)  # Run every hour

async def cleanup_old_files():
    """Delete files older than MAX_FILE_AGE_DAYS"""
    now = datetime.now()
    cutoff = now - timedelta(days=config.MAX_FILE_AGE_DAYS)
    
    for filename in os.listdir(config.DOWNLOADS_DIR):
        file_path = os.path.join(config.DOWNLOADS_DIR, filename)
        if os.path.isfile(file_path):
            file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_modified < cutoff:
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted old file: {filename}")
                except Exception as e:
                    logger.error(f"Failed to delete {filename}: {str(e)}")

async def check_storage_usage():
    """Check if storage usage exceeds MAX_STORAGE_GB"""
    total_size = 0
    for dirpath, _, filenames in os.walk(config.DOWNLOADS_DIR):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    
    # Convert bytes to GB
    total_size_gb = total_size / (1024 ** 3)
    
    if total_size_gb > config.MAX_STORAGE_GB:
        logger.warning(f"Storage limit exceeded: {total_size_gb:.2f}GB used out of {config.MAX_STORAGE_GB}GB limit")
        # Delete oldest files until we're under the limit
        files = []
        for filename in os.listdir(config.DOWNLOADS_DIR):
            file_path = os.path.join(config.DOWNLOADS_DIR, filename)
            if os.path.isfile(file_path):
                files.append((file_path, os.path.getmtime(file_path)))
        
        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x[1])
        
        for file_path, _ in files:
            try:
                file_size = os.path.getsize(file_path) / (1024 ** 3)  # Size in GB
                os.remove(file_path)
                logger.info(f"Deleted file due to storage limit: {os.path.basename(file_path)}")
                
                total_size_gb -= file_size
                if total_size_gb <= config.MAX_STORAGE_GB:
                    break
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {str(e)}")

def progress_hook(d, download_id):
    """Update download progress information"""
    if d['status'] == 'downloading':
        if '_percent_str' in d:
            percent = float(d['_percent_str'].strip('%'))
        else:
            percent = 0
            
        eta = d.get('eta', None)
        
        if download_id in active_downloads:
            active_downloads[download_id]['progress'] = percent
            active_downloads[download_id]['eta'] = eta
    
    elif d['status'] == 'finished':
        if download_id in active_downloads:
            active_downloads[download_id]['status'] = 'processing'
    
    elif d['status'] == 'error':
        if download_id in active_downloads:
            active_downloads[download_id]['status'] = 'error'
            active_downloads[download_id]['error'] = d.get('error', 'Unknown error')

async def download_video_task(download_id: str, request: DownloadRequest):
    """Background task to download video"""
    async with download_lock:
        # Check if we're at max concurrent downloads
        active_count = sum(1 for v in active_downloads.values() if v['status'] in ['downloading', 'processing'])
        if active_count >= config.MAX_CONCURRENT_DOWNLOADS:
            active_downloads[download_id]['status'] = 'error'
            active_downloads[download_id]['error'] = 'Too many concurrent downloads'
            return

    try:
        # Update status to downloading
        active_downloads[download_id]['status'] = 'downloading'
        
        # Create temp directory for this download
        temp_dir = os.path.join(config.TEMP_DIR, download_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Set up output template
        temp_output = os.path.join(temp_dir, '%(title).100s-%(id)s.%(ext)s')
        final_output = os.path.join(config.DOWNLOADS_DIR, '%(title).100s-%(id)s.%(ext)s')
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': request.format,
            'outtmpl': temp_output,
            'quiet': True,
            'no_warnings': False,
            'nocheckcertificate': True,
            'restrictfilenames': True,
            'prefer_ffmpeg': True,
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
        }
        
        # Handle format conversion
        if request.convert_to:
            if request.audio_only:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': request.convert_to if request.convert_to in ['mp3', 'aac', 'm4a'] else 'mp3',
                    'preferredquality': '192',
                }]
            else:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': request.convert_to,
                }]
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting video info for {download_id}...")
            info = ydl.extract_info(request.url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            # Handle format conversion changing the extension
            if not os.path.exists(downloaded_file):
                possible_extensions = ['.mp4', '.mkv', '.webm', '.mp3', '.m4a', '.aac']
                for ext in possible_extensions:
                    potential_file = os.path.splitext(downloaded_file)[0] + ext
                    if os.path.exists(potential_file):
                        downloaded_file = potential_file
                        break
                else:
                    raise Exception(f"File not found after download")
            
            # Move from temp to downloads directory
            final_file = os.path.join(config.DOWNLOADS_DIR, os.path.basename(downloaded_file))
            shutil.move(downloaded_file, final_file)
            
            # Calculate file hash for integrity
            file_hash = hashlib.md5()
            with open(final_file, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    file_hash.update(chunk)
            
            # Update download status
            active_downloads[download_id]['status'] = 'completed'
            active_downloads[download_id]['file_path'] = os.path.basename(final_file)
            active_downloads[download_id]['completed_at'] = datetime.now()
            active_downloads[download_id]['file_hash'] = file_hash.hexdigest()
            active_downloads[download_id]['metadata'] = {
                'title': info.get('title', 'Video'),
                'description': info.get('description', ''),
                'duration': info.get('duration', 0),
                'upload_date': info.get('upload_date', ''),
                'uploader': info.get('uploader', ''),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'tags': info.get('tags', []),
                'categories': info.get('categories', []),
                'filesize': os.path.getsize(final_file),
                'filesize_formatted': format_size(os.path.getsize(final_file))
            }
            
            logger.info(f"Successfully downloaded: {final_file}")
    
    except Exception as e:
        logger.error(f"Download failed for {download_id}: {str(e)}")
        active_downloads[download_id]['status'] = 'error'
        active_downloads[download_id]['error'] = str(e)
    
    finally:
        # Clean up temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def format_size(size_bytes):
    """Format file size in human-readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"

@app.post("/download", 
          response_model=DownloadStatus,
          dependencies=[Depends(RateLimiter(times=10, seconds=60))])
async def start_download(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    try:
        # Generate a unique ID for this download
        download_id = str(uuid.uuid4())
        
        # Initialize download status
        active_downloads[download_id] = {
            'id': download_id,
            'url': str(request.url),
            'status': 'queued',
            'progress': 0,
            'started_at': datetime.now(),
            'completed_at': None,
            'file_path': None,
            'error': None
        }
        
        # Start download in background
        background_tasks.add_task(download_video_task, download_id, request)
        
        return DownloadStatus(**active_downloads[download_id])
    
    except Exception as e:
        logger.error(f"Failed to start download: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{download_id}", response_model=DownloadStatus)
async def get_download_status(
    download_id: str,
    api_key: str = Depends(verify_api_key)
):
    if download_id not in active_downloads:
        raise HTTPException(status_code=404, detail="Download not found")
    
    return DownloadStatus(**active_downloads[download_id])

@app.get("/downloads", response_model=List[DownloadStatus])
async def list_downloads(
    status: Optional[str] = None,
    api_key: str = Depends(verify_api_key)
):
    filtered_downloads = []
    for download in active_downloads.values():
        if status is None or download['status'] == status:
            filtered_downloads.append(DownloadStatus(**download))
    
    return filtered_downloads

@app.get("/files/{filename}")
async def get_file(
    filename: str,
    api_key: str = Depends(verify_api_key)
):
    file_path = os.path.join(config.DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(
        file_path, 
        media_type=media_type or "application/octet-stream", 
        filename=filename
    )

@app.get("/files")
async def list_files(
    api_key: str = Depends(verify_api_key)
):
    files = []
    for filename in os.listdir(config.DOWNLOADS_DIR):
        file_path = os.path.join(config.DOWNLOADS_DIR, filename)
        if os.path.isfile(file_path):
            size = os.path.getsize(file_path)
            modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            files.append({
                "filename": filename,
                "size": size,
                "size_formatted": format_size(size),
                "modified": modified.isoformat(),
                "media_type": mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            })
    
    return {"files": files}

@app.delete("/files/{filename}")
async def delete_file(
    filename: str,
    api_key: str = Depends(verify_api_key)
):
    file_path = os.path.join(config.DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    os.remove(file_path)
    logger.info(f"Successfully deleted file: {filename}")
    
    return {"success": True, "message": f"File {filename} deleted successfully"}

@app.get("/storage")
async def get_storage_info(
    api_key: str = Depends(verify_api_key)
):
    total_size = 0
    file_count = 0
    for dirpath, _, filenames in os.walk(config.DOWNLOADS_DIR):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
            file_count += 1
    
    total_size_gb = total_size / (1024 ** 3)
    
    return {
        "total_size": total_size,
        "total_size_formatted": format_size(total_size),
        "file_count": file_count,
        "max_storage_gb": config.MAX_STORAGE_GB,
        "usage_percentage": (total_size_gb / config.MAX_STORAGE_GB) * 100 if config.MAX_STORAGE_GB > 0 else 0
    }

@app.get("/version")
async def check_version(api_key: str = Depends(verify_api_key)):
    try:
        ffmpeg_status, ffmpeg_version = "Not installed", None
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                ffmpeg_status = "Installed"
                # Extract version from the first line
                ffmpeg_version = result.stdout.split('\n')[0]
        except:
            pass
            
        return {
            "service_version": "1.0.0",
            "yt_dlp_version": yt_dlp.version.__version__,
            "ffmpeg_status": ffmpeg_status,
            "ffmpeg_version": ffmpeg_version,
            "python_version": platform.python_version()
        }
    except Exception as e:
        logger.error(f"Version check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    # Public endpoint, no API key required
    try:
        # Check if downloads directory is writable
        test_file = os.path.join(config.DOWNLOADS_DIR, "test.txt")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        
        # Check yt-dlp functionality (just version check, no actual download)
        yt_dlp_version = yt_dlp.version.__version__
        
        # Check for ffmpeg
        ffmpeg_available = subprocess.run(
            ["which", "ffmpeg"], 
            capture_output=True
        ).returncode == 0

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "downloads_dir_writable": True,
                "yt_dlp_available": True,
                "yt_dlp_version": yt_dlp_version,
                "ffmpeg_available": ffmpeg_available
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
