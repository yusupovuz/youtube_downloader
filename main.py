# main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os

# Import the class from your downloader.py file
from downloader import VideoDownloader 

app = FastAPI()

# Initialize the downloader
downloader = VideoDownloader(cache_dir="./api_downloads", max_cache_size=5)

class DownloadRequest(BaseModel):
    url: str
    ext: str = "mp4"
    quality: str = "best"

@app.post("/api/download")
def start_download(req: DownloadRequest):
    result = downloader.trigger_download(req.url, req.ext, req.quality)
    return result

@app.get("/api/progress/{video_id}")
def check_progress(video_id: str):
    return downloader.get_progress(video_id)

@app.get("/api/file/{video_id}")
def get_video_file(video_id: str):
    filepath = downloader.get_file_path(video_id)
    
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found or still downloading")
        
    return FileResponse(
        path=filepath, 
        media_type='application/octet-stream', 
        filename=os.path.basename(filepath)
    )