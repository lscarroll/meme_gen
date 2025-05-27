import requests
import xml.etree.ElementTree as ET
import re
import os
from urllib.parse import urlparse
from tqdm import tqdm
import time
import subprocess
import random
import shutil
from datetime import datetime
import math
import logging
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
TARGET_DURATION = 14 * 60 + 20  # 14 minutes and 20 seconds (860 seconds)
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
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    before_sleep=lambda retry_state: print(f"Download failed, retrying in {retry_state.next_action.sleep} seconds...")
)
def download_reddit_video(post_url, title, subreddit, directory="reddit_videos"):
    """Download Reddit video using yt-dlp for proper audio/video merging."""
    try:
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
        print(f"Rate limited! Waiting for {retry_after} seconds before retrying...")
        time.sleep(retry_after)
        response = requests.get(url, headers=headers)
    
    response.raise_for_status()
    return response.text

def parse_rss_and_download_videos(rss_content, subreddit):
    """Parse RSS content and download all videos."""
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
                
            # Add a small delay between downloads
            #time.sleep(random.uniform(1, 3))
            
            # Try to download the video
            video_path = download_reddit_video(post_url, title, subreddit)
            
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

def create_compilation(video_files_with_meta, target_length=TARGET_DURATION, output_file="compilation.mp4"):
    """
    Create a compilation video that's exactly the target length.
    
    Args:
        video_files_with_meta: List of tuples (video_path, duration, subreddit)
        target_length: Target length in seconds
        output_file: Output file path
    
    Returns:
        Path to the created compilation or False on failure
    """
    if not video_files_with_meta:
        print("No videos to compile!")
        return False, []
        
    try:
        # Check if FFmpeg is installed
        try:
            subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
        except FileNotFoundError:
            print("FFmpeg not found. Please install FFmpeg to create compilations.")
            return False, []
        
        # Verify all video files exist first
        video_files_with_meta = [(path, duration, sub) for path, duration, sub in video_files_with_meta if os.path.exists(path)]
        
        if not video_files_with_meta:
            print("None of the video files exist!")
            return False, []
            
        print(f"Starting with {len(video_files_with_meta)} valid videos")
        
        # Select videos that will fit into our target length
        selected_videos = []
        selected_videos_info = []  # To store full info for each selected video
        current_duration = 0
        
        for video_path, duration, subreddit in video_files_with_meta:
            if current_duration + duration <= target_length:
                selected_videos.append(video_path)
                selected_videos_info.append((video_path, duration, subreddit))
                current_duration += duration
                print(f"Added: {os.path.basename(video_path)} - Duration: {duration:.2f}s - r/{subreddit}")
            else:
                # If we're almost at target length, we might want to add one more video
                # if the difference is small enough
                remaining = target_length - current_duration
                if remaining < 5:  # If we're within 5 seconds, consider it close enough
                    break
                    
                # Calculate how much of the video we'd need to trim to fit exactly
                trim_point = remaining - 0.5  # Leave a tiny buffer
                
                if trim_point > 3:  # Only trim if we can get at least 3 seconds
                    print(f"Trimming final video to fit exactly: {os.path.basename(video_path)}")
                    
                    # Create a temporary trimmed version
                    temp_output = f"temp_trimmed_{int(time.time())}.mp4"
                    trim_cmd = [
                        "ffmpeg",
                        "-i", video_path,
                        "-t", str(trim_point),
                        "-c", "copy",
                        temp_output
                    ]
                    
                    try:
                        # Run the trimming command
                        subprocess.run(trim_cmd, check=True, capture_output=True)
                        selected_videos.append(temp_output)
                        selected_videos_info.append((temp_output, trim_point, subreddit))
                        current_duration += trim_point
                        print(f"Added trimmed video: Duration: {trim_point:.2f}s (from original {duration:.2f}s)")
                        break
                    except Exception as e:
                        print(f"Error trimming video: {e}")
                        if os.path.exists(temp_output):
                            os.remove(temp_output)
        
        if not selected_videos:
            print("No videos were selected for the compilation!")
            return False, []
            
        print(f"Selected {len(selected_videos)} videos with total duration of {current_duration:.2f}s")
        print(f"Target duration: {target_length}s ({target_length/60:.2f} minutes)")
        
        # If we don't have enough videos to get close to our target, report
        if current_duration < (target_length - 10):
            print(f"Warning: Could only get to {current_duration:.2f}s, which is {target_length - current_duration:.2f}s short of target")
        
        # Process each video to maintain original aspect ratio
        processed_videos = []
        temp_dir = f"temp_processed_{int(time.time())}"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        for i, (video_path, duration, subreddit) in enumerate(selected_videos_info):
            # Get video dimensions
            try:
                cmd = [
                    "ffprobe", 
                    "-v", "error", 
                    "-select_streams", "v:0", 
                    "-show_entries", "stream=width,height", 
                    "-of", "csv=s=x:p=0", 
                    video_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                dimensions = result.stdout.strip()
                print(f"Video dimensions: {dimensions}")
                
                # Create processed video with padding if needed to maintain aspect ratio
                temp_output = os.path.join(temp_dir, f"processed_{i}.mp4")
                process_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_path,
                    "-vf", "scale=iw*min(1920/iw,1080/ih):ih*min(1920/iw,1080/ih),pad=1920:1080:(1920-iw*min(1920/iw,1080/ih))/2:(1080-ih*min(1920/iw,1080/ih))/2:black",
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    temp_output
                ]
                
                print(f"Processing video to maintain aspect ratio: {os.path.basename(video_path)}")
                subprocess.run(process_cmd, check=True, capture_output=True)
                processed_videos.append(temp_output)
                
            except Exception as e:
                print(f"Error processing video: {e}")
                # If processing fails, use the original video
                processed_videos.append(video_path)
        
        # Create a temporary file list for FFmpeg
        list_file = f"video_list_{int(time.time())}.txt"
        with open(list_file, "w", encoding='utf-8') as f:  # Added UTF-8 encoding
            for video_file in processed_videos:
                # Handle backslashes in Windows paths
                safe_path = video_file.replace('\\', '\\\\')
                f.write(f"file '{safe_path}'\n")
        
        # Run FFmpeg to concatenate the videos
        print(f"Creating compilation of {len(processed_videos)} videos...")
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output file if it exists
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",  # Use copy codec to avoid re-encoding
            output_file
        ]
        
        # Run the command
        subprocess.run(cmd, check=True)
        
        # Clean up the temporary files
        if os.path.exists(list_file):
            os.remove(list_file)
            
        # Clean up temp processed videos
        for video in processed_videos:
            if video.startswith(temp_dir) and os.path.exists(video):
                os.remove(video)
                
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except:
                print(f"Could not remove temp directory: {temp_dir}")
        
        # Verify the output file was created
        if os.path.exists(output_file):
            output_duration = get_video_duration(output_file)
            print(f"Compilation created successfully: {output_file}")
            print(f"Final duration: {output_duration:.2f}s ({output_duration/60:.2f} minutes)")
            # Return the list of used videos and the output file
            return output_file, selected_videos
        else:
            print(f"Error: Compilation file {output_file} was not created")
            return False, []
        
    except subprocess.CalledProcessError as e:
        print(f"Error running FFmpeg: {e}")
        if hasattr(e, 'stderr'):
            print(f"Error details: {e.stderr}")
        return False, []
    except Exception as e:
        print(f"Error creating compilation: {e}")
        import traceback
        traceback.print_exc()
        return False, []

