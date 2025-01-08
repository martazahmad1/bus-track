import asyncio
import websockets
import json
import datetime
import logging
import os
from dotenv import load_dotenv
from http import HTTPStatus
import pathlib

# Load environment variables
load_dotenv()

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global variables for state management
last_known_position = None
websocket_clients = set()

# Socket Server Configuration
HOST = '0.0.0.0'  # Listen on all available interfaces

# Handle PORT environment variable with better error handling
try:
    PORT = int(os.getenv('PORT', '10000'))
except (ValueError, TypeError):
    logger.warning("Invalid PORT environment variable, using default port 10000")
    PORT = 10000

# Get the path to the frontend directory and file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
POSSIBLE_PATHS = [
    'index.html',  # Current directory
    os.path.join(PROJECT_ROOT, 'index.html'),  # Project root
    os.path.join(PROJECT_ROOT, 'frontend', 'index.html'),  # Frontend directory
    '/opt/render/project/src/index.html',  # Render.com specific path
    '/opt/render/project/src/frontend/index.html'  # Render.com frontend path
]

logger.info(f"Current directory: {CURRENT_DIR}")
logger.info(f"Project root: {PROJECT_ROOT}")
logger.info(f"Looking for frontend file in multiple locations:")
for path in POSSIBLE_PATHS:
    logger.info(f"- {path}")

def read_frontend_file():
    """Read the contents of the frontend HTML file"""
    try:
        # Try all possible paths
        for path in POSSIBLE_PATHS:
            if os.path.exists(path):
                logger.info(f"Found index.html at: {path}")
                with open(path, 'rb') as f:
                    return f.read()
        
        # If no file found, log all directory contents
        logger.error("Frontend file not found in any location")
        logger.error("Current directory contents:")
        logger.error(os.listdir('.'))
        logger.error(f"Project root contents:")
        logger.error(os.listdir(PROJECT_ROOT))
        if os.path.exists('/opt/render/project/src'):
            logger.error("Render project directory contents:")
            logger.error(os.listdir('/opt/render/project/src'))
        return None
    except Exception as e:
        logger.error(f"Error reading frontend file: {str(e)}")
        return None

async def broadcast_to_websockets(data):
    """Broadcast data to all connected WebSocket clients"""
    global last_known_position
    
    if isinstance(data, dict) and data.get('type') == 'gps':
        last_known_position = data
    
    if websocket_clients:
        # Convert data to JSON if it's not already a string
        message = data if isinstance(data, str) else json.dumps(data)
        
        # Send to all connected clients
        disconnected = set()
        for client in websocket_clients:
            try:
                await client.send(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        for client in disconnected:
            if client in websocket_clients:
                websocket_clients.remove(client)

async def process_request(path, request_headers):
    """Process HTTP requests before WebSocket upgrade"""
    logger.info(f"Processing request: {path}")
    logger.info(f"Headers: {request_headers}")
    
    # Handle WebSocket upgrade
    if request_headers.get('Upgrade', '').lower() == 'websocket':
        return None  # Let WebSocket handle the connection
    
    # Handle HTTP requests
    if path == "/" or path == "/index.html":
        content = read_frontend_file()
        if content:
            return HTTPStatus.OK, [
                ("Content-Type", "text/html"),
                ("Content-Length", str(len(content))),
                ("Connection", "keep-alive"),
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Headers", "*"),
                ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
                ("Sec-WebSocket-Version", "13"),
                ("Sec-WebSocket-Protocol", "bus-tracker"),
            ], content
    
    # Return 404 for other paths
    return HTTPStatus.NOT_FOUND, [], b"404 Not Found"

async def broadcast_message(message):
    disconnected_clients = []
    for client in websocket_clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected_clients.append(client)
    
    # Remove disconnected clients
    for client in disconnected_clients:
        if client in websocket_clients:
            websocket_clients.remove(client)
            logger.info("Removed disconnected client")

async def handle_websocket(websocket, path):
    logger.info("New WebSocket client connected")
    websocket_clients.add(websocket)
    try:
        async for message in websocket:
            logger.debug(f"Received WebSocket message: {message}")
            # Handle any client messages if needed
            pass
    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket client disconnected")
    finally:
        websocket_clients.remove(websocket)

async def main():
    """Main function to start the server"""
    logger.info(f"Starting Bus Tracking Server on port {PORT}...")
    
    # Create server with both HTTP and WebSocket support
    server = await websockets.serve(
        handle_websocket,
        HOST,
        PORT,
        process_request=process_request,
        ping_interval=20,
        ping_timeout=30,
        compression=None,
        max_size=10_485_760,  # 10MB max message size
        max_queue=32,
        close_timeout=10,
        create_protocol=websockets.WebSocketServerProtocol,
        subprotocols=['bus-tracker']
    )
    
    logger.info(f"Server started on port {PORT}")
    
    try:
        await server.wait_closed()
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
    finally:
        logger.info("Server shutting down...")

if __name__ == "__main__":
    asyncio.run(main()) 