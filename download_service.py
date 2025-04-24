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

# Simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ytdl_simple")

# Simple config
DOWNLOADS_DIR = "/opt/ytdl_service/downloads"
API_KEY_FILE = "/opt/ytdl_service/api_key.txt"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

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
  api_key: str = Depends(verify_api_key)
):
  try:
      logger.info(f"Starting download for URL: {request.url}")

      # Generate unique ID for filename
      download_id = str(uuid.uuid4())[:8]
      output_template = os.path.join(DOWNLOADS_DIR, f'{download_id}-%(title)s.%(ext)s')

      # Setup yt-dlp options
      ydl_opts = {
          'format': request.format,
          'outtmpl': output_template,
          'quiet': False,  # Enable output for debugging
          'no_warnings': False,  # Show warnings for debugging
          'restrictfilenames': True,
          'prefer_ffmpeg': True,
          'merge_output_format': 'mp4',  # Force MP4 output format
      }

      # Special options for YouTube clips
      if 'youtube.com/clip' in request.url.lower():
          logger.info("YouTube clip detected - applying specialized configuration")
          
          # Extract clip ID for better logging
          clip_id = "unknown"
          try:
              if "clip/" in request.url:
                  clip_id = request.url.split("clip/")[1].split("?")[0]
          except:
              pass
              
          logger.info(f"Processing YouTube clip ID: {clip_id}")
          
          # For YouTube clips section
          ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',  # Modified format string
                'force_generic_extractor': False,
                'no_playlist': True,
                'geo_bypass': True,
                'socket_timeout': 30,
                'retries': 10,
                'fragment_retries': 10,
                'skip_download': False,
                'keepvideo': True,
                'verbose': True,
                'listformats': True,  # Add this to log available formats
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                }
            })
          
          # Check if ffmpeg is available
          ffmpeg_available = subprocess.run(
              ["which", "ffmpeg"],
              capture_output=True
          ).returncode == 0
          
          if ffmpeg_available:
              logger.info("ffmpeg detected, using as external downloader")
              ydl_opts.update({
                  'external_downloader': 'ffmpeg',
                  'external_downloader_args': {
                      'ffmpeg': ['-loglevel', 'warning', '-reconnect', '1', 
                                '-reconnect_streamed', '1', '-reconnect_delay_max', '5']
                  }
              })
          else:
              logger.warning("ffmpeg not found, using native downloaders")
              ydl_opts.update({
                  'hls_prefer_native': True  # Use native downloader if ffmpeg not available
              })

      # Download the video
      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
          logger.info("Extracting video info...")
          info = ydl.extract_info(request.url, download=True)
          downloaded_file = ydl.prepare_filename(info)
          logger.info(f"Expected downloaded file path: {downloaded_file}")
          logger.info(f"Files in directory: {os.listdir(DOWNLOADS_DIR)}")
          
          # Log format details for debugging
          if 'youtube.com/clip' in request.url.lower():
              logger.info(f"Selected format: {info.get('format_id', 'unknown')}")
              logger.info(f"Video resolution: {info.get('width', 'unknown')}x{info.get('height', 'unknown')}")
              logger.info(f"Format description: {info.get('format', 'unknown')}")
              
              # Log available formats
              logger.info(f"Available formats:")
              for fmt in info.get('formats', []):
                  logger.info(f"  - {fmt.get('format_id')}: {fmt.get('width')}x{fmt.get('height')} ({fmt.get('ext')})")

          # Check if file exists (account for format changes)
          if not os.path.exists(downloaded_file):
              base, _ = os.path.splitext(downloaded_file)
              fallback_extensions = ['.mp4', '.webm', '.mkv', '.m4a']

              for ext in fallback_extensions:
                potential_file = base + ext
                if os.path.exists(potential_file):
                    downloaded_file = potential_file
                    logger.info(f"Found file with different extension: {downloaded_file}")
                    break
              else:
                # Fallback based on custom file pattern if title extraction failed
                title = info.get('title') or 'video'
                fallback_file = os.path.join(DOWNLOADS_DIR, f"{download_id}-{title}.mp4")
                if os.path.exists(fallback_file):
                    downloaded_file = fallback_file
                    logger.info(f"Found file using fallback pattern: {downloaded_file}")
                else:
                    raise Exception("File not found after download")

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
      
      # Handle common YouTube clip errors
      if "youtube.com/clip" in request.url.lower():
          logger.error(f"YouTube clip download failed with error: {error_msg}")
          
          # Try one more time with different options if it's a clip
          try:
              logger.info("Attempting fallback download method for clip")
              
              # Different approach for clips
              alt_opts = {
                  'format': 'bestvideo+bestaudio/best',     # Simpler format string
                  'outtmpl': output_template,
                  'quiet': False,
                  'no_warnings': False,
                  'restrictfilenames': True,
                  'prefer_ffmpeg': True,
                  'merge_output_format': 'mp4',
                  'force_generic_extractor': True,  # Try with this option
                  'extractor_args': {'youtube': {'player_client': ['android']}},  # Try android client
                  'geo_bypass': True,
                  'nocheckcertificate': True,
              }
              
              with yt_dlp.YoutubeDL(alt_opts) as ydl2:
                  info = ydl2.extract_info(request.url, download=True)
                  downloaded_file = ydl2.prepare_filename(info)
                  logger.info(f"Expected downloaded file path: {downloaded_file}")
                  logger.info(f"Files in directory: {os.listdir(DOWNLOADS_DIR)}")
                  
                  # Log resolution info for fallback method
                  logger.info(f"Fallback - Selected format: {info.get('format_id', 'unknown')}")
                  logger.info(f"Fallback - Video resolution: {info.get('width', 'unknown')}x{info.get('height', 'unknown')}")
                  
                  # Check for the file with possible extensions
                  if not os.path.exists(downloaded_file):
                      base, _ = os.path.splitext(downloaded_file)
                      for ext in ['.mp4', '.webm', '.mkv']:
                          if os.path.exists(base + ext):
                              downloaded_file = base + ext
                              break
                  
                  if os.path.exists(downloaded_file):
                      logger.info(f"Fallback download successful: {downloaded_file}")
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
              logger.error(f"Fallback download also failed: {str(inner_e)}")
              
      return {
          "success": False,
          "error": str(e)
      }
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