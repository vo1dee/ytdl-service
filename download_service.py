from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
from pydantic import BaseModel
import yt_dlp
import os
import logging
import shutil
from fastapi.responses import FileResponse
import uuid
import subprocess
import secrets
import time
from datetime import datetime
import pkg_resources
import sys
import asyncio
from fastapi import BackgroundTasks
import logging.handlers

# Enhanced logging
import logging.handlers

# Create logs directory if it doesn't exist
LOGS_DIR = "/var/log"
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "ytdl_service.log")

# Configure logging
logger = logging.getLogger("ytdl_service")
logger.setLevel(logging.INFO)

# Create formatters
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler with rotation
file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Prevent propagation to root logger
logger.propagate = False

# Configuration
DOWNLOADS_DIR = "/opt/ytdl_service/downloads"
API_KEY_FILE = "/opt/ytdl_service/api_key.txt"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Add configuration for update check and cleanup
YTDLP_UPDATE_INTERVAL = 24 * 60 * 60  # 24 hours in seconds
CLEANUP_INTERVAL = 60 * 60  # 1 hour in seconds
FILE_MAX_AGE = 24 * 60 * 60  # 24 hours in seconds
last_update_check = 0
last_update_status = None
last_cleanup_time = 0

# Handle API key
def get_api_key():
    if not os.path.exists(API_KEY_FILE):
        try:
            api_key = secrets.token_urlsafe(32)
            with open(API_KEY_FILE, "w") as f:
                f.write(api_key)
            logger.info(f"Generated new API key file: {API_KEY_FILE}")
            return api_key
        except IOError as e:
            logger.error(f"Error writing API key file {API_KEY_FILE}: {e}")
            logger.warning("Failed to write API key file, using temporary key.")
            return secrets.token_urlsafe(32)
    else:
        try:
            with open(API_KEY_FILE, "r") as f:
                return f.read().strip()
        except IOError as e:
            logger.error(f"Error reading API key file {API_KEY_FILE}: {e}")
            logger.warning("Failed to read API key file, using temporary key.")
            return secrets.token_urlsafe(32)

API_KEY = get_api_key()
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != API_KEY:
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid API key"
        )
    return api_key_header

app = FastAPI()

class DownloadRequest(BaseModel):
    url: str
    format: str = 'best[height<=2160][ext=mp4]/best[height<=1440][ext=mp4]/best[height<=1080][ext=mp4]/best[ext=mp4]/best'
    
    # Add additional optional parameters
    subtitles: bool = False
    audio_only: bool = False
    max_height: int = 2160  # Max video height (e.g., 720, 1080, 2160, etc.)

