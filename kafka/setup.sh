#!/bin/bash

# Generate cluster UUID
KAFKA_CLUSTER_ID=$(kafka-storage.sh random-uuid)
echo "Generated Cluster ID: $KAFKA_CLUSTER_ID"

# Format the storage
kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c /opt/kafka/config/server.properties

# Start Kafka
kafka-server-start.sh /opt/kafka/config/server.properties