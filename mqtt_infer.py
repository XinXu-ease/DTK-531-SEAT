import paho.mqtt.client as mqtt
import time, json
import joblib
from pathlib import Path
import time
import sqlite3
import numpy as np
from datetime import datetime

MODEL_PATH = "model_blc.pkl"
model_blc = joblib.load(MODEL_PATH)
OUT_FILE = Path("latest_result.json")

last_timestamp = None
time_sit = 0.0
time_blc = 0.0

sit_time_day = 0.0
blc_count_day = 0
blc_time_day = 0.0
pressure_samples_day = []

prev_blc_bad = 0
last_ts_day = None
current_date = None 

current_user_id = "u1"

def init_db(db_path="chair.db"):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        ts REAL NOT NULL,
        p1 REAL NOT NULL,
        p2 REAL NOT NULL,
        p3 REAL NOT NULL,
        p4 REAL NOT NULL,
        y INTEGER NOT NULL
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS thresholds (
    user_id TEXT PRIMARY KEY,
    thr REAL NOT NULL,
    updated_at REAL NOT NULL
    );
    """)
    conn.commit()
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_summary (
    date TEXT NOT NULL,
    user_id TEXT NOT NULL,
    sit_time_sec REAL NOT NULL,
    blc_count INTEGER NOT NULL,
    blc_time_sec REAL NOT NULL,
    pressure_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(date, user_id)
    );""")
    return conn

def save_daily_summary(conn, user_id):
    conn.execute("""
    INSERT INTO daily_summary
      (date, user_id, sit_time_sec, blc_count, blc_time_sec, pressure_json, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(date, user_id) DO UPDATE SET
      sit_time_sec=excluded.sit_time_sec,
      blc_count=excluded.blc_count,
      blc_time_sec=excluded.blc_time_sec,
      pressure_json=excluded.pressure_json,
      updated_at=excluded.updated_at
    """, (
        current_date,
        user_id,
        float(sit_time_day),
        int(blc_count_day),
        float(blc_time_day),
        json.dumps(pressure_samples_day),
        time.time()
    ))
    conn.commit()
    

def insert_sample(conn, user_id, ts, pressure, y):
    conn.execute(
        "INSERT INTO samples (user_id, ts, p1, p2, p3, p4, y) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, float(ts),
         float(pressure[0]), float(pressure[1]), float(pressure[2]), float(pressure[3]),
         int(y))
    )
    conn.commit()

conn = init_db("chair.db")

recording = False
record_user_id = None
record_label = None
record_end_ts = 0.0

def load_user_xy(conn, user_id):
    cur = conn.execute(
        "SELECT p1,p2,p3,p4,y FROM samples WHERE user_id=?",
        (user_id,)
    )
    rows = cur.fetchall()
    if not rows:
        return None, None
    X = np.array([r[:4] for r in rows], dtype=float)
    y = np.array([r[4] for r in rows], dtype=int)
    return X, y

def compute_threshold_from_calib(model, X, y):
    # p_bad: 每条样本属于 bad=1 的概率
    p_bad = model.predict_proba(X)[:, 1]

    p0 = p_bad[y == 0]  # balanced
    p1 = p_bad[y == 1]  # unbalanced

    if len(p0) < 3 or len(p1) < 3:
        # 数据太少就回退默认
        return 0.5

    thr = 0.5 * (float(np.median(p0)) + float(np.median(p1)))
    # 防止极端值
    thr = max(0.05, min(0.95, thr))
    return thr

def upsert_threshold(conn, user_id, thr):
    conn.execute(
        "INSERT INTO thresholds (user_id, thr, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET thr=excluded.thr, updated_at=excluded.updated_at",
        (user_id, float(thr), time.time())
    )
    conn.commit()
def get_threshold(conn, user_id, default=0.5):
    cur = conn.execute(
        "SELECT thr FROM thresholds WHERE user_id=?",
        (user_id,)
    )
    row = cur.fetchone()
    return float(row[0]) if row else default

