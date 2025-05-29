#!/usr/bin/env python3
import json
import argparse
from kafka import KafkaProducer
from kafka.errors import KafkaError
import logging
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

class MemeOrchestrator:
    def __init__(self):
        self.setup_logging()
        self.producer = None
        self.connect_to_kafka()
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def connect_to_kafka(self):
        max_retries = 30
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=['kafka:9092'],
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    api_version=(2, 8)
                )
                self.logger.info("Connected to Kafka successfully")
                return
            except KafkaError as e:
                retry_count += 1
                self.logger.warning(f"Failed to connect to Kafka (attempt {retry_count}/{max_retries}): {e}")
                time.sleep(2)
        
        self.logger.error("Failed to connect to Kafka after maximum retries")
        sys.exit(1)
    
    def send_download_message(self, duration, max_clip):
        message = {
            'task': 'download',
            'duration': duration,
            'max_clip': max_clip,
            'timestamp': time.time()
        }
        
        try:
            future = self.producer.send('meme-tasks', value=message)
            result = future.get(timeout=10)
            self.logger.info(f"Download task sent: {message}")
        except KafkaError as e:
            self.logger.error(f"Failed to send download message: {e}")
    
    def send_compile_message(self, duration, pad_method):
        message = {
            'task': 'compile',
            'duration': duration,
            'pad_method': pad_method,
            'timestamp': time.time()
        }
        
        try:
            future = self.producer.send('meme-tasks', value=message)
            result = future.get(timeout=10)
            self.logger.info(f"Compile task sent: {message}")
        except KafkaError as e:
            self.logger.error(f"Failed to send compile message: {e}")
    
    def run_pipeline(self, duration, max_clip, pad_method, download_only=False, compile_only=False):
        self.logger.info("Starting Meme Generator pipeline")
        
        if download_only:
            self.logger.info("Running in download-only mode")
            self.send_download_message(duration, max_clip)
        elif compile_only:
            self.logger.info("Running in compile-only mode")
            self.send_compile_message(duration, pad_method)
        else:
            self.logger.info("Running full pipeline: Download → Compile")
            self.send_download_message(duration, max_clip)
            # Add delay to ensure download completes before compile
            time.sleep(5)
            self.send_compile_message(duration, pad_method)
        
        self.logger.info("Pipeline tasks sent to Kafka")
    
    def close(self):
        if self.producer:
            self.producer.close()

def main():
    parser = argparse.ArgumentParser(description="Meme Video Compilation Generator Orchestrator")
    parser.add_argument("--duration", type=int, default=Config.DEFAULT_TARGET_DURATION, 
                        help=f"Target duration of compilation in seconds (default: {Config.DEFAULT_TARGET_DURATION})")
    parser.add_argument("--max-clip", type=int, default=Config.MAX_CLIP_DURATION, 
                        help=f"Maximum duration of individual clips in seconds (default: {Config.MAX_CLIP_DURATION})")
    parser.add_argument("--pad-method", choices=["letterbox", "blur"], default=Config.DEFAULT_PAD_METHOD, 
                        help="Method to handle aspect ratio")
    parser.add_argument("--download-only", action="store_true", help="Only download videos")
    parser.add_argument("--compile-only", action="store_true", help="Only create compilations")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (keeps orchestrator alive)")
    
    args = parser.parse_args()
    
    orchestrator = MemeOrchestrator()
    try:
        if args.daemon:
            orchestrator.logger.info("Starting in daemon mode - orchestrator will stay alive")
            # In daemon mode, just stay alive and let other containers handle their own startup
            while True:
                time.sleep(60)
        else:
            orchestrator.run_pipeline(
                args.duration, 
                args.max_clip, 
                args.pad_method,
                args.download_only,
                args.compile_only
            )
    except KeyboardInterrupt:
        orchestrator.logger.info("Shutting down orchestrator...")
    finally:
        orchestrator.close()

if __name__ == "__main__":
    main()