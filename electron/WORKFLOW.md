# Electron 应用完整工作流

## 系统架构（不使用 Flask）

```
┌─────────────────────────────────────────────────────────────────┐
│                      MQTT Broker                                 │
│            (test.mosquitto.org:1883 / 8081)                      │
└─────────────────────────────────────────────────────────────────┘
         ▲                                   ▲
         │ WebSocket                         │
         │ (wss://...)                       │
         │                                   │
    ┌────────┐                          ┌──────────────────────┐
    │ Raspi  │                          │  Electron App        │
    │ MQTT   │ chair/sensors            │  (Windows/Mac/Linux) │
    │ Pub    │◄────────────────────────►│  MQTT Sub            │
    │        │                          │                      │
    │        │ chair/user               │  - Pet Window        │
    │ mqtt   │◄────────────────────────►│  - Dashboard Window  │
    │_infer  │ (user_id, recording      │                      │
    │.py     │  commands)               │  Full UI Features    │
    │        │                          │  (Calibration, UI)   │
    └────────┘                          └──────────────────────┘
    
    OR
    
    ┌────────┐
    │emu     │
    │lator   │
    │.py     │
    └────────┘
```

## ✅ 你现在拥有的

### 前端（Electron）
- ✨ **Pet 浮窗** - 轻量级、透明、始终置顶
  - 实时 emoji 显示
  - Hover 气泡显示详情
  - 打开 Dashboard 按钮
  
- 📊 **Dashboard 仪表板** - 完整分析界面
  - **Monitoring 标签页**
    - Mood emoji card
    - State cards (seated, balance, time)
    - 压力分布可视化
    - 原始 JSON 输出
  
  - **Calibration 标签页**
    - User ID 输入（与浮窗同步）
    - 持续时间设置
    - Record Label 0/1 按钮
    - 校准状态反馈

### 后端（树莓派）
- `mqtt_infer.py` - 实时传感器读取 + MQTT 发布
- `emulator.py` - 模拟传感器数据（用于测试）
- `test_db.ipynb` - 校准数据查询分析

### 通讯中枢
- **MQTT Broker** - test.mosquitto.org（公共）
- **主题**：
  - `chair/sensors` - 传感器数据流
  - `chair/user` - 用户 ID + 校准命令

---

## 🚀 完整启动流程

### 第 1 步：准备硬件侧（树莮派）

#### 方案 A：使用真实传感器
```bash
# 树莓派上运行
cd d:\DeskTOP\531 Seat\pi
python mqtt_infer.py
```
→ 自动连接 MQTT，读取 FSR 传感器，发布到 `chair/sensors`

#### 方案 B：使用模拟器（用于测试）
```bash
# 任何电脑上运行
cd d:\DeskTOP\531 Seat\pi
python emulator.py

# 然后在提示符输入：
> 1   # 进入 seated + balanced 模式
# (会发送虚拟数据到 MQTT)
```

### 第 2 步：启动前端应用（Windows/Mac/Linux）

#### 首次运行
```bash
cd d:\DeskTOP\531 Seat\electron
npm install
npm start
```

#### 后续运行
```bash
# Windows
start.bat

# Mac/Linux
./start.sh

# 或
npm start
```

→ 会出现两个窗口：
1. **小浮窗**（底部左侧） - 🐾 桌宠
2. **Dashboard 窗口**（需按 📊 按钮打开）

### 第 3 步：配置用户

在 Dashboard 中：
1. 输入 User ID（如 `user123`）
2. 点击 **Sync** 按钮
3. 观察 MQTT 状态指示器（应该是🟢绿色）

### 第 4 步：验证数据流

#### 实时监测
- 浮窗 emoji 会根据坐姿时间变化
- Dashboard 显示实时数据（时间、压力分布、原始 JSON）

#### 校准录制（可选）
1. 切换到 **Dashboard → Calibration Mode**
2. 确保用户 ID 已填写
3. 设置持续时间（如 30 秒）
4. 点击 **Record Label 0** 或 **Record Label 1**
5. 系统开始录制所有数据到 `chair.db`

### 第 5 步：查看历史数据

```bash
# 运行 Jupyter 笔记本
cd d:\DeskTOP\531 Seat\pi
jupyter notebook test_db.ipynb
```

→ 查询校准数据：
```
SELECT * FROM sensor_data WHERE record_label IS NOT NULL
```

---

## 🔄 数据流详解

### 传感器 → MQTT → 前端

