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
DEFAULT_BLC_PROBA_THRESHOLD = 0.5  # Probability threshold for blc_bad=1


# ============ Runtime State ============
class SystemState:
    def __init__(self):
        self.current_user_id = None  # Set by frontend command
        self.is_running = True
        self.recording = False
        self.record_label = None
        self.record_end_ts = None
        self.record_session_id = None

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
        self.blc_proba_threshold = DEFAULT_BLC_PROBA_THRESHOLD
        self.default_blc_proba_threshold = DEFAULT_BLC_PROBA_THRESHOLD
        self.user_blc_thresholds = {}

        self.db_path = Path(__file__).parent / "chair.db"
        self.json_path = Path(__file__).parent / "latest_result.json"
        self.threshold_config_path = Path(__file__).parent / "threshold_config.json"

        # Hardware objects
        self.seesaw = None
        self.motor = None
        self.motor_running = False


state = SystemState()


# ============ Threshold Utilities ============
def ensure_database_schema(cursor):
    """Create runtime and calibration tables when missing."""
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
        CREATE TABLE IF NOT EXISTS calibration_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            user_id TEXT NOT NULL,
            session_id TEXT,
            label INTEGER NOT NULL,
            label_name TEXT,
            raw_values TEXT,
            norm_values TEXT
        )
        """
    )


def compute_f1(y_true, y_pred):
    """Compute binary F1 score for label=1."""
    tp = 0
    fp = 0
    fn = 0
    for yt, yp in zip(y_true, y_pred):
        if yp == 1 and yt == 1:
            tp += 1
        elif yp == 1 and yt == 0:
            fp += 1
        elif yp == 0 and yt == 1:
            fn += 1

    if tp == 0:
        return 0.0

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def parse_record_label(label):
    """Normalize record_label into binary class: balanced=0, unbalanced=1."""
    if label is None:
        return None

    s = str(label).strip().lower()
    if s in {"0", "balanced", "balance", "good"}:
        return 0
    if s in {"1", "unbalanced", "bad", "imbalance"}:
        return 1
    return None


def clamp_threshold(value):
    """Clamp threshold to [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def load_threshold_config():
    """Load threshold config: default + per-user mapping."""
    default_thr = DEFAULT_BLC_PROBA_THRESHOLD
    by_user = {}
    try:
        if not state.threshold_config_path.exists():
            return default_thr, by_user

        with open(state.threshold_config_path, "r") as f:
            config = json.load(f)

        # Backward compatible with old shape: {"blc_proba_threshold": 0.5}
        if "blc_proba_threshold" in config and "default_threshold" not in config:
            default_thr = clamp_threshold(float(config["blc_proba_threshold"]))
        else:
            default_thr = clamp_threshold(
                float(config.get("default_threshold", DEFAULT_BLC_PROBA_THRESHOLD))
            )

        raw_by_user = config.get("by_user", {})
        if isinstance(raw_by_user, dict):
            for user_id, thr in raw_by_user.items():
                try:
                    by_user[str(user_id)] = clamp_threshold(float(thr))
                except Exception:
                    continue
    except Exception as e:
        print(f"[CALIB] Failed to load threshold config, using default: {e}")

    return default_thr, by_user


def save_threshold_config():
    """Persist threshold config with default + per-user mapping."""
    try:
        payload = {
            "default_threshold": float(state.default_blc_proba_threshold),
            "by_user": state.user_blc_thresholds,
        }
        with open(state.threshold_config_path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[CALIB] Saved threshold config: {state.threshold_config_path}")
    except Exception as e:
        print(f"[CALIB] Failed to save threshold config: {e}")


def get_threshold_for_user(user_id):
    """Resolve threshold for a user, falling back to default."""
    if user_id:
        key = str(user_id)
        if key in state.user_blc_thresholds:
            return state.user_blc_thresholds[key]
    return state.default_blc_proba_threshold


def apply_threshold_for_user(user_id):
    """Apply threshold for the specified user to runtime state."""
    state.blc_proba_threshold = get_threshold_for_user(user_id)
    print(
        f"[STATE] Applied threshold={state.blc_proba_threshold} for user_id={user_id} "
        f"(default={state.default_blc_proba_threshold})"
    )


def load_calibration_xy(user_id):
    """
    Read calibration samples from SQLite and build (X, y).

    Data source:
    - table: calibration_samples
    - filter: current user
    - feature X: norm_values (len=4)
    - label y: label (0 balanced, 1 unbalanced)
    """
    if not user_id:
        return [], []

    X = []
    y = []
    try:
        conn = sqlite3.connect(state.db_path)
        cursor = conn.cursor()
        ensure_database_schema(cursor)
        cursor.execute(
            """
            SELECT norm_values, label
            FROM calibration_samples
            WHERE user_id = ?
            ORDER BY timestamp ASC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        for norm_values_raw, label in rows:
            if label not in (0, 1):
                continue
            try:
                values = json.loads(norm_values_raw)
            except Exception:
                continue

            if not isinstance(values, list) or len(values) != 4:
                continue

            try:
                feature = [float(v) for v in values]
            except Exception:
                continue

            X.append(feature)
            y.append(label)
    except Exception as e:
        print(f"[CALIB] Failed to load calibration samples: {e}")

    return X, y


def pick_threshold(model, X_val, y_val, step=0.01):
    """Scan thresholds and return the best one by F1 score."""
    if model is None:
        raise ValueError("Model is not loaded")
    if not X_val or not y_val:
        raise ValueError("Validation set is empty")
    if not hasattr(model, "predict_proba"):
        raise ValueError("Model does not support predict_proba")

    proba = model.predict_proba(X_val)
    p_bad = [float(row[1]) for row in proba]

    best_thr = DEFAULT_BLC_PROBA_THRESHOLD
    best_f1 = -1.0

    thr = 0.05
    while thr <= 0.95 + 1e-9:
        y_hat = [1 if p >= thr else 0 for p in p_bad]
        f1 = compute_f1(y_val, y_hat)
        if f1 > best_f1:
            best_f1 = f1
            best_thr = round(float(thr), 4)
        thr += step

    return best_thr, best_f1


def recalibrate_threshold_from_db(user_id):
    """
    Recompute threshold from calibration samples and persist it.
    Returns (ok, message).
    """
    if state.model is None:
        return False, "model is not loaded"

    X, y = load_calibration_xy(user_id)
    if not X:
        return False, f"no calibration samples found for user={user_id}"

    count_balanced = sum(1 for label in y if label == 0)
    count_unbalanced = sum(1 for label in y if label == 1)
    if count_balanced == 0 or count_unbalanced == 0:
        return (
            False,
            f"need both classes; got balanced={count_balanced}, unbalanced={count_unbalanced}",
        )

    try:
        best_thr, best_f1 = pick_threshold(state.model, X, y)
    except Exception as e:
        return False, f"pick_threshold failed: {e}"

    user_key = str(user_id) if user_id is not None else None
    if user_key:
        state.user_blc_thresholds[user_key] = best_thr
        if state.current_user_id is not None and str(state.current_user_id) == user_key:
            state.blc_proba_threshold = best_thr
    save_threshold_config()
    return (
        True,
        f"recalibrated threshold={best_thr} with f1={best_f1:.3f}, "
        f"samples={len(y)} (balanced={count_balanced}, unbalanced={count_unbalanced})",
    )


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


def detect_bad_balance(norm_values, model=None, proba_threshold=DEFAULT_BLC_PROBA_THRESHOLD):
    """
    Infer whether posture is unbalanced.
    Uses model prediction when available; otherwise falls back to variance rule.
    """
    if not norm_values or all(v == 0 for v in norm_values):
        return 0

    if model is not None:
        try:
            if hasattr(model, "predict_proba"):
                p_bad = float(model.predict_proba([norm_values])[0][1])
                return 1 if p_bad >= proba_threshold else 0
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
    state.blc_bad = detect_bad_balance(
        state.norm_values, state.model, state.blc_proba_threshold
    )

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
        "blc_threshold": state.blc_proba_threshold,
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
    Write runtime logs and calibration samples to SQLite.

    Runtime log rule:
    - user_id is set, and
    - seattype changed in this cycle.

    Calibration sample rule:
    - user_id is set, and
    - recording mode is active, and
    - record_label is valid (balanced/unbalanced).
    """
    has_user = state.current_user_id is not None
    should_write_runtime = has_user and state.seattype_changed

    calib_label = parse_record_label(state.record_label)
    should_write_calibration = has_user and state.recording and calib_label is not None

    print(
        "[DB] Write check: "
        f"user_id={state.current_user_id}, "
        f"seattype_changed={state.seattype_changed}, "
        f"recording={state.recording}, "
        f"runtime={should_write_runtime}, "
        f"calibration={should_write_calibration}"
    )

    if not should_write_runtime and not should_write_calibration:
        return

    try:
        conn = sqlite3.connect(state.db_path)
        cursor = conn.cursor()
        ensure_database_schema(cursor)

        if should_write_runtime:
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
                    None,
                ),
            )

        if should_write_calibration:
            cursor.execute(
                """
                INSERT INTO calibration_samples
                (timestamp, user_id, session_id, label, label_name, raw_values, norm_values)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["timestamp"],
                    state.current_user_id,
                    state.record_session_id,
                    calib_label,
                    str(state.record_label),
                    json.dumps(payload["raw_values"]),
                    json.dumps(payload["norm_values"]),
                ),
            )

        conn.commit()
        conn.close()

        if should_write_runtime:
            status = "seated" if payload["seattype"] == 1 else "left seat"
            duration_str = (
                f"duration={payload['sit_duration']}s" if payload["seattype"] == 0 else ""
            )
            print(
                f"[DB] Runtime row saved: user {state.current_user_id} "
                f"{status} {duration_str} | blc_bad={payload['blc_bad']}"
            )
        if should_write_calibration:
            print(
                f"[DB] Calibration row saved: user={state.current_user_id}, "
                f"session_id={state.record_session_id}, label={calib_label}"
            )

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
            apply_threshold_for_user(state.current_user_id)

        # Update recording state
        if "recording" in payload:
            state.recording = payload["recording"]
            if state.recording:
                state.record_label = payload.get("label", None)
                duration = payload.get("duration", 60)
                state.record_end_ts = time.time() + duration
                state.record_session_id = (
                    f"{state.current_user_id}_{int(time.time() * 1000)}"
                )
                print(f"[REC] Recording started: label={state.record_label}, duration={duration}s")
            else:
                print("[REC] Recording stopped")
                state.record_end_ts = None
                state.record_label = None
                state.record_session_id = None
                ok, message = recalibrate_threshold_from_db(state.current_user_id)
                print(f"[CALIB] Auto recalibration after recording stop: ok={ok}, {message}")

        # Calibration command
        if "calibrate" in payload:
            calib_type = payload["calibrate"]
            print(f"[CALIB] Calibration command received: {calib_type}")
            if str(calib_type).lower() in {
                "recompute",
                "recompute_threshold",
                "threshold",
                "done",
                "finish",
            }:
                user_id = payload.get("user_id", state.current_user_id)
                ok, message = recalibrate_threshold_from_db(user_id)
                print(f"[CALIB] Manual recalibration result: ok={ok}, {message}")

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

    # 3.2) Load threshold config (default + per-user)
    (
        state.default_blc_proba_threshold,
        state.user_blc_thresholds,
    ) = load_threshold_config()
    apply_threshold_for_user(None)

    # 3.5) Restore user_id from DB (session persistence)
    print("[INIT] Restoring user_id from DB...")
    state.current_user_id = load_user_id_from_db()
    if state.current_user_id:
        print(f"[STATE] Restored user_id: {state.current_user_id}")
        apply_threshold_for_user(state.current_user_id)
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
                state.record_end_ts = None
                state.record_label = None
                state.record_session_id = None
                print("[REC] Recording window completed")
                ok, message = recalibrate_threshold_from_db(state.current_user_id)
                print(f"[CALIB] Auto recalibration after timed recording: ok={ok}, {message}")

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
