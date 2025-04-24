from fastapi import FastAPI, HTTPException, Depends, Security, Request
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
import asyncio
import redis.asyncio as redis
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
# Simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ytdl_simple")

# Simple config
DOWNLOADS_DIR = "/opt/ytdl_service/downloads"
API_KEY_FILE = "/opt/ytdl_service/api_key.txt"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


@app.on_event("startup")
async def startup():
    # Initialize the rate limiter with Redis
    # You'll need Redis installed and running
    try:
        redis_instance = redis.from_url("redis://localhost:6379/0", encoding="utf-8", decode_responses=True)
        await FastAPILimiter.init(redis_instance)
        logger.info("Rate limiter initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize rate limiter: {str(e)}")
        logger.warning("API will run without rate limiting")

# Handle API key
def get_api_key():
  if not os.path.exists(API_KEY_FILE):
      with open(API_KEY_FILE, "w") as f:
          api_key = secrets.token_urlsafe(32)
          f.write(api_key)
      logger.info(f"Generated new API key: {api_key}")
      return api_key
  else:
      with open(API_KEY_FILE, "r") as f:
          return f.read().strip()

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
  format: str = 'best'

@app.get("/health")
async def health_check():
  # Public endpoint, no API key required
  try:
      # Check for ffmpeg
      ffmpeg_available = subprocess.run(
          ["which", "ffmpeg"],
          capture_output=True
      ).returncode == 0

      return {
          "status": "healthy",
          "ffmpeg_available": ffmpeg_available,
          "yt_dlp_version": yt_dlp.version.__version__
      }
  except Exception as e:
      logger.error(f"Health check failed: {str(e)}")
      return {
          "status": "unhealthy",
          "error": str(e)
      }

