from machine import UART, Pin, I2C
import time
import json
from micropyGPS import MicropyGPS
from ssd1306 import SSD1306_I2C

# Module Status
module_status = {
    "gps": {
        "status": "Initializing",
        "fix": False,
        "satellites": 0,
        "hdop": 0.0,
        "altitude": 0.0,
        "speed_kmh": 0.0,
        "course": 0.0,
        "last_fix": None
    },
    "gsm": {
        "status": "Initializing",
        "network": False,
        "internet": False,
        "last_connect": None
    },
    "oled": {
        "status": "Initializing",
        "last_update": None,
        "display_content": ["", "", "", "", "", ""]  # Current display content
    },
    "server": {
        "status": "Disconnected",
        "last_send": None,
        "connected": False
    }
}

# Server configuration
SERVER_IP = "bus-track-otfv.onrender.com"  # Using default Render.com URL
SERVER_PORT = "80"  # Using standard HTTP port

def send_at_command(command, timeout=1000):
    """Send an AT command and wait for response"""
    print(f"Sending: {command}")
    
    # Clear any pending data
    while gsm_uart.any():
        gsm_uart.read()
    
    # Send the command
    gsm_uart.write(command.encode() + b'\r\n')
    time.sleep_ms(100)  # Short delay after sending
    
    # Wait for response
    response = ""
    start_time = time.ticks_ms()
    
    while (time.ticks_ms() - start_time) < timeout:
        if gsm_uart.any():
            try:
                data = gsm_uart.read()
                if data:
                    response += data.decode('utf-8', 'ignore')
                    if 'OK' in response or 'ERROR' in response:
                        break
            except Exception as e:
                print(f"Read error: {str(e)}")
        time.sleep_ms(100)
    
    print(f"Response: {response}")
    return response

def wait_response(timeout=1000):
    response = ""
    start_time = time.ticks_ms()
    
    while (time.ticks_ms() - start_time) < timeout:
        if gsm_uart.any():
            try:
                # Read all available bytes
                data = gsm_uart.read()
                if data:
                    try:
                        response += data.decode('ascii', errors='replace')
                    except:
                        continue
                
                # Check for response completion
                if "OK" in response or "ERROR" in response or "+CME ERROR" in response:
                    print(f"Full response: {response}")  # Debug print
                    break
            except Exception as e:
                print(f"Read error: {str(e)}")
        time.sleep_ms(100)
    
    return response

# Initialize UART for GSM
gsm_uart = None
gsm_initialized = False

def init_uart_gsm(baudrate=115200):
    """Initialize GSM UART with specified baudrate"""
    global gsm_uart, gsm_initialized
    try:
        print(f"\nInitializing GSM UART with baudrate {baudrate}...")
        gsm_uart = UART(1, baudrate=baudrate, tx=Pin(4), rx=Pin(5))
        gsm_initialized = True
        return True
    except Exception as e:
        print(f"GSM UART Error: {str(e)}")
        gsm_initialized = False
        return False

def init_gsm():
    global gsm_uart, gsm_initialized
    
    update_display("GSM Init", "Starting...")
    time.sleep(2)  # Give module time to stabilize
    
    # Initialize UART first if not already initialized
    if not gsm_initialized:
        if not init_uart_gsm(9600):  # Start with 9600 baud
            update_display("GSM Error", "UART Failed")
            return False
    
    # Test AT command
    update_display("GSM Init", "Testing AT...")
    response = send_at_command("AT")
    if "OK" not in response:
        update_display("GSM Error", "AT Failed")
        return False
    
    # Turn off echo
    update_display("GSM Init", "Setup...")
    response = send_at_command("ATE0")
    if "OK" not in response:
        update_display("GSM Error", "Echo Failed")
        return False
    
    # Check network registration
    update_display("GSM Init", "Network...")
    response = send_at_command("AT+CREG?")
    if not (",1" in response or ",5" in response):
        update_display("GSM Error", "No Network")
        return False
    
    # Check signal strength
    update_display("GSM Init", "Signal...")
    response = send_at_command("AT+CSQ")
    if "+CSQ:" in response:
        try:
            signal = int(response.split("+CSQ: ")[1].split(",")[0])
            if signal < 5:
                update_display("GSM Warning", f"Weak signal: {signal}")
                time.sleep(2)
            else:
                update_display("GSM Init", f"Signal OK: {signal}")
        except:
            pass
    
    # Configure GPRS
    update_display("GSM Init", "Internet...")
    
    # First, check if we're already registered to GPRS
    response = send_at_command('AT+CGREG?')
    if not (',1' in response or ',5' in response):
        update_display("GSM Init", "Wait GPRS...")
        time.sleep(2)
        response = send_at_command('AT+CGREG?')
        if not (',1' in response or ',5' in response):
            update_display("GSM Error", "No GPRS")
            return False
    
    # Shut down any existing connections
    update_display("GSM Init", "Reset GPRS...")
    send_at_command("AT+CIPSHUT", 2000)
    time.sleep(1)
    
    # Disable all PDP contexts first
    send_at_command("AT+SAPBR=0,1", 2000)
    time.sleep(1)
    
    # Set bearer settings for Ufone
    update_display("GSM Init", "Set APN...")
    send_at_command('AT+SAPBR=3,1,"Contype","GPRS"')
    response = send_at_command('AT+SAPBR=3,1,"APN","ufone.internet"')
    if "OK" not in response:
        update_display("GSM Error", "APN Failed")
        return False
    time.sleep(1)
    
    # Try to enable GPRS multiple times
    for attempt in range(3):
        update_display("GSM Init", f"GPRS try {attempt+1}")
        response = send_at_command("AT+SAPBR=1,1", 5000)
        if "OK" in response:
            # Verify we got an IP
            response = send_at_command("AT+SAPBR=2,1", 2000)
            if "+SAPBR: 1,1" in response:
                module_status["gsm"]["internet"] = True
                module_status["gsm"]["status"] = "Internet OK"
                module_status["gsm"]["last_connect"] = time.time()
                update_display("GSM Ready", "Connected")
                return True
        time.sleep(2)
    
    update_display("GSM Error", "GPRS Failed")
    return False

