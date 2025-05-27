#!/usr/bin/env python3

# Configuration settings
class Config:
    # Subreddits configuration
    MEME_SUBREDDITS = [
        "MemeVideos",
        "perfectlycutscreams",
        "AbruptChaos",
        "funnyvideos"
    ]

    ANIMAL_SUBREDDITS = [
        "wunkus",
        "FunnyAnimals",
        "AnimalsBeingDerps",
        "animalsdoingstuff"
    ]
    
    # Processing settings
    MAX_CLIP_DURATION = 27  # Maximum duration for clips in seconds
    MAX_VIDEOS_PER_SUBREDDIT = 100  # Maximum videos to download from each subreddit
    SKIP_EXISTING = True  # Skip downloading if file already exists
    DEBUG_MODE = True

    # Default compilation settings
    DEFAULT_TARGET_DURATION = 11 * 60  # 11 minutes (660 seconds)
    DEFAULT_PAD_METHOD = "letterbox"  # Options: "letterbox" or "blur"

    # Directories
    DATA_DIR = "reddit_data"
    MEME_VIDEOS_DIR = "meme_videos"
    ANIMAL_VIDEOS_DIR = "animal_videos"
    MEME_COMPS_DIR = "meme_comps"
    ANIMAL_COMPS_DIR = "animal_comps"
    ARCHIVED_VIDEOS_DIR = "archived_videos"
    METADATA_DIR = "metadata"
    THUMBNAILS_DIR = "thumbnails"
    TEMP_DIR = "temp_pitch_processed"
