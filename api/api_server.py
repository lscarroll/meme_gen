#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import logging
from kafka import KafkaProducer
from kafka.errors import KafkaError
import glob
from config import Config
from services.utils import Utils

app = Flask(__name__)
CORS(app)

# Set up logging
logger = Utils.setup_logging("api_server.log")

# Initialize Kafka producer
producer = None

def init_kafka_producer():
    """Initialize Kafka producer with retry logic"""
    global producer
    try:
        producer = KafkaProducer(
            bootstrap_servers=['localhost:9092'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=3
        )
        logger.info("Kafka producer initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        return False

@app.before_first_request
def startup():
    """Initialize the API server"""
    Utils.ensure_directories()
    init_kafka_producer()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "meme-gen-api"})

@app.route('/api/trigger/download', methods=['POST'])
def trigger_download():
    """Manually trigger video download"""
    try:
        data = request.get_json() or {}
        
        # Build message for download task
        message = {
            "action": "download",
            "duration": data.get("duration", Config.TARGET_DURATION),
            "max_clip": data.get("max_clip", Config.MAX_CLIP_DURATION),
            "timestamp": data.get("timestamp", None)
        }
        
        if producer is None:
            if not init_kafka_producer():
                return jsonify({"error": "Kafka producer not available"}), 500
        
        # Send message to Kafka
        future = producer.send('meme-tasks', message)
        producer.flush()
        
        logger.info(f"Download task triggered: {message}")
        return jsonify({
            "status": "success", 
            "message": "Download task triggered",
            "task": message
        })
        
    except Exception as e:
        logger.error(f"Error triggering download: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/trigger/compile', methods=['POST'])
def trigger_compile():
    """Manually trigger video compilation"""
    try:
        data = request.get_json() or {}
        
        # Build message for compile task
        message = {
            "action": "compile",
            "pad_method": data.get("pad_method", "letterbox"),
            "timestamp": data.get("timestamp", None)
        }
        
        if producer is None:
            if not init_kafka_producer():
                return jsonify({"error": "Kafka producer not available"}), 500
        
        # Send message to Kafka
        future = producer.send('meme-tasks', message)
        producer.flush()
        
        logger.info(f"Compile task triggered: {message}")
        return jsonify({
            "status": "success", 
            "message": "Compile task triggered",
            "task": message
        })
        
    except Exception as e:
        logger.error(f"Error triggering compile: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/trigger/upload', methods=['POST'])
def trigger_upload():
    """Manually trigger video upload"""
    try:
        data = request.get_json() or {}
        
        # Build message for upload task
        message = {
            "action": "upload",
            "video_path": data.get("video_path", None),  # Optional specific video
            "timestamp": data.get("timestamp", None)
        }
        
        if producer is None:
            if not init_kafka_producer():
                return jsonify({"error": "Kafka producer not available"}), 500
        
        # Send message to Kafka
        future = producer.send('upload-tasks', message)
        producer.flush()
        
        logger.info(f"Upload task triggered: {message}")
        return jsonify({
            "status": "success", 
            "message": "Upload task triggered",
            "task": message
        })
        
    except Exception as e:
        logger.error(f"Error triggering upload: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/trigger/full-pipeline', methods=['POST'])
def trigger_full_pipeline():
    """Trigger the complete download -> compile -> upload pipeline"""
    try:
        data = request.get_json() or {}
        
        if producer is None:
            if not init_kafka_producer():
                return jsonify({"error": "Kafka producer not available"}), 500
        
        # Send download task first
        download_message = {
            "action": "download",
            "duration": data.get("duration", Config.TARGET_DURATION),
            "max_clip": data.get("max_clip", Config.MAX_CLIP_DURATION),
            "trigger_compile": True,  # Auto-trigger compile when done
            "trigger_upload": True    # Auto-trigger upload when compile done
        }
        
        future = producer.send('meme-tasks', download_message)
        producer.flush()
        
        logger.info(f"Full pipeline triggered: {download_message}")
        return jsonify({
            "status": "success", 
            "message": "Full pipeline triggered (download -> compile -> upload)",
            "task": download_message
        })
        
    except Exception as e:
        logger.error(f"Error triggering full pipeline: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/videos', methods=['GET'])
def get_video_status():
    """Get status of videos in the system"""
    try:
        status = {
            "meme_videos": len(glob.glob(f"{Config.MEME_VIDEOS_DIR}/*.mp4")),
            "animal_videos": len(glob.glob(f"{Config.ANIMAL_VIDEOS_DIR}/*.mp4")),
            "meme_compilations": len(glob.glob(f"{Config.MEME_COMPS_DIR}/*.mp4")),
            "animal_compilations": len(glob.glob(f"{Config.ANIMAL_COMPS_DIR}/*.mp4")),
            "archived_videos": len(glob.glob(f"{Config.ARCHIVED_VIDEOS_DIR}/*.mp4"))
        }
        
        # Calculate total disk usage
        total_size = 0
        for directory in [Config.MEME_VIDEOS_DIR, Config.ANIMAL_VIDEOS_DIR, 
                         Config.MEME_COMPS_DIR, Config.ANIMAL_COMPS_DIR, 
                         Config.ARCHIVED_VIDEOS_DIR]:
            for file_path in glob.glob(f"{directory}/*.mp4"):
                try:
                    total_size += os.path.getsize(file_path)
                except:
                    pass
        
        status["total_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting video status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/services', methods=['GET'])
def get_service_status():
    """Check status of system services"""
    try:
        # Check if Kafka is accessible
        kafka_status = "unknown"
        if producer is not None:
            kafka_status = "connected"
        else:
            kafka_status = "disconnected"
        
        # Check if directories exist
        directories_status = {}
        for name, path in [
            ("data", Config.DATA_DIR),
            ("meme_videos", Config.MEME_VIDEOS_DIR),
            ("animal_videos", Config.ANIMAL_VIDEOS_DIR),
            ("meme_comps", Config.MEME_COMPS_DIR),
            ("animal_comps", Config.ANIMAL_COMPS_DIR),
            ("archived", Config.ARCHIVED_VIDEOS_DIR),
            ("metadata", Config.METADATA_DIR),
            ("thumbnails", Config.THUMBNAILS_DIR)
        ]:
            directories_status[name] = os.path.exists(path)
        
        return jsonify({
            "kafka": kafka_status,
            "directories": directories_status,
            "api": "running"
        })
        
    except Exception as e:
        logger.error(f"Error checking service status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        config_data = {
            "target_duration": Config.TARGET_DURATION,
            "max_clip_duration": Config.MAX_CLIP_DURATION,
            "meme_subreddits": Config.MEME_SUBREDDITS,
            "animal_subreddits": Config.ANIMAL_SUBREDDITS,
            "debug_mode": Config.DEBUG_MODE,
            "data_dir": Config.DATA_DIR
        }
        return jsonify(config_data)
        
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/manual/compile-existing', methods=['POST'])
def compile_existing():
    """Create compilation from existing downloaded videos"""
    try:
        # Check if we have existing videos
        meme_videos, animal_videos = Utils.load_video_metadata()
        
        if not meme_videos and not animal_videos:
            return jsonify({
                "error": "No existing videos found to compile"
            }), 400
        
        data = request.get_json() or {}
        message = {
            "action": "compile",
            "pad_method": data.get("pad_method", "letterbox"),
            "use_existing": True
        }
        
        if producer is None:
            if not init_kafka_producer():
                return jsonify({"error": "Kafka producer not available"}), 500
        
        future = producer.send('meme-tasks', message)
        producer.flush()
        
        logger.info(f"Existing video compilation triggered: {message}")
        return jsonify({
            "status": "success",
            "message": f"Compilation triggered with {len(meme_videos)} meme videos and {len(animal_videos)} animal videos",
            "meme_count": len(meme_videos),
            "animal_count": len(animal_videos)
        })
        
    except Exception as e:
        logger.error(f"Error compiling existing videos: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/manual/upload-existing', methods=['POST'])
def upload_existing():
    """Upload existing compilation videos"""
    try:
        # Find existing compilation videos
        meme_comps = glob.glob(f"{Config.MEME_COMPS_DIR}/*.mp4")
        animal_comps = glob.glob(f"{Config.ANIMAL_COMPS_DIR}/*.mp4")
        
        if not meme_comps and not animal_comps:
            return jsonify({
                "error": "No existing compilation videos found to upload"
            }), 400
        
        if producer is None:
            if not init_kafka_producer():
                return jsonify({"error": "Kafka producer not available"}), 500
        
        # Trigger upload for each compilation
        uploaded_count = 0
        for comp_path in meme_comps + animal_comps:
            message = {
                "action": "upload",
                "video_path": comp_path
            }
            future = producer.send('upload-tasks', message)
            uploaded_count += 1
        
        producer.flush()
        
        logger.info(f"Upload triggered for {uploaded_count} existing compilations")
        return jsonify({
            "status": "success",
            "message": f"Upload triggered for {uploaded_count} existing compilations",
            "meme_compilations": len(meme_comps),
            "animal_compilations": len(animal_comps)
        })
        
    except Exception as e:
        logger.error(f"Error uploading existing videos: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG_MODE)