import os
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
import random
import time
import json
from google.auth.transport.requests import Request
import logging
import sys
import shutil
import subprocess

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("youtube_upload.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# Define scopes needed for YouTube uploads
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", 
          "https://www.googleapis.com/auth/youtube"]

def get_authenticated_service():
    """Get authenticated YouTube API service for headless environment"""
    creds = None
    
    # Check if we have stored credentials
    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as token:
                creds_data = json.load(token)
                creds = google.oauth2.credentials.Credentials.from_authorized_user_info(creds_data)
            logging.info("Loaded credentials from token.json")
        except Exception as e:
            logging.error(f"Error loading credentials: {e}")
    
    # If no valid credentials, let's authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Refreshed expired credentials")
            except Exception as e:
                logging.error(f"Error refreshing credentials: {e}")
                creds = None
        
        if not creds:
            try:
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    'client_secrets.json', SCOPES)
                
                # Explicitly set the redirect URI to match what's in client_secrets.json
                flow.redirect_uri = 'http://localhost'
                
                # Generate a URL for the user to visit and authorize
                auth_url, _ = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true',
                    prompt='consent'  # Force to get refresh_token
                )
                
                logging.info("Please go to this URL in a browser to authenticate:")
                print("\n" + "*" * 80)
                print("Please go to this URL in a browser to authenticate:")
                print(auth_url)
                print("*" * 80)
                print("\nAfter authorizing, you'll receive a code. Paste that code here:")
                
                code = input().strip()
                # DON'T pass redirect_uri again here - that's causing the error
                flow.fetch_token(code=code)
                creds = flow.credentials
                
                # Save the credentials for the next run
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
                logging.info("Saved new credentials to token.json")
            
            except Exception as e:
                logging.error(f"Authentication error: {e}")
                raise RuntimeError("Failed to authenticate with YouTube API")
    
    # Return the authenticated service
    try:
        service = googleapiclient.discovery.build('youtube', 'v3', credentials=creds)
        logging.info("Successfully authenticated with YouTube API")
        return service
    except Exception as e:
        logging.error(f"Error building YouTube service: {e}")
        raise RuntimeError("Failed to build YouTube service")

def set_thumbnail(youtube, video_id, thumbnail_path, max_retries=3):
    """Set a custom thumbnail for a video with retry logic"""
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Setting thumbnail for video {video_id} (Attempt {attempt}/{max_retries})...")
            
            media = MediaFileUpload(thumbnail_path, resumable=True)
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=media
            ).execute()
            
            logging.info(f"Thumbnail successfully set for video {video_id}")
            return True
        
        except googleapiclient.errors.HttpError as e:
            error_content = json.loads(e.content.decode())
            error_reason = error_content.get('error', {}).get('errors', [{}])[0].get('reason', 'unknown')
            
            logging.error(f"HTTP error setting thumbnail (attempt {attempt}): {e.resp.status} - {error_reason}")
            
            # Rate limiting or server error - worth retrying
            if e.resp.status in [429, 500, 503] and attempt < max_retries:
                retry_delay = min(2 ** attempt + random.uniform(0, 1), 60)  # Exponential backoff with jitter
                logging.info(f"Retrying in {retry_delay:.2f} seconds...")
                time.sleep(retry_delay)
            else:
                logging.error(f"Failed to set thumbnail after {attempt} attempts: {e}")
                return False
        
        except Exception as e:
            logging.error(f"Unexpected error setting thumbnail: {str(e)}")
            if attempt < max_retries:
                retry_delay = min(2 ** attempt + random.uniform(0, 1), 60)
                logging.info(f"Retrying in {retry_delay:.2f} seconds...")
                time.sleep(retry_delay)
            else:
                return False
    
    return False  # All retries failed

def generate_thumbnail(video_path, output_path):
    """Generate a thumbnail from the video using ffmpeg"""
    try:
        # Create thumbnails directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Try to get a frame from 25% into the video
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
        logging.info(f"Generated thumbnail: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Error generating thumbnail: {e}")
        return None

