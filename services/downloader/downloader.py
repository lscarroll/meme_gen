#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import time
import random
import subprocess
import re
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from tqdm import tqdm
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import json
from kafka import KafkaProducer
from kafka.errors import KafkaError
from config import Config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import Utils

class Downloader:
    def __init__(self, logger):
        self.logger = logger
        self.producer = None
        self.setup_kafka_producer()

    def setup_kafka_producer(self):
        """Setup Kafka producer for sending compilation triggers"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=['kafka:9092'],
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                api_version=(2, 8)
            )
            self.logger.info("Kafka producer connected successfully")
        except Exception as e:
            self.logger.warning(f"Failed to setup Kafka producer: {e}")
            self.producer = None

    def trigger_compilation(self, target_duration):
        """Send compilation task to Kafka"""
        if not self.producer:
            self.logger.warning("Kafka producer not available, skipping compilation trigger")
            return False
            
        try:
            message = {
                'task': 'compile',
                'duration': target_duration,
                'pad_method': 'letterbox',
                'timestamp': time.time()
            }
            
            future = self.producer.send('meme-tasks', value=message)
            result = future.get(timeout=10)
            self.logger.info(f"Compilation task sent: {message}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send compilation task: {e}")
            return False

    def download_file(self, url, directory="downloads", filename=None):
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
    def download_reddit_video(self, post_url, title, subreddit, video_type=None):
        """Download Reddit video using yt-dlp for proper audio/video merging."""
        try:
            # Determine the output directory based on video type
            if video_type == "meme":
                directory = Config.MEME_VIDEOS_DIR
            elif video_type == "animal":
                directory = Config.ANIMAL_VIDEOS_DIR
            else:
                directory = "reddit_videos"
            
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

    @retry(
        retry=retry_if_exception_type(requests.exceptions.HTTPError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda retry_state: print(f"Rate limited, retrying in {retry_state.next_action.sleep} seconds...")
    )
    def fetch_rss_content(self, subreddit, limit=100):
        """Fetch RSS content from the given subreddit with retry logic."""
        url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
        print(f"Fetching RSS feed from: {url}")
        headers = {
            'User-Agent': 'Python/RedditCompilationScript 1.0 (by RandomUser)',
            'Accept': 'application/xml',
            'Accept-Encoding': 'gzip, deflate, br',
        }
        
        # Add a random delay between 1-2 seconds to avoid hitting rate limits
        delay = random.uniform(1, 2)
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

    def save_rss_to_file(self, rss_content, subreddit, filename=None):
        """Save RSS content to a file."""
        if filename is None:
            filename = f"reddit_{subreddit}_rss.xml"
            
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(rss_content)
        print(f"Saved RSS content to {filename}")

    def parse_rss_and_download_videos(self, rss_content, subreddit, video_type=None):
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
                video_path = self.download_reddit_video(post_url, title, subreddit, video_type=video_type)
                
                if video_path and os.path.exists(video_path):
                    # Calculate duration of the video
                    try:
                        duration = Utils.get_video_duration(video_path)
                        if duration > 0:
                            downloaded_count += 1
                            downloaded_videos.append((video_path, duration, subreddit))
                            print(f"Successfully added video: {title} ({duration:.2f}s)")
                            
                            # If we've downloaded enough videos from this subreddit, stop
                            # This helps prevent rate limiting and saves time
                            if downloaded_count >= Config.MAX_VIDEOS_PER_SUBREDDIT:
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

    def download_videos(self, max_clip_duration=None, target_duration=None):
        """
        Download videos from Reddit continuously, triggering compilations when target duration is reached
        
        Args:
            max_clip_duration: Maximum duration for individual clips in seconds
            target_duration: Target total duration for each compilation batch
        """
        if max_clip_duration is None:
            max_clip_duration = Config.MAX_CLIP_DURATION
            
        if target_duration is None:
            target_duration = Config.DEFAULT_TARGET_DURATION
            
        self.logger.info("Starting Reddit video downloader with rate limit handling")
        self.logger.info(f"Target total duration: {target_duration}s, Max clip duration: {max_clip_duration}s")
        
        try:
            all_meme_videos = []
            all_animal_videos = []
            
            # Tracking total duration
            total_meme_duration = 0
            total_animal_duration = 0
            
            # Add a startup delay to ensure any rate limiting resets
            time.sleep(random.uniform(2, 5))
            
            # Create data directory if it doesn't exist
            if not os.path.exists(Config.DATA_DIR):
                os.makedirs(Config.DATA_DIR)
            
            # First, cache the RSS content for all subreddits to have them ready
            meme_subreddit_data = {}
            animal_subreddit_data = {}
            
            # Fetch RSS for meme subreddits
            for subreddit in Config.MEME_SUBREDDITS:
                try:
                    rss_cache_file = f"{Config.DATA_DIR}/{subreddit}_rss.xml"
                    if os.path.exists(rss_cache_file) and Config.SKIP_EXISTING:
                        try:
                            with open(rss_cache_file, 'r', encoding='utf-8') as f:
                                self.logger.info(f"Using cached RSS content for r/{subreddit}")
                                rss_content = f.read()
                        except Exception as e:
                            self.logger.warning(f"Could not read cached RSS content: {e}, fetching fresh data")
                            rss_content = self.fetch_rss_content(subreddit, 100)
                    else:
                        rss_content = self.fetch_rss_content(subreddit, 100)
                    
                    # Save RSS content to a file for reference
                    self.save_rss_to_file(rss_content, subreddit, f"{Config.DATA_DIR}/{subreddit}_rss.xml")
                    meme_subreddit_data[subreddit] = rss_content
                    
                    # Add a small delay between fetches to avoid rate limiting
                    time.sleep(random.uniform(1, 3))
                    
                except Exception as e:
                    self.logger.error(f"Error fetching RSS for r/{subreddit}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
            
            # Fetch RSS for animal subreddits
            for subreddit in Config.ANIMAL_SUBREDDITS:
                try:
                    rss_cache_file = f"{Config.DATA_DIR}/{subreddit}_rss.xml"
                    if os.path.exists(rss_cache_file) and Config.SKIP_EXISTING:
                        try:
                            with open(rss_cache_file, 'r', encoding='utf-8') as f:
                                self.logger.info(f"Using cached RSS content for r/{subreddit}")
                                rss_content = f.read()
                        except Exception as e:
                            self.logger.warning(f"Could not read cached RSS content: {e}, fetching fresh data")
                            rss_content = self.fetch_rss_content(subreddit, 100)
                    else:
                        rss_content = self.fetch_rss_content(subreddit, 100)
                    
                    # Save RSS content to a file for reference
                    self.save_rss_to_file(rss_content, subreddit, f"{Config.DATA_DIR}/{subreddit}_rss.xml")
                    animal_subreddit_data[subreddit] = rss_content
                    
                    # Add a small delay between fetches to avoid rate limiting
                    time.sleep(random.uniform(1, 3))
                    
                except Exception as e:
                    self.logger.error(f"Error fetching RSS for r/{subreddit}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
            
            # Create a list of (subreddit, entry index) pairs to process for meme videos
            meme_subreddits_with_entries = []
            animal_subreddits_with_entries = []
            
            # Build the list of possible entries for meme subreddits
            for subreddit, rss_content in meme_subreddit_data.items():
                try:
                    # Parse the XML to get entries
                    root = ET.fromstring(rss_content)
                    namespace = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
                    entries = root.findall('.//atom:entry', namespace)
                    
                    for i in range(len(entries)):
                        meme_subreddits_with_entries.append((subreddit, i))
                except Exception as e:
                    self.logger.error(f"Error parsing RSS content for r/{subreddit}: {e}")
            
            # Build the list of possible entries for animal subreddits
            for subreddit, rss_content in animal_subreddit_data.items():
                try:
                    # Parse the XML to get entries
                    root = ET.fromstring(rss_content)
                    namespace = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
                    entries = root.findall('.//atom:entry', namespace)
                    
                    for i in range(len(entries)):
                        animal_subreddits_with_entries.append((subreddit, i))
                except Exception as e:
                    self.logger.error(f"Error parsing RSS content for r/{subreddit}: {e}")
            
            # Shuffle the lists to randomize the order
            random.shuffle(meme_subreddits_with_entries)
            random.shuffle(animal_subreddits_with_entries)
            
            # Download meme videos one at a time from random subreddits
            self.logger.info(f"Starting to download meme videos from random subreddits")
            failed_attempts = 0
            max_failed_attempts = 10  # Stop after 10 consecutive videos that don't fit
            
            for subreddit, entry_index in meme_subreddits_with_entries:
                # Check if we've reached the target duration - trigger compilation and reset
                if total_meme_duration >= target_duration:
                    self.logger.info(f"Reached target meme duration ({total_meme_duration:.2f}s). Triggering compilation and continuing downloads.")
                    
                    # Save current metadata
                    Utils.save_video_metadata(all_meme_videos, all_animal_videos)
                    
                    # Trigger compilation
                    self.trigger_compilation(target_duration)
                    
                    # Reset counters for next batch (but keep any leftover animal videos)
                    all_meme_videos = []
                    total_meme_duration = 0
                    failed_attempts = 0
                
                # Skip if we've had too many failed attempts to find videos that fit (but continue processing)
                if failed_attempts >= max_failed_attempts:
                    self.logger.info(f"Too many consecutive videos don't fit. Skipping ahead in meme downloads.")
                    failed_attempts = 0  # Reset to try again
                    continue
                
                try:
                    # Get the specific entry
                    rss_content = meme_subreddit_data[subreddit]
                    root = ET.fromstring(rss_content)
                    namespace = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
                    entries = root.findall('.//atom:entry', namespace)
                    
                    if entry_index >= len(entries):
                        continue
                    
                    entry = entries[entry_index]
                    
                    # Get the title
                    title_elem = entry.find('atom:title', namespace)
                    title = title_elem.text if title_elem is not None else f"Unknown_Title_{entry_index}"
                    
                    # Skip stickied/announcement posts that often aren't videos
                    if title.lower().startswith(("join the", "reform", "moderator", "accepting")):
                        self.logger.info(f"Skipping likely announcement post: {title}")
                        continue
                    
                    # Get the link element for the post URL
                    link_elem = entry.find('atom:link', namespace)
                    if link_elem is not None and 'href' in link_elem.attrib:
                        post_url = link_elem.attrib['href']
                        
                        self.logger.info(f"Processing: {title} from r/{subreddit}")
                        self.logger.info(f"Post URL: {post_url}")
                        
                        # Try to download the video
                        video_path = self.download_reddit_video(post_url, title, subreddit, video_type="meme")
                        
                        if video_path and os.path.exists(video_path):
                            # Calculate duration of the video
                            duration = Utils.get_video_duration(video_path)
                            
                            # Check if the video is too long
                            if duration > max_clip_duration:
                                self.logger.info(f"Video too long ({duration:.2f}s > {max_clip_duration}s), removing: {title}")
                                if os.path.exists(video_path):
                                    os.remove(video_path)
                                continue
                            
                            # Check if adding this video would exceed the target duration
                            if total_meme_duration + duration > target_duration:
                                self.logger.info(f"Adding this video would exceed target duration. Triggering compilation first.")
                                
                                # Save current metadata and trigger compilation
                                Utils.save_video_metadata(all_meme_videos, all_animal_videos)
                                self.trigger_compilation(target_duration)
                                
                                # Reset for next batch and add this video to the new batch
                                all_meme_videos = []
                                total_meme_duration = 0
                                failed_attempts = 0
                            
                            # Add this video to our collection
                            all_meme_videos.append((video_path, duration, subreddit))
                            total_meme_duration += duration
                            failed_attempts = 0  # Reset failed attempts counter
                            
                            self.logger.info(f"Added video: {title} ({duration:.2f}s) from r/{subreddit}")
                            self.logger.info(f"Current total meme duration: {total_meme_duration:.2f}s / {target_duration}s")
                            
                            # Small delay to avoid rate limiting
                            time.sleep(random.uniform(0.5, 1))
                except Exception as e:
                    self.logger.error(f"Error processing entry from r/{subreddit}: {e}")
            
            # Download animal videos one at a time from random subreddits
            self.logger.info(f"Starting to download animal videos from random subreddits")
            failed_attempts = 0
            max_failed_attempts = 10  # Stop after 10 consecutive videos that don't fit
            
            for subreddit, entry_index in animal_subreddits_with_entries:
                # Check if we've reached the target duration - trigger compilation and reset
                if total_animal_duration >= target_duration:
                    self.logger.info(f"Reached target animal duration ({total_animal_duration:.2f}s). Triggering compilation and continuing downloads.")
                    
                    # Save current metadata
                    Utils.save_video_metadata(all_meme_videos, all_animal_videos)
                    
                    # Trigger compilation
                    self.trigger_compilation(target_duration)
                    
                    # Reset counters for next batch (but keep any leftover meme videos)
                    all_animal_videos = []
                    total_animal_duration = 0
                    failed_attempts = 0
                
                # Skip if we've had too many failed attempts to find videos that fit (but continue processing)
                if failed_attempts >= max_failed_attempts:
                    self.logger.info(f"Too many consecutive videos don't fit. Skipping ahead in animal downloads.")
                    failed_attempts = 0  # Reset to try again
                    continue
                
                try:
                    # Get the specific entry
                    rss_content = animal_subreddit_data[subreddit]
                    root = ET.fromstring(rss_content)
                    namespace = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
                    entries = root.findall('.//atom:entry', namespace)
                    
                    if entry_index >= len(entries):
                        continue
                    
                    entry = entries[entry_index]
                    
                    # Get the title
                    title_elem = entry.find('atom:title', namespace)
                    title = title_elem.text if title_elem is not None else f"Unknown_Title_{entry_index}"
                    
                    # Skip stickied/announcement posts that often aren't videos
                    if title.lower().startswith(("join the", "reform", "moderator", "accepting")):
                        self.logger.info(f"Skipping likely announcement post: {title}")
                        continue
                    
                    # Get the link element for the post URL
                    link_elem = entry.find('atom:link', namespace)
                    if link_elem is not None and 'href' in link_elem.attrib:
                        post_url = link_elem.attrib['href']
                        
                        self.logger.info(f"Processing: {title} from r/{subreddit}")
                        self.logger.info(f"Post URL: {post_url}")
                        
                        # Try to download the video
                        video_path = self.download_reddit_video(post_url, title, subreddit, video_type="animal")
                        
                        if video_path and os.path.exists(video_path):
                            # Calculate duration of the video
                            duration = Utils.get_video_duration(video_path)
                            
                            # Check if the video is too long
                            if duration > max_clip_duration:
                                self.logger.info(f"Video too long ({duration:.2f}s > {max_clip_duration}s), removing: {title}")
                                if os.path.exists(video_path):
                                    os.remove(video_path)
                                continue
                            
                            # Check if adding this video would exceed the target duration
                            if total_animal_duration + duration > target_duration:
                                self.logger.info(f"Adding this video would exceed target duration. Triggering compilation first.")
                                
                                # Save current metadata and trigger compilation
                                Utils.save_video_metadata(all_meme_videos, all_animal_videos)
                                self.trigger_compilation(target_duration)
                                
                                # Reset for next batch and add this video to the new batch
                                all_animal_videos = []
                                total_animal_duration = 0
                                failed_attempts = 0
                            
                            # Add this video to our collection
                            all_animal_videos.append((video_path, duration, subreddit))
                            total_animal_duration += duration
                            failed_attempts = 0  # Reset failed attempts counter
                            
                            self.logger.info(f"Added video: {title} ({duration:.2f}s) from r/{subreddit}")
                            self.logger.info(f"Current total animal duration: {total_animal_duration:.2f}s / {target_duration}s")
                            
                            # Small delay to avoid rate limiting
                            time.sleep(random.uniform(0.5, 1))
                except Exception as e:
                    self.logger.error(f"Error processing entry from r/{subreddit}: {e}")
            
            self.logger.info(f"Finished processing all RSS entries.")
            self.logger.info(f"Remaining meme videos: {len(all_meme_videos)} with duration {total_meme_duration:.2f}s")
            self.logger.info(f"Remaining animal videos: {len(all_animal_videos)} with duration {total_animal_duration:.2f}s")
            
            # Save metadata for any remaining videos
            if all_meme_videos or all_animal_videos:
                Utils.save_video_metadata(all_meme_videos, all_animal_videos)
                
                # If we have sufficient content for a final compilation, trigger it
                min_duration = target_duration * 0.3  # 30% of target duration minimum
                if (total_meme_duration >= min_duration or total_animal_duration >= min_duration):
                    self.logger.info(f"Triggering final compilation for remaining videos")
                    self.trigger_compilation(target_duration)
                else:
                    self.logger.info(f"Not enough content for final compilation (need {min_duration:.1f}s minimum)")
            
            # Clean up Kafka producer
            if self.producer:
                self.producer.close()
            
            return all_meme_videos, all_animal_videos
            
        except Exception as e:
            self.logger.error(f"Unexpected error in download_videos: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return [], []