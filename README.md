# Meme Video Compilation Generator (Dockerized with Kafka)

A Python application that automatically downloads Reddit videos and creates compilation videos from popular meme and animal subreddits, now containerized with Docker and using Apache Kafka for message-driven processing.

## What it does

- **Downloads videos** from Reddit subreddits (memes and funny animals)
- **Tracks duration** while downloading to hit your target compilation length
- **Creates compilations** by splicing clips together without re-encoding
- **Preserves original quality** and audio without modifications
- **Uses Kafka** for decoupled, scalable message-driven processing

## Architecture

The application now uses a microservices architecture with Kafka:

- **Orchestrator Service**: Sends tasks to Kafka topics (replaces run_all.py)
- **Downloader Service**: Consumes download tasks from Kafka
- **Compiler Service**: Consumes compilation tasks from Kafka
- **Kafka (KRaft)**: Message broker for inter-service communication

## Directory Structure

```
meme_gen/
├── services/
│   ├── orchestrator/           # Task orchestration
│   ├── downloader/            # Video downloading service
│   ├── compiler/              # Video compilation service
│   ├── utils.py               # Shared utilities
│   └── audio_processor.py     # Audio processing
├── videos/                    # All video files
│   ├── meme_videos/          # Downloaded meme videos
│   ├── animal_videos/        # Downloaded animal videos
│   ├── meme_comps/           # Compiled meme videos
│   ├── animal_comps/         # Compiled animal videos
│   └── archived_videos/      # Used videos
├── data/                     # Data files
│   ├── metadata/             # Video metadata
│   ├── thumbnails/           # Video thumbnails
│   └── reddit_data/          # Reddit API data
├── kafka/                    # Kafka configuration
│   └── config/               # Kafka server config
├── docker-compose.yml        # Docker services definition
├── Dockerfile               # Container image definition
└── start.sh                 # Quick start script
```

## Quick Start

### Using Docker (Recommended)

1. **Start all services**:
   ```bash
   ./start.sh
   ```
   
   Or manually:
   ```bash
   docker-compose up --build
   ```

2. **The system will automatically**:
   - Start Kafka with KRaft mode
   - Launch downloader and compiler consumers
   - Run the orchestrator to send initial tasks

### Custom Task Execution

Send specific tasks to the system:

```bash
# Download only (5 minutes of content)
docker-compose exec orchestrator python services/orchestrator/orchestrator.py --duration 300 --download-only

# Compile only
docker-compose exec orchestrator python services/orchestrator/orchestrator.py --duration 300 --compile-only

# Full pipeline with custom settings
docker-compose exec orchestrator python services/orchestrator/orchestrator.py --duration 600 --max-clip 30 --pad-method blur
```

### Manual Installation (Development)

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install system requirements**:
   - Python 3.x
   - FFmpeg (for video processing)
   - Java 17+ (for Kafka)
   - Apache Kafka

3. **Run services manually**:
   ```bash
   # Start Kafka
   ./kafka/setup.sh

   # Start consumers (in separate terminals)
   python services/downloader/consumer.py
   python services/compiler/consumer.py

   # Send tasks
   python services/orchestrator/orchestrator.py --duration 300
   ```

## Subreddits

**Meme Videos:**
- r/MemeVideos
- r/perfectlycutscreams  
- r/AbruptChaos
- r/funnyvideos

**Animal Videos:**
- r/wunkus
- r/FunnyAnimals
- r/AnimalsBeingDerps
- r/animalsdoingstuff

## Configuration

Edit `config.py` to customize:
- Target compilation duration
- Maximum clip duration
- Subreddit lists
- Directory paths

## How it works

1. **Orchestrator** sends download/compile messages to Kafka topics
2. **Downloader Service** processes download messages, fetches videos from Reddit
3. **Compiler Service** processes compile messages, creates compilation videos
4. **All services** communicate through Kafka for scalable, fault-tolerant processing

## Output

- **Compilations**: Saved to `videos/meme_comps/` and `videos/animal_comps/`
- **Used videos**: Moved to `videos/archived_videos/`
- **Logs**: Detailed logging from each service

## Docker Services

- **kafka**: Kafka broker with KRaft configuration
- **orchestrator**: Task coordination service
- **downloader**: Video download consumer
- **compiler**: Video compilation consumer

## Benefits of Kafka Architecture

- **Scalability**: Add more consumer instances to handle increased load
- **Fault Tolerance**: Failed tasks can be retried automatically
- **Decoupling**: Services can be developed and deployed independently
- **Monitoring**: Track message processing through Kafka metrics

## Note

This tool is for educational/personal use. Respect Reddit's terms of service and content creators' rights.