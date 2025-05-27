#!/usr/bin/env python3
import os
import logging
import time
import random
import subprocess
import json
import shutil
from config import Config

class Utils:
    @staticmethod
    def setup_logging(log_file="meme_generator.log"):
        """Set up logging configuration."""
        logging.basicConfig(
            level=logging.INFO if not Config.DEBUG_MODE else logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger("MemeGenerator")

    @staticmethod
    def ensure_directories():
        """Create all necessary directories if they don't exist."""
        directories = [
            Config.DATA_DIR, 
            Config.MEME_VIDEOS_DIR, 
            Config.ANIMAL_VIDEOS_DIR, 
            Config.MEME_COMPS_DIR, 
            Config.ANIMAL_COMPS_DIR, 
            Config.ARCHIVED_VIDEOS_DIR,
            Config.METADATA_DIR,
            Config.THUMBNAILS_DIR,
            Config.TEMP_DIR
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"Created directory: {directory}")

    @staticmethod
    def get_video_duration(video_path):
        """Get the duration of a video file in seconds using FFmpeg."""
        try:
            cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            return duration
        except Exception as e:
            print(f"Error getting video duration: {e}")
            return 0

    @staticmethod
    def save_video_metadata(meme_videos, animal_videos):
        """Save downloaded video metadata to JSON files for later use by compilation generator."""
        # Create metadata directory if it doesn't exist
        if not os.path.exists(Config.METADATA_DIR):
            os.makedirs(Config.METADATA_DIR)
            
        # Save meme videos metadata
        meme_data = [{"path": v[0], "duration": v[1], "subreddit": v[2]} for v in meme_videos]
        with open(f"{Config.METADATA_DIR}/meme_videos.json", "w") as f:
            json.dump(meme_data, f, indent=2)
            
        # Save animal videos metadata
        animal_data = [{"path": v[0], "duration": v[1], "subreddit": v[2]} for v in animal_videos]
        with open(f"{Config.METADATA_DIR}/animal_videos.json", "w") as f:
            json.dump(animal_data, f, indent=2)
            
        print(f"Saved metadata for {len(meme_videos)} meme videos and {len(animal_videos)} animal videos")

    @staticmethod
    def load_video_metadata():
        """Load metadata for videos downloaded by download phase"""
        meme_videos = []
        animal_videos = []
        
        try:
            # Load meme videos metadata
            meme_metadata_path = f"{Config.METADATA_DIR}/meme_videos.json"
            if os.path.exists(meme_metadata_path):
                with open(meme_metadata_path, "r") as f:
                    meme_data = json.load(f)
                    for video in meme_data:
                        meme_videos.append((video["path"], video["duration"], video["subreddit"]))
            
            # Load animal videos metadata
            animal_metadata_path = f"{Config.METADATA_DIR}/animal_videos.json"
            if os.path.exists(animal_metadata_path):
                with open(animal_metadata_path, "r") as f:
                    animal_data = json.load(f)
                    for video in animal_data:
                        animal_videos.append((video["path"], video["duration"], video["subreddit"]))
                        
            print(f"Loaded metadata for {len(meme_videos)} meme videos and {len(animal_videos)} animal videos")
            return meme_videos, animal_videos
            
        except Exception as e:
            print(f"Error loading video metadata: {e}")
            return [], []

    @staticmethod
    def generate_thumbnail(video_path, output_path):
        """Generate a thumbnail from the video using ffmpeg"""
        try:
            # Create thumbnails directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Try to get a frame from 30 seconds into the video
            cmd = [
                "ffmpeg", 
                "-i", video_path, 
                "-ss", "00:00:30",  # 30 seconds in
                "-vframes", "1", 
                "-vf", "scale=1280:720", 
                "-y",  # Overwrite output file
                output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"Generated thumbnail: {output_path}")
            return output_path
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            return None

    @staticmethod
    def move_to_archive(used_videos, logger):
        """Move used videos to the archived_videos folder"""
        archive_count = 0
        
        for video_path in used_videos:
            try:
                # Check if the file exists
                if os.path.exists(video_path):
                    # Get the filename without path
                    filename = os.path.basename(video_path)
                    # Create the destination path in archived_videos folder
                    dest_path = os.path.join(Config.ARCHIVED_VIDEOS_DIR, filename)
                    
                    # Move the file
                    shutil.move(video_path, dest_path)
                    logger.info(f"Moved used video to archive: {filename}")
                    archive_count += 1
            except Exception as e:
                logger.error(f"Error moving video to archive: {e}")
        
        logger.info(f"Archived {archive_count} used videos in total")
        return archive_count