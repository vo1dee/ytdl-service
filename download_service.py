from fastapi import FastAPI, HTTPException, Request, Depends, Security, Response
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
from fastapi.responses import FileResponse

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
        
        # Use persistent directory and sanitize filename
        output_template = os.path.join(DOWNLOADS_DIR, '%(title).100s-%(id)s.%(ext)s')
        
        ydl_opts = {
            'format': request.format,
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'restrictfilenames': True  # This will ensure safe filenames
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Extracting video info...")
            info = ydl.extract_info(request.url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            if not os.path.exists(downloaded_file):
                raise Exception(f"File not found after download: {downloaded_file}")
                
            logger.info(f"Successfully downloaded: {downloaded_file}")
            # Return just the filename instead of full path
            return DownloadResponse(
                success=True,
                file_path=os.path.basename(downloaded_file)
            )
                
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
    
    return FileResponse(
        file_path,
        media_type='video/mp4',
        filename=filename
    )

@app.get("/health")
async def health_check(api_key: str = Depends(get_api_key)):
    try:
        # Check if downloads directory is writable
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)