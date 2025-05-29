#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import time
import json
from kafka import KafkaProducer
from kafka.errors import KafkaError
import logging

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("/app/data/upload_trigger.log"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("UploadTrigger")

def main():
    logger = setup_logging()
    logger.info("Starting YouTube Upload Trigger")
    
    # Setup Kafka producer
    max_retries = 30
    retry_count = 0
    producer = None
    
    while retry_count < max_retries:
        try:
            producer = KafkaProducer(
                bootstrap_servers=['kafka:9092'],
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                api_version=(2, 8)
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
        # Send upload task
        message = {
            'task': 'upload',
            'timestamp': time.time()
        }
        
        future = producer.send('upload-tasks', value=message)
        result = future.get(timeout=10)
        logger.info(f"Upload task sent successfully: {message}")
        print("Upload task has been queued successfully!")
        print("The uploader service will process all compilation videos and upload them to YouTube.")
        
    except Exception as e:
        logger.error(f"Failed to send upload task: {e}")
        print(f"Error: Failed to queue upload task: {e}")
        return 1
    finally:
        if producer:
            producer.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())