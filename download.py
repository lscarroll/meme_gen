import requests
import xml.etree.ElementTree as ET
import re
import os
from urllib.parse import urlparse
from tqdm import tqdm
import time
import subprocess
import random
from datetime import datetime
import logging
import json
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# List of subreddits to download from
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

# Configuration settings
MAX_CLIP_DURATION = 20  # Maximum duration for clips in seconds
MAX_VIDEOS_PER_SUBREDDIT = 100  # Maximum videos to download from each subreddit
USE_PROXY = False  # Set to True if you want to use a proxy
PROXY = None  # Example: "http://user:pass@host:port"
MAX_DOWNLOAD_RETRIES = 3  # Maximum number of retries for downloading videos
SKIP_EXISTING = True  # Skip downloading if file already exists

# Set DEBUG_MODE to True to print more diagnostic information
DEBUG_MODE = True

def download_file(url, directory="downloads", filename=None):
    """Download a file from a URL and save it to the specified directory."""
    # Create the directory if it doesn't exist
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    if not filename:
        # Extract the filename from the URL or use the last part of the path
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # If no filename was extracted, generate one based on the timestamp
        if not filename:
            filename = f"file_{int(time.time())}"
    
    filepath = os.path.join(directory, filename)
    
    # Make request with stream=True to download in chunks
    response = requests.get(url, stream=True)
    
    # Raise an error for bad responses
    response.raise_for_status()
    
    # Get total file size if available
    total_size = int(response.headers.get('content-length', 0))
    
    # Use tqdm for a progress bar during download
    with open(filepath, 'wb') as f, tqdm(
            desc=filename,
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                size = f.write(chunk)
                bar.update(size)
    
    return filepath

@retry(
    retry=retry_if_exception_type((subprocess.CalledProcessError, requests.exceptions.HTTPError)),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: print(f"Download failed, retrying in {retry_state.next_action.sleep} seconds...")
)
def download_reddit_video(post_url, title, subreddit, directory="reddit_videos", video_type=None):
    """Download Reddit video using yt-dlp for proper audio/video merging."""
    try:
        # Determine the output directory based on video type
        if video_type == "meme":
            directory = "meme_videos"
        elif video_type == "animal":
            directory = "animal_videos"
        
        # Create output filename based on title and subreddit (sanitize it)
        safe_title = re.sub(r'[^\w\-_. ]', '_', title)
        safe_subreddit = re.sub(r'[^\w\-_. ]', '_', subreddit)
        # Ensure filename isn't too long (filesystem limits)
        max_length = 50
        if len(safe_title) > max_length:
            safe_title = safe_title[:max_length]
        output_path = os.path.join(directory, f"{safe_subreddit}_{safe_title}.mp4")
        
        # Create directory if it doesn't exist
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        # Check if yt-dlp is installed
        try:
            # Add a small delay to avoid rate limiting
            time.sleep(random.uniform(1, 3))
            
            # Use yt-dlp to download the video with audio
            print(f"Downloading with yt-dlp: {title} from r/{subreddit}")
            cmd = [
                "yt-dlp",
                "--no-warnings",
                "-f", "bestvideo+bestaudio/best",  # Added fallback to 'best' if separate streams not available
                "--merge-output-format", "mp4",
                "--socket-timeout", "30",
                "--retries", "3",
                "--retry-sleep", "5",
                "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "-o", output_path,
                post_url
            ]
            
            # Run the command and capture output
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"Successfully downloaded: {output_path}")
            return output_path
            
        except FileNotFoundError:
            print("yt-dlp not found. Please install it with: pip install yt-dlp")
            print("Falling back to basic download method (no audio)...")
            return None
        except subprocess.CalledProcessError as e:
            # Check if error indicates no video found (normal for text posts)
            if "does not contain video" in str(e.stderr) or "No video formats found" in str(e.stderr):
                print(f"No video content found in post (this is normal for text posts): {title}")
                return None
            # Check for too many requests error
            elif "Too Many Requests" in str(e.stderr) or "HTTP Error 429" in str(e.stderr):
                print(f"Rate limited (HTTP 429): Too many requests for {title}")
                print("Pausing for 60 seconds before retrying...")
                time.sleep(60)  # Extra long pause for rate limiting
                raise  # Raise to trigger retry mechanism
            else:
                print(f"Error running yt-dlp: {e}")
                if hasattr(e, 'output'):
                    print(f"Output: {e.output}")
                if hasattr(e, 'stderr'):
                    print(f"Error: {e.stderr}")
                # This will trigger a retry if we're within the retry limits
                raise
        
    except Exception as e:
        print(f"Error in download_reddit_video: {e}")
        # If this is a rate limit error that wasn't caught above
        if "Too Many Requests" in str(e) or "HTTP Error 429" in str(e):
            print("Rate limited: Too many requests detected in error")
            print("Pausing for 60 seconds before continuing...")
            time.sleep(60)
        return None

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

