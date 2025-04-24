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
import time # Import time for potential small delay

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
        try:
            api_key = secrets.token_urlsafe(32)
            with open(API_KEY_FILE, "w") as f:
                f.write(api_key)
            logger.info(f"Generated new API key file: {API_KEY_FILE}")
            return api_key
        except IOError as e:
            logger.error(f"Error writing API key file {API_KEY_FILE}: {e}")
            # Fallback to generating a key without saving if file writing fails
            return secrets.token_urlsafe(32)
    else:
        try:
            with open(API_KEY_FILE, "r") as f:
                return f.read().strip()
        except IOError as e:
            logger.error(f"Error reading API key file {API_KEY_FILE}: {e}")
            # Fallback to generating a temporary key if file reading fails
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
    format: str = 'bestvideo+bestaudio/best' # Defaulting to best video and audio, or best if merging not possible

# Custom PostProcessor to collect the final filename
class FilenameCollectorPP(yt_dlp.postprocessor.PostProcessor):
    def __init__(self, collector):
        self.collector = collector

    def run(self, info):
        # yt-dlp might call this multiple times for different stages (e.g., before and after merge)
        # We want the final filepath
        self.collector['final_filepath'] = info['filepath']
        logger.info(f"FilenameCollectorPP collected filepath: {self.collector['final_filepath']}")
        return [], info # Return no changes and the original info

@app.get("/health")
async def health_check():
    # Public endpoint, no API key required
    try:
        # Check for ffmpeg
        ffmpeg_available = subprocess.run(
            ["which", "ffmpeg"],
            capture_output=True
        ).returncode == 0

        # Check for required directory permissions (basic check)
        write_permission = os.access(DOWNLOADS_DIR, os.W_OK)
        read_permission = os.access(DOWNLOADS_DIR, os.R_OK)

        return {
            "status": "healthy",
            "ffmpeg_available": ffmpeg_available,
            "yt_dlp_version": yt_dlp.version.__version__,
            "downloads_dir": DOWNLOADS_DIR,
            "downloads_dir_writeable": write_permission,
            "downloads_dir_readable": read_permission
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
    download_id = str(uuid.uuid4())[:8]
    # Use a simpler output template for yt-dlp
    output_template = os.path.join(DOWNLOADS_DIR, f'{download_id}.%(ext)s')
    final_filepath_collector = {} # Dictionary to collect the final filename

    try:
        logger.info(f"Starting download for URL: {request.url} with format: {request.format}")

        # Setup yt-dlp options
        ydl_opts = {
            'format': request.format,
            'outtmpl': output_template,
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,  # Show warnings for debugging
            'restrictfilenames': True,
            'prefer_ffmpeg': True,
            'merge_output_format': 'mp4', # Force MP4 output format for merged streams
            'concurrent_fragment_downloads': 3,
            'retries': 5,
            'fragment_retries': 5,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'verbose': True, # More verbose output
            'progress': True, # Show progress
            'progress_hooks': [lambda d: logger.info(f"yt-dlp progress: {d.get('_percent_str', 'N/A')} {d.get('_eta_str', 'N/A')}") if d['status'] != 'finished' else logger.info("yt-dlp progress: Finished")], # Log progress
            'postprocessors': [], # Initialize postprocessors list
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            }
        }

        # Add the FilenameCollectorPP
        ydl_opts['postprocessors'].append({
            'key': FilenameCollectorPP,
            'collector': final_filepath_collector
        })

        # Ensure a merge postprocessor is present if merging is expected
        # yt-dlp automatically adds FFmpegVideoRemuxer if merge_output_format is set and ffmpeg is preferred,
        # but adding it explicitly here makes the postprocessor chain more predictable.
        if 'bestvideo' in request.format or 'bestaudio' in request.format:
             ydl_opts['postprocessors'].append({
                 'key': 'FFmpegVideoRemuxer',
                 'loglevel': 'warning',
                 'already_have_ext': 'mp4'
             })


        # Check if ffmpeg is available and configure as external downloader if needed
        ffmpeg_available = subprocess.run(
            ["which", "ffmpeg"],
            capture_output=True
        ).returncode == 0

        if ffmpeg_available:
            logger.info("ffmpeg detected, configuring as external downloader args")
            ydl_opts.update({
                 'external_downloader_args': {
                      'ffmpeg': ['-loglevel', 'warning', '-reconnect', '1',
                                 '-reconnect_streamed', '1', '-reconnect_delay_max', '5']
                 }
            })
        else:
             # If ffmpeg is not available, ensure we don't try to use it for merging/remuxing
             logger.warning("ffmpeg not found. Merging/remuxing may not work correctly.")
             # Remove FFmpegVideoRemuxer if added above
             ydl_opts['postprocessors'] = [pp for pp in ydl_opts['postprocessors'] if pp.get('key') != 'FFmpegVideoRemuxer']
             # Fallback to native HLS downloader if applicable
             ydl_opts['hls_prefer_native'] = True


        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"yt-dlp options: {ydl_opts}")
            logger.info("Extracting video info and starting download...")
            info = ydl.extract_info(request.url, download=True)

        # Retrieve the final filepath from the collector
        downloaded_file = final_filepath_collector.get('final_filepath')

        # Small delay to ensure file system sync
        time.sleep(1)

        # Verify the file exists using the collected path
        if downloaded_file and os.path.exists(downloaded_file):
            logger.info(f"Download successful: {downloaded_file}")

            # Clean up other files in the directory that start with the same download_id
            # This helps remove partial downloads or other artifacts
            for item in os.listdir(DOWNLOADS_DIR):
                 if item.startswith(download_id) and os.path.join(DOWNLOADS_DIR, item) != downloaded_file:
                     item_path = os.path.join(DOWNLOADS_DIR, item)
                     try:
                         if os.path.isfile(item_path):
                              os.remove(item_path)
                              logger.info(f"Cleaned up artifact file: {item}")
                     except Exception as cleanup_e:
                          logger.warning(f"Failed to clean up file {item}: {cleanup_e}")


            return {
                "success": True,
                "file_path": os.path.basename(downloaded_file),
                "title": info.get('title', 'Video'),
                "url": request.url,
                "description": info.get('description', ''),
                "tags": info.get('tags', [])
            }
        else:
            # If the file was not found via the PostProcessor
            logger.error(f"Download failed: File not found after download. Expected path: {downloaded_file}")
            # Log directory contents again for debugging the failure case
            logger.info(f"Files in directory after failed check: {os.listdir(DOWNLOADS_DIR)}")
            raise Exception("File not found after download process completion.")


    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"YouTube download error: {error_msg}")
        return {
            "success": False,
            "error": error_msg
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
    # Basic sanitization to prevent directory traversal
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Determine media type based on file extension
    ext = os.path.splitext(filename)[1].lower()
    media_type = 'application/octet-stream' # Default
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


    return FileResponse(
        file_path,
        media_type=media_type,
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
            "files": files
        }
    except Exception as e:
        logger.error(f"Storage info error: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)