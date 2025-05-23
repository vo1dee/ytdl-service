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

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ytdl_service")

# Configuration
DOWNLOADS_DIR = "/opt/ytdl_service/downloads"
API_KEY_FILE = "/opt/ytdl_service/api_key.txt"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Add configuration for update check
YTDLP_UPDATE_INTERVAL = 24 * 60 * 60  # 24 hours in seconds
last_update_check = 0
last_update_status = None

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
    format: str = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best'
    
    # Add additional optional parameters
    subtitles: bool = False
    audio_only: bool = False
    max_height: int = 1080  # Max video height (e.g., 720, 1080, etc.)

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
        return False, current_version

async def periodic_ytdlp_update():
    """Background task to periodically check and update yt-dlp"""
    global last_update_check, last_update_status
    
    while True:
        try:
            current_time = time.time()
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
            await asyncio.sleep(60)  # Check every minute if it's time for an update
        except Exception as e:
            logger.error(f"Error in periodic yt-dlp update: {str(e)}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying on error

@app.on_event("startup")
async def startup_event():
    """Initialize background tasks on startup"""
    asyncio.create_task(periodic_ytdlp_update())

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

@app.post("/download")
async def download_video(
    request: DownloadRequest,
    api_key: str = Depends(verify_api_key)
):
    download_id = str(uuid.uuid4())[:8]
    output_template_base = os.path.join(DOWNLOADS_DIR, f'{download_id}')
    output_template = f'{output_template_base}.%(ext)s'
    download_info = {}

    # Clean up any existing files with this ID (shouldn't happen, but just in case)
    for item in os.listdir(DOWNLOADS_DIR):
        if item.startswith(download_id):
            item_path = os.path.join(DOWNLOADS_DIR, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
            except Exception as e:
                logger.warning(f"Error cleaning up pre-existing file {item}: {e}")

    try:
        logger.info(f"Starting download for URL: {request.url}")
        
        # Adjust format based on request parameters
        format_string = request.format
        if request.audio_only:
            format_string = 'bestaudio[ext=m4a]/bestaudio/best'
        elif request.max_height and request.max_height > 0:
            # Apply max height constraint to video format
            format_string = f'bestvideo[height<={request.max_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={request.max_height}][ext=mp4]/best'

        logger.info(f"Using format string: {format_string}")

        # Setup yt-dlp options
        ydl_opts = {
            'format': format_string,
            'outtmpl': output_template,
            'restrictfilenames': True,
            'merge_output_format': 'mp4',  # Force MP4 output format for merged streams
            'concurrent_fragment_downloads': 3,
            'retries': 5,
            'fragment_retries': 5,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'verbose': True,
            'quiet': False,
            'no_warnings': False,
            'progress_hooks': [
                lambda d: logger.info(
                    f"yt-dlp progress: {d.get('_percent_str', 'N/A')} {d.get('_eta_str', 'N/A')}"
                ) if d['status'] != 'finished' else logger.info("yt-dlp progress: Finished")
            ],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            }
        }

        # Add subtitles if requested
        if request.subtitles:
            ydl_opts.update({
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en'],  # Default to English
                'postprocessors': [{
                    'key': 'FFmpegEmbedSubtitle',
                    'already_have_subtitle': False,
                }],
            })

        # Configure ffmpeg
        ffmpeg_available = subprocess.run(
            ["which", "ffmpeg"],
            capture_output=True
        ).returncode == 0

        if ffmpeg_available:
            logger.info("ffmpeg detected, configuring")
            # Add ffmpeg options to improve reliability
            ydl_opts.update({
                'prefer_ffmpeg': True,
                'external_downloader_args': {
                    'ffmpeg': [
                        '-loglevel', 'warning',
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_delay_max', '5',
                        # Add codec options to avoid the "codec frame size is not set" issue
                        '-strict', 'experimental'
                    ]
                },
                'postprocessor_args': {
                    'ffmpeg': [
                        '-movflags', 'faststart',
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        '-strict', 'experimental'
                    ]
                }
            })
        else:
            logger.warning("ffmpeg not found. Merging/remuxing may not work correctly.")

        # Download the video and get info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting extraction and download with options: {ydl_opts}")
            info = ydl.extract_info(request.url, download=True)
            
            # Store needed info
            download_info = {
                'title': info.get('title', 'Video'),
                'description': info.get('description', ''),
                'tags': info.get('tags', []),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'expected_filepath': ydl.prepare_filename(info)
            }
            
            logger.info(f"Download completed. Expected filepath: {download_info['expected_filepath']}")

        # Give the filesystem a moment to finalize writes
        time.sleep(1)

        # Find the downloaded file
        files_in_dir = os.listdir(DOWNLOADS_DIR)
        logger.info(f"Files in directory after download: {files_in_dir}")
        
        # Look for files with our download_id
        potential_files = [f for f in files_in_dir if f.startswith(f"{download_id}.")]
        
        if not potential_files:
            logger.error(f"No file found with ID {download_id} in {DOWNLOADS_DIR}")
            raise Exception("Downloaded file not found or named as expected.")
        
        # If multiple files, find the main video file (should be .mp4 for merged output)
        downloaded_file = None
        if len(potential_files) == 1:
            downloaded_file = os.path.join(DOWNLOADS_DIR, potential_files[0])
        else:
            # Look for the MP4 file or the largest file
            logger.info(f"Multiple files found for ID {download_id}: {potential_files}")
            
            # Prefer MP4 files
            mp4_files = [f for f in potential_files if f.endswith('.mp4')]
            if mp4_files:
                downloaded_file = os.path.join(DOWNLOADS_DIR, mp4_files[0])
                logger.info(f"Selected MP4 file: {downloaded_file}")
            else:
                # Otherwise get the largest file
                max_size = -1
                for fname in potential_files:
                    fpath = os.path.join(DOWNLOADS_DIR, fname)
                    if os.path.isfile(fpath):
                        size = os.path.getsize(fpath)
                        if size > max_size:
                            max_size = size
                            downloaded_file = fpath
                
                if downloaded_file:
                    logger.info(f"Selected largest file: {downloaded_file}")
                else:
                    logger.error(f"Could not identify a valid downloaded file")
                    raise Exception("Downloaded file identification failed")
        
        # Verify the file exists and has content
        if downloaded_file and os.path.exists(downloaded_file) and os.path.getsize(downloaded_file) > 0:
            logger.info(f"Download successful: {downloaded_file}")
            
            # Clean up other temporary files
            for item in os.listdir(DOWNLOADS_DIR):
                if item.startswith(download_id) and os.path.join(DOWNLOADS_DIR, item) != downloaded_file:
                    item_path = os.path.join(DOWNLOADS_DIR, item)
                    try:
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                            logger.info(f"Cleaned up artifact file: {item}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up item {item}: {e}")
            
            # Return success response
            return {
                "success": True,
                "file_path": os.path.basename(downloaded_file),
                "title": download_info.get('title', 'Video'),
                "url": request.url,
                "description": download_info.get('description', ''),
                "tags": download_info.get('tags', []),
                "duration": download_info.get('duration'),
                "uploader": download_info.get('uploader'),
                "file_size_bytes": os.path.getsize(downloaded_file),
                "file_size_mb": round(os.path.getsize(downloaded_file) / (1024 * 1024), 2)
            }
        else:
            logger.error(f"Downloaded file verification failed: {downloaded_file}")
            raise Exception("Downloaded file verification failed")

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"YouTube download error: {error_msg}")
        
        # Cleanup any partial files
        cleanup_files(download_id)
        
        return {
            "success": False,
            "error": error_msg
        }
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        
        # Cleanup any partial files
        cleanup_files(download_id)
        
        return {
            "success": False,
            "error": str(e)
        }

