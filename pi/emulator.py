import paho.mqtt.client as mqtt
import json
import time, threading
import sys
import sqlite3

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Successfully connected to broker")
    else:
        print(f"Connection failed with code {rc}")

# ============ 数据库写入函数 ============
def write_to_database(payload):
    """
    将数据写入SQLite数据库
    """
    try:
        conn = sqlite3.connect("chair.db")
        cursor = conn.cursor()
        
        # 创建表（如果不存在）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                user_id TEXT,
                raw_values TEXT,
                norm_values TEXT,
                blc_bad INTEGER,
                record_label TEXT
            )
        """)
        
        cursor.execute("""
            INSERT INTO sensor_data 
            (timestamp, user_id, raw_values, norm_values, blc_bad, record_label)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            payload["timestamp"],
            payload.get("user_id"),
            json.dumps(payload["raw_values"]),
            json.dumps(payload["norm_values"]),
            payload["blc_bad"],
            payload.get("record_label")  # 外部设置的标签
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Error writing to database: {e}")

# ============ MQTT 客户端设置 ============
# 创建publisher和subscriber client
publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "emulator_pub")
subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "emulator_sub")

publisher.on_connect = on_connect
subscriber.on_connect = on_connect

# 全局变量：存储前端发送的calibration信息
calibration_state = {
    "user_id": None,
    "record_label": None,
    "lock": threading.Lock()
}

def on_message_user(client, userdata, msg):
    """订阅chair/user主题，接收前端的calibration命令"""
    try:
        payload = json.loads(msg.payload.decode())
        with calibration_state["lock"]:
            if "user_id" in payload:
                calibration_state["user_id"] = payload["user_id"]
                print(f"[MQTT] Received user_id: {payload['user_id']}")
            if "label" in payload:
                calibration_state["record_label"] = payload["label"]
                print(f"[MQTT] Received record_label: {payload['label']}")
    except Exception as e:
        print(f"[MQTT] Error parsing message: {e}")

subscriber.on_message = on_message_user

# Connect to public broker
print("Connecting to broker...")
publisher.connect("test.mosquitto.org", 1883, 60)
subscriber.connect("test.mosquitto.org", 1883, 60)

publisher.loop_start()
subscriber.loop_start()

# 订阅chair/user主题
subscriber.subscribe("chair/user", qos=1)

# ============ 数据处理逻辑（从mqtt_infer.py复制） ============
SEATTYPE_THRESHOLD = 0.2
BAD_POSTURE_THRESHOLD = 5

def detect_seattype(norm_values):
    """判断是否入座"""
    pressure_sum = sum(norm_values)
    return 1 if pressure_sum > SEATTYPE_THRESHOLD else 0

def detect_bad_balance(norm_values):
    """判断坐姿是否不平衡"""
    if not norm_values or all(v == 0 for v in norm_values):
        return 0
    
    # 方差规则：计算压力值分布的方差
    mean_val = sum(norm_values) / len(norm_values)
    variance = sum((v - mean_val) ** 2 for v in norm_values) / len(norm_values)
    
    # 方差过大则认为坐姿不平衡
    return 1 if variance > 0.05 else 0

# ============ 模拟数据 ============
patterns = {
    "0": [0.0, 0.0, 0.1, 0.0], #unseated
    "1": [0.5, 0.5, 0.5, 0.5], #balanced
    "2": [0.9, 0.1, 0.8, 0.2],#unbalanced
} 
current_mode = "0"
lock = threading.Lock()
stop_event = threading.Event()

# 时间计数
st_time = None  # 坐下开始时间
blc_time = None  # 不良坐姿开始时间

def input_listener():
    """
    交互输入线程：随时更新模式
    状态转换规则：
    - 0 → 1/2: 开始计时 (第一次入座)
    - 1 → 2 或 2 → 1: 保持时间连续 (只是坐姿改变，不是状态转变)
    - 1/2 → 0: 重置时间 (离座)
    """
    global current_mode, st_time, blc_time
    print("Press 0 for Unseated, 1 for Balanced, 2 for Unbalanced, q to quit")
    while True:
        cmd = input("> ").strip()
        if cmd in ("0", "1", "2"):
            with lock:
                prev_mode = current_mode
                current_mode = cmd
                
                # 状态转换逻辑
                if cmd == "0":  # 转到unseated - 重置所有计时
                    st_time = None
                    blc_time = None
                    print(f"Switched to mode {cmd} (UNSEATED) - timing reset")
                elif prev_mode == "0":  # 从unseated转到seated - 开始新的计时周期
                    st_time = time.time()
                    if cmd == "2":
                        blc_time = time.time()
                    else:
                        blc_time = None
                    print(f"Switched to mode {cmd} (SEATED) - timing started")
                else:  # 1→2 或 2→1: 坐姿改变但保持在seated状态
                    # 时间保持连续，只更新bad_balance计时
                    if cmd == "2" and blc_time is None:
                        blc_time = time.time()
                    elif cmd == "1":
                        blc_time = None
                    print(f"Switched to mode {cmd} - timing continues")
        elif cmd.lower() == "q":
            raise SystemExit
        
threading.Thread(target=input_listener, daemon=True).start()
        
try:
    while True:
        with lock:
            mode = current_mode
            sit_start = st_time
            blc_start = blc_time
        
        # 获取当前norm_values
        norm_values = patterns[mode]
        
        # 数据处理（使用mqtt_infer的逻辑）
        seattype = detect_seattype(norm_values)
        blc_bad = detect_bad_balance(norm_values)
        
        # 计时
        current_time = time.time()
        time_sit = int(current_time - sit_start) if sit_start is not None else 0
        time_blc = int(current_time - blc_start) if blc_start is not None else 0
        
        # 决定是否应该振动
        should_vibrate = (blc_bad == 1 and time_blc > BAD_POSTURE_THRESHOLD)
        
        # 获取前端设置的user_id和record_label
        with calibration_state["lock"]:
            user_id = calibration_state["user_id"]
            record_label = calibration_state["record_label"]
        
        # 构建payload（与mqtt_infer一致）
        payload = {
            "timestamp": current_time,
            "user_id": user_id,
            "is_running": True,
            "raw_values": [int(v * 1000) for v in norm_values],  # 模拟raw值
            "norm_values": norm_values,
            "seattype": seattype,
            "blc_bad": blc_bad,
            "time_sit": time_sit,
            "time_blc": time_blc,
            "should_vibrate": should_vibrate,
            "record_label": record_label  # 添加record_label
        }
        
        # 发布到MQTT
        publisher.publish("chair/sensors", json.dumps(payload), qos=1)
        
        # 写入数据库
        write_to_database(payload)
        
        print(f"[MODE {mode}] seattype={seattype} blc_bad={blc_bad} time_sit={time_sit} time_blc={time_blc} vibrate={should_vibrate}")
        
        time.sleep(1)
except KeyboardInterrupt:
    publisher.disconnect()
    publisher.loop_stop()
    subscriber.disconnect()
    subscriber.loop_stop()