import asyncio
import websockets
import json
import logging
import os
from http import HTTPStatus
from pathlib import Path
import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server settings
HOST = '0.0.0.0'
PORT = int(os.getenv('PORT', '10000'))

# Global variables
websocket_clients = set()
last_known_position = None

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

async def handle_websocket(websocket, path):
    """Handle WebSocket connections from web clients"""
    logger.info("New WebSocket client connected")
    websocket_clients.add(websocket)
    
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
        websocket_clients.remove(websocket)

def main(environ, start_response):
    """WSGI application entry point"""
    if environ.get('HTTP_UPGRADE', '').lower() == 'websocket':
        ws_server = websockets.serve(
            handle_websocket,
            HOST,
            PORT,
            ping_interval=None,
            compression=None,
            max_size=10_485_760,  # 10MB max message size
            subprotocols=['bus-tracker']
        )
        asyncio.get_event_loop().run_until_complete(ws_server)
        asyncio.get_event_loop().run_forever()
    return []

if __name__ == "__main__":
    asyncio.run(main(None, None)) 