@retry(
    retry=retry_if_exception_type(requests.exceptions.HTTPError),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: print(f"Rate limited, retrying in {retry_state.next_action.sleep} seconds...")
)
def fetch_rss_content(subreddit, limit=100):
    """Fetch RSS content from the given subreddit with retry logic."""
    url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
    print(f"Fetching RSS feed from: {url}")
    headers = {
        'User-Agent': 'Python/RedditCompilationScript 1.0 (by RandomUser)',
        'Accept': 'application/xml',
        'Accept-Encoding': 'gzip, deflate, br',
    }
    
    # Add a random delay between 2-5 seconds to avoid hitting rate limits
    delay = random.uniform(1,2)
    print(f"Waiting {delay:.2f} seconds before making request to avoid rate limits...")
    time.sleep(delay)
    
    response = requests.get(url, headers=headers)
    
    # Check for rate limiting
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 60))
        print(f"Rate limited! HTTP 429 - Too Many Requests. Waiting for {retry_after} seconds before retrying...")
        time.sleep(retry_after + 5)  # Add a little extra time to be safe
        print("Retrying request after rate limit pause...")
        response = requests.get(url, headers=headers)
    
    response.raise_for_status()
    return response.text

def parse_rss_and_download_videos(rss_content, subreddit, video_type=None):
    """Parse RSS content and download all videos with rate limit handling."""
    # Parse the XML
    root = ET.fromstring(rss_content)
    
    # Find all entry elements (posts)
    # Using namespace prefix for Atom
    namespace = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
    entries = root.findall('.//atom:entry', namespace)
    
    print(f"Found {len(entries)} entries in the RSS feed for r/{subreddit}.")
    
    downloaded_count = 0
    downloaded_videos = []
    
    # Process all entries to download all videos
    for i, entry in enumerate(entries):
        # Get the title
        title_elem = entry.find('atom:title', namespace)
        title = title_elem.text if title_elem is not None else f"Unknown_Title_{i}"
        
        # Get the link element for the post URL
        link_elem = entry.find('atom:link', namespace)
        if link_elem is not None and 'href' in link_elem.attrib:
            post_url = link_elem.attrib['href']
            
            print(f"Processing: {title}")
            print(f"Post URL: {post_url}")
            
            # Since all Reddit posts can potentially have videos, we'll just try to 
            # download all of them instead of filtering by content
            
            # Skip stickied/announcement posts that often aren't videos
            if title.lower().startswith(("join the", "reform", "moderator", "accepting")):
                print(f"Skipping likely announcement post: {title}")
                continue
                
            # Try to download the video to the appropriate directory
            video_path = download_reddit_video(post_url, title, subreddit, video_type=video_type)
            
            if video_path and os.path.exists(video_path):
                # Calculate duration of the video
                try:
                    duration = get_video_duration(video_path)
                    if duration > 0:
                        downloaded_count += 1
                        downloaded_videos.append((video_path, duration, subreddit))
                        print(f"Successfully added video: {title} ({duration:.2f}s)")
                        
                        # If we've downloaded enough videos from this subreddit, stop
                        # This helps prevent rate limiting and saves time
                        if downloaded_count >= MAX_VIDEOS_PER_SUBREDDIT:
                            print(f"Downloaded {downloaded_count} videos from r/{subreddit}, stopping early to avoid rate limits")
                            break
                    else:
                        print(f"Video has zero duration, skipping: {title}")
                        if os.path.exists(video_path):
                            os.remove(video_path)
                except Exception as e:
                    print(f"Error calculating video duration: {e}")
                    if os.path.exists(video_path):
                        os.remove(video_path)
            else:
                print(f"Failed to download video or non-video post: {title}")
    
    print(f"Downloaded {downloaded_count} videos from r/{subreddit}")
    return downloaded_videos

