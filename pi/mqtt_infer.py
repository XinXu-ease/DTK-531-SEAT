import json
import time
import pickle
import sqlite3
from pathlib import Path

import paho.mqtt.client as mqtt

# ============ Hardware Dependencies ============
try:
    import board
    import busio
    from adafruit_seesaw.seesaw import Seesaw

    HARDWARE_AVAILABLE = True
except ImportError:
    print("[WARN] adafruit_seesaw not installed, using simulation mode")
    HARDWARE_AVAILABLE = False

# Stepper motor driver
try:
    from adafruit_crickit import crickit
    from adafruit_motor import stepper

    MOTOR_AVAILABLE = True
except ImportError:
    print("[WARN] adafruit_crickit not installed, motor will run in simulation mode")
    MOTOR_AVAILABLE = False

# ============ Configuration ============
MQTT_BROKER = "localhost"  # Local MQTT broker
MQTT_PORT = 1883  # Standard MQTT port
MQTT_PUBLISH_TOPIC = "chair/sensors"
MQTT_SUBSCRIBE_TOPIC = "chair/user"

# FSR/Seesaw settings
FSR_PINS = [2, 3, 4, 5]  # Seesaw pin numbers
MIN_VALS = [200, 200, 200, 200]  # Raw lower bounds
MAX_VALS = [900, 900, 900, 900]  # Raw upper bounds

# Decision thresholds
BAD_POSTURE_THRESHOLD = 5  # Seconds before vibration triggers
SEATTYPE_THRESHOLD = 0.2  # Sum(norm_values) threshold for seated state


# ============ Runtime State ============
class SystemState:
    def __init__(self):
        self.current_user_id = None  # Set by frontend command
        self.is_running = True
        self.recording = False
        self.record_label = None
        self.record_end_ts = None

        self.raw_values = [0, 0, 0, 0]
        self.norm_values = [0.0, 0.0, 0.0, 0.0]
        self.seattype = 0
        self.seattype_changed = False  # Whether seattype changed this cycle
        self.blc_bad = 0
        self.time_sit = 0
        self.time_blc = 0
        self.should_vibrate = False

        self.last_sit_start = None  # Timestamp when user sat down
        self.last_blc_time = None
        self.sit_duration = 0  # Latest completed sit duration (seconds)
        self.model = None

        self.db_path = Path(__file__).parent / "chair.db"
        self.json_path = Path(__file__).parent / "latest_result.json"

        # Hardware objects
        self.seesaw = None
        self.motor = None
        self.motor_running = False


state = SystemState()


# ============ Hardware Initialization ============
def init_seesaw():
    """Initialize Seesaw over I2C."""
    if not HARDWARE_AVAILABLE:
        print("[INFO] Seesaw unavailable, running sensor simulation")
        return False

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        state.seesaw = Seesaw(i2c)
        print("[INIT] Seesaw initialized")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to initialize Seesaw: {e}")
        return False


def init_motor():
    """Initialize stepper motor via Crickit."""
    if not MOTOR_AVAILABLE:
        print("[WARN] Motor driver unavailable, using motor simulation")
        return False

    try:
        state.motor = crickit.stepper_motor
        # Release immediately to ensure a safe stopped state.
        state.motor.release()
        state.motor_running = False
        print("[INIT] Motor initialized and released")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to initialize motor: {e}")
        return False


def force_stop_motor():
    """Force stop and release motor, if initialized."""
    if state.motor is not None:
        try:
            state.motor.release()
            state.motor_running = False
            print("[MOTOR] Force stopped")
        except Exception as e:
            print(f"[MOTOR] Failed to force stop motor: {e}")


# ============ Sensor Reading ============
def read_raw_pressures():
    """
    Read 4 FSR raw values.
    Returns: [raw1, raw2, raw3, raw4]

    In simulation mode, values alternate every 10 seconds
    between "seated-like" and "empty-seat-like" ranges.
    """
    if state.seesaw is None:
        import random
        import time as time_module

        current_time = time_module.time()
        cycle_position = int(current_time) % 20  # 20-second cycle

        if cycle_position < 10:
            # First 10s: higher pressure (simulate seated)
            return [random.randint(500, 800) for _ in range(4)]
        # Last 10s: lower pressure (simulate empty seat)
        return [random.randint(50, 150) for _ in range(4)]

    try:
        return [state.seesaw.analog_read(pin) for pin in FSR_PINS]
    except Exception as e:
        print(f"[ERROR] Failed to read FSR values: {e}")
        return [0, 0, 0, 0]


