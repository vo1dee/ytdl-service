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
    format: str = 'bestvideo[height<=2160][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][ext=mp4]/best'
    
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
        return False, current_version

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
        
        # Initialize ydl_opts with default settings first
        ydl_opts = {
            'format': request.format,
            'outtmpl': output_template,
            'restrictfilenames': True,
            'merge_output_format': 'mp4',
            'concurrent_fragment_downloads': 3,
            'retries': 10,
            'fragment_retries': 10,
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
            },
            'socket_timeout': 30,
            'extractor_retries': 5,
            'ignoreerrors': True,
            'no_color': True,
            'extract_flat': False,
            'force_generic_extractor': False,
            'prefer_ffmpeg': True,
            'postprocessor_args': {
                'ffmpeg': [
                    '-movflags', 'faststart',  # Enable fast start for web playback
                    '-c:v', 'libx264',  # Use H.264 codec for maximum compatibility
                    '-preset', 'medium',  # Balance between quality and encoding speed
                    '-crf', '18',  # High quality (lower CRF = better quality)
                    '-profile:v', 'high',  # Use high profile for better quality
                    '-level', '4.1',  # Compatibility level for most devices
                    '-c:a', 'aac',  # Use AAC audio codec for maximum compatibility
                    '-b:a', '192k',  # High quality audio
                    '-ar', '48000',  # Standard audio sample rate
                    '-strict', 'experimental'
                ]
            },
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
        }
        
        # Check if it's a YouTube clip
        is_clip = 'youtube.com/clip' in request.url or 'youtu.be/clip' in request.url
        is_shorts = 'youtube.com/shorts' in request.url or 'youtu.be/shorts' in request.url
        
        if is_clip or is_shorts:
            logger.info("Detected YouTube clip/shorts URL, applying specific settings")
            
            # Initialize format_string with a default value
            format_string = 'bestvideo[height>=1080][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height>=720][ext=mp4]+bestaudio[ext=m4a]/best[height>=720][ext=mp4]/best'
            
            # For shorts, we'll analyze available formats first
            if is_shorts:
                logger.info("Analyzing available formats for Shorts...")
                try:
                    # First get video info to analyze formats
                    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                        info = ydl.extract_info(request.url, download=False)
                        if info is None:
                            raise Exception("Failed to extract video information")
                        
                        formats = info.get('formats', [])
                        best_format = None
                        best_height = 0
                        
                        # Find the best format with highest resolution
                        for fmt in formats:
                            height = fmt.get('height', 0)
                            if height and height > best_height and fmt.get('ext') == 'mp4':
                                best_format = fmt
                                best_height = height
                                logger.info(f"Found format: {height}p, format_id: {fmt.get('format_id')}, note: {fmt.get('format_note', '')}")
                        
                        if best_format:
                            logger.info(f"Selected best format: {best_height}p")
                            # Use a more reliable format string that includes fallbacks
                            format_string = f"bestvideo[height={best_height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height={best_height}][ext=mp4]/best[height={best_height}][ext=mp4]/best"
                        else:
                            # Fallback to high quality format if specific format not found
                            format_string = 'bestvideo[height>=1080][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height>=720][ext=mp4]+bestaudio[ext=m4a]/best[height>=720][ext=mp4]/best'
                            logger.info("No specific format found, using fallback format")
                        
                        logger.info(f"Using format string for Shorts: {format_string}")
                except Exception as e:
                    logger.error(f"Error analyzing formats: {str(e)}")
                    # Fallback to high quality format with more specific options
                    format_string = 'bestvideo[height>=1080][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height>=720][ext=mp4]+bestaudio[ext=m4a]/best[height>=720][ext=mp4]/best'
                    logger.info(f"Using fallback format string: {format_string}")
            
            # Update ydl_opts for clips/shorts
            ydl_opts.update({
                'format': format_string,
                'extract_flat': False,
                'force_generic_extractor': False,
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_client': ['android', 'web'],
                        'player_skip': ['js', 'configs', 'webpage'],
                    }
                },
                'concurrent_fragment_downloads': 1,  # Reduce concurrent downloads for clips
                'socket_timeout': 30,  # Increased timeout
                'retries': 10,  # More retries
                'fragment_retries': 10,  # More fragment retries
                'retry_sleep': 5,  # Wait between retries
                'ignoreerrors': True,  # Continue on errors
                'no_warnings': True,  # Reduce noise
                'quiet': True,  # Reduce noise
                'verbose': False,  # Reduce noise
            })

            # Try to get video info first with minimal options
            try:
                logger.info("Attempting to extract video info first...")
                with yt_dlp.YoutubeDL({
                    'quiet': True,
                    'no_warnings': True,
                    'format': 'best',  # Use simplest format for info extraction
                    'extract_flat': True,
                    'force_generic_extractor': True,
                }) as ydl:
                    info = ydl.extract_info(request.url, download=False)
                    if info is None:
                        raise Exception("Failed to extract video information")
                    
                    logger.info(f"Successfully extracted video info: {info.get('title', 'Unknown Title')}")
            except Exception as info_error:
                logger.error(f"Error extracting video info: {str(info_error)}")
                logger.info("Attempting alternative clip extraction method...")
                try:
                    # Try with absolute minimal options
                    with yt_dlp.YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'format': 'best',
                        'extract_flat': True,
                        'force_generic_extractor': True,
                        'ignoreerrors': True,
                    }) as ydl:
                        info = ydl.extract_info(request.url, download=False)
                        if info is None:
                            raise Exception("Alternative extraction also failed")
                        logger.info("Alternative extraction successful")
                except Exception as alt_error:
                    logger.error(f"Alternative extraction failed: {str(alt_error)}")
                    # Don't raise here, continue with download attempt

        # Adjust format based on request parameters
        if not (is_clip or is_shorts):  # Only apply these if it's not a clip or shorts
            if request.audio_only:
                format_string = 'bestaudio[ext=m4a]/bestaudio/best'
            elif request.max_height and request.max_height > 0:
                # Apply max height constraint to video format
                format_string = f'bestvideo[height<={request.max_height}][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<={request.max_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={request.max_height}][ext=mp4]/best'
            else:
                format_string = request.format
            
            logger.info(f"Using format string: {format_string}")
            ydl_opts['format'] = format_string

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
                        '-strict', 'experimental'
                    ]
                }
            })
        else:
            logger.warning("ffmpeg not found. Merging/remuxing may not work correctly.")

        # Download the video and get info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting extraction and download with options: {ydl_opts}")
            try:
                info = ydl.extract_info(request.url, download=True)
                if info is None:
                    raise Exception("Failed to extract video information")
                
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
            except Exception as download_error:
                logger.error(f"Error during download: {str(download_error)}")
                if is_clip:
                    logger.info("Attempting fallback download method for clip...")
                    try:
                        # Try with absolute minimal options
                        fallback_opts = {
                            'format': 'best',
                            'outtmpl': output_template,
                            'quiet': True,
                            'no_warnings': True,
                            'extract_flat': True,
                            'force_generic_extractor': True,
                        }
                        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                            info = ydl.extract_info(request.url, download=True)
                            if info is None:
                                raise Exception("Fallback download failed to extract info")
                            logger.info("Fallback download successful")
                    except Exception as fallback_error:
                        logger.error(f"Fallback download failed: {str(fallback_error)}")
                        raise Exception(f"Download failed: {str(download_error)}. Fallback also failed: {str(fallback_error)}")
                else:
                    raise

        # Give the filesystem a moment to finalize writes
        time.sleep(5)  # Increased wait time for live stream clips

        # Find the downloaded file
        files_in_dir = os.listdir(DOWNLOADS_DIR)
        logger.info(f"Files in directory after download: {files_in_dir}")
        
        # Initialize downloaded_file variable
        downloaded_file = None
        
        # First, look for files with our download_id
        potential_files = [f for f in files_in_dir if f.startswith(f"{download_id}.")]
        
        if potential_files:
            # Check for both complete and partial files
            for fname in potential_files:
                fpath = os.path.join(DOWNLOADS_DIR, fname)
                if os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
                    # If it's a partial file, wait a bit longer for it to complete
                    if fname.endswith('.part'):
                        logger.info(f"Found partial file {fname}, waiting for completion...")
                        time.sleep(10)  # Increased wait time for clips
                        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                            # Check if the file is still being written to
                            initial_size = os.path.getsize(fpath)
                            time.sleep(5)  # Increased wait time for clips
                            if os.path.getsize(fpath) == initial_size:
                                # File size hasn't changed, assume it's complete
                                downloaded_file = fpath
                                logger.info(f"Partial file appears to be complete: {fname}")
                                break
                    else:
                        downloaded_file = fpath
                        logger.info(f"Found complete file: {fname}")
                        break
        
        if not downloaded_file:
            logger.info("No file found with exact ID match, searching for recently modified files...")
            # Get all files and their modification times
            file_times = []
            for fname in files_in_dir:
                fpath = os.path.join(DOWNLOADS_DIR, fname)
                if os.path.isfile(fpath):
                    try:
                        mtime = os.path.getmtime(fpath)
                        file_times.append((fpath, mtime, fname))
                    except Exception as e:
                        logger.warning(f"Error getting mtime for {fname}: {e}")
            
            # Sort by modification time, newest first
            file_times.sort(key=lambda x: x[1], reverse=True)
            
            # Look at the most recently modified files
            recent_files = [(f[0], f[2]) for f in file_times[:5]]  # Check last 5 modified files
            logger.info(f"Most recently modified files: {[f[0] for f in recent_files]}")
            
            # Try to find a valid video file
            for fpath, fname in recent_files:
                if os.path.getsize(fpath) > 0:  # Ensure file has content
                    # Handle both complete and partial files
                    if fname.endswith('.part'):
                        logger.info(f"Found partial file {fname}, waiting for completion...")
                        time.sleep(5)  # Wait for potential completion
                        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                            # Check if the file is still being written to
                            initial_size = os.path.getsize(fpath)
                            time.sleep(2)
                            if os.path.getsize(fpath) == initial_size:
                                # File size hasn't changed, assume it's complete
                                downloaded_file = fpath
                                logger.info(f"Partial file appears to be complete: {fname}")
                                break
                    else:
                        ext = os.path.splitext(fpath)[1].lower()
                        if ext in ['.mp4', '.webm', '.mkv']:  # Common video extensions
                            downloaded_file = fpath
                            logger.info(f"Found recently downloaded file: {fname}")
                            break
        
        if not downloaded_file:
            # If still no file found, try to find any video file that was modified in the last minute
            current_time = time.time()
            for fname in files_in_dir:
                fpath = os.path.join(DOWNLOADS_DIR, fname)
                if os.path.isfile(fpath):
                    try:
                        mtime = os.path.getmtime(fpath)
                        if current_time - mtime < 60:  # Modified in last minute
                            if fname.endswith('.part'):
                                logger.info(f"Found recent partial file {fname}, waiting for completion...")
                                time.sleep(5)  # Wait for potential completion
                                if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                                    # Check if the file is still being written to
                                    initial_size = os.path.getsize(fpath)
                                    time.sleep(2)
                                    if os.path.getsize(fpath) == initial_size:
                                        # File size hasn't changed, assume it's complete
                                        downloaded_file = fpath
                                        logger.info(f"Partial file appears to be complete: {fname}")
                                        break
                            else:
                                ext = os.path.splitext(fpath)[1].lower()
                                if ext in ['.mp4', '.webm', '.mkv'] and os.path.getsize(fpath) > 0:
                                    downloaded_file = fpath
                                    logger.info(f"Found recently modified video file: {fname}")
                                    break
                    except Exception as e:
                        logger.warning(f"Error checking file {fname}: {e}")
        
        if not downloaded_file:
            logger.error(f"No suitable downloaded file found in {DOWNLOADS_DIR}")
            raise Exception("Downloaded file not found or named as expected.")
        
        # Verify the file exists and has content
        if downloaded_file and os.path.exists(downloaded_file) and os.path.getsize(downloaded_file) > 0:
            # If it's a .part file, rename it to remove the .part extension
            if downloaded_file.endswith('.part'):
                new_path = downloaded_file[:-5]  # Remove .part extension
                try:
                    os.rename(downloaded_file, new_path)
                    downloaded_file = new_path
                    logger.info(f"Renamed partial file to: {os.path.basename(new_path)}")
                except Exception as e:
                    logger.warning(f"Failed to rename partial file: {e}")
            
            # Verify the file is a valid video file
            try:
                # Use ffprobe to check the file
                ffprobe_cmd = [
                    'ffprobe',
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,codec_name',
                    '-of', 'json',
                    downloaded_file
                ]
                result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"Video file verification successful: {result.stdout}")
                else:
                    logger.warning(f"Video file verification failed: {result.stderr}")
            except Exception as e:
                logger.warning(f"Error verifying video file: {e}")
            
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
        
        # Add specific handling for clip errors
        if is_clip:
            logger.error("Clip download failed, attempting fallback method...")
            try:
                # Try with a simpler format as fallback
                ydl_opts['format'] = 'best'
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(request.url, download=True)
                    logger.info("Fallback download successful")
                    # Continue with normal processing...
            except Exception as fallback_error:
                logger.error(f"Fallback download also failed: {str(fallback_error)}")
                error_msg = f"Clip download failed: {error_msg}. Fallback also failed: {str(fallback_error)}"
        
        # Cleanup any partial files
        cleanup_files(download_id)
        
        return {
            "success": False,
            "error": error_msg,
            "is_clip": is_clip
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