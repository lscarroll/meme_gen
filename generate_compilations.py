import os
import json
import time
import random
import subprocess
import shutil
from datetime import datetime
import math
import logging
import traceback

# Configuration settings
TARGET_DURATION = 11 * 60  # 11 minutes (660 seconds)

# Set DEBUG_MODE to True to print more diagnostic information
DEBUG_MODE = True

def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO if not DEBUG_MODE else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("compilation_generator.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("CompilationGenerator")

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
                # Enhanced to ensure proper YouTube dimensions (1920x1080) without stretching
                temp_output = os.path.join(temp_dir, f"processed_{i}.mp4")
                process_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_path,
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-max_muxing_queue_size", "9999",
                    temp_output
                ]
                
                print(f"Processing video to maintain aspect ratio: {os.path.basename(video_path)}")
                try:
                    result = subprocess.run(process_cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"FFmpeg error: {result.stderr}")
                        # Fall back to a simpler processing method if the first one fails
                        fallback_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", video_path,
                            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                            "-c:v", "libx264",
                            "-c:a", "copy",
                            temp_output
                        ]
                        print("Trying fallback conversion method...")
                        fallback_result = subprocess.run(fallback_cmd, capture_output=True, text=True)
                        if fallback_result.returncode != 0:
                            print(f"Fallback FFmpeg error: {fallback_result.stderr}")
                            # Add the original video if both methods fail
                            processed_videos.append(video_path)
                            print(f"Using original video without processing: {os.path.basename(video_path)}")
                        else:
                            processed_videos.append(temp_output)
                            print(f"Fallback processing successful: {os.path.basename(video_path)}")
                    else:
                        processed_videos.append(temp_output)
                        print(f"Processing successful: {os.path.basename(video_path)}")
                except Exception as e:
                    print(f"Exception during video processing: {e}")
                    # Add the original video on exception
                    processed_videos.append(video_path)
                    print(f"Using original video after exception: {os.path.basename(video_path)}")
                
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
        traceback.print_exc()
        return False, []

def load_video_metadata():
    """Load metadata for videos downloaded by download.py"""
    meme_videos = []
    animal_videos = []
    
    try:
        # Load meme videos metadata
        if os.path.exists("metadata/meme_videos.json"):
            with open("metadata/meme_videos.json", "r") as f:
                meme_data = json.load(f)
                for video in meme_data:
                    meme_videos.append((video["path"], video["duration"], video["subreddit"]))
        
        # Load animal videos metadata
        if os.path.exists("metadata/animal_videos.json"):
            with open("metadata/animal_videos.json", "r") as f:
                animal_data = json.load(f)
                for video in animal_data:
                    animal_videos.append((video["path"], video["duration"], video["subreddit"]))
                    
        print(f"Loaded metadata for {len(meme_videos)} meme videos and {len(animal_videos)} animal videos")
        return meme_videos, animal_videos
        
    except Exception as e:
        print(f"Error loading video metadata: {e}")
        return [], []

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
                dest_path = os.path.join("archived_videos", filename)
                
                # Move the file
                shutil.move(video_path, dest_path)
                logger.info(f"Moved used video to archive: {filename}")
                archive_count += 1
        except Exception as e:
            logger.error(f"Error moving video to archive: {e}")
    
    logger.info(f"Archived {archive_count} used videos in total")
    return archive_count

def main():
    # Set up logging
    logger = setup_logging()
    logger.info("Starting compilation generator")
    
    try:
        timestamp = int(time.time())
        
        # Create output directories if they don't exist
        if not os.path.exists("meme_comps"):
            os.makedirs("meme_comps")
        if not os.path.exists("animal_comps"):
            os.makedirs("animal_comps")
        if not os.path.exists("archived_videos"):
            os.makedirs("archived_videos")
        
        # Load video metadata
        all_meme_videos, all_animal_videos = load_video_metadata()
        
        # Check if we have videos to process
        if not all_meme_videos and not all_animal_videos:
            logger.warning("No videos found in metadata. Please run download.py first.")
            return
            
        logger.info(f"Found {len(all_meme_videos)} meme videos and {len(all_animal_videos)} animal videos")
        
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
                        
                        # Move used videos to archive
                        logger.info(f"Moving {len(used_videos)} used meme videos to archive...")
                        move_to_archive(used_videos, logger)
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
            logger.warning("No meme videos were found. Cannot create meme compilations.")
            
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
                        
                        # Move used videos to archive
                        logger.info(f"Moving {len(used_videos)} used animal videos to archive...")
                        move_to_archive(used_videos, logger)
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
            logger.warning("No animal videos were found. Cannot create animal compilations.")
            
        # No need to clean up leftover videos - keep them for future compilations
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()