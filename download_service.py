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
from contextlib import asynccontextmanager

# Import configuration validator
from config_validator import validate_startup_config

# Enhanced logging
import logging.handlers

# Validate configuration on startup
validated_config = validate_startup_config()

# Container-aware configuration - use validated values
LOGS_DIR = validated_config['LOGS_DIR']
DOWNLOADS_DIR = validated_config['DOWNLOADS_DIR']
API_KEY_FILE = validated_config['API_KEY_FILE']
PORT = int(validated_config['PORT'])

# Create directories if they don't exist
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(API_KEY_FILE), exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "ytdl_service.log")

# Configure logging with container-specific settings
logger = logging.getLogger("ytdl_service")
logger.setLevel(logging.INFO)

# Create formatters
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Console handler (important for container logs)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler with rotation (only if logs directory is writable)
try:
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info(f"File logging enabled: {LOG_FILE}")
except (OSError, PermissionError) as e:
    logger.warning(f"File logging disabled due to permission error: {e}")

# Prevent propagation to root logger
logger.propagate = False

# Log configuration for debugging
logger.info(f"Container configuration loaded:")
logger.info(f"  DOWNLOADS_DIR: {DOWNLOADS_DIR}")
logger.info(f"  LOGS_DIR: {LOGS_DIR}")
logger.info(f"  API_KEY_FILE: {API_KEY_FILE}")
logger.info(f"  PORT: {PORT}")

# Add configuration for update check and cleanup - use validated config
YTDLP_UPDATE_INTERVAL = int(validated_config['YTDLP_UPDATE_INTERVAL'])
CLEANUP_INTERVAL = int(validated_config['CLEANUP_INTERVAL'])
FILE_MAX_AGE = int(validated_config['FILE_MAX_AGE'])

# Additional container configuration - use validated config
YTDL_MAX_RETRIES = int(validated_config['YTDL_MAX_RETRIES'])
YTDL_RETRY_DELAY = int(validated_config['YTDL_RETRY_DELAY'])

last_update_check = 0
last_update_status = None
last_cleanup_time = 0

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    task = asyncio.create_task(periodic_tasks())
    logger.info("Background tasks started")
    yield
    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Background tasks cancelled")

app = FastAPI(lifespan=lifespan)

# Handle API key with container-aware logic
def get_api_key():
    # First check if API key is provided via validated configuration
    env_api_key = validated_config.get('YTDL_SERVICE_API_KEY')
    if env_api_key:
        logger.info("Using API key from environment variable")
        return env_api_key
    
    # If not in environment, try to read from file
    if not os.path.exists(API_KEY_FILE):
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(API_KEY_FILE), exist_ok=True)
            api_key = secrets.token_urlsafe(32)
            with open(API_KEY_FILE, "w") as f:
                f.write(api_key)
            logger.info(f"Generated new API key file: {API_KEY_FILE}")
            return api_key
        except (IOError, OSError, PermissionError) as e:
            logger.error(f"Error writing API key file {API_KEY_FILE}: {e}")
            logger.warning("Failed to write API key file, using temporary key for this session.")
            return secrets.token_urlsafe(32)
    else:
        try:
            with open(API_KEY_FILE, "r") as f:
                api_key = f.read().strip()
                logger.info(f"Loaded API key from file: {API_KEY_FILE}")
                return api_key
        except (IOError, OSError, PermissionError) as e:
            logger.error(f"Error reading API key file {API_KEY_FILE}: {e}")
            logger.warning("Failed to read API key file, using temporary key for this session.")
            return secrets.token_urlsafe(32)

API_KEY = get_api_key()
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != API_KEY:
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API key")
    return api_key_header

class DownloadRequest(BaseModel):
    url: str
    format: str = 'best[ext=mp4]/best'
    subtitles: bool = False
    audio_only: bool = False
    max_height: int = 1080

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

