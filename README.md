# Realtime Bus Tracking System

This project implements a realtime bus tracking system using a Raspberry Pi Pico with GPS module and a web interface for live tracking. The system is deployed and accessible globally.

## Project Structure

```
.
├── pico_tracker/     # Raspberry Pi Pico GPS tracking code
├── server/          # WebSocket server for realtime communication
└── frontend/         # Web interface with interactive map
```

## Live Demo

The system is deployed and accessible at: https://bustracker.devmartaz.online

Access Key: `bus123`

## Features

- Real-time GPS tracking with live updates
- Secure access with authentication
- Interactive map interface with fullscreen support
- Mobile-responsive design
- WebSocket communication for instant updates
- OLED display on the tracker for status information
- Route history visualization
- System status monitoring

## Hardware Setup

### Raspberry Pi Pico Setup

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

## Server Setup

1. Create a Python virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the server locally:
```bash
python server/socket_server.py
```

The server will run on port 10000

## Deployment

The system is deployed on Render.com with the following configuration:

1. Web Service Configuration:
   - Environment: Python
   - Build Command: Specified in render.yaml
   - Start Command: `python server/socket_server.py`

2. Environment Variables:
   - PORT: Automatically set by Render
   - RENDER: "true"

## Usage

1. Access the web interface at https://bustracker.devmartaz.online
2. Enter the access key: `bus123`
3. View real-time bus location on the map
4. Use the control buttons to:
   - Center on bus location
   - View route history
   - Toggle fullscreen mode
   - Clear history

## Requirements

- Raspberry Pi Pico with MicroPython
- NEO-6M GPS Module
- 0.96" OLED Display
- GSM Module for internet connectivity
- Python 3.9+ for server
- Modern web browser for frontend 