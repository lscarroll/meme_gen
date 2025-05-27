# Meme Video Compilation Generator

A Python tool that automatically downloads Reddit videos and creates compilation videos from popular meme and animal subreddits.

## What it does

- **Downloads videos** from Reddit subreddits (memes and funny animals)
- **Tracks duration** while downloading to hit your target compilation length
- **Creates compilations** by splicing clips together without re-encoding
- **Preserves original quality** and audio without modifications

## Features

- Duration-based downloading (stops when target duration is reached)
- Filters videos by maximum clip length (currently 27 seconds)
- Creates separate meme and animal compilations
- Automatically archives used videos
- Preserves original video quality with simple concatenation

## Subreddits

**Meme Videos:**
- r/MemeVideos
- r/perfectlycutscreams  
- r/AbruptChaos
- r/funnyvideos

**Animal Videos:**
- r/wunkus
- r/FunnyAnimals
- r/AnimalsBeingDerps
- r/animalsdoingstuff

## Requirements

- Python 3.x
- FFmpeg (for video processing)
- yt-dlp (for downloading Reddit videos)

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage
```bash
# Download ~60 seconds of content and create compilations
./run_all.py --duration 60

# Download ~5 minutes of content
./run_all.py --duration 300

# Download ~2 minutes of content  
./run_all.py --duration 120
```

### Options
```bash
# Only download videos (don't create compilations)
./run_all.py --download-only --duration 60

# Only create compilations from already downloaded videos
./run_all.py --compile-only --duration 60

# Set maximum individual clip duration (default: 27 seconds)
./run_all.py --duration 60 --max-clip 30

# Choose aspect ratio handling method
./run_all.py --duration 60 --pad-method letterbox  # black bars
./run_all.py --duration 60 --pad-method blur      # blurred background
```

## How it works

1. **Download Phase**: Fetches videos from Reddit subreddits randomly until target duration is reached
2. **Compilation Phase**: Concatenates videos into compilation files using FFmpeg
3. **Archive Phase**: Moves used videos to archive folder

## Output

- **Compilations**: Saved to `meme_comps/` and `animal_comps/` directories
- **Used videos**: Moved to `archived_videos/` folder
- **Logs**: Detailed logging to track the process

## Configuration

Edit `config.py` to customize:
- Target compilation duration
- Maximum clip duration
- Subreddit lists
- Directory paths

## Note

This tool is for educational/personal use. Respect Reddit's terms of service and content creators' rights.