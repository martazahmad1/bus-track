import asyncio
import websockets
import json
import logging
import os
from http import HTTPStatus
from pathlib import Path
import aiohttp
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server settings
HOST = '0.0.0.0'
try:
    PORT = int(os.getenv('PORT', '10000'))
except (ValueError, TypeError):
    logger.warning("Invalid PORT environment variable, using default port 10000")
    PORT = 10000

# Global variables
websocket_clients = set()
last_known_position = None

# Keep-alive settings
KEEP_ALIVE_INTERVAL = 10  # seconds
RENDER_URL = "https://bus-track-otfv.onrender.com"

async def send_heartbeat(websocket):
    """Send periodic heartbeat to keep connection alive"""
    while True:
        try:
            await websocket.send(json.dumps({"type": "heartbeat", "timestamp": time.time()}))
            await asyncio.sleep(15)  # Send heartbeat every 15 seconds
        except:
            break

async def keep_alive():
    """Periodically ping the server to keep it alive"""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(RENDER_URL) as response:
                    logger.debug(f"Keep-alive ping sent, status: {response.status}")
            except Exception as e:
                logger.error(f"Keep-alive ping failed: {str(e)}")
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)

def read_frontend_file():
    """Read the frontend HTML file"""
    try:
        frontend_path = Path(__file__).parent.parent / 'frontend' / 'index.html'
        if not frontend_path.exists():
            # Try current directory
            frontend_path = Path('index.html')
        
        if frontend_path.exists():
            with open(frontend_path, 'rb') as f:
                return f.read()
        else:
            logger.error(f"Frontend file not found at {frontend_path}")
            return None
    except Exception as e:
        logger.error(f"Error reading frontend file: {str(e)}")
        return None

async def process_request(path, request_headers):
    """Process HTTP requests before WebSocket upgrade"""
    logger.info(f"Processing request: {path}")
    
    # Handle WebSocket upgrade
    if request_headers.get('Upgrade', '').lower() == 'websocket':
        return None
    
    # Handle HTTP requests
    if path == "/" or path == "/index.html":
        content = read_frontend_file()
        if content:
            return HTTPStatus.OK, [
                ("Content-Type", "text/html"),
                ("Content-Length", str(len(content)))
            ], content
    
    # Return 404 for other paths
    return HTTPStatus.NOT_FOUND, [], b"404 Not Found"

async def broadcast_message(message):
    """Broadcast message to all connected WebSocket clients"""
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

async def handle_tcp_connection(reader, writer):
    """Handle TCP connections from the Pico tracker"""
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                break
            
            try:
                message = data.decode()
                logger.info(f"Received TCP message: {message}")
                
                # Try to parse as JSON and broadcast to WebSocket clients
                json_data = json.loads(message)
                if json_data.get("type") == "gps":
                    global last_known_position
                    last_known_position = json_data
                    await broadcast_message(message)
                
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON data")
            except Exception as e:
                logger.error(f"Error processing TCP message: {str(e)}")
    except Exception as e:
        logger.error(f"TCP connection error: {str(e)}")
    finally:
        writer.close()
        await writer.wait_closed()

async def handle_websocket(websocket, path):
    """Handle WebSocket connections from web clients"""
    logger.info("New WebSocket client connected")
    websocket_clients.add(websocket)
    
    # Start heartbeat task for this connection
    heartbeat_task = asyncio.create_task(send_heartbeat(websocket))
    
    # Send initial state if available
    if last_known_position:
        try:
            await websocket.send(json.dumps(last_known_position))
        except Exception as e:
            logger.error(f"Error sending initial state: {str(e)}")
    
    try:
        async for message in websocket:
            logger.debug(f"Received WebSocket message: {message}")
            # Handle any client messages if needed
            pass
    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket client disconnected")
    finally:
        heartbeat_task.cancel()  # Cancel heartbeat when connection closes
        websocket_clients.remove(websocket)

async def main():
    """Main function to start the server"""
    logger.info(f"Starting Bus Tracking Server on port {PORT}...")
    
    # Start WebSocket server for both web clients and Pico tracker
    server = await websockets.serve(
        handle_websocket,
        HOST,
        PORT,
        process_request=process_request,
        ping_interval=None,  # Disable ping to allow TCP connections
        compression=None,
        max_size=10_485_760,  # 10MB max message size
        subprotocols=['bus-tracker']
    )
    
    logger.info(f"Server started on port {PORT}")
    
    # Start keep-alive task
    keep_alive_task = asyncio.create_task(keep_alive())
    
    try:
        await server.wait_closed()
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
    finally:
        keep_alive_task.cancel()
        logger.info("Server shutting down...")

if __name__ == "__main__":
    asyncio.run(main()) 