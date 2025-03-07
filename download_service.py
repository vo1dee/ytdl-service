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
import re

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
    title: str = None
    description: str = None
    hashtags: list = None
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

def extract_hashtags(text):
    if not text:
        return []
    # Extract hashtags using regex
    hashtags = re.findall(r'#\w+', text)
    return hashtags

@app.post("/download")
async def download_video(
    request: DownloadRequest,
    api_key: str = Depends(get_api_key)
):
    try:
        logger.info(f"Starting download for URL: {request.url}")
        
        # Use advanced options for extracting metadata
        info_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,  # We just want metadata first
            'writeinfojson': False,
            'writethumbnail': False,
            'nocheckcertificate': True,
            # Force fetching comments to get more metadata
            'getcomments': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_skip': ['js', 'configs'],
                }
            }
        }
        
        # First, get the info without downloading to extract the actual title and metadata
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            logger.info("Extracting detailed video info...")
            info_dict = ydl.extract_info(request.url, download=False)
            
            # Get the actual title from the video
            video_title = info_dict.get('title', 'Unknown')
            video_id = info_dict.get('id', 'Unknown')
            video_description = info_dict.get('description', '')
            
            # Extract hashtags from description
            hashtags = extract_hashtags(video_description)
            
            # Fix for Shorts: if title is generic "Video" or empty, try to extract from description
            if video_title in ['Video', '', 'Unknown'] and video_description:
                # Try to get first line of description as title
                first_line = video_description.strip().split('\n')[0]
                if first_line and not first_line.startswith('#'):
                    video_title = first_line.strip()
                    logger.info(f"Using first line of description as title: {video_title}")
                # If no suitable first line, use ID with "YouTube Short" prefix
                else:
                    video_title = f"YouTube Short - {video_id}"
            
            logger.info(f"Video title: {video_title}, ID: {video_id}")
            logger.info(f"Found {len(hashtags)} hashtags")
        
        # Custom sanitization function to avoid overly restricted filenames
        def sanitize_filename(s):
            # Replace problematic characters with underscores
            s = re.sub(r'[\\/*?:"<>|]', '_', s)
            # Limit length to avoid issues
            return s[:100]
        
        # Create a sanitized title for filename
        safe_title = sanitize_filename(video_title)
        output_filename = f"{safe_title}-{video_id}"
        
        # Use persistent directory with our custom filename
        output_template = os.path.join(DOWNLOADS_DIR, f"{output_filename}.%(ext)s")
        
        ydl_opts = {
            'format': request.format,
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'restrictfilenames': False,  # We'll handle our own sanitization
            'writeinfojson': False,
            'writethumbnail': False
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Downloading video...")
            ydl.download([request.url])
            
            # Find the downloaded file
            possible_extensions = ['.mp4', '.webm', '.mkv', '.mp3', '.m4a', '.wav']
            downloaded_file = None
            
            for ext in possible_extensions:
                test_path = f"{output_template.replace('%(ext)s', ext.lstrip('.'))}"
                if os.path.exists(test_path):
                    downloaded_file = test_path
                    break
            
            if not downloaded_file:
                # Final fallback - look for any file with the ID in the name
                for filename in os.listdir(DOWNLOADS_DIR):
                    if video_id in filename:
                        downloaded_file = os.path.join(DOWNLOADS_DIR, filename)
                        break
                
                if not downloaded_file:
                    raise Exception(f"File not found after download. Tried basename: {output_filename}")
                
            logger.info(f"Successfully downloaded: {downloaded_file}")
            
            # Return the filename and actual video metadata
            return DownloadResponse(
                success=True,
                file_path=os.path.basename(downloaded_file),
                title=video_title,
                description=video_description,
                hashtags=hashtags
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
    
    # Determine media type based on file extension
    extension = os.path.splitext(filename)[1].lower()
    media_type = 'video/mp4'  # Default
    
    # Map common extensions to media types
    if extension in ['.mp3', '.m4a', '.wav']:
        media_type = 'audio/mpeg'
    elif extension in ['.webm']:
        media_type = 'video/webm'
    elif extension in ['.mkv']:
        media_type = 'video/x-matroska'
    
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename
    )

@app.delete("/files/{filename}")
async def delete_file(
    filename: str,
    api_key: str = Depends(get_api_key)
):
    try:
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        os.remove(file_path)
        logger.info(f"Successfully deleted file: {filename}")
        
        return {
            "success": True,
            "message": f"File {filename} deleted successfully"
        }
    except Exception as e:
        logger.error(f"Failed to delete file {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