@app.get("/health")
async def health_check():
    # Public endpoint, no API key required
    try:
        # Enhanced dependency checks with version information
        ffmpeg_available = False
        ffmpeg_version = None
        try:
            ffmpeg_result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            ffmpeg_available = ffmpeg_result.returncode == 0
            if ffmpeg_available:
                # Extract version from first line
                first_line = ffmpeg_result.stdout.split('\n')[0]
                if 'version' in first_line:
                    ffmpeg_version = first_line.split('version')[1].split()[0]
        except Exception as e:
            logger.warning(f"FFmpeg check failed: {e}")
        
        # Enhanced yt-dlp availability check
        ytdlp_available = False
        ytdlp_version = None
        ytdlp_functional = False
        try:
            ytdlp_version = yt_dlp.version.__version__
            ytdlp_available = True
            
            # Test yt-dlp functionality with a simple extraction
            test_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'simulate': True
            }
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                # Test with a simple YouTube URL (doesn't actually download)
                test_info = ydl.extract_info('https://www.youtube.com/watch?v=dQw4w9WgXcQ', download=False)
                ytdlp_functional = test_info is not None
        except Exception as e:
            logger.warning(f"yt-dlp functionality test failed: {e}")
        
        # Enhanced directory permission checks
        downloads_write_permission = os.access(DOWNLOADS_DIR, os.W_OK)
        downloads_read_permission = os.access(DOWNLOADS_DIR, os.R_OK)
        downloads_exists = os.path.exists(DOWNLOADS_DIR)
        logs_write_permission = os.access(LOGS_DIR, os.W_OK)
        logs_exists = os.path.exists(LOGS_DIR)
        
        # Enhanced disk space monitoring for both downloads and logs
        downloads_disk_usage = None
        logs_disk_usage = None
        
        try:
            # Downloads directory disk usage
            if downloads_exists:
                statvfs = os.statvfs(DOWNLOADS_DIR)
                free_bytes = statvfs.f_frsize * statvfs.f_bavail
                total_bytes = statvfs.f_frsize * statvfs.f_blocks
                used_bytes = total_bytes - free_bytes
                downloads_disk_usage = {
                    "total_gb": round(total_bytes / (1024**3), 2),
                    "used_gb": round(used_bytes / (1024**3), 2),
                    "free_gb": round(free_bytes / (1024**3), 2),
                    "usage_percent": round((used_bytes / total_bytes) * 100, 1),
                    "available_mb": round(free_bytes / (1024**2), 2)
                }
            
            # Logs directory disk usage (may be on different filesystem)
            if logs_exists:
                logs_statvfs = os.statvfs(LOGS_DIR)
                logs_free_bytes = logs_statvfs.f_frsize * logs_statvfs.f_bavail
                logs_total_bytes = logs_statvfs.f_frsize * logs_statvfs.f_blocks
                logs_used_bytes = logs_total_bytes - logs_free_bytes
                logs_disk_usage = {
                    "total_gb": round(logs_total_bytes / (1024**3), 2),
                    "used_gb": round(logs_used_bytes / (1024**3), 2),
                    "free_gb": round(logs_free_bytes / (1024**3), 2),
                    "usage_percent": round((logs_used_bytes / logs_total_bytes) * 100, 1),
                    "available_mb": round(logs_free_bytes / (1024**2), 2)
                }
        except Exception as e:
            logger.warning(f"Could not get disk usage: {e}")
        
        # System resource monitoring
        system_resources = {}
        try:
            # Memory usage
            import psutil
            memory = psutil.virtual_memory()
            system_resources["memory"] = {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent,
                "free_gb": round(memory.free / (1024**3), 2)
            }
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            system_resources["cpu"] = {
                "usage_percent": cpu_percent,
                "count": psutil.cpu_count(),
                "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None
            }
            
            # Process information
            current_process = psutil.Process()
            system_resources["process"] = {
                "pid": current_process.pid,
                "memory_mb": round(current_process.memory_info().rss / (1024**2), 2),
                "cpu_percent": current_process.cpu_percent(),
                "threads": current_process.num_threads(),
                "open_files": len(current_process.open_files()),
                "connections": len(current_process.connections())
            }
        except ImportError:
            logger.warning("psutil not available for system resource monitoring")
        except Exception as e:
            logger.warning(f"System resource monitoring failed: {e}")
        
        # Process health checks
        process_health = {}
        try:
            # Check if current process is healthy
            current_pid = os.getpid()
            process_health["current_process"] = {
                "pid": current_pid,
                "running": True  # If we're here, we're running
            }
            
            # Check for other related processes
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if 'video_downloader.py' in cmdline:
                            process_health["telegram_bot"] = {
                                "pid": proc.info['pid'],
                                "running": True
                            }
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                else:
                    process_health["telegram_bot"] = {
                        "pid": None,
                        "running": False
                    }
            except ImportError:
                pass
        except Exception as e:
            logger.warning(f"Process health check failed: {e}")
        
        # Check API key file accessibility
        api_key_accessible = os.path.exists(API_KEY_FILE) and os.access(API_KEY_FILE, os.R_OK)
        api_key_from_env = bool(validated_config.get('YTDL_SERVICE_API_KEY'))
        
        # Network connectivity test
        network_health = {}
        try:
            # Test DNS resolution
            import socket
            socket.gethostbyname('www.youtube.com')
            network_health["dns_resolution"] = True
            
            # Test HTTP connectivity
            import urllib.request
            urllib.request.urlopen('https://www.youtube.com', timeout=5)
            network_health["http_connectivity"] = True
        except Exception as e:
            network_health["dns_resolution"] = False
            network_health["http_connectivity"] = False
            logger.warning(f"Network connectivity test failed: {e}")
        
        # Container-specific health indicators
        container_health = {
            "ffmpeg_available": ffmpeg_available,
            "ytdlp_available": ytdlp_available,
            "ytdlp_functional": ytdlp_functional,
            "api_key_accessible": api_key_accessible or api_key_from_env,
            "downloads_dir_accessible": downloads_exists and downloads_read_permission and downloads_write_permission,
            "logs_dir_accessible": logs_exists and logs_write_permission,
            "disk_space_ok": (downloads_disk_usage["usage_percent"] < 90 if downloads_disk_usage else True) and 
                           (logs_disk_usage["usage_percent"] < 95 if logs_disk_usage else True),
            "network_connectivity": network_health.get("http_connectivity", False),
            "dns_resolution": network_health.get("dns_resolution", False)
        }
        
        # Critical vs non-critical health checks
        critical_checks = [
            "ffmpeg_available",
            "ytdlp_available", 
            "downloads_dir_accessible",
            "disk_space_ok"
        ]
        
        critical_healthy = all(container_health[check] for check in critical_checks)
        overall_healthy = all(container_health.values())
        
        # Determine status
        if critical_healthy and overall_healthy:
            status = "healthy"
        elif critical_healthy:
            status = "degraded"
        else:
            status = "unhealthy"
        
        health_response = {
            "status": status,
            "container_health": container_health,
            "system_info": {
                "yt_dlp_version": ytdlp_version or "unavailable",
                "ffmpeg_version": ffmpeg_version or "unavailable",
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "last_update_check": datetime.fromtimestamp(last_update_check).isoformat() if last_update_check else None,
                "last_update_status": last_update_status,
                "uptime_seconds": time.time() - (last_update_check or time.time())
            },
            "directories": {
                "downloads_dir": DOWNLOADS_DIR,
                "logs_dir": LOGS_DIR,
                "api_key_file": API_KEY_FILE,
                "downloads_dir_exists": downloads_exists,
                "downloads_dir_writeable": downloads_write_permission,
                "downloads_dir_readable": downloads_read_permission,
                "logs_dir_exists": logs_exists,
                "logs_dir_writeable": logs_write_permission,
            },
            "disk_usage": {
                "downloads": downloads_disk_usage,
                "logs": logs_disk_usage
            },
            "system_resources": system_resources,
            "process_health": process_health,
            "network_health": network_health,
            "configuration": {
                "port": PORT,
                "max_retries": YTDL_MAX_RETRIES,
                "retry_delay": YTDL_RETRY_DELAY,
                "update_interval_hours": YTDLP_UPDATE_INTERVAL / 3600,
                "cleanup_interval_hours": CLEANUP_INTERVAL / 3600,
                "file_max_age_hours": FILE_MAX_AGE / 3600,
                "api_key_source": "environment" if api_key_from_env else "file"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        if not overall_healthy:
            logger.warning(f"Health check shows {status} status: {container_health}")
        
        return health_response
        
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

def find_downloaded_file(download_id):
    """Find the downloaded file with the given ID"""
    try:
        if not os.path.exists(DOWNLOADS_DIR):
            logger.error(f"Downloads directory doesn't exist: {DOWNLOADS_DIR}")
            return None
        
        files_in_dir = os.listdir(DOWNLOADS_DIR)
        logger.info(f"Looking for files with prefix '{download_id}' in {len(files_in_dir)} files")
        
        # Look for files with our download_id
        matching_files = []
        for fname in files_in_dir:
            if fname.startswith(download_id):
                fpath = os.path.join(DOWNLOADS_DIR, fname)
                if os.path.isfile(fpath):
                    size = os.path.getsize(fpath)
                    if size > 0:
                        matching_files.append((fpath, size, fname))
                        logger.info(f"Found matching file: {fname} ({size} bytes)")
        
        if matching_files:
            # Sort by file size (largest first) to get the main video file
            matching_files.sort(key=lambda x: x[1], reverse=True)
            best_file = matching_files[0][0]
            logger.info(f"Selected best file: {os.path.basename(best_file)} ({matching_files[0][1]} bytes)")
            return best_file
        
        logger.error(f"No matching files found for download_id: {download_id}")
        logger.info(f"Available files: {[f for f in files_in_dir if os.path.isfile(os.path.join(DOWNLOADS_DIR, f))]}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding downloaded file: {e}")
        return None

def cleanup_files(prefix):
    """Clean up all files with the given prefix"""
    try:
        if not os.path.exists(DOWNLOADS_DIR):
            logger.error(f"Downloads directory doesn't exist: {DOWNLOADS_DIR}")
            return
        
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

def get_clip_formats():
    """Get format selection specifically optimized for YouTube clips.
    Prioritizes MP4 format for better compatibility and includes fallback options.
    """
    return [
        # Best quality MP4 with audio (up to 1080p)
        'bestvideo[ext=mp4][height<=1080][fps<=60][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]',
        
        # Fallback to any MP4 with audio (up to 1080p)
        'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]',
        
        # Best quality with any video codec (up to 1080p)
        'bestvideo[height<=1080][fps<=60]+bestaudio/best[height<=1080]',
        
        # Fallback to any quality with MP4 container
        'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        
        # Final fallback to any format
        'bestvideo+bestaudio/best',
        'best[height>=1080]/best',
        'best'
    ]
    
    return format_string

def download_progress_hook(d):
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '0%').strip()
        speed = d.get('_speed_str', 'N/A')
        eta = d.get('_eta_str', 'N/A')
        logger.info(f"Download progress: {progress} at {speed} - ETA: {eta}")
    elif d['status'] == 'finished':
        logger.info("Download complete - Merging formats...")

def download_youtube_video(request: DownloadRequest, download_id: str, output_template: str):
    """Enhanced YouTube download with working strategies - FIXED VERSION"""
    
    # Detect YouTube Shorts, Clips, and regular videos
    is_youtube_shorts = "youtube.com/shorts" in request.url
    is_youtube_clips = "youtube.com/clip" in request.url
    is_youtube = any(x in request.url for x in ["youtube.com", "youtu.be"])
    
    if not is_youtube:
        return None  # Not YouTube, use regular download
    
    logger.info(f"🎬 YouTube download detected: {request.url}")
    logger.info(f"   Type: {'Shorts' if is_youtube_shorts else 'Clips' if is_youtube_clips else 'Regular'}")
    
    # Special handling for YouTube clips - Explicit format selection
    if is_youtube_clips:
        logger.info("Using explicit format selection for YouTube clips")
        # Prioritize high quality formats that we know exist based on logs
        clip_format = '\n'.join([
            # Try high quality formats first (from the available formats in logs)
            'bestvideo[height<=1440][fps<=60][vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[height<=1440]',
            'bestvideo[height<=1440][fps<=60]+bestaudio/best[height<=1440]',
            # Fallback to standard formats
            '22/18/36/43',  # Standard formats that usually work with clips
            # Final fallback to any format
            'best[ext=mp4]/best[ext=webm]/best'
        ])
    else:
        clip_format = None
    
    # Define working strategies - Simplified for clips
    strategies = [
        {
            'name': 'Direct format download (best for clips)',
            'opts': {
                'format': clip_format if is_youtube_clips else 'best',
                'outtmpl': output_template,
                'restrictfilenames': True,
                'retries': YTDL_MAX_RETRIES,
                'fragment_retries': YTDL_MAX_RETRIES,
                'socket_timeout': 30,
                'ignoreerrors': False,
                'geo_bypass': True,
                'nocheckcertificate': True,
                'quiet': False,
                'no_warnings': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.youtube.com/'
                }
            }
        },
        {
            'name': 'Web client (with format selection)',
            'opts': {
                'format': clip_format if is_youtube_clips else 'best',
                'merge_output_format': 'mp4',
                'format_sort': ['res:1440', 'res:1080', 'res:720', 'res:480', 'res:360'],
                'format_sort_force': True,  # Enforce the format sort order
                'prefer_free_formats': False,  # Prefer non-DASH formats first
                'outtmpl': output_template,
                'restrictfilenames': True,
                'retries': 3,
                'fragment_retries': 5,
                'socket_timeout': 30,
                'extract_flat': False,
                'noprogress': False,
                'nopart': True,  # Don't use .part files
                'noresizebuffer': True,
                'buffersize': 1024 * 1024,  # 1MB buffer
                'http_chunk_size': 1048576,  # 1MB chunks
                'concurrent_fragment_downloads': 4,  # Parallel downloads
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Referer': 'https://www.youtube.com/'
                },
                'extractor_retries': 3,
                'fragment_retry_sleep': 1,
                'ignoreerrors': False,
                'geo_bypass': True,
                'nocheckcertificate': True,
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
                'prefer_ffmpeg': True,  # Important for merging
                'progress_hooks': [download_progress_hook],
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],  # Try android first as it's more reliable for clips
                        'skip': ['hls'],  # Only skip HLS, allow DASH for higher quality
                        'noplaylist': True,  # Ensure we don't try to download playlists
                        'quiet': False,
                        'no_warnings': False,
                        'extract_flat': False,  # Ensure we don't use flat extraction
                        'format': 'bestvideo[height<=1440]+bestaudio/best[height>=720]'  # Direct format selection
                    }
                },
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }] if is_youtube_clips else []
            }
        },
        {
            'name': 'Specific format targeting',
            'opts': {
                # Simple format selection
                'format': clip_format if is_youtube_clips else 'best',
                'merge_output_format': 'mp4',
                'format_sort': ['res:1080', 'res:720', 'res:480', 'res:360'],
                'outtmpl': output_template,
                'restrictfilenames': True,
                'retries': 3,
                'fragment_retries': 3,
                'socket_timeout': 30,
                'ignoreerrors': False,
                'geo_bypass': True,
                'nocheckcertificate': True,
                'quiet': False,
                'no_warnings': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.youtube.com/'
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web']
                    }
                }
            }
        },
        {
            'name': 'iOS client with high quality',
            'opts': {
                'format': clip_format if is_youtube_clips else 'bestvideo[height<=1080]+bestaudio/best',
                'outtmpl': output_template,
                'restrictfilenames': True,
                'retries': 2,
                'fragment_retries': 3,
                'socket_timeout': 30,
                'ignoreerrors': False,
                'geo_bypass': True,
                'nocheckcertificate': True,
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
                'http_headers': {
                    'User-Agent': 'com.google.ios.youtube/17.36.4 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)'
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['ios'],
                        'skip': ['hls']
                    }
                }
            }
        }
    ]
    
    # Try each strategy
    for i, strategy in enumerate(strategies, 1):
        logger.info(f"📋 Trying YouTube strategy {i}/{len(strategies)}: {strategy['name']}")
        
        if is_youtube_clips:
            logger.info(f"   Using clip-optimized format: {strategy['opts']['format']}")
        
        try:
            # DEBUGGING: Show available formats for first strategy only
            if i == 1 and is_youtube_clips:
                try:
                    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl_info:
                        info_dict = ydl_info.extract_info(request.url, download=False)
                        if 'formats' in info_dict:
                            logger.info("Available formats for clip:")
                            
                            # Show video formats
                            video_formats = [f for f in info_dict['formats'] 
                                           if f.get('vcodec') != 'none' and f.get('height')]
                            logger.info("Video streams:")
                            for f in sorted(video_formats, key=lambda x: x.get('height', 0), reverse=True)[:10]:
                                vcodec = (f.get('vcodec') or '?').split('.')[0]
                                height = f.get('height', '?')
                                fps = f.get('fps', '?')
                                logger.info(f"  - {f.get('format_id')}: {height}p@{fps}fps {vcodec}")
                            
                            # Show audio formats
                            audio_formats = [f for f in info_dict['formats'] 
                                           if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                            logger.info("Audio streams:")
                            for f in audio_formats[:5]:
                                acodec = (f.get('acodec') or '?').split('.')[0]
                                abr = f.get('abr', '?')
                                logger.info(f"  - {f.get('format_id')}: {acodec} {abr}kbps")
                            
                            # CRITICAL DEBUG: Show what our format selector would choose
                            test_opts = strategy['opts'].copy()
                            test_opts['simulate'] = True
                            test_opts['quiet'] = True
                            try:
                                with yt_dlp.YoutubeDL(test_opts) as test_ydl:
                                    test_info = test_ydl.extract_info(request.url, download=False)
                                    if 'requested_formats' in test_info:
                                        logger.info("Format selector would choose:")
                                        for rf in test_info['requested_formats']:
                                            logger.info(f"  - {rf.get('format_id')}: {rf.get('resolution', '?')} {rf.get('vcodec', rf.get('acodec', '?'))}")
                                    else:
                                        logger.info(f"Format selector would choose: {test_info.get('format_id')} - {test_info.get('resolution')}")
                            except:
                                pass
                                
                except Exception as e:
                    logger.warning(f"Failed to show formats: {e}")
            
            # Perform the download
            ydl_opts = strategy['opts'].copy()
            
            logger.info(f"Downloading with format: {ydl_opts['format']}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to see what will be downloaded
                info = ydl.extract_info(request.url, download=False)
                
                # Log what format will be selected
                if 'requested_formats' in info:
                    for rf in info['requested_formats']:
                        format_type = "Video" if rf.get('vcodec') != 'none' else "Audio"
                        resolution = rf.get('height', '?')
                        codec = rf.get('vcodec') or rf.get('acodec', '?')
                        logger.info(f"Will download: {format_type} {rf.get('format_id')} ({resolution}p {codec})")
                else:
                    logger.info(f"Will download single format: {info.get('format_id')} - {info.get('resolution')}")
                
                # Now perform the actual download
                info = ydl.extract_info(request.url, download=True)
            
            if info:
                logger.info(f"✅ YouTube strategy '{strategy['name']}' succeeded!")
                
                # Wait for file system
                time.sleep(2)
                
                # Find downloaded file
                downloaded_file = find_downloaded_file(download_id)
                if downloaded_file:
                    video_info = get_video_info(downloaded_file)
                    logger.info(f"YouTube download successful: {os.path.basename(downloaded_file)} - {video_info['width']}x{video_info['height']}")
                    
                    return {
                        "success": True,
                        "file_path": os.path.basename(downloaded_file),
                        "download_url": f"/files/{os.path.basename(downloaded_file)}",
                        "title": info.get('title', 'YouTube Video'),
                        "url": request.url,
                        "description": info.get('description', ''),
                        "tags": info.get('tags', []),
                        "duration": info.get('duration'),
                        "uploader": info.get('uploader'),
                        "file_size_bytes": os.path.getsize(downloaded_file),
                        "file_size_mb": round(os.path.getsize(downloaded_file) / (1024 * 1024), 2),
                        "video_info": video_info,
                        "quality": f"{video_info['width']}x{video_info['height']}" if video_info['width'] > 0 else "Audio only",
                        "strategy_used": strategy['name']
                    }
                else:
                    logger.error(f"Downloaded file not found for strategy: {strategy['name']}")
                    
        except yt_dlp.utils.DownloadError as e:
            logger.warning(f"❌ YouTube strategy '{strategy['name']}' failed: {str(e)}")
            cleanup_files(download_id)
        except Exception as e:
            logger.error(f"❌ YouTube strategy '{strategy['name']}' error: {str(e)}")
            cleanup_files(download_id)
    
    # All strategies failed
    logger.error(f"❌ All YouTube strategies failed for: {request.url}")
    return {
        "success": False,
        "error": "All YouTube strategies failed",
        "error_type": "youtube_extraction_failed"
    }
    
@app.post("/download")
async def download_video(request: DownloadRequest,
                        background_tasks: BackgroundTasks,
                        api_key: str = Depends(verify_api_key)):
    
    download_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(DOWNLOADS_DIR, f'{download_id}.%(ext)s')
    
    # Clean up any existing files with this ID
    cleanup_files(download_id)
    
    # Check if it's YouTube and use specialized handler
    is_youtube = any(x in request.url for x in ["youtube.com", "youtu.be"])
    
    if is_youtube:
        logger.info(f"🎯 YouTube URL detected, using specialized handler: {request.url}")
        result = download_youtube_video(request, download_id, output_template)
        if result:
            return result
        # If YouTube handler fails, fall through to regular handler
        logger.warning("YouTube handler failed, trying regular handler")
    
    # Instagram detection
    is_instagram = any(x in request.url for x in ["instagram.com/p/", "instagram.com/reel/", "instagram.com/tv/"])
    
    if is_instagram:
        logger.info(f"📸 Instagram download attempt: {request.url}")
        
        cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
        
        ydl_opts = {
            'format': request.format or 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'restrictfilenames': True,
            'retries': YTDL_MAX_RETRIES,
            'fragment_retries': YTDL_MAX_RETRIES,
            'socket_timeout': 60,
            'concurrent_fragment_downloads': 2,
            'max_downloads': 2,
            'http_chunk_size': 10485760,
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            'progress_hooks': [
                lambda d: logger.info(f"[Instagram] Download progress: {d.get('_percent_str', 'N/A')} - {d.get('filename', 'N/A')}") 
                if d['status'] == 'downloading' 
                else logger.info(f"[Instagram] Download status: {d['status']}")
            ],
            'ignoreerrors': False,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Range': 'bytes=0-',
                'Cache-Control': 'no-cache',
            },
        }
        
        # Use cookies if available
        if os.path.exists(cookies_path):
            ydl_opts['cookiefile'] = cookies_path
            logger.info(f"Using Instagram cookies from {cookies_path}")
        else:
            logger.warning("No cookies.txt found for Instagram. Some videos may require login.")
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
                
                if not info:
                    raise Exception("Failed to extract Instagram video information")
                
                time.sleep(2)
                downloaded_file = find_downloaded_file(download_id)
                
                if not downloaded_file:
                    raise Exception("Downloaded file not found for Instagram video")
                
                video_info = get_video_info(downloaded_file)
                logger.info(f"Instagram download successful: {os.path.basename(downloaded_file)} - {video_info['width']}x{video_info['height']}")
                
                return {
                    "success": True,
                    "file_path": os.path.basename(downloaded_file),
                    "download_url": f"/files/{os.path.basename(downloaded_file)}",
                    "title": info.get('title', 'Instagram Video') if info else 'Instagram Video',
                    "url": request.url,
                    "description": info.get('description', '') if info else '',
                    "tags": info.get('tags', []) if info else [],
                    "duration": info.get('duration') if info else None,
                    "uploader": info.get('uploader') if info else None,
                    "file_size_bytes": os.path.getsize(downloaded_file),
                    "file_size_mb": round(os.path.getsize(downloaded_file) / (1024 * 1024), 2),
                    "video_info": video_info,
                    "quality": f"{video_info['width']}x{video_info['height']}" if video_info['width'] > 0 else "Audio only"
                }
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"[Instagram] yt-dlp download error: {error_msg}")
            cleanup_files(download_id)
            return {
                "success": False,
                "error": f"Instagram download failed: {error_msg}",
                "error_type": "download_error"
            }
        except Exception as e:
            logger.error(f"[Instagram] Download failed with exception: {str(e)}")
            cleanup_files(download_id)
            return {
                "success": False,
                "error": str(e),
                "error_type": "general_error"
            }
    
    # For other platforms, use simplified approach
    try:
        logger.info(f"🌐 Starting regular download for URL: {request.url}")
        
        # Simplified format for non-YouTube platforms
        format_string = request.format or 'best[ext=mp4]/best'
        
        ydl_opts = {
            'format': format_string,
            'outtmpl': output_template,
            'restrictfilenames': True,
            'retries': YTDL_MAX_RETRIES,
            'fragment_retries': YTDL_MAX_RETRIES,
            'socket_timeout': 60,
            'ignoreerrors': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'quiet': False,
            'no_warnings': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'postprocessors': []  # Minimal post-processing
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=True)
            
            if not info:
                raise Exception("Failed to extract video information")
            
            time.sleep(2)
            downloaded_file = find_downloaded_file(download_id)
            
            if not downloaded_file:
                raise Exception("Downloaded file not found")
            
            video_info = get_video_info(downloaded_file)
            logger.info(f"Regular download successful: {os.path.basename(downloaded_file)}")
            
            return {
                "success": True,
                "file_path": os.path.basename(downloaded_file),
                "download_url": f"/files/{os.path.basename(downloaded_file)}",
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

@app.get("/files")
async def list_files(api_key: str = Depends(verify_api_key)):
    """List available downloaded files"""
    try:
        files = []
        if os.path.exists(DOWNLOADS_DIR):
            for filename in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, filename)
                if os.path.isfile(file_path):
                    try:
                        size = os.path.getsize(file_path)
                        modified = os.path.getmtime(file_path)
                        files.append({
                            "filename": filename,
                            "download_url": f"/files/{filename}",
                            "size_bytes": size,
                            "size_mb": round(size / (1024 * 1024), 2),
                            "modified_timestamp": modified,
                            "modified_iso": datetime.fromtimestamp(modified).isoformat()
                        })
                    except Exception as e:
                        logger.error(f"Error processing file {filename}: {str(e)}")
        
        # Sort by modification time, newest first
        files.sort(key=lambda x: x['modified_timestamp'], reverse=True)
        
        return {
            "files": files,
            "file_count": len(files),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return {"error": str(e)}

@app.get("/files/{filename}")
async def get_file(filename: str, api_key: str = Depends(verify_api_key)):
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
async def cleanup_storage(api_key: str = Depends(verify_api_key)):
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
async def get_storage_info(api_key: str = Depends(verify_api_key)):
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

@app.get("/formats")
async def get_available_formats(url: str, api_key: str = Depends(verify_api_key)):
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

# Store download statuses in memory (in production, use Redis or database)
download_statuses = {}

@app.get("/status/{download_id}")
async def get_download_status(download_id: str, api_key: str = Depends(verify_api_key)):
    """Get the status of a background download"""
    if download_id not in download_statuses:
        raise HTTPException(status_code=404, detail="Download not found")
    
    return download_statuses[download_id]

@app.get("/downloads")
async def list_downloads(api_key: str = Depends(verify_api_key)):
    """List all current download statuses"""
    return {
        "downloads": download_statuses,
        "total_downloads": len(download_statuses),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting FastAPI server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
