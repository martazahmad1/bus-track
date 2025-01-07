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

async def handle_websocket(websocket, path):
    """Handle WebSocket connections"""
    try:
        # Check if this is a frontend client (has proper WebSocket headers)
        if websocket.request_headers.get('Upgrade', '').lower() == 'websocket':
            # Handle frontend WebSocket client
            websocket_clients.add(websocket)
            client_info = websocket.remote_address
            logger.info(f"New WebSocket client connected from {client_info}")
            
            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        logger.info(f"Received WebSocket message: {data}")
                        await broadcast_to_websockets(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from WebSocket client")
            except Exception as e:
                logger.error(f"WebSocket error: {str(e)}")
            finally:
                if websocket in websocket_clients:
                    websocket_clients.remove(websocket)
                logger.info(f"WebSocket client disconnected")
        else:
            # Handle Pico TCP client
            client_info = websocket.remote_address
            logger.info(f"New TCP client connected from {client_info}")
            
            # Send welcome message
            welcome = json.dumps({"status": "connected", "message": "Welcome to Bus Tracker Server"}) + "\n"
            await websocket.send(welcome)
            
            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        data['server_time'] = datetime.datetime.now().strftime('%H:%M:%S')
                        data['source_ip'] = client_info[0]
                        logger.info(f"Received TCP message: {data}")
                        await broadcast_to_websockets(data)
                        await websocket.send('OK\n')
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from TCP client")
                        await websocket.send('ERROR: Invalid JSON\n')
            except Exception as e:
                if not str(e).startswith('[Errno 104]'):
                    logger.error(f"TCP error: {str(e)}")
            finally:
                logger.info(f"TCP client disconnected")
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")

async def main():
    """Main function to start the server"""
    logger.info(f"Starting Bus Tracking Server on port {PORT}...")
    
    # Create WebSocket server
    async with websockets.serve(handle_websocket, HOST, PORT) as server:
        logger.info(f"Server started on port {PORT}")
        await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main()) 