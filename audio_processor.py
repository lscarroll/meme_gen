#!/usr/bin/env python3
import os
import time
import subprocess
import shutil
from config import Config

class AudioProcessor:
    def __init__(self, logger):
        self.logger = logger

    def process_audio_pitch(self, input_path, output_path):
        """Process video to pitch up the audio by one semitone"""
        try:
            # Create a temporary directory if it doesn't exist
            temp_dir = Config.TEMP_DIR
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
            
            print(f"Processing audio pitch for: {os.path.basename(input_path)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Error processing audio: {result.stderr}")
                return None
            
            # Move the temp file to the output path
            shutil.move(temp_output, output_path)
            print(f"Successfully processed audio pitch: {os.path.basename(output_path)}")
            return output_path
        
        except Exception as e:
            print(f"Error processing audio pitch: {e}")
            return None
        finally:
            # Clean up temp files
            if 'temp_output' in locals() and os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                except:
                    pass

    def process_compilations(self):
        """Process compilations for upload by pitching up audio"""
        self.logger.info("Processing compilations for upload")
        
        try:
            # Create necessary directories if they don't exist
            temp_dir = Config.TEMP_DIR
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            # Check for compilation videos in both directories
            meme_files = []
            animal_files = []
            
            # Check meme compilations
            if os.path.exists(Config.MEME_COMPS_DIR):
                meme_files = [f for f in os.listdir(Config.MEME_COMPS_DIR) 
                              if f.lower().endswith(('.mp4', '.mov', '.avi'))]
                self.logger.info(f"Found {len(meme_files)} meme compilation videos")
            else:
                self.logger.warning(f"Meme compilation directory '{Config.MEME_COMPS_DIR}' does not exist")
            
            # Check animal compilations
            if os.path.exists(Config.ANIMAL_COMPS_DIR):
                animal_files = [f for f in os.listdir(Config.ANIMAL_COMPS_DIR) 
                              if f.lower().endswith(('.mp4', '.mov', '.avi'))]
                self.logger.info(f"Found {len(animal_files)} animal compilation videos")
            else:
                self.logger.warning(f"Animal compilation directory '{Config.ANIMAL_COMPS_DIR}' does not exist")
            
            # Process meme videos
            for video_file in meme_files:
                video_path = os.path.join(Config.MEME_COMPS_DIR, video_file)
                pitched_video_path = os.path.join(temp_dir, f"pitched_{int(time.time())}_{video_file}")
                
                # Process audio (pitch up by one semitone)
                self.logger.info(f"Processing audio for {video_file}...")
                processed_path = self.process_audio_pitch(video_path, pitched_video_path)
                
                if processed_path:
                    # Replace original with processed version
                    try:
                        shutil.move(processed_path, video_path)
                        self.logger.info(f"Replaced original with audio-processed version: {video_file}")
                    except Exception as e:
                        self.logger.error(f"Error replacing original video: {e}")
                else:
                    self.logger.error(f"Failed to process audio for {video_file}")
            
            # Process animal videos
            for video_file in animal_files:
                video_path = os.path.join(Config.ANIMAL_COMPS_DIR, video_file)
                pitched_video_path = os.path.join(temp_dir, f"pitched_{int(time.time())}_{video_file}")
                
                # Process audio (pitch up by one semitone)
                self.logger.info(f"Processing audio for {video_file}...")
                processed_path = self.process_audio_pitch(video_path, pitched_video_path)
                
                if processed_path:
                    # Replace original with processed version
                    try:
                        shutil.move(processed_path, video_path)
                        self.logger.info(f"Replaced original with audio-processed version: {video_file}")
                    except Exception as e:
                        self.logger.error(f"Error replacing original video: {e}")
                else:
                    self.logger.error(f"Failed to process audio for {video_file}")
            
            self.logger.info("Audio processing complete for all compilations")
            
        except Exception as e:
            self.logger.error(f"Unexpected error in process_compilations: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