def save_rss_to_file(rss_content, subreddit, filename=None):
    """Save RSS content to a file."""
    if filename is None:
        filename = f"reddit_{subreddit}_rss.xml"
        
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(rss_content)
    print(f"Saved RSS content to {filename}")

def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO if not DEBUG_MODE else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("reddit_download.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("RedditDownload")

def save_video_metadata(meme_videos, animal_videos):
    """Save downloaded video metadata to JSON files for later use by compilation generator."""
    # Create metadata directory if it doesn't exist
    if not os.path.exists("metadata"):
        os.makedirs("metadata")
        
    # Save meme videos metadata
    meme_data = [{"path": v[0], "duration": v[1], "subreddit": v[2]} for v in meme_videos]
    with open("metadata/meme_videos.json", "w") as f:
        json.dump(meme_data, f, indent=2)
        
    # Save animal videos metadata
    animal_data = [{"path": v[0], "duration": v[1], "subreddit": v[2]} for v in animal_videos]
    with open("metadata/animal_videos.json", "w") as f:
        json.dump(animal_data, f, indent=2)
        
    print(f"Saved metadata for {len(meme_videos)} meme videos and {len(animal_videos)} animal videos")

def main():
    # Set up logging
    logger = setup_logging()
    logger.info("Starting Reddit video downloader with rate limit handling")
    
    try:
        all_meme_videos = []
        all_animal_videos = []
        
        # Add a startup delay to ensure any rate limiting resets
        time.sleep(random.uniform(2, 5))
        
        # Create data directory if it doesn't exist
        if not os.path.exists("reddit_data"):
            os.makedirs("reddit_data")
        
        # Process each meme subreddit
        for subreddit in MEME_SUBREDDITS:
            try:
                # Fetch the RSS content with retry logic
                logger.info(f"Processing meme subreddit r/{subreddit}")
                
                # Check if we have a cached version of the RSS content
                rss_cache_file = f"reddit_data/{subreddit}_rss.xml"
                if os.path.exists(rss_cache_file) and SKIP_EXISTING:
                    try:
                        with open(rss_cache_file, 'r', encoding='utf-8') as f:
                            logger.info(f"Using cached RSS content for r/{subreddit}")
                            rss_content = f.read()
                    except Exception as e:
                        logger.warning(f"Could not read cached RSS content: {e}, fetching fresh data")
                        rss_content = fetch_rss_content(subreddit, 100)
                else:
                    rss_content = fetch_rss_content(subreddit, 100)
                
                # Save RSS content to a file for reference
                save_rss_to_file(rss_content, subreddit, f"reddit_data/{subreddit}_rss.xml")
                
                # Parse and download all videos from the feed
                downloaded_videos = parse_rss_and_download_videos(rss_content, subreddit)
                
                # Filter videos by duration (only keep videos under MAX_CLIP_DURATION)
                filtered_videos = [v for v in downloaded_videos if v[1] <= MAX_CLIP_DURATION]
                if len(filtered_videos) < len(downloaded_videos):
                    logger.info(f"Filtered out {len(downloaded_videos) - len(filtered_videos)} videos over {MAX_CLIP_DURATION} seconds")
                    # Remove files for filtered videos
                    for video_path, duration, _ in downloaded_videos:
                        if duration > MAX_CLIP_DURATION and os.path.exists(video_path):
                            try:
                                os.remove(video_path)
                                logger.info(f"Removed video over {MAX_CLIP_DURATION}s: {os.path.basename(video_path)}")
                            except Exception as e:
                                logger.error(f"Error removing {os.path.basename(video_path)}: {e}")
                
                # Add to our meme videos list
                all_meme_videos.extend(filtered_videos)
                
                logger.info(f"Completed processing meme subreddit r/{subreddit}. Kept {len(filtered_videos)} videos under {MAX_CLIP_DURATION}s.")
                
                # Add a delay between processing each subreddit to avoid rate limiting
                if subreddit != MEME_SUBREDDITS[-1]:  # Skip delay after the last subreddit
                    delay = random.uniform(5, 10)
                    logger.info(f"Waiting {delay:.2f} seconds before processing next subreddit...")
                    time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error processing subreddit r/{subreddit}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Process each animal subreddit
        for subreddit in ANIMAL_SUBREDDITS:
            try:
                # Fetch the RSS content with retry logic
                logger.info(f"Processing animal subreddit r/{subreddit}")
                
                # Check if we have a cached version of the RSS content
                rss_cache_file = f"reddit_data/{subreddit}_rss.xml"
                if os.path.exists(rss_cache_file) and SKIP_EXISTING:
                    try:
                        with open(rss_cache_file, 'r', encoding='utf-8') as f:
                            logger.info(f"Using cached RSS content for r/{subreddit}")
                            rss_content = f.read()
                    except Exception as e:
                        logger.warning(f"Could not read cached RSS content: {e}, fetching fresh data")
                        rss_content = fetch_rss_content(subreddit, 100)
                else:
                    rss_content = fetch_rss_content(subreddit, 100)
                
                # Save RSS content to a file for reference
                save_rss_to_file(rss_content, subreddit, f"reddit_data/{subreddit}_rss.xml")
                
                # Parse and download all videos from the feed
                downloaded_videos = parse_rss_and_download_videos(rss_content, subreddit)
                
                # Filter videos by duration (only keep videos under MAX_CLIP_DURATION)
                filtered_videos = [v for v in downloaded_videos if v[1] <= MAX_CLIP_DURATION]
                if len(filtered_videos) < len(downloaded_videos):
                    logger.info(f"Filtered out {len(downloaded_videos) - len(filtered_videos)} videos over {MAX_CLIP_DURATION} seconds")
                    # Remove files for filtered videos
                    for video_path, duration, _ in downloaded_videos:
                        if duration > MAX_CLIP_DURATION and os.path.exists(video_path):
                            try:
                                os.remove(video_path)
                                logger.info(f"Removed video over {MAX_CLIP_DURATION}s: {os.path.basename(video_path)}")
                            except Exception as e:
                                logger.error(f"Error removing {os.path.basename(video_path)}: {e}")
                
                # Add to our animal videos list
                all_animal_videos.extend(filtered_videos)
                
                logger.info(f"Completed processing animal subreddit r/{subreddit}. Kept {len(filtered_videos)} videos under {MAX_CLIP_DURATION}s.")
                
                # Add a delay between processing each subreddit to avoid rate limiting
                if subreddit != ANIMAL_SUBREDDITS[-1]:  # Skip delay after the last subreddit
                    delay = random.uniform(5, 10)
                    logger.info(f"Waiting {delay:.2f} seconds before processing next subreddit...")
                    time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error processing subreddit r/{subreddit}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info(f"Total meme videos downloaded and filtered: {len(all_meme_videos)}")
        logger.info(f"Total animal videos downloaded and filtered: {len(all_animal_videos)}")
        
        # Save metadata for compilation generator to use
        save_video_metadata(all_meme_videos, all_animal_videos)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()