def check_and_update_ytdlp():
    """Check if yt-dlp is up to date and update if necessary"""
    try:
        # Get current version
        current_version = yt_dlp.version.__version__
        
        # Get latest version from PyPI
        latest_version = subprocess.check_output(
            [sys.executable, "-m", "pip", "index", "versions", "yt-dlp"],
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        # Parse the output to get the latest version
        latest_version = latest_version.split("LATEST: ")[1].split("\n")[0].strip()
        
        if latest_version > current_version:
            logger.info(f"Updating yt-dlp from {current_version} to {latest_version}")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logger.info("yt-dlp updated successfully")
            return True, latest_version
        return False, current_version
    except Exception as e:
        logger.error(f"Error checking/updating yt-dlp: {str(e)}")
        return False, current_version if 'current_version' in locals() else "unknown"

async def cleanup_old_files():
    """Clean up files older than FILE_MAX_AGE"""
    global last_cleanup_time
    current_time = time.time()
    
    if current_time - last_cleanup_time < CLEANUP_INTERVAL:
        return
    
    logger.info("Running periodic cleanup of old files...")
    deleted_count = 0
    saved_space = 0
    
    try:
        for filename in os.listdir(DOWNLOADS_DIR):
            file_path = os.path.join(DOWNLOADS_DIR, filename)
            if os.path.isfile(file_path):
                try:
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > FILE_MAX_AGE:
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        deleted_count += 1
                        saved_space += file_size
                        logger.info(f"Cleaned up old file: {filename} (age: {round(file_age/3600, 1)} hours)")
                except Exception as e:
                    logger.warning(f"Error cleaning up file {filename}: {e}")
        
        logger.info(f"Cleanup completed: {deleted_count} files deleted, {round(saved_space/(1024*1024), 2)} MB saved")
        last_cleanup_time = current_time
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

async def periodic_tasks():
    """Background task to periodically check for updates and cleanup"""
    global last_update_check, last_update_status
    
    while True:
        try:
            current_time = time.time()
            
            # Check for yt-dlp updates
            if current_time - last_update_check >= YTDLP_UPDATE_INTERVAL:
                logger.info("Running periodic yt-dlp update check")
                was_updated, version = check_and_update_ytdlp()
                last_update_check = current_time
                last_update_status = {
                    "was_updated": was_updated,
                    "version": version,
                    "timestamp": datetime.now().isoformat()
                }
                logger.info(f"yt-dlp update check completed: {last_update_status}")
            
            # Run cleanup
            await cleanup_old_files()
            
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in periodic tasks: {str(e)}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying on error

@app.on_event("startup")
async def startup_event():
    """Initialize background tasks on startup"""
    asyncio.create_task(periodic_tasks())

@app.get("/health")
async def health_check():
    # Public endpoint, no API key required
    try:
        # Check for ffmpeg
        ffmpeg_available = subprocess.run(
            ["which", "ffmpeg"],
            capture_output=True
        ).returncode == 0

        # Check for required directory permissions
        write_permission = os.access(DOWNLOADS_DIR, os.W_OK)
        read_permission = os.access(DOWNLOADS_DIR, os.R_OK)

        # Get current yt-dlp version without checking for updates
        current_version = yt_dlp.version.__version__

        return {
            "status": "healthy",
            "ffmpeg_available": ffmpeg_available,
            "yt_dlp_version": current_version,
            "last_update_check": datetime.fromtimestamp(last_update_check).isoformat() if last_update_check else None,
            "last_update_status": last_update_status,
            "downloads_dir": DOWNLOADS_DIR,
            "downloads_dir_writeable": write_permission,
            "downloads_dir_readable": read_permission,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def get_video_info(file_path):
    """Get video information using ffprobe"""
    try:
        ffprobe_cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            if video_stream:
                width = video_stream.get('width', 0)
                height = video_stream.get('height', 0)
                codec = video_stream.get('codec_name', 'unknown')
                
                logger.info(f"Video info: {width}x{height}, codec: {codec}")
                return {
                    'width': width,
                    'height': height,
                    'codec': codec,
                    'quality_score': height if height else 0
                }
            
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
    
    return {'width': 0, 'height': 0, 'codec': 'unknown', 'quality_score': 0}

@app.post("/download")
async def download_video(
    request: DownloadRequest,
    api_key: str = Depends(verify_api_key)
):
    download_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(DOWNLOADS_DIR, f'{download_id}.%(ext)s')
    
    # Clean up any existing files with this ID
    cleanup_files(download_id)

    try:
        logger.info(f"Starting download for URL: {request.url}")
        
        # Determine format string based on request parameters
        if request.audio_only:
            format_string = 'bestaudio[ext=m4a]/bestaudio/best'
        else:
            # Build format string prioritizing high quality
            max_height = request.max_height if request.max_height > 0 else 2160
            
            format_parts = []
            
            # For YouTube, try specific high-quality formats first
            if 'youtube.com' in request.url or 'youtu.be' in request.url:
                # Try to get best video + audio combination
                format_parts.extend([
                    f'bestvideo[height<={max_height}][ext=mp4][vcodec*=avc1]+bestaudio[ext=m4a]',
                    f'bestvideo[height<={max_height}][ext=webm][vcodec*=vp9]+bestaudio[ext=webm]',
                    f'bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]',
                    f'bestvideo[height<={max_height}]+bestaudio',
                ])
            
            # Add fallback formats
            format_parts.extend([
                f'best[height<={max_height}][ext=mp4]',
                f'best[height<={max_height}][ext=webm]',
                f'best[height<={max_height}]',
                'best[ext=mp4]',
                'best'
            ])
            
            format_string = '/'.join(format_parts)
        
        # Enhanced ydl_opts for better quality and reliability
        ydl_opts = {
            'format': format_string,
            'outtmpl': output_template,
            'restrictfilenames': True,
            'merge_output_format': 'mp4' if not request.audio_only else None,
            'writesubtitles': request.subtitles,
            'writeautomaticsub': request.subtitles,
            'subtitleslangs': ['en', 'en-US'] if request.subtitles else [],
            
            # Quality and encoding settings
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                } if not request.audio_only else {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '192',
                }
            ],
            
            # Network and retry settings
            'retries': 10,
            'fragment_retries': 10,
            'socket_timeout': 30,
            'concurrent_fragment_downloads': 4,
            
            # Headers to avoid blocking
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # Extraction settings
            'extract_flat': False,
            'ignoreerrors': False,
            'geo_bypass': True,
            'nocheckcertificate': True,
            
            # Progress and logging
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            'progress_hooks': [
                lambda d: logger.info(
                    f"Download progress: {d.get('_percent_str', 'N/A')} - {d.get('filename', 'N/A')}"
                ) if d['status'] == 'downloading' else logger.info(f"Download status: {d['status']}")
            ],
        }
        
        # Special handling for YouTube clips and shorts
        if any(x in request.url for x in ['youtube.com/clip', 'youtu.be/clip', 'youtube.com/shorts', 'youtu.be/shorts']):
            logger.info("Detected YouTube clip/shorts, using optimized settings")
            ydl_opts.update({
                'format': f'best[height<={max_height}]/best',
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'skip': ['dash', 'hls'] if 'clip' in request.url else []
                    }
                }
            })

        # Perform the download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=True)
            if not info:
                raise Exception("Failed to extract video information")

        # Wait for file system to catch up
        time.sleep(2)

        # Find the downloaded file
        downloaded_file = find_downloaded_file(download_id)
        
        if not downloaded_file:
            raise Exception("Downloaded file not found")

        # Get video information
        video_info = get_video_info(downloaded_file)
        
        # Log success
        logger.info(f"Download successful: {os.path.basename(downloaded_file)} - {video_info['width']}x{video_info['height']}")

        # Return success response
        return {
            "success": True,
            "file_path": os.path.basename(downloaded_file),
            "title": info.get('title', 'Video'),
            "url": request.url,
            "description": info.get('description', ''),
            "tags": info.get('tags', []),
            "duration": info.get('duration'),
            "uploader": info.get('uploader'),
            "file_size_bytes": os.path.getsize(downloaded_file),
            "file_size_mb": round(os.path.getsize(downloaded_file) / (1024 * 1024), 2),
            "video_info": video_info,
            "quality": f"{video_info['width']}x{video_info['height']}" if video_info['width'] > 0 else "Audio only"
        }

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"yt-dlp download error: {error_msg}")
        cleanup_files(download_id)
        
        return {
            "success": False,
            "error": f"Download failed: {error_msg}",
            "error_type": "download_error"
        }
    except Exception as e:
        logger.error(f"Download failed with exception: {str(e)}")
        cleanup_files(download_id)
        
        return {
            "success": False,
            "error": str(e),
            "error_type": "general_error"
        }