def start_record(user_id, label, duration):
    global recording, record_user_id, record_label, record_end_ts, current_user_id
    recording = True
    record_user_id = user_id
    record_label = int(label)
    current_user_id = user_id
    record_end_ts = time.time() + float(duration)
    print(f"[CALIB] START user={current_user_id}, label={label}, duration={duration}s")

def stop_record():
    global recording
    if recording:
        print("[CALIB] STOP")
    recording = False

    X, y = load_user_xy(conn, record_user_id)
    if X is not None and len(X) > 5:
        thr = compute_threshold_from_calib(model_blc, X, y)
        upsert_threshold(conn, record_user_id, thr)
        print("[CALIB] threshold saved:", thr)
    else:
        print("[CALIB] not enough data for threshold")

# Timing
def Timers(seattype, current_ts, blc_bad):
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
        client.subscribe("chair/sensors")
        client.subscribe("chair/calib")
        client.subscribe("chair/user")
    else:
        print(f"Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global recording, record_end_ts, record_user_id, record_label, current_user_id

    payload_text = msg.payload.decode()

    if msg.topic == "chair/user":
        try:
            user_data = json.loads(payload_text)
            new_user_id = str(user_data["user_id"]).strip()
            if new_user_id:
                current_user_id = new_user_id
                print(f"[CONTROL] Active user switched to: {current_user_id}")
        except Exception as e:
            print("[CONTROL] bad user msg:", payload_text, "err:", e)
        return

    if msg.topic == "chair/calib":
        try:
            user_data = json.loads(payload_text)
            user_id = user_data["user_id"]
            label = user_data["label"]         
            duration = user_data.get("duration", 10)
            start_record(user_id, label, duration)
            print("Recording started for user:", user_id)
        except Exception as e:
            print("[CONTROL] bad msg:", payload_text, "err:", e)
        return
    if msg.topic == "chair/sensors":
        try:
            data = json.loads(payload_text) # get data
            current_ts = data.get("timestamp")
            seattype = data.get("seattype")
            pressure = data.get("pressure")

            if (not isinstance(pressure, list)) or len(pressure) != 4:
                return

            if recording:
                print("Recording status:", recording)
                if time.time() >= record_end_ts:
                    stop_record()
                else:
                    insert_sample(conn, record_user_id, current_ts, pressure, record_label)
        except Exception as e:
            print("[SENSORS] bad msg:", payload_text, "err:", e)

        # predict through model
        p_bad = model_blc.predict_proba([pressure])[0][1]  
        thr = get_threshold(conn, current_user_id, 0.5)
        blc_bad = 1 if p_bad >= thr else 0
        sit_duration, blc_duration = Timers(seattype, current_ts, blc_bad)

        # Daily stat
        global sit_time_day, blc_count_day, blc_time_day
        global pressure_samples_day, prev_blc_bad
        global last_ts_day, current_date

        def date_key(ts):
            return datetime.fromtimestamp(ts).date().isoformat()
        d = date_key(current_ts)

        if current_date is None:
            current_date = d
            last_ts_day = current_ts

        if d != current_date:
            if current_user_id:
                save_daily_summary(conn, current_user_id)
            # 简单清零（后续可以加 flush）
            sit_time_day = 0.0
            blc_count_day = 0
            blc_time_day = 0.0
            pressure_samples_day = []
            current_date = d
            last_ts_day = current_ts

        dt = current_ts - last_ts_day if last_ts_day else 0.0
        last_ts_day = current_ts

        if seattype == 1:
            sit_time_day += dt
            pressure_samples_day.append(pressure)

            if blc_bad == 1:
               blc_time_day += dt

            if prev_blc_bad == 0 and blc_bad == 1:
                blc_count_day += 1

        prev_blc_bad = blc_bad
        if current_user_id:
            save_daily_summary(conn, current_user_id)
    
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
