import socket
import json
import threading
import datetime
import asyncio
import logging
import os
from dotenv import load_dotenv
import websockets

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# WebSocket clients
websocket_clients = set()

# Socket Server Configuration
HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = int(os.getenv('PORT', 8000))   # Use PORT from environment or default to 8000

# Store last known position
last_known_position = None

async def websocket_handler(websocket):
    """Handle WebSocket connections from the frontend"""
    try:
        websocket_clients.add(websocket)
        logger.info(f"New WebSocket client connected. Total clients: {len(websocket_clients)}")
        
        # Send last known position if available
        if last_known_position:
            await websocket.send(json.dumps(last_known_position))
        
        # Keep the connection alive
        await websocket.wait_closed()
    finally:
        websocket_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected. Remaining clients: {len(websocket_clients)}")

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
            websocket_clients.remove(client)

class TCPProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport
        self.address = transport.get_extra_info('peername')
        self.buffer = ""
        logger.info(f'TCP Connection from {self.address}')

    def data_received(self, data):
        try:
            self.buffer += data.decode('utf-8')
            
            while '\n' in self.buffer:
                line, self.buffer = self.buffer.split('\n', 1)
                try:
                    message = json.loads(line)
                    message['server_time'] = datetime.datetime.now().strftime('%H:%M:%S')
                    message['source_ip'] = self.address[0]
                    
                    logger.info(f"Received data from {self.address}: {message}")
                    
                    # Use asyncio.create_task to run broadcast_to_websockets
                    asyncio.create_task(broadcast_to_websockets(message))
                    
                    self.transport.write(b'OK\n')
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received from {self.address}: {e}")
                    self.transport.write(b'ERROR: Invalid JSON\n')
                
        except Exception as e:
            logger.error(f"Error handling TCP data: {e}")

    def connection_lost(self, exc):
        logger.info(f'TCP Connection closed from {self.address}')

async def main():
    """Main function to start both servers"""
    logger.info(f"Starting Bus Tracking Server on port {PORT}...")
    
    loop = asyncio.get_running_loop()
    
    # Create TCP server
    tcp_server = await loop.create_server(
        TCPProtocol,
        HOST,
        PORT
    )
    
    # Create WebSocket server
    ws_server = await websockets.serve(
        websocket_handler,
        HOST,
        PORT + 1  # Use next port for WebSocket
    )
    
    logger.info(f"TCP server started on port {PORT}")
    logger.info(f"WebSocket server started on port {PORT + 1}")
    
    await asyncio.gather(
        tcp_server.serve_forever(),
        ws_server.serve_forever()
    )

if __name__ == "__main__":
    asyncio.run(main()) 