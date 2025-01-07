# Local Bus Tracking System

This project implements a local bus tracking system using a Raspberry Pi Pico with GPS module and a web interface for real-time tracking.

## Project Structure

```
.
├── pico_tracker/     # Raspberry Pi Pico GPS tracking code
├── backend/          # FastAPI backend server
└── frontend/         # Web interface with map
```

## Setup Instructions

### 1. Raspberry Pi Pico Setup

1. Connect the hardware:
   - GPS Module (NEO-6M):
     - VCC → 3.3V
     - GND → GND
     - TX → GPIO0 (Pin 1)
     - RX → GPIO1 (Pin 2)
   
   - OLED Display:
     - VCC → 3.3V
     - GND → GND
     - SDA → GPIO8
     - SCL → GPIO9

2. Install required libraries on Pico:
   - Copy `micropyGPS.py` to the Pico
   - Copy `ssd1306.py` to the Pico
   - Copy `main.py` from `pico_tracker/` to the Pico

### 2. Backend Setup

1. Create a Python virtual environment:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the server:
```bash
uvicorn main:app --reload
```

The backend will run on http://localhost:8000

### 3. Frontend Setup

1. Simply open `frontend/index.html` in a web browser
2. The map will automatically connect to the backend via WebSocket

## Usage

1. Power up the Raspberry Pi Pico with GPS module
2. Start the backend server
3. Open the frontend in a web browser
4. The map will show the real-time position of the bus

## Features

- Real-time GPS tracking
- WebSocket communication for live updates
- Interactive map interface
- OLED display on the tracker for status information

## Requirements

- Raspberry Pi Pico with MicroPython
- NEO-6M GPS Module
- 0.96" OLED Display
- Python 3.7+ for backend
- Modern web browser for frontend 