```
mqtt_infer.py / emulator.py
    ↓
发布到 chair/sensors
{
  "timestamp": 1234567890,
  "user_id": "user123",
  "raw_values": [100, 150, 120, 110],
  "norm_values": [0.5, 0.6, 0.55, 0.5],
  "seattype": 1,
  "blc_bad": 0,
  "time_sit": 45,
  "time_blc": 0,

  "record_label": null
}
    ↓
Electron 应用订阅 chair/sensors
    ↓
更新 UI：
  - emoji 心情
  - 时间显示
  - 压力柱
  - 原始 JSON
```

### 前端 → MQTT → 树莓派

```
用户在 Dashboard 输入 User ID + 点击 Sync
    ↓
发布到 chair/user
{
  "user_id": "user123"
}
    ↓
mqtt_infer.py 订阅 chair/user
    ↓
更新 state.current_user_id = "user123"
    ↓
后续发送的 chair/sensors 数据会包含这个 user_id
```

### 校准录制流程

```
用户在 Dashboard 点击 Record Label 0
    ↓
发布到 chair/user
{
  "user_id": "user123",
  "recording": true,
  "label": "0",
  "duration": 30
}
    ↓
mqtt_infer.py 接收：
  - 设置 state.recording = True
  - 设置 state.record_label = "0"
  - 设置 state.record_end_ts = now + 30s
    ↓
每次发送 chair/sensors 时调用 write_to_database()
    ↓
INSERT INTO sensor_data (..., record_label="0")
    ↓
30 秒后自动停止
    ↓
Dashboard 显示 "✓ Recording completed"
```

---

## 🔧 常见配置

### 修改浮窗大小
编辑 `main.js`：
```javascript
function createPetWindow() {
  petWindow = new BrowserWindow({
    width: 200,   // ← 改这里
    height: 250,  // ← 改这里
    // ...
  });
}
```

### 修改浮窗初始位置
```javascript
x: 100,   // ← 改 X 坐标
y: 100,   // ← 改 Y 坐标
```

### 修改 MQTT Broker
编辑 `src/pet/pet.js` 和 `src/dashboard/dashboard.js`：
```javascript
const brokerURL = 'wss://your-broker:8081';  // ← 改这里
```

### 修改 emoji 阈值
编辑 `src/pet/pet.js` 或 `src/dashboard/dashboard.js`：
```javascript
function getEmojiByTimeSit(timeSit) {
  if (timeSit === 0) return '😴';
  if (timeSit < 5) return '😄';      // ← 改这个数字
  if (timeSit < 15) return '😐';     // ← 改这个数字
  return '😭';
}
```

---

## ❌ 不再需要的组件

**不用运行：**
- ~~Flask server (server.py)~~ ✗ 不再需要
- ~~WebSocket 中转~~ ✗ 不再需要
- ~~Streamlit~~ ✗ 已完全废弃

**新架构的优势：**
- ✅ 无需部署 Flask 服务器
- ✅ 前端直接连接 MQTT（低延迟）
- ✅ 可独立打包为 .exe/.dmg/.appimage
- ✅ 可在多台计算机上运行，不需要修改代码

---

## 📝 关键文件一览

| 文件 | 用途 |
|------|------|
| `main.js` | Electron 主进程（窗口创建/管理） |
| `preload.js` | 安全桥接（IPC 通讯） |
| `src/pet/pet.html` | 浮窗 HTML |
| `src/pet/pet.js` | 浮窗逻辑（MQTT 订阅、emoji 更新） |
| `src/pet/pet.css` | 浮窗样式 |
| `src/dashboard/dashboard.html` | Dashboard HTML |
| `src/dashboard/dashboard.js` | Dashboard 逻辑（所有 UI + MQTT 发布） |
| `src/dashboard/dashboard.css` | Dashboard 样式 |
| `package.json` | 项目配置 + 依赖 |

---

## 🎯 下一步

### 短期（本周）
- ✅ 运行 Electron 应用
- ✅ 测试浮窗和 Dashboard 显示
- ✅ 验证 MQTT 连接是否正常
- ✅ 测试校准录制功能

### 中期（下周）
- 📊 添加历史曲线显示（ECharts）
- 🔔 添加系统通知（不良坐姿提醒）
- 💾 添加数据导出功能（CSV）

### 长期（优化阶段）
- 📦 打包为 .exe/.dmg/.appimage
- 🌐 考虑轻量级数据库替代方案
- 📱 可能的移动端适配

---

## 💡 技术亮点

1. **零 Flask 依赖** - 前端完全独立，不依赖服务器
2. **WebSocket MQTT** - 浏览器友好的 MQTT 连接
3. **Electron 双窗口** - 轻量级浮窗 + 完整仪表板的完美结合
4. **IPC 通讯** - 主进程和渲染进程的高效交互
5. **localStorage 持久化** - 用户设置自动保存

---

**已准备好启动应用！** 🚀