def prepare_for_youtube_upload(compilation_path, comp_number=1, compilation_type="meme"):
    """Prepare the compilation for YouTube upload by copying it to the right directory."""
    # Determine the output directory based on compilation type
    output_dir = "meme_videos"
    
    # Create the directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Generate a unique filename
    today = datetime.now().strftime("%Y-%m-%d")
    dest_filename = f"{compilation_type}_compilation_{today}_{comp_number}.mp4"
    dest_path = os.path.join(output_dir, dest_filename)
    
    # Copy the file
    try:
        shutil.copy2(compilation_path, dest_path)
        print(f"Copied {compilation_type} compilation to: {dest_path}")
        return dest_path
    except Exception as e:
        print(f"Error copying compilation for upload: {e}")
        return None

def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO if not DEBUG_MODE else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("reddit_compilation.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("RedditCompilation")

def main():
    # Set up logging
    logger = setup_logging()
    logger.info("Starting Reddit video compilation generator")
    
    try:
        timestamp = int(time.time())
        all_meme_videos = []
        all_animal_videos = []
        
        # Add a startup delay to ensure any rate limiting resets
        time.sleep(random.uniform(2, 5))
        
        # Create data directory if it doesn't exist
        if not os.path.exists("reddit_data"):
            os.makedirs("reddit_data")
            
        # Create output directories if they don't exist
        if not os.path.exists("meme_comps"):
            os.makedirs("meme_comps")
        if not os.path.exists("animal_comps"):
            os.makedirs("animal_comps")
        
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
        
        # Process meme videos
        if all_meme_videos:
            # Calculate total duration available for meme videos
            total_meme_duration = sum(duration for _, duration, _ in all_meme_videos)
            
            # Calculate how many meme compilations we can make
            potential_meme_comps = math.floor(total_meme_duration / TARGET_DURATION)
            
            logger.info(f"Total meme video duration: {total_meme_duration:.2f}s")
            logger.info(f"Potential number of meme compilations: {potential_meme_comps}")
            
            # Create meme compilations until we run out of videos
            remaining_meme_videos = all_meme_videos.copy()
            meme_comp_number = 1
            
            while remaining_meme_videos and meme_comp_number <= potential_meme_comps:
                logger.info(f"\n=== Creating Meme Compilation #{meme_comp_number} ===")
                
                # Shuffle the videos
                random.shuffle(remaining_meme_videos)
                
                # Create the compilation
                compilation_file = f"meme_compilation_{timestamp}_{meme_comp_number}.mp4"
                created_file, used_videos = create_compilation(
                    remaining_meme_videos,
                    target_length=TARGET_DURATION,
                    output_file=compilation_file
                )
                
                if created_file and used_videos:
                    # Remove used videos from remaining_videos
                    used_video_paths = set(used_videos)
                    remaining_meme_videos = [v for v in remaining_meme_videos if v[0] not in used_video_paths]
                    
                    # Move the file to meme_comps directory
                    today = datetime.now().strftime("%Y-%m-%d")
                    dest_filename = f"meme_compilation_{today}_{meme_comp_number}.mp4"
                    dest_path = os.path.join("meme_comps", dest_filename)
                    
                    try:
                        shutil.copy2(created_file, dest_path)
                        logger.info(f"Copied meme compilation to: {dest_path}")
                        if os.path.exists(created_file):
                            os.remove(created_file)
                    except Exception as e:
                        logger.error(f"Error copying meme compilation: {e}")
                    
                    logger.info("\n=============================================")
                    logger.info(f"Meme Compilation #{meme_comp_number} created!")
                    logger.info(f"File: {dest_path}")
                    logger.info("=============================================\n")
                    
                    meme_comp_number += 1
                else:
                    logger.error(f"Failed to create meme compilation #{meme_comp_number}.")
                    break
            
            logger.info(f"Created {meme_comp_number-1} meme compilations in total.")
        else:
            logger.warning("No meme videos were downloaded. Cannot create meme compilations.")
            
        # Process animal videos
        if all_animal_videos:
            # Calculate total duration available for animal videos
            total_animal_duration = sum(duration for _, duration, _ in all_animal_videos)
            
            # Calculate how many animal compilations we can make
            potential_animal_comps = math.floor(total_animal_duration / TARGET_DURATION)
            
            logger.info(f"Total animal video duration: {total_animal_duration:.2f}s")
            logger.info(f"Potential number of animal compilations: {potential_animal_comps}")
            
            # Create animal compilations until we run out of videos
            remaining_animal_videos = all_animal_videos.copy()
            animal_comp_number = 1
            
            while remaining_animal_videos and animal_comp_number <= potential_animal_comps:
                logger.info(f"\n=== Creating Animal Compilation #{animal_comp_number} ===")
                
                # Shuffle the videos
                random.shuffle(remaining_animal_videos)
                
                # Create the compilation
                compilation_file = f"animal_compilation_{timestamp}_{animal_comp_number}.mp4"
                created_file, used_videos = create_compilation(
                    remaining_animal_videos,
                    target_length=TARGET_DURATION,
                    output_file=compilation_file
                )
                
                if created_file and used_videos:
                    # Remove used videos from remaining_videos
                    used_video_paths = set(used_videos)
                    remaining_animal_videos = [v for v in remaining_animal_videos if v[0] not in used_video_paths]
                    
                    # Move the file to animal_comps directory
                    today = datetime.now().strftime("%Y-%m-%d")
                    dest_filename = f"animal_compilation_{today}_{animal_comp_number}.mp4"
                    dest_path = os.path.join("animal_comps", dest_filename)
                    
                    try:
                        shutil.copy2(created_file, dest_path)
                        logger.info(f"Copied animal compilation to: {dest_path}")
                        if os.path.exists(created_file):
                            os.remove(created_file)
                    except Exception as e:
                        logger.error(f"Error copying animal compilation: {e}")
                    
                    logger.info("\n=============================================")
                    logger.info(f"Animal Compilation #{animal_comp_number} created!")
                    logger.info(f"File: {dest_path}")
                    logger.info("=============================================\n")
                    
                    animal_comp_number += 1
                else:
                    logger.error(f"Failed to create animal compilation #{animal_comp_number}.")
                    break
            
            logger.info(f"Created {animal_comp_number-1} animal compilations in total.")
        else:
            logger.warning("No animal videos were downloaded. Cannot create animal compilations.")
            
        # Clean up leftover videos if any
        leftover_videos = remaining_meme_videos + remaining_animal_videos
        if leftover_videos:
            logger.info(f"Cleaning up {len(leftover_videos)} leftover videos that weren't included in any compilation")
            for video_path, _, _ in leftover_videos:
                try:
                    if os.path.exists(video_path):
                        os.remove(video_path)
                        logger.info(f"Removed: {os.path.basename(video_path)}")
                except Exception as e:
                    logger.error(f"Error removing {os.path.basename(video_path)}: {e}")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()