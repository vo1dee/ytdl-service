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
from datetime import datetime # Import datetime for storage info

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
            logger.warning("Failed to write API key file, using temporary key.")
            return secrets.token_urlsafe(32)
    else:
        try:
            with open(API_KEY_FILE, "r") as f:
                return f.read().strip()
        except IOError as e:
            logger.error(f"Error reading API key file {API_KEY_FILE}: {e}")
            # Fallback to generating a temporary key if file reading fails
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
    format: str = 'bestvideo+bestaudio/best' # Defaulting to best video and audio, or best if merging not possible

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
    # Use a simpler output template that we can predict
    # yt-dlp will replace %(ext)s with the actual extension during the download/merge process
    output_template_base = os.path.join(DOWNLOADS_DIR, f'{download_id}')
    output_template = f'{output_template_base}.%(ext)s'

    # Dictionary to hold info needed after download
    download_info = {}

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
            'verbose': True, # More verbose output from yt-dlp
            'progress': True, # Show progress
            'progress_hooks': [lambda d: logger.info(f"yt-dlp progress: {d.get('_percent_str', 'N/A')} {d.get('_eta_str', 'N/A')}") if d['status'] != 'finished' else logger.info("yt-dlp progress: Finished")], # Log progress
            # Removed custom postprocessor here to avoid the TypeError
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            }
        }

        # Check if ffmpeg is available and configure if needed
        # external_downloader_args are typically used for downloading fragments (like HLS/DASH)
        # and shouldn't conflict with postprocessors for merging, but we keep the check.
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
             logger.warning("ffmpeg not found. Merging/remuxing may not work correctly if required by format.")


        # Download the video and get info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"yt-dlp options: {ydl_opts}")
            logger.info("Extracting video info and starting download...")
            # download=True makes extract_info also download
            info = ydl.extract_info(request.url, download=True)
            # Store info needed later, like title. This info object *should*
            # contain details about the downloaded file after the download=True call.
            download_info['title'] = info.get('title', 'Video')
            download_info['description'] = info.get('description', '')
            download_info['tags'] = info.get('tags', [])
            # We can try to get the expected filename from info as well,
            # but the filesystem check is the primary verification.
            download_info['expected_filepath_from_info'] = ydl.prepare_filename(info)
            logger.info(f"yt-dlp info after download: expected filepath is {download_info['expected_filepath_from_info']}")


        # --- File Verification After Download ---
        downloaded_file = None
        # Small delay to ensure file system sync after yt-dlp finishes
        time.sleep(1)

        # List files in the download directory
        files_in_dir = os.listdir(DOWNLOADS_DIR)
        logger.info(f"Files in directory after yt-dlp execution: {files_in_dir}")

        # Look for the file starting with the download_id
        # yt-dlp uses the outtmpl base name before the extension
        potential_files = [f for f in files_in_dir if f.startswith(f"{download_id}.")]

        if not potential_files:
            # No file starting with the expected ID. extension found
            logger.error(f"Download failed: No file found matching pattern {download_id}.* in {DOWNLOADS_DIR}")
            # Log the full list of files found for debugging
            logger.info(f"All files in {DOWNLOADS_DIR}: {files_in_dir}")
            raise Exception("Downloaded file not found or named as expected.")

        elif len(potential_files) == 1:
            # Exactly one file found, assume it's the correct one
            downloaded_file = os.path.join(DOWNLOADS_DIR, potential_files[0])
            logger.info(f"Found unique downloaded file: {downloaded_file}")

        else:
            # Multiple files found starting with the ID prefix.
            # This shouldn't happen with a simple outtmpl + merge_output_format.
            # Could indicate temporary files or an issue.
            logger.warning(f"Multiple potential files found for ID {download_id}.*: {potential_files}. Attempting to find the final merged file.")

            # Try to find the file matching the expected final name from info, or the one with the expected merge extension (.mp4)
            expected_final_filename_from_info = os.path.basename(download_info.get('expected_filepath_from_info', ''))
            expected_merged_extension = ydl_opts.get('merge_output_format', 'mp4') # Default to mp4 if not set
            expected_final_filename_by_merge_ext = f"{download_id}.{expected_merged_extension}"

            found_file = None
            if expected_final_filename_from_info and expected_final_filename_from_info in potential_files:
                 found_file = expected_final_filename_from_info
                 logger.info(f"Found file matching expected final name from info: {found_file}")
            elif expected_final_filename_by_merge_ext in potential_files:
                 found_file = expected_final_filename_by_merge_ext
                 logger.info(f"Found file matching expected merge extension name: {found_file}")
            else:
                # Fallback to finding the largest file among potential files
                max_size = -1
                for fname in potential_files:
                    fpath = os.path.join(DOWNLOADS_DIR, fname)
                    try:
                        if os.path.isfile(fpath):
                            size = os.path.getsize(fpath)
                            if size > max_size:
                                max_size = size
                                found_file = fname
                    except Exception as size_e:
                        logger.warning(f"Error getting size of {fname}: {size_e}")

                if found_file:
                    logger.info(f"Selected largest potential file: {found_file}")

            if found_file:
                 downloaded_file = os.path.join(DOWNLOADS_DIR, found_file)
            else:
                 # If still no file is clearly identified
                 logger.error(f"Download failed: Could not confidently identify the final file among {potential_files}")
                 raise Exception("Downloaded file identification failed.")


        if downloaded_file and os.path.exists(downloaded_file):
            logger.info(f"Download successful: {downloaded_file}")

            # Clean up other files in the directory that start with the same download_id
            # This helps remove partial downloads or other artifacts (like .temp files, original audio/video files before merge)
            for item in os.listdir(DOWNLOADS_DIR):
                 if item.startswith(download_id) and os.path.join(DOWNLOADS_DIR, item) != downloaded_file:
                     item_path = os.path.join(DOWNLOADS_DIR, item)
                     try:
                         # Ensure it's a file or an empty directory before attempting to remove
                         if os.path.isfile(item_path):
                              os.remove(item_path)
                              logger.info(f"Cleaned up artifact file: {item}")
                         elif os.path.isdir(item_path):
                              try:
                                  # Only remove empty directories
                                  if not os.listdir(item_path):
                                      os.rmdir(item_path)
                                      logger.info(f"Cleaned up empty directory: {item}")
                              except OSError:
                                   # Ignore if directory is not empty or cannot be removed
                                   pass
                         else:
                             logger.info(f"Skipping cleanup of non-file/non-directory item: {item}")

                     except Exception as cleanup_e:
                          logger.warning(f"Failed to clean up item {item}: {cleanup_e}")

            # Return success response using info stored earlier
            return {
                "success": True,
                "file_path": os.path.basename(downloaded_file),
                "title": download_info['title'],
                "url": request.url,
                "description": download_info['description'],
                "tags": download_info['tags']
            }
        else:
             # This case should ideally be caught by the checks above, but is a final safety net
             logger.error(f"Download failed: Identified path {downloaded_file} does not exist after checks.")
             raise Exception("Downloaded file not found after processing.")


    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"YouTube download error: {error_msg}")
        # Attempt cleanup of partial files on error
        for item in os.listdir(DOWNLOADS_DIR):
             if item.startswith(download_id):
                 item_path = os.path.join(DOWNLOADS_DIR, item)
                 try:
                     if os.path.isfile(item_path):
                          os.remove(item_path)
                          logger.info(f"Cleaned up partial file on error: {item}")
                     elif os.path.isdir(item_path):
                         try:
                             if not os.listdir(item_path):
                                 os.rmdir(item_path)
                                 logger.info(f"Cleaned up empty directory on error: {item}")
                         except OSError:
                              pass
                 except Exception as cleanup_e:
                      logger.warning(f"Failed to clean up item {item} on error: {cleanup_e}")

        return {
            "success": False,
            "error": error_msg
        }
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        # Attempt cleanup of partial files on error
        for item in os.listdir(DOWNLOADS_DIR):
             if item.startswith(download_id):
                 item_path = os.path.join(DOWNLOADS_DIR, item)
                 try:
                     if os.path.isfile(item_path):
                          os.remove(item_path)
                          logger.info(f"Cleaned up partial file on error: {item}")
                     elif os.path.isdir(item_path):
                         try:
                             if not os.listdir(item_path):
                                 os.rmdir(item_path)
                                 logger.info(f"Cleaned up empty directory on error: {item}")
                         except OSError:
                              pass
                 except Exception as cleanup_e:
                      logger.warning(f"Failed to clean up item {item} on error: {cleanup_e}")

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
    elif ext in ['.jpg', '.jpeg']:
         media_type = 'image/jpeg'
    elif ext == '.png':
         media_type = 'image/png'


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
        # Optionally clean up empty directories during cleanup
        elif os.path.isdir(file_path):
             try:
                 if not os.listdir(file_path):
                     os.rmdir(file_path)
                     logger.info(f"Cleaned up empty directory: {filename}")
             except OSError:
                  # Ignore if directory is not empty or cannot be removed
                  pass


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