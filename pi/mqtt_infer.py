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

# 电机驱动
try:
    from adafruit_crickit import crickit
    from adafruit_motor import stepper
    MOTOR_AVAILABLE = True
except ImportError:
    print("警告: adafruit_crickit 未安装，电机将使用模拟模式")
    MOTOR_AVAILABLE = False

# ============ 配置 ============
MQTT_BROKER = "test.mosquitto.org"  # 公共MQTT broker
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
        self.current_user_id = None  # 默认为空，由前端输入设置
        self.is_running = True
        self.recording = False
        self.record_label = None
        self.record_end_ts = None
        
        self.raw_values = [0, 0, 0, 0]
        self.norm_values = [0.0, 0.0, 0.0, 0.0]
        self.seattype = 0
        self.seattype_changed = False  # 标记 seattype 是否改变
        self.blc_bad = 0
        self.time_sit = 0
        self.time_blc = 0
        self.should_vibrate = False
        
        self.last_sit_start = None  # 记录入座开始的时间戳
        self.last_blc_time = None
        self.sit_duration = 0  # 本次坐着的时间（秒）
        self.model = None
        
        self.db_path = Path(__file__).parent / "chair.db"
        self.json_path = Path(__file__).parent / "latest_result.json"
        
        # Seesaw硬件对象
        self.seesaw = None
        
        # 电机硬件对象和控制状态
        self.motor = None
        self.motor_running = False

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

