import json
import time
import pickle
import sqlite3
from datetime import datetime
from pathlib import Path
import paho.mqtt.client as mqtt

# ============ 硬件依赖 ============
try:
    import board
    import busio
    from adafruit_seesaw.seesaw import Seesaw
    HARDWARE_AVAILABLE = True
except ImportError:
    print("警告: adafruit_seesaw 未安装，使用模拟模式")
    HARDWARE_AVAILABLE = False

# ============ 配置 ============
MQTT_BROKER = "localhost"  # 修改为实际MQTT broker地址
MQTT_PORT = 1883
MQTT_PUBLISH_TOPIC = "chair/sensors"
MQTT_SUBSCRIBE_TOPIC = "chair/user"

# FSR Seesaw配置
FSR_PINS = [2, 3, 4, 5]  # Seesaw引脚编号
MIN_VALS = [200, 200, 200, 200]  # 原始值下限
MAX_VALS = [900, 900, 900, 900]  # 原始值上限

# 逻辑阈值
BAD_POSTURE_THRESHOLD = 5  # 秒数，坐姿不良持续时间超过此值触发振动
SEATTYPE_THRESHOLD = 0.2  # 判断入座的压力和阈值

# ============ 全局状态 ============
class SystemState:
    def __init__(self):
        self.current_user_id = None
        self.is_running = True
        self.recording = False
        self.record_label = None
        self.record_end_ts = None
        
        self.raw_values = [0, 0, 0, 0]
        self.norm_values = [0.0, 0.0, 0.0, 0.0]
        self.seattype = 0
        self.blc_bad = 0
        self.time_sit = 0
        self.time_blc = 0
        self.should_vibrate = False
        
        self.last_sit_time = None
        self.last_blc_time = None
        self.model = None
        
        self.db_path = Path(__file__).parent / "chair.db"
        self.json_path = Path(__file__).parent / "latest_result.json"
        
        # Seesaw硬件对象
        self.seesaw = None

state = SystemState()

# ============ 硬件初始化 ============
def init_seesaw():
    """初始化Seesaw I2C设备"""
    if not HARDWARE_AVAILABLE:
        print("硬件模式不可用，使用模拟数据")
        return False
    
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        state.seesaw = Seesaw(i2c)
        print("Seesaw初始化成功")
        return True
    except Exception as e:
        print(f"Seesaw初始化失败: {e}")
        return False

# ============ 传感器读取 ============
def read_raw_pressures():
    """
    从Seesaw读取4个FSR原始值
    return: [raw1, raw2, raw3, raw4]
    """
    if state.seesaw is None:
        # 模拟模式：返回随机数据用于测试
        import random
        return [random.randint(200, 800) for _ in range(4)]
    
    try:
        return [state.seesaw.analog_read(pin) for pin in FSR_PINS]
    except Exception as e:
        print(f"FSR读取失败: {e}")
        return [0, 0, 0, 0]

