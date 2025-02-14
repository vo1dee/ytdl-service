# /opt/ytdl_service/download_service.py
from fastapi import FastAPI, HTTPException, Request, Depends, Security
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
import secrets
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import tempfile
import os
import logging
from datetime import datetime

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
    with open(API_KEY_FILE, "w") as f:
        f.write(secrets.token_urlsafe(32))

with open(API_KEY_FILE) as f:
    API_KEY = f.read().strip()

api_key_header = APIKeyHeader(name="X-API-Key")

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != API_KEY:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Could not validate API key"
        )
    return api_key_header

# Only allow requests from Oracle server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this to Oracle server IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    format: str = 'best'

class DownloadResponse(BaseModel):
    success: bool
    file_path: str
    error: str = None

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    response = await call_next(request)
    duration = datetime.now() - start_time
    logger.info(
        f"Method: {request.method} Path: {request.url.path} "
        f"Duration: {duration.total_seconds():.2f}s "
        f"Status: {response.status_code}"
    )
    return response

@app.post("/download")
async def download_video(
    request: DownloadRequest,
    api_key: str = Depends(get_api_key)
):
    try:
        logger.info(f"Starting download for URL: {request.url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
            
            ydl_opts = {
                'format': request.format,
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                
                logger.info(f"Successfully downloaded: {downloaded_file}")
                return DownloadResponse(
                    success=True,
                    file_path=downloaded_file
                )
                
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