def normalize(value, min_val, max_val):
    """Normalize a raw value to [0, 1]."""
    if max_val <= min_val:
        return 0.0

    x = (value - min_val) / (max_val - min_val)

    if x < 0:
        x = 0.0
    elif x > 1:
        x = 1.0

    return round(x, 4)


def get_normalized_pressures(raw_values):
    """
    Convert raw values into normalized pressure values.
    raw_values: [r1, r2, r3, r4]
    return: [p1, p2, p3, p4]
    """
    return [normalize(raw_values[i], MIN_VALS[i], MAX_VALS[i]) for i in range(4)]


# ============ Posture Inference ============
def detect_seattype(norm_values):
    """
    Infer seated state.
    Rule: sum(norm_values) > SEATTYPE_THRESHOLD => seated (1), otherwise 0.
    """
    pressure_sum = sum(norm_values)
    return 1 if pressure_sum > SEATTYPE_THRESHOLD else 0


def detect_bad_balance(norm_values, model=None):
    """
    Infer whether posture is unbalanced.
    Uses model prediction when available; otherwise falls back to variance rule.
    """
    if not norm_values or all(v == 0 for v in norm_values):
        return 0

    if model is not None:
        try:
            return int(model.predict([norm_values])[0])
        except Exception as e:
            print(f"[WARN] Model prediction failed, using variance fallback: {e}")

    # Variance fallback: high variance means uneven pressure distribution.
    mean_val = sum(norm_values) / len(norm_values)
    variance = sum((v - mean_val) ** 2 for v in norm_values) / len(norm_values)
    return 1 if variance > 0.05 else 0


# ============ Motor Control ============
def trigger_vibration_motor(should_vibrate):
    """
    Start or stop motor based on target state.
    should_vibrate=True: start vibration
    should_vibrate=False: stop and release
    """
    if state.motor is None:
        # Simulation mode logging only.
        if should_vibrate and not state.motor_running:
            print("[MOTOR] Simulated vibration started")
            state.motor_running = True
        elif not should_vibrate and state.motor_running:
            print("[MOTOR] Simulated vibration stopped")
            state.motor_running = False
        return

    try:
        if should_vibrate and not state.motor_running:
            print("[MOTOR] Vibration started")
            state.motor_running = True
            # Continuous stepping is driven by motor_step() in main loop.
        elif not should_vibrate and state.motor_running:
            print("[MOTOR] Vibration stopped")
            state.motor_running = False
            state.motor.release()  # Release motor immediately
    except Exception as e:
        print(f"[ERROR] Motor control failed: {e}")


def motor_step():
    """
    Perform one motor step when motor is running.
    Call this repeatedly in the main loop for continuous vibration.
    """
    if state.motor_running and state.motor is not None:
        try:
            state.motor.onestep(direction=stepper.FORWARD)
        except Exception as e:
            print(f"[ERROR] Motor step failed: {e}")


