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
ws_server = None  # Global WebSocket server instance

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
    '/opt/render/project/src/index.html'  # Render.com specific path
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

async def handle_http_request(first_line, headers, writer):
    """Handle HTTP requests and serve frontend files"""
    try:
        logger.info(f"Handling HTTP request: {first_line}")
        if b"GET / HTTP" in first_line or b"GET /index.html HTTP" in first_line:
            # Serve the frontend HTML file
            content = read_frontend_file()
            if content:
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/html\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
                writer.write(response + content)
                logger.info("Successfully served frontend file")
            else:
                # If we can't read the file, send 500 error with message
                error_message = b"Failed to load frontend file. Please check server logs."
                writer.write(
                    b"HTTP/1.1 500 Internal Server Error\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"Content-Length: " + str(len(error_message)).encode() + b"\r\n"
                    b"\r\n" + error_message
                )
                logger.error("Failed to serve frontend file")
        else:
            # For any other path, send 404 with message
            error_message = b"Page not found"
            writer.write(
                b"HTTP/1.1 404 Not Found\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: " + str(len(error_message)).encode() + b"\r\n"
                b"\r\n" + error_message
            )
            logger.info(f"404 for path: {first_line}")
    except Exception as e:
        logger.error(f"Error handling HTTP request: {str(e)}")
        writer.write(b"HTTP/1.1 500 Internal Server Error\r\n\r\n")
    
    await writer.drain()

async def websocket_handler(websocket):
    """Handle WebSocket connections from the frontend"""
    try:
        # Add the new client to our set
        websocket_clients.add(websocket)
        client_info = websocket.remote_address
        logger.info(f"New WebSocket client connected from {client_info}. Total clients: {len(websocket_clients)}")
        
        # Send initial state
        if last_known_position:
            try:
                await websocket.send(json.dumps(last_known_position))
                logger.info(f"Sent last known position to new client: {last_known_position}")
            except Exception as e:
                logger.error(f"Error sending initial state: {str(e)}")
        
        # Keep connection alive with periodic pings
        while True:
            try:
                # Wait for a message or send a ping every 30 seconds
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30)
                    # Process the received message
                    data = json.loads(message)
                    logger.info(f"Received WebSocket message from {client_info}: {data}")
                    
                    if isinstance(data, dict):
                        message_type = data.get('type')
                        if message_type == 'ping':
                            await websocket.send(json.dumps({'type': 'pong'}))
                        else:
                            await broadcast_to_websockets(data)
                except asyncio.TimeoutError:
                    # Send a ping if no message received
                    await websocket.ping()
                    continue
                
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"WebSocket connection closed by client {client_info}")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket handler: {str(e)}")
                break
    
    finally:
        # Clean up when the connection closes
        websocket_clients.remove(websocket)
        logger.info(f"WebSocket client {client_info} disconnected. Remaining clients: {len(websocket_clients)}")

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
            
            # Handle WebSocket upgrade request
            if any(b"Upgrade: websocket" in line for line in headers):
                logger.info("WebSocket connection detected")
                try:
                    # Create WebSocket connection using the existing transport
                    protocol = websockets.WebSocketServerProtocol(
                        ws_handler=websocket_handler,
                        ws_server=ws_server,
                        max_size=2**20,  # 1MB max message size
                        max_queue=2**5,  # 32 messages max in queue
                    )
                    protocol.connection_made(writer.transport)
                    await protocol.handler()
                except Exception as e:
                    logger.error(f"WebSocket error: {str(e)}")
            else:
                # Handle regular HTTP request
                await handle_http_request(first_line, headers, writer)
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
    global ws_server
    
    logger.info(f"Starting Bus Tracking Server on port {PORT}...")
    
    # Create the WebSocket server
    ws_server = websockets.WebSocketServer(
        host=HOST,
        port=PORT,
        ping_interval=20,
        ping_timeout=30,
        close_timeout=10
    )
    
    # Create the TCP server
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
if __name__ == "__main__":
    asyncio.run(main()) 