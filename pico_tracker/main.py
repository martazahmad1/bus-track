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
    gsm_uart.write(command.encode() + b'\r\n')
    response = wait_response(timeout)
    return response

def wait_response(timeout=1000):
    response = ""
    start_time = time.ticks_ms()
    
    while (time.ticks_ms() - start_time) < timeout:
        if gsm_uart.any():
            try:
                # Read byte by byte and decode safely
                byte = gsm_uart.read(1)
                if byte:
                    try:
                        char = byte.decode('ascii', errors='replace')
                        response += char
                        print(char, end='')  # Print each character for debugging
                    except:
                        continue
                if "OK" in response or "ERROR" in response:
                    print("\nResponse:", response)  # Print full response
                    break
            except Exception as e:
                print("Read error:", str(e))
                continue
        time.sleep_ms(100)
    return response

def init_gsm():
    update_display("GSM Init", "Starting...")
    time.sleep(2)  # Give module time to stabilize
    
    # Test AT command multiple times
    for _ in range(3):
        update_display("GSM Init", "Testing AT...")
        response = send_at_command("AT")
        if "OK" in response:
            break
        time.sleep(1)
    else:
        update_display("GSM Error", "AT Failed", "Check wiring")
        return False
    
    # Check SIM status
    update_display("GSM Init", "Checking SIM...")
    response = send_at_command("AT+CPIN?")
    if "READY" not in response:
        update_display("GSM Error", "SIM not ready", "Check SIM card")
        return False
    
    # Check signal quality
    update_display("GSM Init", "Checking signal...")
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
    
    # Wait for network registration
    update_display("GSM Init", "Connecting to", "network...")
    attempts = 0
    while attempts < 20:  # Try for about 20 seconds
        response = send_at_command("AT+CREG?")
        if ",1" in response or ",5" in response:
            module_status["gsm"]["network"] = True
            module_status["gsm"]["status"] = "Network OK"
            break
        attempts += 1
        update_display("GSM Init", f"Network try {attempts}")
        time.sleep(1)
    else:
        update_display("GSM Error", "Network timeout", "Check coverage")
        return False
    
    # Configure GPRS
    update_display("GSM Init", "Setting up", "internet...")
    
    # Disable GPRS first
    send_at_command("AT+CIPSHUT")
    time.sleep(1)
    
    # Set bearer settings for Ufone
    send_at_command('AT+SAPBR=3,1,"Contype","GPRS"')
    send_at_command('AT+SAPBR=3,1,"APN","ufone.internet"')  # Ufone APN
    time.sleep(1)
    
    # Enable GPRS
    attempts = 0
    while attempts < 3:
        update_display("GSM Init", f"GPRS try {attempts+1}")
        response = send_at_command("AT+SAPBR=1,1")
        if "OK" in response:
            module_status["gsm"]["internet"] = True
            module_status["gsm"]["status"] = "Internet OK"
            module_status["gsm"]["last_connect"] = time.time()
            update_display("GSM Ready", "Internet", "Connected")
            return True
        attempts += 1
        time.sleep(2)
    
    update_display("GSM Error", "GPRS Failed", "Check package")
    return False

def connect_server():
    update_display("Server", "Connecting...")
    
    # Start TCP connection
    send_at_command('AT+CIPSTART="TCP","' + SERVER_IP + '",' + SERVER_PORT)
    response = wait_response(5000)
    
    if "CONNECT OK" in response:
        module_status["server"]["status"] = "Connected"
        module_status["server"]["connected"] = True
        module_status["server"]["last_send"] = time.time()
        update_display("Server", "Connected")
        return True
    else:
        module_status["server"]["status"] = "Failed"
        update_display("Server", "Connection", "Failed")
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

# Initialize UART for GSM
try:
    print("\nInitializing GSM UART...")
    gsm_uart = UART(1, baudrate=115200, tx=Pin(4), rx=Pin(5))
    gsm_initialized = True
except Exception as e:
    print(f"GSM Error: {str(e)}")
    gsm_initialized = False

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
    if not init_gsm():
        update_display("GSM Error", "Check SIM", "card & signal")
        return
    
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