def process_audio_pitch(input_path, output_path):
    """Process video to pitch up the audio by one semitone"""
    try:
        # Create a temporary directory if it doesn't exist
        temp_dir = "temp_pitch_processed"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        # Temporary file path
        temp_output = os.path.join(temp_dir, f"temp_{int(time.time())}.mp4")
        
        # FFmpeg command to pitch up audio by one semitone without changing tempo
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-filter_complex", "asetrate=44100*2^(1/12),aresample=44100",
            "-c:v", "copy",
            temp_output
        ]
        
        logging.info(f"Processing audio pitch for: {os.path.basename(input_path)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logging.error(f"Error processing audio: {result.stderr}")
            return None
        
        # Move the temp file to the output path
        shutil.move(temp_output, output_path)
        logging.info(f"Successfully processed audio pitch: {os.path.basename(output_path)}")
        return output_path
    
    except Exception as e:
        logging.error(f"Error processing audio pitch: {e}")
        return None
    finally:
        # Clean up temp files
        if os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except:
                pass

def upload_video(youtube, file_path, thumbnail_path=None, max_retries=3, video_type="meme"):
    """Upload a video to YouTube as a regular video with retry logic and set thumbnail"""
    # Generate fun, quirky, lowercase title
    meme_titles = [
        "memes to beegle your boggle",
        "memes to cure your anxiety",
        "memes that make you wanna slap yo momma",
        "memes that will make your brain do a flip",
        "memes that hit different at 3am",
        "memes to enlighten your soul",
        "memes that make no sense but are still funny",
        "memes that broke my last brain cell",
        "memes to watch instead of doing chores",
        "memes that made my cat laugh",
        "memes to watch with your grandma",
        "memes that are better than therapy",
        "memes that should be illegal but aren't",
        "memes to send your boss at 2am",
        "memes that explain my life choices"
    ]
    
    animal_titles = [
        "cute animals that will melt your heart",
        "adorable animal moments to brighten your day",
        "animals being derps for 11 minutes straight",
        "animals that don't know how cute they are",
        "funny animals that think they're humans",
        "animal fails that will make you snort-laugh",
        "when animals don't understand how things work",
        "animals with zero brain cells but maximum cuteness",
        "animals having their main character moment",
        "pets that are too pure for this world",
        "animals being absolute goofballs",
        "animals who are definitely plotting something",
        "animals with better personalities than most humans",
        "when animals.exe stops working",
        "wholesome animal moments to restore your faith in life"
    ]
    
    meme_descriptions = [
        "a carefully curated compilation of the finest memes on the internet. enjoy responsibly.\n\n#memes #funny #compilation",
        "when life gives you lemons, watch these memes instead.\n\n#memecompilation #funny #videomemes",
        "why go to therapy when you can watch memes for free?\n\n#memes #funnyvideos #memecompilation",
        "scientifically proven to increase serotonin levels by at least 76%.\n\n#memes #viral #funnyvideos",
        "hand-picked memes that will make your brain produce the happy chemicals.\n\n#memecompilation #bestmemes #funny"
    ]
    
    animal_descriptions = [
        "a heartwarming compilation of the cutest animal moments. watch at your own risk of cuteness overload.\n\n#animals #cute #pets #compilation",
        "sometimes animals are the purest form of joy in this world. here's proof.\n\n#cuteanimals #funny #animalcompilation",
        "animals being their adorable selves for 11 minutes straight. you're welcome.\n\n#animals #funnyanimals #cute",
        "the internet's finest collection of animal shenanigans and heartwarming moments.\n\n#animals #pets #viral #cutemoments",
        "scientists confirm: watching cute animals increases happiness by 200%.\n\n#animals #cute #compilation #funnyanimals"
    ]
    
    meme_tags = ["memes", "funny", "compilation", "viral", "trending", "comedy", "best memes", "dank memes", "funny videos", "meme compilation"]
    
    animal_tags = ["animals", "cute", "pets", "funny animals", "compilation", "adorable", "wholesome", "animal videos", "cute pets", "funny pets"]
    
    # Choose appropriate content based on video type
    if video_type == "animal":
        titles = animal_titles
        descriptions = animal_descriptions
        tags = animal_tags
    else:  # meme
        titles = meme_titles
        descriptions = meme_descriptions
        tags = meme_tags
    ran = random.choice(titles)
    # Video metadata
    body = {
        "snippet": {
            "title": ran,
            "description": random.choice(descriptions),
            "tags": random.sample(tags, k=min(8, len(tags))),
            "categoryId": "23"  # 23 is for Comedy
        },
        "status": {
            "privacyStatus": "public",  # Can be "private", "public", or "unlisted"
            "selfDeclaredMadeForKids": False,
        }
    }
    titles.remove(ran)
    
    # Create the upload request
    media = MediaFileUpload(file_path, resumable=True, chunksize=1024*1024)
    
    # Execute the upload with retries
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Uploading {os.path.basename(file_path)} (Attempt {attempt}/{max_retries})...")
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )
            
            # The actual upload with progress reporting
            response = None
            previous_progress = 0
            
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress > previous_progress + 5:  # Report every 5% progress
                        logging.info(f"Upload progress: {progress}%")
                        previous_progress = progress
            
            video_id = response['id']
            logging.info(f"Upload complete! Video ID: {video_id}")
            
            # Set thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                thumbnail_success = set_thumbnail(youtube, video_id, thumbnail_path)
                if thumbnail_success:
                    logging.info(f"Thumbnail set successfully for video {video_id}")
                else:
                    logging.warning(f"Failed to set thumbnail for video {video_id}")
            
            return video_id
        
        except googleapiclient.errors.HttpError as e:
            error_content = json.loads(e.content.decode())
            error_reason = error_content.get('error', {}).get('errors', [{}])[0].get('reason', 'unknown')
            
            logging.error(f"HTTP error on attempt {attempt}: {e.resp.status} - {error_reason}")
            
            # Check if this is an OAuth error
            if error_reason in ['authError', 'unauthorized', 'forbidden', 'access_denied']:
                logging.error("OAuth authorization error. Please check your credentials and permissions.")
                # Could trigger a re-auth here if needed
                raise
            
            # Rate limiting or server error - worth retrying
            if e.resp.status in [429, 500, 503] and attempt < max_retries:
                retry_delay = min(2 ** attempt + random.uniform(0, 1), 60)  # Exponential backoff with jitter
                logging.info(f"Retrying in {retry_delay:.2f} seconds...")
                time.sleep(retry_delay)
            else:
                logging.error(f"Failed to upload after {attempt} attempts: {e}")
                return None
        
        except Exception as e:
            logging.error(f"Unexpected error during upload: {str(e)}")
            if attempt < max_retries:
                retry_delay = min(2 ** attempt + random.uniform(0, 1), 60)
                logging.info(f"Retrying in {retry_delay:.2f} seconds...")
                time.sleep(retry_delay)
            else:
                return None
    
    return None  # All retries failed

