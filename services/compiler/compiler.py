#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import time
import random
import subprocess
import shutil
import math
import traceback
from datetime import datetime
from config import Config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import Utils

class Compiler:
    def __init__(self, logger):
        self.logger = logger

    def create_compilation(self, video_files_with_meta, target_length, output_file="compilation.mp4", pad_method="letterbox"):
        """
        Create a compilation video that's exactly the target length.
        
        Args:
            video_files_with_meta: List of tuples (video_path, duration, subreddit)
            target_length: Target length in seconds
            output_file: Output file path
            pad_method: Method to handle aspect ratio - "letterbox" (black bars) or "blur" (blurred background)
        
        Returns:
            Path to the created compilation or False on failure, and list of used videos
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
            
            # Use original videos without processing to preserve quality
            processed_videos = []
            for video_path, duration, subreddit in selected_videos_info:
                if os.path.exists(video_path):
                    processed_videos.append(video_path)
                    print(f"Using original video: {os.path.basename(video_path)} - Duration: {duration:.2f}s - r/{subreddit}")
                else:
                    print(f"Warning: Video file not found: {video_path}")
            
            # Create a temporary file list for FFmpeg
            list_file = f"video_list_{int(time.time())}.txt"
            with open(list_file, "w", encoding='utf-8') as f:
                for video_file in processed_videos:
                    # Handle backslashes in Windows paths
                    safe_path = video_file.replace('\\', '\\\\')
                    f.write(f"file '{safe_path}'\n")
            
            # Run FFmpeg to concatenate the videos with original audio
            print(f"Creating compilation of {len(processed_videos)} videos...")
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if it exists
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c:v", "copy",  # Copy video codec without re-encoding
                "-c:a", "copy",  # Copy audio codec without re-encoding
                output_file
            ]
            
            # Run the command
            subprocess.run(cmd, check=True)
            
            # Clean up the temporary files
            if os.path.exists(list_file):
                os.remove(list_file)
            
            # Verify the output file was created
            if os.path.exists(output_file):
                output_duration = Utils.get_video_duration(output_file)
                print(f"Compilation created successfully: {output_file}")
                print(f"Final duration: {output_duration:.2f}s ({output_duration/60:.2f} minutes)")
                # Return the list of used videos and the output file
                return output_file, selected_videos
            else:
                print(f"Error: Compilation file {output_file} was not created")
                return False, []
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Error running FFmpeg: {e}"
            if hasattr(e, 'stderr') and e.stderr:
                error_msg += f"\nStderr: {e.stderr}"
            if hasattr(e, 'stdout') and e.stdout:
                error_msg += f"\nStdout: {e.stdout}"
            print(error_msg)
            self.logger.error(error_msg)
            return False, []
        except Exception as e:
            error_msg = f"Error creating compilation: {e}"
            print(error_msg)
            self.logger.error(error_msg)
            traceback.print_exc()
            return False, []

    def generate_compilations(self, target_duration=None, pad_method=None):
        """Generate compilations based on downloaded videos"""
        if target_duration is None:
            target_duration = Config.DEFAULT_TARGET_DURATION
            
        if pad_method is None:
            pad_method = Config.DEFAULT_PAD_METHOD
            
        self.logger.info("Starting compilation generator")
        self.logger.info(f"Target duration: {target_duration}s, Pad method: {pad_method}")
        
        try:
            timestamp = int(time.time())
            
            # Create output directories if they don't exist
            for directory in [Config.MEME_COMPS_DIR, Config.ANIMAL_COMPS_DIR, Config.ARCHIVED_VIDEOS_DIR]:
                if not os.path.exists(directory):
                    os.makedirs(directory)
            
            # Load video metadata
            all_meme_videos, all_animal_videos = Utils.load_video_metadata()
            
            # Check if we have videos to process
            if not all_meme_videos and not all_animal_videos:
                self.logger.warning("No videos found in metadata. Please run download first.")
                return
                
            self.logger.info(f"Found {len(all_meme_videos)} meme videos and {len(all_animal_videos)} animal videos")
            
            # Process meme videos
            if all_meme_videos:
                # Calculate total duration available for meme videos
                total_meme_duration = sum(duration for _, duration, _ in all_meme_videos)
                
                # Calculate how many meme compilations we can make
                # Create at least one compilation if we have sufficient content (at least 30% of target duration)
                min_compilation_duration = target_duration * 0.3
                potential_meme_comps = max(1 if total_meme_duration >= min_compilation_duration else 0, 
                                         math.floor(total_meme_duration / target_duration))
                
                self.logger.info(f"Total meme video duration: {total_meme_duration:.2f}s")
                self.logger.info(f"Minimum duration for compilation: {min_compilation_duration:.2f}s")
                self.logger.info(f"Potential number of meme compilations: {potential_meme_comps}")
                
                # Create meme compilations until we run out of videos
                remaining_meme_videos = all_meme_videos.copy()
                meme_comp_number = 1
                
                while remaining_meme_videos and meme_comp_number <= potential_meme_comps:
                    self.logger.info(f"\n=== Creating Meme Compilation #{meme_comp_number} ===")
                    
                    # Shuffle the videos
                    random.shuffle(remaining_meme_videos)
                    
                    # Create the compilation
                    compilation_file = f"meme_compilation_{timestamp}_{meme_comp_number}.mp4"
                    created_file, used_videos = self.create_compilation(
                        remaining_meme_videos,
                        target_length=target_duration,
                        output_file=compilation_file,
                        pad_method=pad_method
                    )
                    
                    if created_file and used_videos:
                        # Remove used videos from remaining_videos
                        used_video_paths = set(used_videos)
                        remaining_meme_videos = [v for v in remaining_meme_videos if v[0] not in used_video_paths]
                        
                        # Move the file to meme_comps directory
                        timestamp_full = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        dest_filename = f"meme_compilation_{timestamp_full}_{meme_comp_number}.mp4"
                        dest_path = os.path.join(Config.MEME_COMPS_DIR, dest_filename)
                        
                        try:
                            shutil.copy2(created_file, dest_path)
                            self.logger.info(f"Copied meme compilation to: {dest_path}")
                            if os.path.exists(created_file):
                                os.remove(created_file)
                            
                            # Move used videos to archive
                            self.logger.info(f"Moving {len(used_videos)} used meme videos to archive...")
                            Utils.move_to_archive(used_videos, self.logger)
                        except Exception as e:
                            self.logger.error(f"Error copying meme compilation: {e}")
                        
                        self.logger.info("\n=============================================")
                        self.logger.info(f"Meme Compilation #{meme_comp_number} created!")
                        self.logger.info(f"File: {dest_path}")
                        self.logger.info("=============================================\n")
                        
                        meme_comp_number += 1
                    else:
                        self.logger.error(f"Failed to create meme compilation #{meme_comp_number}.")
                        break
                
                self.logger.info(f"Created {meme_comp_number-1} meme compilations in total.")
            else:
                self.logger.warning("No meme videos were found. Cannot create meme compilations.")
                
            # Process animal videos
            if all_animal_videos:
                # Calculate total duration available for animal videos
                total_animal_duration = sum(duration for _, duration, _ in all_animal_videos)
                
                # Calculate how many animal compilations we can make
                # Create at least one compilation if we have sufficient content (at least 30% of target duration)
                min_compilation_duration = target_duration * 0.3
                potential_animal_comps = max(1 if total_animal_duration >= min_compilation_duration else 0, 
                                           math.floor(total_animal_duration / target_duration))
                
                self.logger.info(f"Total animal video duration: {total_animal_duration:.2f}s")
                self.logger.info(f"Minimum duration for compilation: {min_compilation_duration:.2f}s")
                self.logger.info(f"Potential number of animal compilations: {potential_animal_comps}")
                
                # Create animal compilations until we run out of videos
                remaining_animal_videos = all_animal_videos.copy()
                animal_comp_number = 1
                
                while remaining_animal_videos and animal_comp_number <= potential_animal_comps:
                    self.logger.info(f"\n=== Creating Animal Compilation #{animal_comp_number} ===")
                    
                    # Shuffle the videos
                    random.shuffle(remaining_animal_videos)
                    
                    # Create the compilation
                    compilation_file = f"animal_compilation_{timestamp}_{animal_comp_number}.mp4"
                    created_file, used_videos = self.create_compilation(
                        remaining_animal_videos,
                        target_length=target_duration,
                        output_file=compilation_file,
                        pad_method=pad_method
                    )
                    
                    if created_file and used_videos:
                        # Remove used videos from remaining_videos
                        used_video_paths = set(used_videos)
                        remaining_animal_videos = [v for v in remaining_animal_videos if v[0] not in used_video_paths]
                        
                        # Move the file to animal_comps directory
                        timestamp_full = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        dest_filename = f"animal_compilation_{timestamp_full}_{animal_comp_number}.mp4"
                        dest_path = os.path.join(Config.ANIMAL_COMPS_DIR, dest_filename)
                        
                        try:
                            shutil.copy2(created_file, dest_path)
                            self.logger.info(f"Copied animal compilation to: {dest_path}")
                            if os.path.exists(created_file):
                                os.remove(created_file)
                            
                            # Move used videos to archive
                            self.logger.info(f"Moving {len(used_videos)} used animal videos to archive...")
                            Utils.move_to_archive(used_videos, self.logger)
                        except Exception as e:
                            self.logger.error(f"Error copying animal compilation: {e}")
                        
                        self.logger.info("\n=============================================")
                        self.logger.info(f"Animal Compilation #{animal_comp_number} created!")
                        self.logger.info(f"File: {dest_path}")
                        self.logger.info("=============================================\n")
                        
                        animal_comp_number += 1
                    else:
                        self.logger.error(f"Failed to create animal compilation #{animal_comp_number}.")
                        break
                
                self.logger.info(f"Created {animal_comp_number-1} animal compilations in total.")
            else:
                self.logger.warning("No animal videos were found. Cannot create animal compilations.")
                
            # No need to clean up leftover videos - keep them for future compilations
            
        except Exception as e:
            self.logger.error(f"Unexpected error in generate_compilations: {e}")
            traceback.print_exc()
            self.logger.error(traceback.format_exc())