def find_downloaded_file(download_id):
    """Find the downloaded file with the given ID"""
    try:
        files_in_dir = os.listdir(DOWNLOADS_DIR)
        
        # Look for files with our download_id
        matching_files = []
        for fname in files_in_dir:
            if fname.startswith(download_id):
                fpath = os.path.join(DOWNLOADS_DIR, fname)
                if os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
                    matching_files.append((fpath, os.path.getsize(fpath), fname))
        
        if matching_files:
            # Sort by file size (largest first) to get the main video file
            matching_files.sort(key=lambda x: x[1], reverse=True)
            best_file = matching_files[0][0]
            logger.info(f"Found downloaded file: {os.path.basename(best_file)}")
            return best_file
        
        logger.error("No matching files found")
        return None
        
    except Exception as e:
        logger.error(f"Error finding downloaded file: {e}")
        return None

def cleanup_files(prefix):
    """Clean up all files with the given prefix"""
    try:
        for item in os.listdir(DOWNLOADS_DIR):
            if item.startswith(prefix):
                item_path = os.path.join(DOWNLOADS_DIR, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        logger.info(f"Cleaned up file: {item}")
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        logger.info(f"Cleaned up directory: {item}")
                except Exception as e:
                    logger.warning(f"Failed to clean up item {item}: {e}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

@app.get("/files/{filename}")
async def get_file(
    filename: str,
    api_key: str = Depends(verify_api_key)
):
    # Basic sanitization to prevent directory traversal
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Determine media type based on file extension
    ext = os.path.splitext(filename)[1].lower()
    media_type = 'application/octet-stream'  # Default
    if ext == '.mp4':
        media_type = 'video/mp4'
    elif ext == '.webm':
        media_type = 'video/webm'
    elif ext == '.mkv':
        media_type = 'video/x-matroska'
    elif ext == '.m4a':
        media_type = 'audio/mp4'
    elif ext == '.mp3':
        media_type = 'audio/mpeg'
    elif ext in ['.jpg', '.jpeg']:
        media_type = 'image/jpeg'
    elif ext == '.png':
        media_type = 'image/png'

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename
    )

@app.get("/cleanup")
async def cleanup_storage(
    api_key: str = Depends(verify_api_key)
):
    """Clean up old files to free storage space"""
    await cleanup_old_files()
    
    # Get storage info after cleanup
    try:
        total_size = 0
        file_count = 0
        files = []

        for filename in os.listdir(DOWNLOADS_DIR):
            file_path = os.path.join(DOWNLOADS_DIR, filename)
            if os.path.isfile(file_path):
                try:
                    size = os.path.getsize(file_path)
                    modified = os.path.getmtime(file_path)
                    total_size += size
                    file_count += 1

                    files.append({
                        "filename": filename,
                        "size_bytes": size,
                        "size_mb": round(size / (1024 * 1024), 2),
                        "modified_timestamp": modified,
                        "modified_iso": datetime.fromtimestamp(modified).isoformat(),
                        "age_hours": round((time.time() - modified) / 3600, 1)
                    })
                except Exception as e:
                    logger.error(f"Error processing file {filename}: {str(e)}")

        # Sort files by modification time, newest first
        files.sort(key=lambda x: x['modified_timestamp'], reverse=True)

        return {
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "files": files,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Storage info error: {str(e)}")
        return {"error": str(e)}

@app.get("/storage")
async def get_storage_info(
    api_key: str = Depends(verify_api_key)
):
    """Get storage usage information"""
    try:
        total_size = 0
        file_count = 0
        files = []

        for filename in os.listdir(DOWNLOADS_DIR):
            file_path = os.path.join(DOWNLOADS_DIR, filename)
            if os.path.isfile(file_path):
                try:
                    size = os.path.getsize(file_path)
                    modified = os.path.getmtime(file_path)
                    total_size += size
                    file_count += 1

                    files.append({
                        "filename": filename,
                        "size_bytes": size,
                        "size_mb": round(size / (1024 * 1024), 2),
                        "modified_timestamp": modified,
                        "modified_iso": datetime.fromtimestamp(modified).isoformat()
                    })
                except Exception as e:
                    logger.error(f"Error processing file {filename}: {str(e)}")

        # Sort files by modification time, newest first
        files.sort(key=lambda x: x['modified_timestamp'], reverse=True)

        return {
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "files": files,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Storage info error: {str(e)}")
        return {"error": str(e)}

# Utility endpoints
@app.get("/formats")
async def get_available_formats(
    url: str,
    api_key: str = Depends(verify_api_key)
):
    """Get available formats for a URL without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            if 'formats' in info:
                for fmt in info['formats']:
                    formats.append({
                        'format_id': fmt.get('format_id'),
                        'ext': fmt.get('ext'),
                        'resolution': f"{fmt.get('width', 'N/A')}x{fmt.get('height', 'N/A')}",
                        'fps': fmt.get('fps'),
                        'vcodec': fmt.get('vcodec'),
                        'acodec': fmt.get('acodec'),
                        'filesize': fmt.get('filesize'),
                        'filesize_mb': round(fmt.get('filesize', 0) / (1024 * 1024), 2) if fmt.get('filesize') else None,
                        'format_note': fmt.get('format_note'),
                        'format': fmt.get('format')
                    })
            
            return {
                "title": info.get('title', 'Unknown'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "formats": formats
            }
    except Exception as e:
        logger.error(f"Error getting formats: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)