def init_motor():
    """初始化电机（使用Crickit的步进电机）"""
    if not MOTOR_AVAILABLE:
        print("警告: 电机硬件不可用，使用模拟模式")
        return False
    
    try:
        state.motor = crickit.stepper_motor
        print("电机初始化成功")
        return True
    except Exception as e:
        print(f"电机初始化失败: {e}")
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
        try:
            return int(model.predict([norm_values])[0])
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
    should_vibrate=True: 电机持续转动
    should_vibrate=False: 电机停止并释放
    """
    if state.motor is None:
        # 模拟模式
        if should_vibrate and not state.motor_running:
            print("[MOTOR] 触发振动（模拟模式）")
            state.motor_running = True
        elif not should_vibrate and state.motor_running:
            print("[MOTOR] 停止振动（模拟模式）")
            state.motor_running = False
        return
    
    try:
        if should_vibrate and not state.motor_running:
            # 启动电机：持续转动
            print("[MOTOR] 触发振动（实际电机）")
            state.motor_running = True
            # 电机持续转动，由主循环中的onestep调用触发
        
        elif not should_vibrate and state.motor_running:
            # 停止电机
            print("[MOTOR] 停止振动（实际电机）")
            state.motor_running = False
            state.motor.release()  # 释放电机
    
    except Exception as e:
        print(f"电机控制失败: {e}")

def motor_step():
    """
    每个循环周期执行一次电机步进
    如果电机正在运行，执行一个步进
    """
    if state.motor_running and state.motor is not None:
        try:
            from adafruit_motor import stepper
            state.motor.onestep(direction=stepper.FORWARD)
        except Exception as e:
            print(f"电机步进失败: {e}")

# ============ 数据处理与状态更新 ============
def update_state():
    """
    主处理循环：
    1. 读取FSR原始值
    2. 归一化处理
    3. 坐姿判断（入座、平衡度）
    4. 更新计时
    5. 决定是否振动
    6. 检测seattype变化
    """
    # 保存上一个状态的seattype
    prev_seattype = state.seattype
    
    # 1. 读取原始值
    state.raw_values = read_raw_pressures()
    
    # 2. 归一化
    state.norm_values = get_normalized_pressures(state.raw_values)
    
    # 3. 坐姿判断
    state.seattype = detect_seattype(state.norm_values)
    state.blc_bad = detect_bad_balance(state.norm_values, state.model)
    
    # 检测seattype是否改变
    state.seattype_changed = (prev_seattype != state.seattype)
    
    # 4. 更新计时
    current_time = time.time()
    
    # 坐姿计时：当离座时（seattype 从 1 变为 0）计算本次坐着的时间
    if state.seattype == 1:  # 入座
        if state.last_sit_start is None:
            # 开始坐着
            state.last_sit_start = current_time
        state.time_sit = int(current_time - state.last_sit_start)
        state.sit_duration = 0  # 重置离座时的 duration
    else:  # 未入座
        if state.last_sit_start is not None and state.seattype_changed:
            # 刚离座，计算本次坐着的总时间
            state.sit_duration = int(current_time - state.last_sit_start)
            state.time_sit = state.sit_duration
            print(f"[LOG] Seat duration: {state.sit_duration}s")
        else:
            state.sit_duration = 0
        state.last_sit_start = None
    
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
    # 条件: 只有在入座(seattype=1) 且 处于不良坐姿(blc_bad=1) 且 持续时间超过阈值(5s) 才震动
    state.should_vibrate = (state.seattype == 1 and state.blc_bad == 1 and state.time_blc > BAD_POSTURE_THRESHOLD)
    
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
        "should_vibrate": state.should_vibrate,
        "sit_duration": state.sit_duration  # 本次坐着的时间（秒）
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
    在以下情况下将数据写入SQLite:
    - user_id 已设置 (不等于 None) AND seattype状态发生变化（入座或离座）
    
    原因：
    1. 只要设置了 user_id，就自动开始记录该用户的坐姿数据
    2. 无需额外的 recording 标志
    3. record_label 仍可选，用于标记特殊的训练数据
    """
    # 条件: user_id 已设置 AND seattype 状态改变
    should_record = state.current_user_id is not None and state.seattype_changed
    
    if not should_record:
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
                seattype INTEGER,
                sit_duration REAL,
                blc_bad INTEGER,
                record_label TEXT
            )
        """)
        
        cursor.execute("""
            INSERT INTO sensor_data 
            (timestamp, user_id, raw_values, norm_values, seattype, sit_duration, blc_bad, record_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload["timestamp"],
            state.current_user_id,
            json.dumps(payload["raw_values"]),
            json.dumps(payload["norm_values"]),
            payload["seattype"],
            payload["sit_duration"],
            payload["blc_bad"],
            state.record_label
        ))
        
        conn.commit()
        conn.close()
        
        # 日志输出
        status = "📍 seated" if payload["seattype"] == 1 else "🚶 left seat"
        duration_str = f"duration={payload['sit_duration']}s" if payload["seattype"] == 0 else ""
        print(f"[DB] Recorded: user {state.current_user_id} {status} {duration_str} | blc_bad={payload['blc_bad']}")
    
    except Exception as e:
        print(f"[DB] Error: {e}")

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
        # 打印到终端
        print(f"[MQTT] {payload}")
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
    
    # 2. 初始化电机
    print("[INIT] 初始化电机...")
    init_motor()
    
    # 3. 加载模型
    print("[INIT] 加载坐姿分类模型...")
    try:
        model_path = Path(__file__).parent / "model_blc.pkl"
        if not model_path.exists():
            print(f"[WARN] 模型文件不存在: {model_path}")
        else:
            with open(model_path, 'rb') as f:
                state.model = pickle.load(f)
            print("[INIT] 模型加载成功")
    except Exception as e:
        print(f"[WARN] 模型加载失败，使用规则推理: {e}")
    
    # 4. 初始化MQTT
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
    
    # 5. 主循环
    print("\n[MAIN] 开始主循环，采样间隔100ms...\n")
    try:
        while state.is_running:
            # 更新系统状态
            update_state()
            
            # 执行电机步进（如果电机正在运行）
            motor_step()
            
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
            time.sleep(0.5)
    
    except KeyboardInterrupt:
        print("\n[MAIN] 收到中断信号")
    except Exception as e:
        print(f"\n[ERROR] 主循环异常: {e}")
    finally:
        state.is_running = False
        client.loop_stop()
        client.disconnect()
        
        # 释放电机
        if state.motor is not None:
            try:
                state.motor.release()
                print("[MOTOR] 电机已释放")
            except Exception as e:
                print(f"[MOTOR] 电机释放失败: {e}")
        
        print("[MAIN] 程序已关闭")

if __name__ == "__main__":
    main()