@app.post("/download")
async def download_video(
    request: DownloadRequest,
    api_key: str = Depends(verify_api_key),
    rate_limit: None = Depends(RateLimiter(times=10, seconds=60))  # 10 requests per minute
):

    try:
        logger.info(f"Starting download for URL: {request.url}")

        # Check for ffmpeg before proceeding
        ffmpeg_available = subprocess.run(
            ["which", "ffmpeg"],
            capture_output=True
        ).returncode == 0
        
        if not ffmpeg_available:
            logger.error("ffmpeg is not available! This is required for video downloads.")
            return {
                "success": False,
                "error": "ffmpeg is not installed on the server. Please install ffmpeg before proceeding."
            }

        # Generate unique ID for filename
        download_id = str(uuid.uuid4())[:8]
        output_template = os.path.join(DOWNLOADS_DIR, f'{download_id}-%(title)s.%(ext)s')

        # Setup yt-dlp options
        ydl_opts = {
            'format': request.format if request.format != 'best' else 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            'restrictfilenames': True,
            'prefer_ffmpeg': True,
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
        }

        # Handle clips specially
        is_clip = 'youtube.com/clip' in request.url.lower()
        if is_clip:
            logger.info("YouTube clip detected - adding special clip handling options")
            
            # For clips, try to avoid partial download options if ffmpeg issues
            ydl_opts.update({
                'force_generic_extractor': False,
                'no_playlist': True,
                'geo_bypass': True,
                'socket_timeout': 30,
                'retries': 10,
                'fragment_retries': 10,
                'skip_download': False,
                'keepvideo': True,
                'verbose': True,
                'hls_prefer_native': True,  # Try native downloader first to avoid ffmpeg issues
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                }
            })
            
            # Only use ffmpeg as external downloader if available
            if ffmpeg_available:
                ydl_opts.update({
                    'external_downloader': 'ffmpeg',
                    'external_downloader_args': {
                        'ffmpeg': ['-loglevel', 'warning', '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5']
                    }
                })

        # Download the video
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("Extracting video info...")
                info = ydl.extract_info(request.url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                
                # Log format details for debugging
                logger.info(f"Selected format: {info.get('format_id', 'unknown')}")
                logger.info(f"Format description: {info.get('format', 'unknown')}")
                
                # Check if file exists (account for format changes)
                if not os.path.exists(downloaded_file):
                    base, _ = os.path.splitext(downloaded_file)
                    for ext in ['.mp4', '.mkv', '.webm']:
                        potential_file = base + ext
                        if os.path.exists(potential_file):
                            downloaded_file = potential_file
                            logger.info(f"Found file with different extension: {downloaded_file}")
                            break

                if not os.path.exists(downloaded_file):
                    raise Exception("File not found after download")
                
                # If ffmpeg is available, verify the file has video stream
                if ffmpeg_available and is_clip:
                    file_info = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0", 
                        "-show_entries", "stream=codec_type", "-of", "csv=p=0", downloaded_file],
                        capture_output=True, text=True
                    )
                    
                    if "video" not in file_info.stdout.strip():
                        logger.warning(f"Downloaded file appears to be audio-only! Attempting to re-download with different options.")
                        
                        # If we got audio only, try again with specific video format
                        os.remove(downloaded_file)
                        ydl_opts.update({
                            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                            'merge_output_format': 'mp4',
                        })
                        
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                            info = ydl2.extract_info(request.url, download=True)
                            downloaded_file = ydl2.prepare_filename(info)
                            
                            # Check file again with potential format changes
                            if not os.path.exists(downloaded_file):
                                base, _ = os.path.splitext(downloaded_file)
                                for ext in ['.mp4', '.mkv', '.webm']:
                                    if os.path.exists(base + ext):
                                        downloaded_file = base + ext
                                        break
                
                # Final check to ensure file exists
                if not os.path.exists(downloaded_file):
                    raise Exception("File not found after download attempts")

                logger.info(f"Download successful: {downloaded_file}")

                return {
                    "success": True,
                    "file_path": os.path.basename(downloaded_file),
                    "title": info.get('title', 'Video'),
                    "url": request.url,
                    "description": info.get('description', ''),
                    "tags": info.get('tags', [])
                }
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"YouTube download error: {error_msg}")
            
            # Handle partial download errors explicitly
            if "downloading the video partially" in error_msg and "ffmpeg is not installed" in error_msg:
                logger.error("ffmpeg is required but not available - trying alternative download method")
                # Try again with different options that don't require ffmpeg for partial downloads
                ydl_opts.update({
                    'hls_prefer_native': True,  # Use native downloader instead of ffmpeg
                    'external_downloader': None  # Don't use external downloader
                })
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl3:
                        info = ydl3.extract_info(request.url, download=True)
                        downloaded_file = ydl3.prepare_filename(info)
                        
                        if not os.path.exists(downloaded_file):
                            base, _ = os.path.splitext(downloaded_file)
                            for ext in ['.mp4', '.mkv', '.webm']:
                                if os.path.exists(base + ext):
                                    downloaded_file = base + ext
                                    break
                                    
                        if os.path.exists(downloaded_file):
                            logger.info(f"Alternative download successful: {downloaded_file}")
                            return {
                                "success": True,
                                "file_path": os.path.basename(downloaded_file),
                                "title": info.get('title', 'Video'),
                                "url": request.url,
                                "description": info.get('description', ''),
                                "tags": info.get('tags', []),
                                "note": "Downloaded with fallback method"
                            }
                except Exception as inner_e:
                    logger.error(f"Alternative download also failed: {str(inner_e)}")
            
            # Special handling for common errors
            if "This video is unavailable" in error_msg:
                return {"success": False, "error": "This clip is no longer available on YouTube"}
            elif "Unable to extract URL" in error_msg:
                return {"success": False, "error": "Unable to process this YouTube clip URL"}
            else:
                return {"success": False, "error": f"Download failed: {error_msg}"}

    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/files/{filename}")
async def get_file(
  filename: str,
  api_key: str = Depends(verify_api_key)
):
  file_path = os.path.join(DOWNLOADS_DIR, filename)
  if not os.path.exists(file_path):
      raise HTTPException(status_code=404, detail="File not found")

  return FileResponse(
      file_path,
      media_type='video/mp4',
      filename=filename
  )

# Storage cleanup task
@app.get("/cleanup")
async def cleanup_storage(
  api_key: str = Depends(verify_api_key)
):
  """Clean up old files to free storage space"""
  import time
  from datetime import datetime, timedelta

  max_age_days = 7  # Files older than this will be deleted
  max_age_seconds = max_age_days * 24 * 60 * 60
  now = time.time()
  deleted_count = 0
  saved_space = 0

  for filename in os.listdir(DOWNLOADS_DIR):
      file_path = os.path.join(DOWNLOADS_DIR, filename)
      if os.path.isfile(file_path):
          file_age = now - os.path.getmtime(file_path)
          if file_age > max_age_seconds:
              file_size = os.path.getsize(file_path)
              saved_space += file_size
              os.remove(file_path)
              deleted_count += 1
              logger.info(f"Deleted old file: {filename}")

  return {
      "deleted_files": deleted_count,
      "saved_space_bytes": saved_space,
      "saved_space_mb": round(saved_space / (1024 * 1024), 2)
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
                        "modified": modified
                    })
                except Exception as e:
                    logger.error(f"Error processing file {filename}: {str(e)}")

        return {
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "files": files
        }
    except Exception as e:
        logger.error(f"Storage info error: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=8000)
