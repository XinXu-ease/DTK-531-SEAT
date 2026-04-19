# Flask HTML Frontend Setup Guide

## 新架构说明

已从 **Streamlit** 迁移到 **Flask + HTML/WebSocket**，获得真正的实时更新能力。

### 文件结构

```
remote/
├── server.py                  # Flask + MQTT + WebSocket服务器
├── templates/
│   └── index.html            # HTML前端模板
├── static/
│   ├── style.css             # 样式表
│   └── app.js                # 前端实时更新逻辑
└── app.py                    # 已弃用 (Streamlit版本)
```

## 安装依赖

```bash
cd "d:\DeskTOP\531 Seat"
pip install -r requirements.txt
```

### 关键依赖
- `flask==2.3.3` - Web框架
- `flask-socketio==5.3.4` - WebSocket实时通信
- `paho-mqtt==1.6.1` - MQTT客户端

## 运行方式

**启动Flask服务器：**
```bash
cd d:\DeskTOP\531 Seat\remote
python server.py
```

**预期输出：**
```
============================================================
Chair Posture Monitor - Flask WebSocket Server
============================================================
Open browser at: http://localhost:5000
============================================================

[MQTT] Connecting to test.mosquitto.org:1883...
[MQTT] Connected to test.mosquitto.org, subscribing to chair/sensors
```

**打开浏览器访问：**
```
http://localhost:5000
```

## 工作流程

### 数据流：
```
mqtt_infer.py/emulator.py (发布)
        ↓
    MQTT Broker (chair/sensors)
        ↓
    server.py (订阅 + 广播)
        ↓
    WebSocket连接
        ↓
    index.html (实时显示)
```

### 前端特性：
✅ **实时更新** - 100ms刷新一次  
✅ **坐姿状态** - 显示是否有人坐下  
✅ **平衡检测** - 姿态是否良好  
✅ **振动告警** - 实时振动反馈指示  
✅ **传感器可视化** - 4个FSR传感器的压力条图表  
✅ **性能指标** - 坐姿时长、不良姿态持续时间  
✅ **连接状态** - MQTT和WebSocket连接指示灯  

## 测试流程

### 1. 启动Flask服务器
```bash
cd d:\DeskTOP\531 Seat\remote
python server.py
```

### 2. 在另一个终端启动emulator
```bash
cd d:\DeskTOP\531 Seat\pi
python emulator.py
```

### 3. 打开浏览器
```
http://localhost:5000
```

### 4. 在emulator中切换模式
```
输入 0: 椅子空着 (unseated)
输入 1: 坐姿平衡 (balanced)
输入 2: 坐姿不平衡 (unbalanced)
```

**前端应该实时显示数据变化！** ✨

## 故障排查

### 问题：浏览器显示"无法连接"
- ✅ 确保server.py正在运行
- ✅ 确保没有其他进程占用5000端口
- ✅ 尝试：`http://127.0.0.1:5000` 或 `http://localhost:5000`

### 问题：数据不更新
- ✅ 检查MQTT连接：server.py终端应显示 `[MQTT] Connected`
- ✅ 检查数据发送：运行emulator.py，应该看到 `[MQTT] Received` 消息
- ✅ 打开浏览器开发工具 (F12)，检查Console标签看WebSocket连接

### 问题：连接MQTT失败
- ✅ 尝试ping test.mosquitto.org
- ✅ 确保网络连接正常
- ✅ 检查防火墙是否阻止端口1883

## 性能优化

| 指标 | 值 |
|-----|-----|
| MQTT发布频率 | 100ms |
| WebSocket推送延迟 | <50ms |
| 前端更新帧率 | ~10 FPS (实时) |
| 支持并发客户端 | 无限制 |

## 后续计划

- [ ] 添加数据记录 (CSV/DB导出)
- [ ] 姿态历史图表
- [ ] 用户会话管理
- [ ] 移动端响应式优化
- [ ] LLM建议生成

---

**快速开始：** `python server.py` 然后访问 `http://localhost:5000`