def normalize(value, min_val, max_val):
    """
    将单个原始值归一化到 [0, 1]
    """
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
    将原始值数组归一化
    raw_values: [r1, r2, r3, r4]
    return: [p1, p2, p3, p4]
    """
    norm_values = [
        normalize(raw_values[i], MIN_VALS[i], MAX_VALS[i])
        for i in range(4)
    ]
    return norm_values

# ============ 坐姿判断 ============
def detect_seattype(norm_values):
    """
    判断是否入座
    规则: 4个传感器压力值的和 > SEATTYPE_THRESHOLD 则判定为入座
    """
    pressure_sum = sum(norm_values)
    return 1 if pressure_sum > SEATTYPE_THRESHOLD else 0

def detect_bad_balance(norm_values, model=None):
    """
    判断坐姿是否不平衡
    如果有模型则使用模型推理，否则使用方差规则
    """
    if not norm_values or all(v == 0 for v in norm_values):
        return 0
    
    if model is not None:
        # TODO: 使用model_blc.pkl进行推理
        try:
            # 示例: prediction = model.predict([norm_values])[0]
            # return int(prediction)
            pass
        except Exception as e:
            print(f"模型推理失败: {e}")
    
    # 回退到方差规则：计算压力值分布的方差
    mean_val = sum(norm_values) / len(norm_values)
    variance = sum((v - mean_val) ** 2 for v in norm_values) / len(norm_values)
    
    # 方差过大则认为坐姿不平衡（压力分布不均）
    return 1 if variance > 0.05 else 0

# ============ 电机控制 ============
def trigger_vibration_motor(should_vibrate):
    """
    控制振动电机
    TODO: 连接实际的GPIO或PWM引脚
    """
    try:
        # import RPi.GPIO as GPIO
        # GPIO.output(VIBRATION_PIN, GPIO.HIGH if should_vibrate else GPIO.LOW)
        if should_vibrate:
            print("[MOTOR] 触发振动")
        else:
            print("[MOTOR] 停止振动")
    except Exception as e:
        print(f"电机控制失败: {e}")

# ============ 数据处理与状态更新 ============
def update_state():
    """
    主处理循环：
    1. 读取FSR原始值
    2. 归一化处理
    3. 坐姿判断（入座、平衡度）
    4. 更新计时
    5. 决定是否振动
    """
    # 1. 读取原始值
    state.raw_values = read_raw_pressures()
    
    # 2. 归一化
    state.norm_values = get_normalized_pressures(state.raw_values)
    
    # 3. 坐姿判断
    state.seattype = detect_seattype(state.norm_values)
    state.blc_bad = detect_bad_balance(state.norm_values, state.model)
    
    # 4. 更新计时
    current_time = time.time()
    
    # 坐姿计时
    if state.seattype == 1:  # 入座
        if state.last_sit_time is None:
            state.last_sit_time = current_time
        else:
            state.time_sit = int(current_time - state.last_sit_time)
    else:  # 未入座
        state.last_sit_time = None
        state.time_sit = 0
    
    # 不良坐姿计时
    if state.blc_bad == 1:  # 不平衡
        if state.last_blc_time is None:
            state.last_blc_time = current_time
        else:
            state.time_blc = int(current_time - state.last_blc_time)
    else:  # 平衡
        state.last_blc_time = None
        state.time_blc = 0
    
    # 5. 决定是否振动
    # 条件: 处于不良坐姿且持续时间超过阈值
    state.should_vibrate = (state.blc_bad == 1 and state.time_blc > BAD_POSTURE_THRESHOLD)
    
    # 直接控制电机（本地闭环，不依赖MQTT）
    trigger_vibration_motor(state.should_vibrate)

def get_state_payload():
    """
    生成当前状态payload用于MQTT发布和JSON缓存
    """
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
        "should_vibrate": state.should_vibrate
    }

def save_latest_result(payload):
    """
    保存最新状态到JSON缓存（用于调试和fallback）
    """
    try:
        with open(state.json_path, 'w') as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"JSON保存失败: {e}")

def write_to_database(payload):
    """
    在recording状态下将数据写入SQLite
    """
    if not state.recording:
        return
    
    try:
        conn = sqlite3.connect(state.db_path)
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
            state.current_user_id,
            json.dumps(payload["raw_values"]),
            json.dumps(payload["norm_values"]),
            payload["blc_bad"],
            state.record_label
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"数据库写入失败: {e}")

# ============ MQTT处理 ============
def on_connect(client, userdata, flags, rc):
    """MQTT连接回调"""
    if rc == 0:
        print("MQTT连接成功")
        client.subscribe(MQTT_SUBSCRIBE_TOPIC)
        print(f"已订阅topic: {MQTT_SUBSCRIBE_TOPIC}")
    else:
        print(f"MQTT连接失败，错误码: {rc}")

def on_message(client, userdata, msg):
    """
    处理来自远端的控制命令
    期望payload格式：
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
        print(f"[MQTT] 收到命令: {payload}")
        
        # 设置用户ID
        if "user_id" in payload:
            state.current_user_id = payload["user_id"]
            print(f"[STATE] user_id设置为: {state.current_user_id}")
        
        # 设置recording状态
        if "recording" in payload:
            state.recording = payload["recording"]
            state.record_label = payload.get("label", None)
            if state.recording:
                duration = payload.get("duration", 60)
                state.record_end_ts = time.time() + duration
                print(f"[REC] 开始记录，标签: {state.record_label}，持续时间: {duration}s")
            else:
                print(f"[REC] 停止记录")
        
        # 处理校准命令
        if "calibrate" in payload:
            calib_type = payload["calibrate"]
            print(f"[CALIB] 校准命令: {calib_type}")
            # TODO: 实现校准逻辑
    
    except json.JSONDecodeError:
        print(f"[ERROR] MQTT消息解析失败")
    except Exception as e:
        print(f"[ERROR] MQTT消息处理异常: {e}")

def mqtt_publish(client, payload):
    """发布状态payload到MQTT"""
    try:
        msg = json.dumps(payload)
        client.publish(MQTT_PUBLISH_TOPIC, msg, qos=1)
    except Exception as e:
        print(f"[MQTT] 发布失败: {e}")

# ============ 主循环 ============
def main():
    print("=" * 50)
    print("DTK-531 智能坐姿检测系统 - Pi边缘服务")
    print("=" * 50)
    
    # 1. 初始化硬件
    print("\n[INIT] 初始化Seesaw硬件...")
    init_seesaw()
    
    # 2. 加载模型
    print("[INIT] 加载坐姿分类模型...")
    try:
        with open(Path(__file__).parent / "model_blc.pkl", 'rb') as f:
            state.model = pickle.load(f)
        print("[INIT] 模型加载成功")
    except Exception as e:
        print(f"[WARN] 模型加载失败，使用规则推理: {e}")
    
    # 3. 初始化MQTT
    print("[INIT] 连接MQTT Broker...")
    client = mqtt.Client(client_id="rpi-chair-monitor")
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
        print(f"[MQTT] 连接到 {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        print(f"[ERROR] MQTT连接失败: {e}")
        return
    
    # 4. 主循环
    print("\n[MAIN] 开始主循环，采样间隔100ms...\n")
    try:
        while state.is_running:
            # 更新系统状态
            update_state()
            
            # 生成payload
            payload = get_state_payload()
            
            # 发布到MQTT
            mqtt_publish(client, payload)
            
            # 保存到JSON缓存
            save_latest_result(payload)
            
            # 如果处于recording状态，写入数据库
            write_to_database(payload)
            
            # 检查recording是否应停止
            if state.recording and state.record_end_ts and time.time() > state.record_end_ts:
                state.recording = False
                print("[REC] 记录时间已到，自动停止")
            
            # 采样间隔
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n[MAIN] 收到中断信号")
    except Exception as e:
        print(f"\n[ERROR] 主循环异常: {e}")
    finally:
        state.is_running = False
        client.loop_stop()
        client.disconnect()
        print("[MAIN] 程序已关闭")

if __name__ == "__main__":
    main()