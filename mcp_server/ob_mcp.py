import os
import logging
import json
import redis
import time
from google.cloud import pubsub_v1
from mcp.server.fastmcp import FastMCP


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MCP_SERVER_HOST = os.getenv("MCP_SERVER_HOST", "0.0.0.0")  # For Uvicorn to bind to all interfaces in the container
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", 50051))

REDIS_ADDRESS = "redis-cart:6379"

# GCP Project
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
PUBSUB_TOPIC = "abandoned-carts"

# Initialize FastMCP server
mcp = FastMCP(
    instance_name="online_boutique_mcp_server",
    instructions="This MCP server provides tools that leverages Online Boutique microservices APIs.",
    host=MCP_SERVER_HOST,
    port=MCP_SERVER_PORT,
    # sse_path="/sse", # Default, can be overridden if needed
    # message_path="/messages/", # Default, can be overridden if needed
)
logging.info(f"Online Boutique MCP server starting on {MCP_SERVER_HOST}:{MCP_SERVER_PORT}")

# --- MCP Tools ---
@mcp.tool()
def monitor_carts():
    """Monitors for abandoned carts and returns a list of them."""
    redis_client = redis.Redis.from_url(f'redis://{REDIS_ADDRESS}')
    ABANDONED_THRESHOLD = 150
    abandoned = []

    cursor = '0'
    while cursor != 0:
        cursor, keys = redis_client.scan(cursor=cursor)
        for key in keys:
            key_str = key.decode('utf-8')
            key_type = redis_client.type(key)
            if key_type == b'hash':
                idle_time = redis_client.object('idletime', key)
                if idle_time > ABANDONED_THRESHOLD:
                    fields = redis_client.hgetall(key)
                    # Parse items (assuming "data" field is protobuf or JSON)
                    # items = parse_cart_fields(fields)  # Custom function below
                    entry = {'user_id': key_str, 'idle_time_seconds': idle_time}
                    abandoned.append(entry)
                    # Publish to Pub/Sub
                    try:
                        publisher = pubsub_v1.PublisherClient()
                        topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
                        data = json.dumps(entry).encode('utf-8')
                        future = publisher.publish(topic_path, data)
                        message_id = future.result()
                        logger.info(f"Successfully published {key_str} to Pub/Sub, message_id={message_id}")
                    except Exception as e:
                        logger.error(f"Pub/Sub publish failed for {key_str}: {e}")

    return {'abandoned_carts': abandoned}

def parse_cart_fields(fields):
    items = []
    if b'data' in fields:
        data = fields[b'data']
        try:
            # Assuming protobuf; replace with actual decode if needed
            cart = Hipstershop.Cart.FromString(data)  # Requires protobuf import/setup
            for item in cart.items:
                items.append({'product_id': item.product_id, 'quantity': item.quantity})
        except Exception as e:
            logger.error(f"Decode error: {e}")
            items = [{"raw_data": data.decode('utf-8', errors='ignore')}]
    return items

if __name__ == "__main__":
    logger.info("Starting Online Boutique MCP Server...")
    try:
        mcp.run(transport="sse")
    except Exception as e:
        logging.critical(f"MCP server failed to run: {e}", exc_info=True)
        exit(1)