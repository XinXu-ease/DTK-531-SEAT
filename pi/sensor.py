import paho.mqtt.client as mqtt
import json
import time
import board
import busio
from adafruit_seesaw.seesaw import Seesaw


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

# FSR data
i2c = busio.I2C(board.SCL, board.SDA)
ss = Seesaw(i2c)

#  read from 4 pin
FSR_PINS = [2, 3, 4, 5]

# initial range
MIN_VALS = [200, 200, 200, 200]
MAX_VALS = [900, 900, 900, 900]

TOPIC = "chair/sensors"

def normalize(value, min_val, max_val):
    """
    nomalize to 0~1
    """
    if max_val <= min_val:
        return 0.0

    x = (value - min_val) / (max_val - min_val)

    if x < 0:
        x = 0.0
    elif x > 1:
        x = 1.0

    return round(x, 4)
    
def read_raw_pressures():
    """
    read data from 4 FSR 
    return: [raw1, raw2, raw3, raw4]
    """
    return [ss.analog_read(pin) for pin in FSR_PINS]


def get_normalized_pressures():
    """
      raw_values:  [r1, r2, r3, r4]
      norm_values: [p1, p2, p3, p4]
    """
    raw_values = read_raw_pressures()
    norm_values = [
        normalize(raw_values[i], MIN_VALS[i], MAX_VALS[i])
        for i in range(4)
    ]
    return raw_values, norm_values
              
try:
    while True:
        raw_values, norm_values = get_normalized_pressures()
            
        payload = {
            "timestamp": time.time(),
            "seattype": 1 if sum(norm_values) > 0.2 else 0, 
            "pressure": norm_values
        }
        
        publisher.publish(TOPIC, json.dumps(payload))
        print(f" Sent raw ={raw_values} norm ={norm_values}")
        
        time.sleep(1)
except KeyboardInterrupt:
    publisher.disconnect()
    publisher.loop_stop()
