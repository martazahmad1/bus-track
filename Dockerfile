FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application
COPY . .

# Copy frontend files to the correct location
RUN cp -v frontend/index.html .

# Expose the port the app runs on
EXPOSE 10000

# Command to run the application
CMD ["python", "server/socket_server.py"] 