from flask import Flask, request, jsonify

app = Flask(__name__)

# This will store the latest location received (you can also save it to a database if needed)
latest_location = {
    'latitude': None,
    'longitude': None
}

@app.route('/receive_location', methods=['POST'])
def receive_location():
    global latest_location
    data = request.json
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    # Store the latest location data
    latest_location['latitude'] = latitude
    latest_location['longitude'] = longitude

    print(f"Received Latitude: {latitude}, Longitude: {longitude}")
    return jsonify(status="success", latitude=latitude, longitude=longitude)

@app.route('/get_location', methods=['GET'])
def get_location():
    # Return the latest location data
    return jsonify(latest_location)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
