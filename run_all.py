#!/usr/bin/env python3
import argparse
import traceback
from config import Config
from utils import Utils
from downloader import Downloader
from compiler import Compiler

def main():
    """Main function to run the entire pipeline"""
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Meme Video Compilation Generator")
    parser.add_argument("--duration", type=int, default=Config.DEFAULT_TARGET_DURATION, 
                        help=f"Target duration of compilation in seconds (default: {Config.DEFAULT_TARGET_DURATION} seconds / {Config.DEFAULT_TARGET_DURATION/60:.1f} minutes)")
    parser.add_argument("--max-clip", type=int, default=Config.MAX_CLIP_DURATION, 
                        help=f"Maximum duration of individual clips in seconds (default: {Config.MAX_CLIP_DURATION} seconds)")
    parser.add_argument("--pad-method", choices=["letterbox", "blur"], default=Config.DEFAULT_PAD_METHOD, 
                        help="Method to handle aspect ratio (letterbox: black bars, blur: blurred background)")
    parser.add_argument("--download-only", action="store_true", help="Only download videos, don't create compilations")
    parser.add_argument("--compile-only", action="store_true", help="Only create compilations from downloaded videos")
    
    args = parser.parse_args()
    
    # Set up logging
    logger = Utils.setup_logging()
    logger.info("Starting Meme Generator pipeline")
    logger.info(f"Configuration: Target Duration: {args.duration}s, Max Clip Duration: {args.max_clip}s, Padding Method: {args.pad_method}")
    
    # Ensure all required directories exist
    Utils.ensure_directories()
    
    try:
        # Initialize classes
        downloader = Downloader(logger)
        compiler = Compiler(logger)
        
        # Handle different execution modes
        if args.download_only:
            logger.info("Running in download-only mode")
            downloader.download_videos(args.max_clip, args.duration)
        elif args.compile_only:
            logger.info("Running in compile-only mode")
            compiler.generate_compilations(args.duration, args.pad_method)
        else:
            # Run the full pipeline
            logger.info("Running full pipeline: Download → Compile")
            
            # Step 1: Download videos
            logger.info("STEP 1: Downloading videos")
            meme_videos, animal_videos = downloader.download_videos(args.max_clip, args.duration)
            
            # Step 2: Generate compilations
            logger.info("STEP 2: Generating compilations")
            compiler.generate_compilations(args.duration, args.pad_method)
            
            logger.info("Pipeline complete! Videos are ready for upload.")
            logger.info(f"Check {Config.MEME_COMPS_DIR} and {Config.ANIMAL_COMPS_DIR} for compiled videos.")
        
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        traceback.print_exc()
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()