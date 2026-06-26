import yt_dlp
import threading
import time
import os
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor # YANGA QO'SHILDI: Limitni boshqarish uchun

class VideoDownloader:
    def __init__(self, cache_dir="./downloads", max_cache_size=5, max_concurrent_downloads=20):
        self.cache_dir = cache_dir
        self.max_cache_size = max_cache_size
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.cache = {}
        
        self.progress = {}
        self.lock = threading.Lock()
        
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_downloads)

    def _extract_video_id(self, url):
        """Extracts a unique ID for caching. Avoids full download."""
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('id', urlparse(url).netloc + urlparse(url).path)

    def trigger_download(self, url, ext="mp4", quality="best"):
        """Accepts URL, extension, and quality. Starts or queues the download."""
        try:
            vid_id = self._extract_video_id(url)
        except Exception as e:
            return {"status": "error", "message": f"Failed to extract info: {str(e)}"}

        with self.lock:
            
            if vid_id in self.cache and os.path.exists(self.cache[vid_id]['filepath']):
                self.cache[vid_id]['last_accessed'] = time.time()
                return {"status": "cached", "video_id": vid_id}

            if vid_id in self.progress and self.progress[vid_id]['status'] in ['downloading', 'queued']:
                return {"status": self.progress[vid_id]['status'], "video_id": vid_id}

            self.progress[vid_id] = {"status": "queued", "progress": 0.0, "error": None}

        self.executor.submit(self._download_worker, url, vid_id, ext, quality)

        return {"status": "queued", "video_id": vid_id}

    def _download_worker(self, url, vid_id, ext, quality):
        """The actual background worker for downloading."""
    
        with self.lock:
            if vid_id in self.progress:
                self.progress[vid_id]['status'] = 'downloading'

        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total and d.get('downloaded_bytes'):
                    percent = (d['downloaded_bytes'] / total) * 100
                    with self.lock:
                        self.progress[vid_id]['progress'] = round(percent, 2)
                        
        ydl_opts = {
            'format': f'{quality}[ext={ext}]/best',
            'outtmpl': os.path.join(self.cache_dir, f'{vid_id}.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
            'sleep_interval': 1,
            'max_sleep_interval': 3,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)

            with self.lock:
                self.progress[vid_id]['status'] = 'completed'
                self.progress[vid_id]['progress'] = 100.0
                self.cache[vid_id] = {
                    "filepath": filepath,
                    "last_accessed": time.time()
                }
            
            self._cleanup_cache()

        except Exception as e:
            with self.lock:
                self.progress[vid_id] = {"status": "error", "progress": 0.0, "error": str(e)}

    def get_progress(self, video_id):
        with self.lock:
            return self.progress.get(video_id, {"status": "not_found"})

    def get_file_path(self, video_id):
        with self.lock:
            if video_id in self.cache and os.path.exists(self.cache[video_id]['filepath']):
                self.cache[video_id]['last_accessed'] = time.time()
                return self.cache[video_id]['filepath']
        return None

    def _cleanup_cache(self):
        with self.lock:
            if len(self.cache) <= self.max_cache_size:
                return

            sorted_cache = sorted(self.cache.items(), key=lambda item: item[1]['last_accessed'])
            items_to_remove = len(self.cache) - self.max_cache_size
            
            for i in range(items_to_remove):
                vid_id, data = sorted_cache[i]
                
                try:
                    if os.path.exists(data['filepath']):
                        os.remove(data['filepath'])
                except Exception as e:
                    print(f"Error deleting file {data['filepath']}: {e}")
                
                del self.cache[vid_id]
                if vid_id in self.progress:
                    del self.progress[vid_id]