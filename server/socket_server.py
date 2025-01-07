import asyncio
import websockets
import json
import datetime
import logging
import os
from dotenv import load_dotenv
from http import HTTPStatus

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# WebSocket clients
websocket_clients = set()

# Socket Server Configuration
HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = int(os.getenv('PORT', 10000))   # Use port from Render

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
        
        # Keep the connection alive and handle incoming messages
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"Received WebSocket message: {data}")
            except json.JSONDecodeError:
                pass  # Ignore invalid JSON from WebSocket clients
            
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

async def handle_connection(reader, writer):
    """Handle incoming connections and route to appropriate handler"""
    try:
        # Read the first line to determine the request type
        first_line = await reader.readline()
        
        # Handle health check requests (empty connections)
        if not first_line:
            writer.close()
            return
            
        if b"GET" in first_line:
            # This looks like an HTTP/WebSocket request
            logger.info("HTTP/WebSocket request received")
            headers = []
            while True:
                line = await reader.readline()
                if line == b'\r\n':
                    break
                headers.append(line)
            
            # Check if it's a health check request
            if b"GET / HTTP" in first_line:
                # Send a simple 200 OK response
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                    b"Server is running"
                )
                writer.write(response)
                await writer.drain()
                return
            
            # Handle WebSocket upgrade request
            if any(b"Upgrade: websocket" in line for line in headers):
                logger.info("WebSocket connection detected")
                ws_protocol = websockets.WebSocketServerProtocol(
                    max_size=2**20,  # 1MB max message size
                    max_queue=2**5,  # 32 messages max in queue
                )
                ws_protocol.connection_made(writer.transport)
                await ws_protocol.handler(websocket_handler)
            else:
                # Regular HTTP request, send 400 Bad Request
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
        else:
            # Handle as TCP connection from Pico
            addr = writer.get_extra_info('peername')
            logger.info(f'TCP Connection from {addr}')
            
            # Send welcome message
            welcome = json.dumps({"status": "connected", "message": "Welcome to Bus Tracker Server"}) + "\n"
            writer.write(welcome.encode())
            await writer.drain()
            
            buffer = ""
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                
                try:
                    buffer += data.decode('utf-8')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if not line.strip():
                            continue
                        
                        message = json.loads(line)
                        message['server_time'] = datetime.datetime.now().strftime('%H:%M:%S')
                        message['source_ip'] = addr[0]
                        
                        logger.info(f"Received data from {addr}: {message}")
                        await broadcast_to_websockets(message)
                        
                        writer.write(b'OK\n')
                        await writer.drain()
                        
                except json.JSONDecodeError as e:
                    if buffer.strip():  # Only log if there's actual content
                        logger.warning(f"Invalid JSON received from {addr}: {e}")
                    writer.write(b'ERROR: Invalid JSON\n')
                    await writer.drain()
                    
    except Exception as e:
        if not str(e).startswith('[Errno 104]'):  # Don't log normal connection resets
            logger.error(f"Connection error: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception as e:
            if not str(e).startswith('[Errno 104]'):  # Don't log normal connection resets
                logger.error(f"Error closing connection: {e}")

async def main():
    """Main function to start the server"""
    logger.info(f"Starting Bus Tracking Server on port {PORT}...")
    
    server = await asyncio.start_server(
        handle_connection,
        HOST,
        PORT
    )
    
    logger.info(f"Server started on port {PORT}")
    
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main()) 