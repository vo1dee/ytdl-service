from fastapi import FastAPI, HTTPException
  from pydantic import BaseModel
  import yt_dlp
  import os
  import logging
  import shutil
  from fastapi.responses import FileResponse
  import uuid
  import subprocess

  # Simple logging
  logging.basicConfig(level=logging.INFO)
  logger = logging.getLogger("ytdl_simple")

  # Simple config
  DOWNLOADS_DIR = "/opt/ytdl_service/downloads"
  os.makedirs(DOWNLOADS_DIR, exist_ok=True)

  app = FastAPI()

  class DownloadRequest(BaseModel):
      url: str
      format: str = 'best'

  @app.get("/health")
  async def health_check():
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
  async def download_video(request: DownloadRequest):
      try:
          logger.info(f"Starting download for URL: {request.url}")

          # Generate unique ID for filename
          download_id = str(uuid.uuid4())[:8]
          output_template = os.path.join(DOWNLOADS_DIR, f'{download_id}-%(title)s.%(ext)s')

          # Setup yt-dlp options
          ydl_opts = {
              'format': request.format,
              'outtmpl': output_template,
              'quiet': True,
              'no_warnings': True,
              'restrictfilenames': True,
              'prefer_ffmpeg': True
          }

          # Special options for YouTube clips
          if 'youtube.com/clip' in request.url.lower():
              logger.info("YouTube clip detected - adding special options")
              ydl_opts.update({
                  'force_generic_extractor': True,
                  'no_playlist': True,
                  'geo_bypass': True
              })

          # Download the video
          with yt_dlp.YoutubeDL(ydl_opts) as ydl:
              logger.info("Extracting video info...")
              info = ydl.extract_info(request.url, download=True)
              downloaded_file = ydl.prepare_filename(info)

              # Check if file exists (account for format changes)
              if not os.path.exists(downloaded_file):
                  base, _ = os.path.splitext(downloaded_file)
                  for ext in ['.mp4', '.webm', '.mkv']:
                      if os.path.exists(base + ext):
                          downloaded_file = base + ext
                          break

              if not os.path.exists(downloaded_file):
                  raise Exception("File not found after download")

              logger.info(f"Download successful: {downloaded_file}")

              return {
                  "success": True,
                  "file_path": os.path.basename(downloaded_file),
                  "title": info.get('title', 'Video'),
                  "url": request.url
              }

      except Exception as e:
          logger.error(f"Download failed: {str(e)}")
          return {
              "success": False,
              "error": str(e)
          }

  @app.get("/files/{filename}")
  async def get_file(filename: str):
      file_path = os.path.join(DOWNLOADS_DIR, filename)
      if not os.path.exists(file_path):
          raise HTTPException(status_code=404, detail="File not found")

      return FileResponse(
          file_path,
          media_type='video/mp4',
          filename=filename
      )

  if __name__ == "__main__":
      import uvicorn
      uvicorn.run(app, host="0.0.0.0", port=8000)
