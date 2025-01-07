import socket
import json
import threading
import datetime
from websockets.server import serve
import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# WebSocket clients
websocket_clients = set()

# Socket Server Configuration
HOST = '0.0.0.0'  # Listen on all available interfaces
TCP_PORT = int(os.getenv('PORT', 8000))   # Use PORT from environment or default to 8000
WS_PORT = TCP_PORT  # Use same port for WebSocket on Render

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

def handle_tcp_client(client_socket, address):
    """Handle TCP connection from the Pico"""
    logger.info(f"Accepted connection from {address}")
    
    buffer = ""
    while True:
        try:
            # Receive data
            data = client_socket.recv(1024).decode('utf-8')
            if not data:
                break
            
            buffer += data
            
            # Process complete JSON messages
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                try:
                    # Parse JSON data
                    message = json.loads(line)
                    
                    # Add timestamp and source IP
                    message['server_time'] = datetime.datetime.now().strftime('%H:%M:%S')
                    message['source_ip'] = address[0]
                    
                    # Log the received data
                    logger.info(f"Received data from {address}: {message}")
                    
                    # Broadcast to WebSocket clients
                    asyncio.run(broadcast_to_websockets(message))
                    
                    # Send acknowledgment back to Pico
                    client_socket.send(b'OK\n')
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received from {address}: {e}")
                    client_socket.send(b'ERROR: Invalid JSON\n')
                
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
            break
    
    logger.info(f"Client {address} disconnected")
    client_socket.close()

async def run_websocket_server():
    """Run the WebSocket server for frontend connections"""
    async with serve(websocket_handler, HOST, WS_PORT):
        logger.info(f"WebSocket server started on port {WS_PORT}")
        await asyncio.Future()  # run forever

def run_tcp_server():
    """Run the TCP server for Pico connections"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, TCP_PORT))
    server.listen(5)
    
    logger.info(f"TCP server started on port {TCP_PORT}")
    
    while True:
        client_sock, address = server.accept()
        client_handler = threading.Thread(
            target=handle_tcp_client,
            args=(client_sock, address)
        )
        client_handler.start()

def main():
    """Main function to start both servers"""
    logger.info(f"Starting Bus Tracking Server on port {TCP_PORT}...")
    
    # Start TCP server in a separate thread
    tcp_thread = threading.Thread(target=run_tcp_server)
    tcp_thread.daemon = True
    tcp_thread.start()
    
    # Start WebSocket server in the main thread
    asyncio.run(run_websocket_server())

if __name__ == "__main__":
    main() 