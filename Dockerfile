FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Install Kafka
RUN wget -q https://archive.apache.org/dist/kafka/3.6.0/kafka_2.13-3.6.0.tgz \
    && tar -xzf kafka_2.13-3.6.0.tgz \
    && mv kafka_2.13-3.6.0 /opt/kafka \
    && rm kafka_2.13-3.6.0.tgz

# Add Kafka to PATH
ENV PATH="/opt/kafka/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p videos/{meme_videos,animal_videos,meme_comps,animal_comps,archived_videos,reddit_videos} \
    kafka/{config,logs} \
    services/{downloader,compiler,orchestrator} \
    data/{metadata,thumbnails,reddit_data,temp_pitch_processed}

# Copy Kafka configuration
COPY kafka/config/server.properties /opt/kafka/config/

# Set Python path
ENV PYTHONPATH="/app"

# Expose Kafka port
EXPOSE 9092 9093

# Default command
CMD ["python", "services/orchestrator/orchestrator.py"]