# ============ State Update and Processing ============
def update_state():
    """
    Main state update pipeline:
    1) Read sensors
    2) Normalize pressures
    3) Infer seated state and balance
    4) Update timers
    5) Evaluate vibration condition
    6) Apply motor control
    """
    # Save previous seated state for edge detection.
    prev_seattype = state.seattype

    # 1) Read raw values
    state.raw_values = read_raw_pressures()

    # 2) Normalize
    state.norm_values = get_normalized_pressures(state.raw_values)

    # 3) Inference
    state.seattype = detect_seattype(state.norm_values)
    state.blc_bad = detect_bad_balance(state.norm_values, state.model)

    # Detect seated-state transition.
    state.seattype_changed = prev_seattype != state.seattype

    if state.seattype_changed:
        print(f"[SEATTYPE] Changed: {prev_seattype} -> {state.seattype}, user_id={state.current_user_id}")

    # 4) Update timers
    current_time = time.time()

    # Sitting timer and completed sit duration.
    if state.seattype == 1:  # seated
        if state.last_sit_start is None:
            state.last_sit_start = current_time
        state.time_sit = int(current_time - state.last_sit_start)
        state.sit_duration = 0  # reset completed duration while seated
    else:  # not seated
        if state.last_sit_start is not None and state.seattype_changed:
            state.sit_duration = int(current_time - state.last_sit_start)
            state.time_sit = 0
            print(f"[LOG] Seat duration: {state.sit_duration}s")
        else:
            state.sit_duration = 0
            state.time_sit = 0
        state.last_sit_start = None

    # Bad-balance timer
    if state.blc_bad == 1:  # unbalanced
        if state.last_blc_time is None:
            state.last_blc_time = current_time
        else:
            state.time_blc = int(current_time - state.last_blc_time)
    else:  # balanced
        state.last_blc_time = None
        state.time_blc = 0

    # 5) Vibration condition
    # Condition: seated + unbalanced + duration over threshold
    state.should_vibrate = (
        state.seattype == 1
        and state.blc_bad == 1
        and state.time_blc > BAD_POSTURE_THRESHOLD
    )

    # 6) Local closed-loop motor control (not MQTT-dependent)
    trigger_vibration_motor(state.should_vibrate)


def get_state_payload():
    """Build MQTT payload from current state."""
    return {
        "timestamp": time.time(),
        "user_id": state.current_user_id,
        "is_running": state.is_running,
        "raw_values": state.raw_values,
        "norm_values": state.norm_values,
        "seattype": state.seattype,
        "blc_bad": state.blc_bad,
        "time_sit": state.time_sit,
        "time_blc": state.time_blc,
        "should_vibrate": state.should_vibrate,
        "sit_duration": state.sit_duration,  # last completed sit duration
    }


def save_latest_result(payload):
    """Save latest payload as JSON cache for debugging/fallback."""
    try:
        with open(state.json_path, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save JSON cache: {e}")


def load_user_id_from_db():
    """Restore last known user_id from database (most recent row)."""
    try:
        conn = sqlite3.connect(state.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM sensor_data ORDER BY timestamp DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        if result and result[0]:
            return result[0]
    except Exception as e:
        print(f"[DB] Failed to load user_id: {e}")
    return None


def write_to_database(payload):
    """
    Write transition rows to SQLite.

    Current write rule:
    - user_id is set, and
    - seattype changed in this cycle.
    """
    should_record = state.current_user_id is not None and state.seattype_changed

    print(
        "[DB] Record check: "
        f"user_id={state.current_user_id}, "
        f"seattype_changed={state.seattype_changed}, "
        f"should_record={should_record}"
    )

    if not should_record:
        return

    try:
        conn = sqlite3.connect(state.db_path)
        cursor = conn.cursor()

        # Create table if needed.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                user_id TEXT,
                raw_values TEXT,
                norm_values TEXT,
                seattype INTEGER,
                sit_duration REAL,
                blc_bad INTEGER,
                record_label TEXT
            )
            """
        )

        cursor.execute(
            """
            INSERT INTO sensor_data
            (timestamp, user_id, raw_values, norm_values, seattype, sit_duration, blc_bad, record_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["timestamp"],
                state.current_user_id,
                json.dumps(payload["raw_values"]),
                json.dumps(payload["norm_values"]),
                payload["seattype"],
                payload["sit_duration"],
                payload["blc_bad"],
                state.record_label,
            ),
        )

        conn.commit()
        conn.close()

        status = "seated" if payload["seattype"] == 1 else "left seat"
        duration_str = f"duration={payload['sit_duration']}s" if payload["seattype"] == 0 else ""
        print(f"[DB] Recorded: user {state.current_user_id} {status} {duration_str} | blc_bad={payload['blc_bad']}")

    except Exception as e:
        print(f"[DB] Error: {e}")


# ============ MQTT Handlers ============
def on_connect(client, userdata, flags, rc):
    """MQTT connection callback."""
    if rc == 0:
        print("[MQTT] Connected")
        client.subscribe(MQTT_SUBSCRIBE_TOPIC)
        print(f"[MQTT] Subscribed to topic: {MQTT_SUBSCRIBE_TOPIC}")
    else:
        print(f"[MQTT] Connection failed with code: {rc}")