def main():
    try:
        # Get the YouTube service
        logging.info("Starting YouTube upload process")
        youtube = get_authenticated_service()
        
        # Directories
        meme_comps_dir = "meme_comps"
        animal_comps_dir = "animal_comps"
        archived_videos_dir = "archived_videos"
        thumbnails_dir = "thumbnails"
        temp_dir = "temp_pitch_processed"
        
        # Create necessary directories if they don't exist
        for directory in [archived_videos_dir, thumbnails_dir, temp_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logging.info(f"Created directory: {directory}")
        
        # Check for compilation videos in both directories
        all_videos = []
        
        # Check meme compilations
        if os.path.exists(meme_comps_dir):
            meme_files = [f for f in os.listdir(meme_comps_dir) 
                          if f.lower().endswith(('.mp4', '.mov', '.avi'))]
            for video in meme_files:
                all_videos.append({"path": os.path.join(meme_comps_dir, video), "type": "meme"})
            logging.info(f"Found {len(meme_files)} meme compilation videos")
        else:
            logging.warning(f"Meme compilation directory '{meme_comps_dir}' does not exist")
        
        # Check animal compilations
        if os.path.exists(animal_comps_dir):
            animal_files = [f for f in os.listdir(animal_comps_dir) 
                           if f.lower().endswith(('.mp4', '.mov', '.avi'))]
            for video in animal_files:
                all_videos.append({"path": os.path.join(animal_comps_dir, video), "type": "animal"})
            logging.info(f"Found {len(animal_files)} animal compilation videos")
        else:
            logging.warning(f"Animal compilation directory '{animal_comps_dir}' does not exist")
        
        if not all_videos:
            logging.warning("No compilation videos found in either directory")
            print("No compilation videos found. Please make sure your videos are in the meme_comps or animal_comps directories.")
            return
        
        logging.info(f"Found {len(all_videos)} total compilation videos to upload")
        print(f"Found {len(all_videos)} total compilation videos to upload")
        
        # Upload each video
        uploaded_count = 0
        for video_info in all_videos:
            video_path = video_info["path"]
            video_type = video_info["type"]
            video_file = os.path.basename(video_path)
            
            # Process the audio (pitch up by one semitone)
            logging.info(f"Processing audio for {video_file}...")
            pitched_video_path = os.path.join(temp_dir, f"pitched_{int(time.time())}_{video_file}")
            processed_path = process_audio_pitch(video_path, pitched_video_path)
            
            if not processed_path:
                logging.error(f"Failed to process audio for {video_file}. Skipping upload.")
                continue
            
            # Generate a thumbnail from the video
            thumbnail_path = os.path.join(thumbnails_dir, f"thumb_{os.path.splitext(video_file)[0]}.jpg")
            if not os.path.exists(thumbnail_path):
                thumbnail_path = generate_thumbnail(processed_path, thumbnail_path)
            
            # Upload the processed video with thumbnail
            video_id = upload_video(youtube, processed_path, thumbnail_path, video_type=video_type)
            
            if video_id:
                uploaded_count += 1
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                print(f"Video URL: {video_url}")
                print(f"Uploaded {uploaded_count}/{len(all_videos)}")
                
                # Archive the original video
                archived_video_path = os.path.join(archived_videos_dir, video_file)
                try:
                    shutil.move(video_path, archived_video_path)
                    logging.info(f"Archived video: {video_file}")
                except Exception as e:
                    logging.error(f"Error archiving video {video_file}: {e}")
                
                # Clean up the processed video
                if os.path.exists(processed_path):
                    try:
                        os.remove(processed_path)
                        logging.info(f"Removed processed video: {os.path.basename(processed_path)}")
                    except Exception as e:
                        logging.error(f"Error removing processed video: {e}")
                
                # Add delay between uploads to avoid rate limiting
                if uploaded_count < len(all_videos):
                    delay = random.randint(60, 180)  # 1m to 3m delay
                    print(f"Waiting {delay} seconds before next upload...")
                    time.sleep(delay)
            else:
                print(f"Failed to upload {video_file}")
                # Clean up the processed video on failure
                if os.path.exists(processed_path):
                    try:
                        os.remove(processed_path)
                    except:
                        pass
        
        logging.info(f"Upload process complete. Successfully uploaded {uploaded_count}/{len(all_videos)} videos.")
        print(f"Upload process complete. Successfully uploaded {uploaded_count}/{len(all_videos)} videos.")
        print(f"Uploaded videos have been moved to the archive directory.")
    
    except Exception as e:
        logging.error(f"Main process error: {str(e)}")
        print(f"An error occurred: {str(e)}")
        print("Check the 'youtube_upload.log' file for more details.")

if __name__ == "__main__":
    main()