def cleanup_files(prefix):
    """Clean up all files with the given prefix"""
    for item in os.listdir(DOWNLOADS_DIR):
        if item.startswith(prefix):
            item_path = os.path.join(DOWNLOADS_DIR, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                    logger.info(f"Cleaned up file: {item}")
                elif os.path.isdir(item_path):
                    try:
                        if not os.listdir(item_path):
                            os.rmdir(item_path)
                            logger.info(f"Cleaned up empty directory: {item}")
                    except OSError:
                        pass
            except Exception as e:
                logger.warning(f"Failed to clean up item {item}: {e}")

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
    max_age_days = 7  # Files older than this will be deleted
    max_age_seconds = max_age_days * 24 * 60 * 60
    now = time.time()
    deleted_count = 0
    saved_space = 0

    for filename in os.listdir(DOWNLOADS_DIR):
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        if os.path.isfile(file_path):
            try:
                file_age = now - os.path.getmtime(file_path)
                if file_age > max_age_seconds:
                    file_size = os.path.getsize(file_path)
                    saved_space += file_size
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(f"Deleted old file: {filename}")
            except Exception as e:
                logger.warning(f"Error cleaning up file {filename}: {e}")
        # Clean up empty directories
        elif os.path.isdir(file_path):
            try:
                if not os.listdir(file_path):
                    os.rmdir(file_path)
                    logger.info(f"Cleaned up empty directory: {filename}")
            except OSError:
                pass

    return {
        "deleted_files": deleted_count,
        "saved_space_bytes": saved_space,
        "saved_space_mb": round(saved_space / (1024 * 1024), 2),
        "timestamp": datetime.now().isoformat()
    }

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