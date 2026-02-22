import paho.mqtt.client as mqtt
import time, json
import joblib
from pathlib import Path
import time

MODEL_PATH = "model_blc.pkl"
model_blc = joblib.load(MODEL_PATH)
OUT_FILE = Path("latest_result.json")

last_timestamp = None
time_sit = 0.0
time_blc = 0.0

# Timing
def Timers(seattype,current_ts,blc_bad):
    global time_sit, time_blc, last_timestamp
    if last_timestamp is None:
        last_timestamp = current_ts
        return 0.0, 0.0
    dt = current_ts - last_timestamp
    last_timestamp = current_ts

    if seattype == 1:
        time_sit += dt
    else:
        time_sit = 0.0

    if blc_bad == 1:
        time_blc += dt
    else:
        time_blc = 0.0
    return round(time_sit, 1), round(time_blc, 1)

def Blctimer(blc_bad):
    global time_blc
    if blc_bad == 1:
        time_blc += 1
    else:
        time_blc = 0
    return time_blc

def atomic_write_json(path: Path, data: dict, retries: int = 20, delay: float = 0.02):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")

    for i in range(retries):
        try:
            tmp.replace(path)  
            return
        except PermissionError:
            time.sleep(delay)
    tmp.replace(path)
    
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Successfully connected to broker")
        # Subscribe to topic
        client.subscribe("Balancestate")
    else:
        print(f"Connection failed with code {rc}")

def on_message(client, userdata, msg):
    payload_text = msg.payload.decode()
    try: #str -> dict
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        print(f"[WARN] Non-JSON payload received: {payload_text}")
        return
    # get data
    pressure = payload.get("pressure")
    seattype = payload.get("seattype")
    current_ts = payload.get("timestamp")

    # predict through model
    try:
        pred = model_blc.predict([pressure])[0]  
    except Exception as e:
        print(f"[ERROR] Model inference failed: {e}. pressure={pressure}")
        return
    blc_bad = int(pred)

    sit_duration, blc_duration = Timers(seattype, current_ts, blc_bad)

    result = {
        "timestamp": current_ts,
        "seattype": seattype,
        "time_sit": sit_duration,
        "blc_bad": blc_bad,
        "time_blc": blc_duration
    }
    atomic_write_json(OUT_FILE, result)
    print(f"Topic: {msg.topic}, Message: {payload_text}")
    print(f"Inference result: {result}")

# Create subscriber client
subscriber = mqtt.Client()
subscriber.on_connect = on_connect
subscriber.on_message = on_message


# Connect to public broker
print("Connecting to broker...")
subscriber.connect("test.mosquitto.org", 1883, 60) # "test.mosquitto.org"is a public test bocker

# Start the subscriber loop
subscriber.loop_start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping subscriber...")
    subscriber.loop_stop()
    subscriber.disconnect()