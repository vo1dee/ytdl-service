#!/usr/bin/env python3
"""
Minimal stub for video_downloader.py
This is a placeholder file to allow Docker builds to succeed when the full
video_downloader.py (which contains Telegram bot functionality) is not available.
"""

import logging

logger = logging.getLogger(__name__)

class VideoDownloader:
    """Minimal stub class for VideoDownloader"""
    
    def __init__(self, *args, **kwargs):
        logger.info("VideoDownloader stub initialized")
        
    async def download_video(self, url: str):
        """Stub method for video downloading"""
        logger.warning("VideoDownloader stub called - full functionality not available")
        return None, None
        
    async def handle_video_link(self, update, context):
        """Stub method for handling video links"""
        logger.warning("VideoDownloader stub called - Telegram bot functionality not available")
        return None

# For backward compatibility
if __name__ == "__main__":
    logger.info("VideoDownloader stub module loaded")