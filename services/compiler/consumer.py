#!/usr/bin/env python3
import json
import logging
import sys
import os
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.compiler.compiler import Compiler
from services.utils import Utils

class CompileConsumer:
    def __init__(self):
        self.setup_logging()
        self.consumer = None
        self.compiler = None
        self.connect_to_kafka()
        self.setup_compiler()
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_compiler(self):
        Utils.ensure_directories()
        self.compiler = Compiler(self.logger)
    
    def connect_to_kafka(self):
        max_retries = 30
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.consumer = KafkaConsumer(
                    'meme-tasks',
                    bootstrap_servers=['kafka:9092'],
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    group_id='compiler-group',
                    api_version=(2, 8),
                    auto_offset_reset='latest',
                    enable_auto_commit=True
                )
                self.logger.info("Connected to Kafka successfully")
                return
            except KafkaError as e:
                retry_count += 1
                self.logger.warning(f"Failed to connect to Kafka (attempt {retry_count}/{max_retries}): {e}")
                time.sleep(2)
        
        self.logger.error("Failed to connect to Kafka after maximum retries")
        sys.exit(1)
    
    def process_message(self, message):
        try:
            if message['task'] == 'compile':
                self.logger.info(f"Processing compile task: {message}")
                duration = message.get('duration', 660)
                pad_method = message.get('pad_method', 'letterbox')
                
                self.compiler.generate_compilations(duration, pad_method)
                self.logger.info("Compilation complete")
            else:
                self.logger.info(f"Ignoring non-compile task: {message['task']}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    def run(self):
        self.logger.info("Starting compile consumer...")
        try:
            for message in self.consumer:
                self.process_message(message.value)
        except KeyboardInterrupt:
            self.logger.info("Shutting down compile consumer...")
        finally:
            if self.consumer:
                self.consumer.close()

if __name__ == "__main__":
    consumer = CompileConsumer()
    consumer.run()