def on_message(client, userdata, msg):
    """
    Handle incoming messages from `chair/user`.

    Expected payload shape example:
    {
        "user_id": "xin",
        "recording": true,
        "label": "balanced",
        "duration": 60,
        "calibrate": "balanced"
    }
    """
    try:
        payload = json.loads(msg.payload.decode())
        print(f"[MQTT] Received command: {payload}")

        # Update user_id
        if "user_id" in payload:
            state.current_user_id = payload["user_id"]
            print(f"[STATE] user_id set to: {state.current_user_id}")

        # Update recording state
        if "recording" in payload:
            state.recording = payload["recording"]
            state.record_label = payload.get("label", None)
            if state.recording:
                duration = payload.get("duration", 60)
                state.record_end_ts = time.time() + duration
                print(f"[REC] Recording started: label={state.record_label}, duration={duration}s")
            else:
                print("[REC] Recording stopped")

        # Calibration command (placeholder)
        if "calibrate" in payload:
            calib_type = payload["calibrate"]
            print(f"[CALIB] Calibration command received: {calib_type}")
            # TODO: implement calibration logic

    except json.JSONDecodeError:
        print("[ERROR] Failed to parse MQTT payload as JSON")
    except Exception as e:
        print(f"[ERROR] Failed to handle MQTT message: {e}")


def mqtt_publish(client, payload):
    """Publish payload to MQTT topic."""
    try:
        msg = json.dumps(payload)
        client.publish(MQTT_PUBLISH_TOPIC, msg, qos=1)
        print(f"[MQTT] Published: {payload}")
    except Exception as e:
        print(f"[MQTT] Publish failed: {e}")


# ============ Main Loop ============
def main():
    print("=" * 50)
    print("DTK-531 Smart Posture System - Pi Runtime")
    print("=" * 50)

    # 1) Initialize sensor hardware
    print("\n[INIT] Initializing Seesaw...")
    init_seesaw()

    # 2) Initialize motor
    print("[INIT] Initializing motor...")
    init_motor()
    force_stop_motor()  # Safety stop right after initialization

    # 3) Load posture model
    print("[INIT] Loading balance model...")
    try:
        model_path = Path(__file__).parent / "model_blc.pkl"
        if not model_path.exists():
            print(f"[WARN] Model file not found: {model_path}")
        else:
            with open(model_path, "rb") as f:
                state.model = pickle.load(f)
            print("[INIT] Model loaded")
    except Exception as e:
        print(f"[WARN] Failed to load model, using fallback rule: {e}")

    # 3.5) Restore user_id from DB (session persistence)
    print("[INIT] Restoring user_id from DB...")
    state.current_user_id = load_user_id_from_db()
    if state.current_user_id:
        print(f"[STATE] Restored user_id: {state.current_user_id}")
    else:
        print("[STATE] No previous user_id found; waiting for dashboard sync")

    # 4) Initialize MQTT
    print("[INIT] Connecting to MQTT broker...")
    client = mqtt.Client(client_id="rpi-chair-monitor")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        # Standard MQTT port, no TLS
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
        print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        print(f"[ERROR] MQTT connection failed: {e}")
        return

    # 5) Main loop
    print("\n[MAIN] Running at 1 Hz...\n")
    try:
        while state.is_running:
            # Update system state
            update_state()

            # Perform one motor step if motor is running
            motor_step()

            # Build payload
            payload = get_state_payload()

            # Publish to MQTT
            mqtt_publish(client, payload)

            # Save JSON cache
            save_latest_result(payload)

            # Write DB row when transition conditions are met
            write_to_database(payload)

            # Auto-stop recording when timer expires
            if state.recording and state.record_end_ts and time.time() > state.record_end_ts:
                state.recording = False
                print("[REC] Recording window completed")

            # Sampling interval
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Main loop crashed: {e}")
    finally:
        state.is_running = False
        client.loop_stop()
        client.disconnect()

        # Release motor
        if state.motor is not None:
            try:
                state.motor.release()
                print("[MOTOR] Released")
            except Exception as e:
                print(f"[MOTOR] Failed to release motor: {e}")

        print("[MAIN] Shutdown complete")


if __name__ == "__main__":
    main()
