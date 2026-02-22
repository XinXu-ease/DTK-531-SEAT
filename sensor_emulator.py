import paho.mqtt.client as mqtt
import json
import time, threading
import sys

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Successfully connected to broker")
    else:
        print(f"Connection failed with code {rc}")

# Create publisher client
publisher = mqtt.Client()
publisher.on_connect = on_connect

# Connect to public broker
print("Connecting to broker...")

# (broker, port, keepalive)
publisher.connect("test.mosquitto.org", 1883, 60)
publisher.loop_start()

#fake data now
patterns = {
    "0": [0.0, 0.0, 0.1, 0.0], #unseated
    "1": [0.5, 0.5, 0.5, 0.5], #balanced
    "2": [0.9, 0.1, 0.8, 0.2],#unbalanced
} 
current_mode = "0"
lock = threading.Lock()
stop_event = threading.Event()

def input_listener():
    """
    交互输入线程：随时更新 p_cur
    """
    global current_mode
    print("Press 0 for Unseated, 1 for Balanced, 2 for Unbalanced, q to quit")
    while True:
        cmd = input("> ").strip()
        if cmd in ("1", "2"):
            with lock:
                current_mode = cmd
            print(f"Switched to mode {cmd}")
        elif cmd.lower() == "q":
            raise SystemExit
        
threading.Thread(target=input_listener, daemon=True).start()
        
try:
    while True:
        with lock:
            mode = current_mode
            
        TOPIC = "Balancestate"
        payload = {
            "timestamp": time.time(),
            "seattype": 1 if sum(patterns[mode]) > 0.2 else 0, 
            "pressure": patterns[mode]
        }
        
        publisher.publish(TOPIC, json.dumps(payload))
        print(f"Mode {mode} sent: {patterns[mode]}")
        
        time.sleep(1)
except KeyboardInterrupt:
    publisher.disconnect()
    publisher.loop_stop()