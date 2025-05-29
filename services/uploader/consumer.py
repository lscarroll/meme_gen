#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import time
import json
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from config import Config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import Utils
import subprocess
import logging

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("/app/data/uploader.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("UploaderConsumer")

def main():
    logger = setup_logging()
    logger.info("Starting YouTube Uploader Consumer")
    
    # Wait for Kafka to be ready
    max_retries = 30
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            consumer = KafkaConsumer(
                'upload-tasks',
                bootstrap_servers=['kafka:9092'],
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                api_version=(2, 8),
                consumer_timeout_ms=10000
            )
            logger.info("Connected to Kafka successfully")
            break
        except Exception as e:
            retry_count += 1
            logger.warning(f"Failed to connect to Kafka (attempt {retry_count}/{max_retries}): {e}")
            if retry_count >= max_retries:
                logger.error("Max retries reached. Exiting.")
                return
            time.sleep(5)
    
    try:
        logger.info("Waiting for upload tasks...")
        
        for message in consumer:
            try:
                task_data = message.value
                logger.info(f"Received upload task: {task_data}")
                
                if task_data.get('task') == 'upload':
                    logger.info("Starting YouTube upload process")
                    
                    # Run the upload script
                    result = subprocess.run([
                        sys.executable, 
                        '/app/services/uploader/upload.py'
                    ], capture_output=True, text=True, cwd='/app/services/uploader')
                    
                    if result.returncode == 0:
                        logger.info("Upload process completed successfully")
                        logger.info(f"Upload output: {result.stdout}")
                    else:
                        logger.error(f"Upload process failed with return code {result.returncode}")
                        logger.error(f"Upload stderr: {result.stderr}")
                        logger.error(f"Upload stdout: {result.stdout}")
                else:
                    logger.warning(f"Unknown task type: {task_data.get('task')}")
                    
            except Exception as e:
                logger.error(f"Error processing upload task: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Consumer error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        consumer.close()
        logger.info("Upload consumer shutdown complete")

if __name__ == "__main__":
    main()