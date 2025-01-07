from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import json
from datetime import datetime

app = FastAPI()

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active WebSocket connections
active_connections: List[WebSocket] = []

class GPSData(BaseModel):
    latitude: float
    longitude: float
    timestamp: str

class PicoStatus(BaseModel):
    gps_status: str
    oled_status: str
    last_seen: str = None

# Store the latest Pico status
latest_pico_status = {
    "gps_status": "Unknown",
    "oled_status": "Unknown",
    "last_seen": None
}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # Send initial Pico status
        await websocket.send_json({
            "type": "pico_status",
            "data": latest_pico_status
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.post("/gps")
async def receive_gps_data(data: GPSData):
    # Update last seen time for Pico
    latest_pico_status["last_seen"] = datetime.now().strftime("%H:%M:%S")
    
    # Broadcast GPS data to all connected clients
    disconnected = []
    for connection in active_connections:
        try:
            # Send GPS data
            await connection.send_json({
                "type": "gps_data",
                "data": {
                    "latitude": data.latitude,
                    "longitude": data.longitude,
                    "timestamp": data.timestamp
                }
            })
            # Send updated Pico status
            await connection.send_json({
                "type": "pico_status",
                "data": latest_pico_status
            })
        except Exception:
            disconnected.append(connection)
    
    # Clean up disconnected clients
    for connection in disconnected:
        if connection in active_connections:
            active_connections.remove(connection)
    
    return {"status": "success"}

@app.post("/pico/status")
async def update_pico_status(status: PicoStatus):
    latest_pico_status.update({
        "gps_status": status.gps_status,
        "oled_status": status.oled_status,
        "last_seen": datetime.now().strftime("%H:%M:%S")
    })
    
    # Broadcast new status to all connected clients
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json({
                "type": "pico_status",
                "data": latest_pico_status
            })
        except Exception:
            disconnected.append(connection)
    
    # Clean up disconnected clients
    for connection in disconnected:
        if connection in active_connections:
            active_connections.remove(connection)
    
    return {"status": "success"}

@app.get("/")
async def root():
    return {"message": "Bus Tracking API is running"} 