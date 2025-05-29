#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
from upload import main as upload_main

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("/app/data/uploader_monitor.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("UploaderMonitor")

class VideoUploadHandler(FileSystemEventHandler):
    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self.upload_lock = threading.Lock()
        self.last_upload_time = 0
        self.upload_delay = 30  # Wait 30 seconds after file creation before uploading
        
    def on_created(self, event):
        """Handle file creation events"""
        if not event.is_dir and event.src_path.lower().endswith(('.mp4', '.mov', '.avi')):
            self.logger.info(f"New compilation video detected: {event.src_path}")
            # Add a delay to ensure file is completely written
            threading.Timer(self.upload_delay, self._process_upload).start()
    
    def on_moved(self, event):
        """Handle file move events (when files are moved into the directory)"""
        if not event.is_dir and event.dest_path.lower().endswith(('.mp4', '.mov', '.avi')):
            self.logger.info(f"Compilation video moved to directory: {event.dest_path}")
            # Add a delay to ensure file is completely written
            threading.Timer(self.upload_delay, self._process_upload).start()
    
    def _process_upload(self):
        """Process upload with lock to prevent concurrent uploads"""
        with self.upload_lock:
            current_time = time.time()
            # Prevent too frequent uploads (at least 60 seconds between uploads)
            if current_time - self.last_upload_time >= 60:
                self.logger.info("Starting upload process for detected videos...")
                try:
                    upload_main()
                    self.last_upload_time = current_time
                    self.logger.info("Upload process completed")
                except Exception as e:
                    self.logger.error(f"Error during upload process: {e}")
            else:
                self.logger.info("Upload skipped - too soon since last upload")

def check_existing_videos(logger):
    """Check for existing videos and upload them on startup"""
    meme_comps_dir = "/app/videos/meme_comps"
    animal_comps_dir = "/app/videos/animal_comps"
    
    existing_videos = []
    
    # Check meme compilations
    if os.path.exists(meme_comps_dir):
        meme_files = [f for f in os.listdir(meme_comps_dir) 
                      if f.lower().endswith(('.mp4', '.mov', '.avi'))]
        existing_videos.extend([os.path.join(meme_comps_dir, f) for f in meme_files])
    
    # Check animal compilations
    if os.path.exists(animal_comps_dir):
        animal_files = [f for f in os.listdir(animal_comps_dir) 
                       if f.lower().endswith(('.mp4', '.mov', '.avi'))]
        existing_videos.extend([os.path.join(animal_comps_dir, f) for f in animal_files])
    
    if existing_videos:
        logger.info(f"Found {len(existing_videos)} existing compilation videos on startup")
        logger.info("Starting initial upload process...")
        try:
            upload_main()
            logger.info("Initial upload process completed")
        except Exception as e:
            logger.error(f"Error during initial upload process: {e}")
    else:
        logger.info("No existing compilation videos found on startup")

def main():
    logger = setup_logging()
    logger.info("Starting YouTube Uploader Monitor")
    
    # Check for existing videos and upload them
    check_existing_videos(logger)
    
    # Set up file system monitoring
    meme_comps_dir = "/app/videos/meme_comps"
    animal_comps_dir = "/app/videos/animal_comps"
    
    # Create directories if they don't exist
    os.makedirs(meme_comps_dir, exist_ok=True)
    os.makedirs(animal_comps_dir, exist_ok=True)
    
    # Create event handler and observer
    event_handler = VideoUploadHandler(logger)
    observer = Observer()
    
    # Watch both compilation directories
    observer.schedule(event_handler, meme_comps_dir, recursive=False)
    observer.schedule(event_handler, animal_comps_dir, recursive=False)
    
    try:
        observer.start()
        logger.info(f"Monitoring directories:")
        logger.info(f"  - {meme_comps_dir}")
        logger.info(f"  - {animal_comps_dir}")
        logger.info("Upload monitor is running. Press Ctrl+C to stop.")
        
        # Keep the script running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Monitor error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        observer.stop()
        observer.join()
        logger.info("Upload monitor shutdown complete")

if __name__ == "__main__":
    main()