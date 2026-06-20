import yt_dlp
import threading
import time
import os
from urllib.parse import urlparse

class VideoDownloader:
    def __init__(self, cache_dir="./downloads", max_cache_size=5):
        self.cache_dir = cache_dir
        self.max_cache_size = max_cache_size
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Cache structure: { video_id: {"filepath": str, "last_accessed": float} }
        self.cache = {}
        
        # Progress structure: { video_id: {"status": str, "progress": float, "error": str} }
        self.progress = {}
        
        # Lock for thread-safe operations on cache and progress dictionaries
        self.lock = threading.Lock()

    def _extract_video_id(self, url):
        """Extracts a unique ID for caching. Avoids full download."""
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('id', urlparse(url).netloc + urlparse(url).path)

    def trigger_download(self, url, ext="mp4", quality="best"):
        """
        Req 1, 10: Accepts URL, extension, and quality.
        Starts the download in a background thread if not already cached.
        """
        try:
            vid_id = self._extract_video_id(url)
        except Exception as e:
            return {"status": "error", "message": f"Failed to extract info: {str(e)}"}

        with self.lock:
            # Req 4: If cached and file exists on disk, update access time and return
            if vid_id in self.cache and os.path.exists(self.cache[vid_id]['filepath']):
                self.cache[vid_id]['last_accessed'] = time.time()
                return {"status": "cached", "video_id": vid_id}

            # Check if currently downloading
            if vid_id in self.progress and self.progress[vid_id]['status'] == 'downloading':
                return {"status": "downloading", "video_id": vid_id}

            # Initialize progress state
            self.progress[vid_id] = {"status": "downloading", "progress": 0.0, "error": None}

        # Req 7: Download happens in a separate thread
        thread = threading.Thread(target=self._download_worker, args=(url, vid_id, ext, quality))
        thread.daemon = True
        thread.start()

        return {"status": "started", "video_id": vid_id}

    def _download_worker(self, url, vid_id, ext, quality):
        """The actual background worker for downloading."""
        def progress_hook(d):
            # Req 6: Support retrieving download progress
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total and d.get('downloaded_bytes'):
                    percent = (d['downloaded_bytes'] / total) * 100
                    with self.lock:
                        self.progress[vid_id]['progress'] = round(percent, 2)
                        
        # Req 9: YouTube Anti-bot measures via yt_dlp options
        ydl_opts = {
            'format': f'{quality}[ext={ext}]/best',
            'outtmpl': os.path.join(self.cache_dir, f'{vid_id}.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
            'sleep_interval': 1,
            'max_sleep_interval': 3,
            # 'cookiesfrombrowser': ('chrome',), # UNCOMMENT to use local browser cookies (highly effective)
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)

            # Req 2: Downloads the file and saves state
            with self.lock:
                self.progress[vid_id]['status'] = 'completed'
                self.progress[vid_id]['progress'] = 100.0
                self.cache[vid_id] = {
                    "filepath": filepath,
                    "last_accessed": time.time()
                }
            
            # Run cleanup after a successful download
            self._cleanup_cache()

        except Exception as e:
            # Req 8: Exception handling
            with self.lock:
                self.progress[vid_id] = {"status": "error", "progress": 0.0, "error": str(e)}

    def get_progress(self, video_id):
        """Returns the current progress dictionary for a given video ID."""
        with self.lock:
            return self.progress.get(video_id, {"status": "not_found"})

    def get_file_path(self, video_id):
        """Req 3: Returns the file path for the API to serve."""
        with self.lock:
            if video_id in self.cache and os.path.exists(self.cache[video_id]['filepath']):
                # Update access time for LRU cache
                self.cache[video_id]['last_accessed'] = time.time()
                return self.cache[video_id]['filepath']
        return None

    def _cleanup_cache(self):
        """Req 5: Time-based cache eviction (LRU). Removes the least-used items."""
        with self.lock:
            if len(self.cache) <= self.max_cache_size:
                return

            # Sort dictionary by last_accessed timestamp (ascending)
            sorted_cache = sorted(self.cache.items(), key=lambda item: item[1]['last_accessed'])
            
            items_to_remove = len(self.cache) - self.max_cache_size
            
            for i in range(items_to_remove):
                vid_id, data = sorted_cache[i]
                
                # Delete the physical file
                try:
                    if os.path.exists(data['filepath']):
                        os.remove(data['filepath'])
                except Exception as e:
                    print(f"Error deleting file {data['filepath']}: {e}")
                
                # Remove from tracking dictionaries
                del self.cache[vid_id]
                if vid_id in self.progress:
                    del self.progress[vid_id]