from fastapi import FastAPI, HTTPException, Request, Depends, Security
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
import secrets
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os
import logging
from datetime import datetime
from fastapi.responses import FileResponse
import mimetypes

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/ytdl_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ytdl_service')

app = FastAPI()

# Generate a random API key if not exists
API_KEY_FILE = "/opt/ytdl_service/api_key.txt"
if not os.path.exists(API_KEY_FILE):
    logger.warning("API Key file missing, generating a new one.")
    with open(API_KEY_FILE, "w") as f:
        f.write(secrets.token_urlsafe(32))

with open(API_KEY_FILE) as f:
    API_KEY = f.read().strip()

api_key_header = APIKeyHeader(name="X-API-Key")

# Create downloads directory
DOWNLOADS_DIR = "/opt/ytdl_service/downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != API_KEY:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Could not validate API key"
        )
    return api_key_header

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    format: str = 'best'

@app.middleware("http")
async def log_requests_and_errors(request: Request, call_next):
    """Middleware for logging requests and handling errors."""
    start_time = datetime.now()
    try:
        response = await call_next(request)
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"Method: {request.method} Path: {request.url.path} "
            f"Duration: {duration:.2f}s Status: {response.status_code}"
        )
        return response
    except Exception as e:
        logger.error(f"Request failed: {request.url.path} - Error: {str(e)}")
        raise

@app.post("/download")
async def download_video(
    request: DownloadRequest,
    api_key: str = Depends(get_api_key)
):
    try:
        logger.info(f"Starting download for URL: {request.url}")

        output_template = os.path.join(DOWNLOADS_DIR, '%(title).100s-%(id)s.%(ext)s')

        ydl_opts = {
            'format': request.format,
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'restrictfilenames': True,
            'prefer_ffmpeg': True,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Extracting video info...")
            info = ydl.extract_info(request.url, download=True)
            downloaded_file = ydl.prepare_filename(info)

            # Adjust file extension if FFmpeg conversion changed it
            if not os.path.exists(downloaded_file):
                mp4_file = os.path.splitext(downloaded_file)[0] + '.mp4'
                if os.path.exists(mp4_file):
                    downloaded_file = mp4_file
                else:
                    raise Exception(f"File not found after download: {downloaded_file}")

            logger.info(f"Successfully downloaded: {downloaded_file}")

            return {
                "success": True,
                "file_path": os.path.basename(downloaded_file),
                "title": info.get('title', 'Video'),
                "description": info.get('description', ''),
                "hashtags": info.get('tags', []),
                "duration": info.get('duration', 0)
            }

    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/{filename}")
async def get_file(
    filename: str,
    api_key: str = Depends(get_api_key)
):
    file_path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(file_path, media_type=media_type or "application/octet-stream", filename=filename)

@app.delete("/files/{filename}")
async def delete_file(
    filename: str,
    api_key: str = Depends(get_api_key)
):
    file_path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    os.remove(file_path)
    logger.info(f"Successfully deleted file: {filename}")
    
    return {"success": True, "message": f"File {filename} deleted successfully"}

@app.get("/version")
async def check_version(api_key: str = Depends(get_api_key)):
    try:
        return {
            "yt-dlp_version": yt_dlp.version.__version__,
            "ffmpeg_installed": os.system("which ffmpeg > /dev/null") == 0
        }
    except Exception as e:
        logger.error(f"Version check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check(api_key: str = Depends(get_api_key)):
    try:
        test_file = os.path.join(DOWNLOADS_DIR, "test.txt")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "downloads_dir": DOWNLOADS_DIR,
            "api_key_configured": bool(API_KEY)
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