def connect_server():
    update_display("Server", "Connecting...")
    # First check if GPRS is still active and get IP
    response = send_at_command('AT+SAPBR=2,1', 2000)
    print("GPRS Status:", response)  # Debug print
    if '+SAPBR: 1,1' not in response:
        # Try to re-establish GPRS
        update_display("Server", "Restart GPRS")
        send_at_command("AT+SAPBR=0,1", 2000)  # Disable bearer
        time.sleep(1)
        send_at_command('AT+SAPBR=3,1,"Contype","GPRS"')
        send_at_command('AT+SAPBR=3,1,"APN","ufone.internet"')
        response = send_at_command("AT+SAPBR=1,1", 5000)
        if "OK" not in response:
            update_display("Server", "No GPRS")
            return False
    
    # Configure TCP/IP
    update_display("Server", "TCP Setup...")
    send_at_command("AT+CIPSHUT", 2000)  # Reset TCP/IP
    
    # Initialize TCP/IP
    response = send_at_command("AT+CSTT=\"ufone.internet\"", 2000)
    if "OK" not in response:
        update_display("Server", "APN Failed")
        return False
    
    # Bring up wireless connection
    response = send_at_command("AT+CIICR", 10000)
    if "OK" not in response:
        update_display("Server", "CIICR Failed")
        return False
    
    # Get IP address
    response = send_at_command("AT+CIFSR", 2000)
    print("IP Response:", response)  # Debug print
    if not any(char.isdigit() for char in response):
        update_display("Server", "No IP")
        return False
    
    # Start TCP connection with longer timeout
    update_display("Server", "TCP Connect...")
    cmd = f'AT+CIPSTART="TCP","{SERVER_IP}",{SERVER_PORT}'
    print("TCP Command:", cmd)  # Debug print
    response = send_at_command(cmd, 15000)  # Increased timeout
    time.sleep(1)
    print("TCP Response:", response)  # Debug print
    time.sleep(1)
    
    if "CONNECT OK" in response or "ALREADY CONNECT" in response:
        module_status["server"]["status"] = "Connected"
        module_status["server"]["connected"] = True
        module_status["server"]["last_send"] = time.time()
        update_display("Server", "Connected")
        return True
    else:
        module_status["server"]["status"] = "Failed"
        update_display("Server", "TCP Failed")
        return False

def send_data(data):
    if not module_status["server"]["connected"]:
        return False
    
    try:
        json_data = json.dumps(data)
        send_at_command('AT+CIPSEND=' + str(len(json_data)))
        response = wait_response(1000)
        
        if ">" in response:
            send_at_command(json_data)
            response = wait_response(2000)
            
            if "SEND OK" in response:
                module_status["server"]["last_send"] = time.time()
                return True
    except Exception as e:
        print("Send Error:", str(e))
    
    return False

def update_display(line1, line2="", line3="", line4="", line5="", line6=""):
    if not oled_initialized:
        print(f"Display message (OLED offline):\n{line1}\n{line2}\n{line3}\n{line4}\n{line5}\n{line6}")
        return
    try:
        # Update the display content in module_status
        module_status["oled"]["display_content"] = [
            str(line1)[:21],
            str(line2)[:21],
            str(line3)[:21],
            str(line4)[:21],
            str(line5)[:21],
            str(line6)[:21]
        ]
        
        oled.fill(0)  # Clear display
        # Super compact spacing (8 pixels) and support for 6 lines
        oled.text(module_status["oled"]["display_content"][0], 0, 0)     # Line 1 at y=0
        oled.text(module_status["oled"]["display_content"][1], 0, 8)     # Line 2 at y=8
        oled.text(module_status["oled"]["display_content"][2], 0, 16)    # Line 3 at y=16
        oled.text(module_status["oled"]["display_content"][3], 0, 24)    # Line 4 at y=24
        oled.text(module_status["oled"]["display_content"][4], 0, 32)    # Line 5 at y=32
        oled.text(module_status["oled"]["display_content"][5], 0, 40)    # Line 6 at y=40
        oled.show()
        
        module_status["oled"]["last_update"] = time.time()
        module_status["oled"]["status"] = "OK"
    except Exception as e:
        print(f"Display Error: {str(e)}")
        module_status["oled"]["status"] = "Error"

