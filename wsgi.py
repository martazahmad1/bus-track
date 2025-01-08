import os
import sys

# Add your project directory to the sys.path
project_home = '/home/Martaz/bus-track'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Import your WebSocket server
from server.socket_server import main

# PythonAnywhere WSGI configuration
def application(environ, start_response):
    if environ.get('HTTP_UPGRADE', '').lower() == 'websocket':
        # Handle WebSocket
        return main(environ, start_response)
    else:
        # Serve the static file for regular HTTP requests
        try:
            with open('index.html', 'rb') as f:
                response_body = f.read()
            status = '200 OK'
            headers = [('Content-type', 'text/html'),
                      ('Content-Length', str(len(response_body)))]
            start_response(status, headers)
            return [response_body]
        except FileNotFoundError:
            status = '404 Not Found'
            response_body = b'File not found'
            headers = [('Content-type', 'text/plain'),
                      ('Content-Length', str(len(response_body)))]
            start_response(status, headers)
            return [response_body] 