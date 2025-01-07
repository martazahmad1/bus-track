import asyncio
import websockets
import json
import datetime
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
PORT = int(os.getenv('PORT', 10000))   # Main port from Render
WS_PORT = PORT + 1  # WebSocket port will be main port + 1

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

async def tcp_handler(reader, writer):
    """Handle TCP connections from the Pico"""
    addr = writer.get_extra_info('peername')
    logger.info(f'TCP Connection from {addr}')
    
    try:
        # Send welcome message
        welcome = json.dumps({"status": "connected", "message": "Welcome to Bus Tracker Server"}) + "\n"
        writer.write(welcome.encode())
        await writer.drain()
        
        buffer = ""
        while True:
            try:
                # Read data
                data = await reader.read(1024)
                if not data:
                    break
                
                try:
                    # Decode and buffer the data
                    buffer += data.decode('utf-8')
                    
                    # Process complete messages
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if not line.strip():
                            continue
                            
                        # Parse JSON message
                        message = json.loads(line)
                        message['server_time'] = datetime.datetime.now().strftime('%H:%M:%S')
                        message['source_ip'] = addr[0]
                        
                        logger.info(f"Received data from {addr}: {message}")
                        
                        # Broadcast to WebSocket clients
                        await broadcast_to_websockets(message)
                        
                        # Send acknowledgment
                        writer.write(b'OK\n')
                        await writer.drain()
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON received from {addr}: {e}")
                    writer.write(b'ERROR: Invalid JSON\n')
                    await writer.drain()
                    
            except Exception as e:
                logger.error(f"Error handling TCP data from {addr}: {e}")
                writer.write(b'ERROR: Internal server error\n')
                await writer.drain()
                break
                
    except Exception as e:
        logger.error(f"TCP Connection error from {addr}: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info(f'TCP Connection closed from {addr}')

async def main():
    """Main function to start both servers"""
    logger.info(f"Starting Bus Tracking Server...")
    
    # Create TCP server
    tcp_server = await asyncio.start_server(
        tcp_handler,
        HOST,
        PORT
    )
    logger.info(f"TCP server started on port {PORT}")
    
    # Create WebSocket server
    ws_server = await websockets.serve(
        websocket_handler,
        HOST,
        WS_PORT
    )
    logger.info(f"WebSocket server started on port {WS_PORT}")
    
    async with tcp_server, ws_server:
        await asyncio.gather(
            tcp_server.serve_forever(),
            ws_server.serve_forever()
        )

if __name__ == "__main__":
    asyncio.run(main()) 