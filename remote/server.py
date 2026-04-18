"""
Flask + WebSocket server for real-time chair posture monitoring
Subscribes to MQTT chair/sensors and broadcasts to connected clients via WebSocket
"""

import json
import threading
import time
from datetime import datetime
from flask import Flask, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import paho.mqtt.client as mqtt

# ============ Flask App Setup ============
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ============ Global State ============
MQTT_BROKER = "test.mosquitto.org"
MQTT_TOPIC = "chair/sensors"
MQTT_PORT = 1883

# Thread-safe data cache
data_lock = threading.Lock()
mqtt_connected = False  # Track MQTT connection state
current_data = {
    "seattype": False,
    "blc_bad": False,
    "time_sit": 0.0,
    "time_blc": 0.0,
    "raw_values": [0, 0, 0, 0],
    "norm_values": [0, 0, 0, 0],
    "should_vibrate": False,
    "timestamp": None,
    "user_id": "default",
}

mqtt_client = None
connected_clients = set()

# ============ MQTT Callbacks ============
def on_mqtt_connect(client, userdata, flags, rc):
    """Called when MQTT client connects"""
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        print(f"[MQTT] Connected to {MQTT_BROKER}, subscribing to {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC, qos=1)
        # 广播MQTT连接成功状态给所有WebSocket客户端
        socketio.emit('mqtt_status', {'status': 'connected'}, to=None)
    else:
        mqtt_connected = False
        print(f"[MQTT] Connection failed with code {rc}")
        # 广播MQTT连接失败状态给所有WebSocket客户端
        socketio.emit('mqtt_status', {'status': 'failed', 'code': rc}, to=None)

def on_mqtt_message(client, userdata, msg):
    """Called when MQTT message received"""
    global current_data
    try:
        payload = json.loads(msg.payload.decode())
        with data_lock:
            current_data.update({
                "seattype": bool(payload.get("seattype", 0)),
                "blc_bad": bool(payload.get("blc_bad", 0)),
                "time_sit": float(payload.get("time_sit", 0)),
                "time_blc": float(payload.get("time_blc", 0)),
                "raw_values": payload.get("raw_values", [0, 0, 0, 0]),
                "norm_values": payload.get("norm_values", [0, 0, 0, 0]),
                "should_vibrate": bool(payload.get("should_vibrate", 0)),
                "timestamp": payload.get("timestamp"),
                "user_id": payload.get("user_id", "default"),
            })
        
        # Broadcast to all connected WebSocket clients
        print(f"[MQTT] Received: seattype={current_data['seattype']}, blc_bad={current_data['blc_bad']}")
        socketio.emit('chair_data', current_data, to=None)
        
    except json.JSONDecodeError:
        print(f"[MQTT] Failed to parse message: {msg.payload}")
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

def on_mqtt_disconnect(client, userdata, rc):
    """Called when MQTT client disconnects"""
    global mqtt_connected
    mqtt_connected = False
    if rc != 0:
        print(f"[MQTT] Unexpected disconnection: {rc}")
    else:
        print("[MQTT] Disconnected")
    # 广播MQTT断开连接状态给所有WebSocket客户端
    socketio.emit('mqtt_status', {'status': 'disconnected'}, to=None)

# ============ Flask Routes ============
@app.route('/')
def index():
    """Serve main HTML page"""
    return render_template('index.html')

# ============ WebSocket Events ============
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"[WebSocket] Client connected: {threading.current_thread().ident}")
    connected_clients.add(threading.current_thread().ident)
    
    # Send current data to newly connected client
    with data_lock:
        emit('chair_data', current_data)
    
    # Send current MQTT connection status to newly connected client
    mqtt_status = 'connected' if mqtt_connected else 'disconnected'
    emit('mqtt_status', {'status': mqtt_status})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"[WebSocket] Client disconnected")
    connected_clients.discard(threading.current_thread().ident)

@socketio.on('request_data')
def handle_request_data():
    """Handle explicit data request from client"""
    with data_lock:
        emit('chair_data', current_data)

@socketio.on('set_user_id')
def handle_set_user_id(data):
    """Handle user ID update from client"""
    global mqtt_client
    try:
        user_id = data.get('user_id', '').strip()
        if user_id:
            # Publish user_id to MQTT topic "chair/user"
            mqtt_payload = json.dumps({"user_id": user_id, "timestamp": time.time()})
            mqtt_client.publish("chair/user", mqtt_payload, qos=1, retain=True)
            print(f"[WebSocket] User ID synced: {user_id}")
            emit('user_id_synced', {'user_id': user_id, 'status': 'success'})
        else:
            emit('user_id_synced', {'status': 'error', 'message': 'Empty user ID'})
    except Exception as e:
        print(f"[WebSocket] Error setting user ID: {e}")
        emit('user_id_synced', {'status': 'error', 'message': str(e)})

@socketio.on('start_calibration')
def handle_start_calibration(data):
    """Handle calibration command from client"""
    global mqtt_client
    try:
        user_id = data.get('user_id', '')
        label = data.get('label', 0)
        duration = data.get('duration', 10)
        
        # Publish calibration command to MQTT topic "chair/user"
        # Format: recording=true, label=0/1, duration=seconds
        mqtt_payload = json.dumps({
            "user_id": user_id,
            "recording": True,
            "label": label,
            "duration": duration,
            "timestamp": time.time()
        })
        mqtt_client.publish("chair/user", mqtt_payload, qos=1)
        print(f"[WebSocket] Calibration started: user={user_id}, label={label}, duration={duration}s")
        emit('calibration_status', {'status': 'started', 'label': label})
    except Exception as e:
        print(f"[WebSocket] Error starting calibration: {e}")
        emit('calibration_status', {'status': 'error', 'message': str(e)})

# ============ MQTT Connection Thread ============
def mqtt_thread():
    """Run MQTT client in background thread"""
    global mqtt_client
    try:
        mqtt_client = mqtt.Client(client_id="flask-chair-ui")
        mqtt_client.on_connect = on_mqtt_connect
        mqtt_client.on_message = on_mqtt_message
        mqtt_client.on_disconnect = on_mqtt_disconnect
        
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_forever()
        
    except Exception as e:
        print(f"[MQTT] Connection error: {e}")
        time.sleep(5)
        mqtt_thread()  # Reconnect

# ============ Application Startup ============
if __name__ == '__main__':
    # Start MQTT thread
    mqtt_t = threading.Thread(target=mqtt_thread, daemon=True)
    mqtt_t.start()
    time.sleep(1)  # Give MQTT time to connect
    
    # Start Flask server
    print("\n" + "="*60)
    print("Chair Posture Monitor - Flask WebSocket Server")
    print("="*60)
    print("Open browser at: http://localhost:5000")
    print("="*60 + "\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