# Initialize UART for GPS
try:
    print("Initializing GPS UART...")
    gps_uart = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))
    gps = MicropyGPS()
    gps_initialized = True
    module_status["gps"]["status"] = "Initialized"
    print("GPS initialized successfully")
except Exception as e:
    print(f"GPS Error: {str(e)}")
    gps_initialized = False
    module_status["gps"]["status"] = "Error"

# Initialize I2C for OLED Display (128x64 resolution)
try:
    print("\nInitializing I2C and OLED Display...")
    i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400000)
    oled = SSD1306_I2C(128, 64, i2c)
    oled_initialized = True
    module_status["oled"]["status"] = "OK"
    print("OLED initialized successfully")
except Exception as e:
    print(f"I2C/OLED Error: {str(e)}")
    oled_initialized = False
    module_status["oled"]["status"] = "Error"

def main():
    print("\n=== Starting Bus Tracker ===")
    
    if not oled_initialized:
        print("OLED Init Failed - Check connections")
        return
    
    update_display("Bus Tracker", "Starting up...")
    time.sleep(1)
    
    # Step 1: Initialize GSM and connect to internet
    while not init_gsm():
        update_display("GSM Error", "Check SIM", "card & signal")
        time.sleep(2)
    
    # Step 2: Connect to server
    while not module_status["server"]["connected"]:
        if connect_server():
            break
        update_display("Server Retry", "in 5s...")
        time.sleep(5)
    
    # Step 3: Wait for GPS fix
    first_data_sent = False
    
    while True:
        gps_data = None
        gps_status_msg = "Wait..."
        
        # Get GPS Data
        if gps_initialized:
            start_time = time.time()
            while time.time() - start_time < 1.0:
                if gps_uart.any():
                    char = gps_uart.read(1)
                    if char is None:
                        continue
                    try:
                        stat = gps.update(str(char, 'ascii'))
                        if stat:
                            module_status["gps"].update({
                                "fix": gps.fix_stat,
                                "satellites": gps.satellites_in_use,
                                "hdop": gps.hdop,
                                "altitude": gps.altitude,
                                "speed_kmh": gps.speed[2],
                                "course": gps.course,
                            })
                            
                            if gps.fix_stat:
                                lat = gps.latitude[0] + (gps.latitude[1] / 60)
                                if gps.latitude[2] == 'S':
                                    lat = -lat
                                
                                lon = gps.longitude[0] + (gps.longitude[1] / 60)
                                if gps.longitude[2] == 'W':
                                    lon = -lon
                                
                                timestamp = f"{gps.timestamp[0]:02d}:{gps.timestamp[1]:02d}:{int(gps.timestamp[2]):02d}"
                                module_status["gps"]["status"] = "Fix OK"
                                module_status["gps"]["last_fix"] = time.time()
                                
                                gps_data = {
                                    "type": "gps",
                                    "latitude": lat,
                                    "longitude": lon,
                                    "timestamp": timestamp,
                                    "status": module_status
                                }
                    except Exception as e:
                        print(f"GPS Parse Error: {str(e)}")
        
        # Update display with current status
        if gps_data:
            if not first_data_sent:
                update_display(
                    "First Fix OK",
                    "Sending Vertices...",
                    f"Sats:{module_status['gps']['satellites']}",
                    f"GSM:{module_status['gsm']['status']}"
                )
                
                # Try to send first data
                if send_data(gps_data):
                    first_data_sent = True
                    update_display(
                        "System Ready",
                        f"GPS:{module_status['gps']['status']}",
                        f"GSM:{module_status['gsm']['status']}",
                        f"Srv:{module_status['server']['status']}"
                    )
            else:
                # Regular update display
                update_display(
                    f"GPS:{module_status['gps']['status']}",
                    f"Sats:{module_status['gps']['satellites']}",
                    f"GSM:{module_status['gsm']['status']}",
                    f"Srv:{module_status['server']['status']}"
                )
                
                # Send data in real-time
                send_data(gps_data)
        else:
            update_display(
                f"GPS:{module_status['gps']['status']}",
                f"GSM:{module_status['gsm']['status']}",
                f"Srv:{module_status['server']['status']}",
                "Wait GPS fix..."
            )
        
        time.sleep(0.1)

if __name__ == "__main__":
    main() 

