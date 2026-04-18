# Chair Desktop Pet - Electron 应用

一款基于 Electron 的桌面应用，实时监控坐姿健康，提供友好的 UI 交互体验。

## 功能特性

✨ **双窗口设计**
- 🐾 **Pet 浮窗**：轻量级悬浮窗，显示实时 emoji 心情，可置顶、透明、随意移动
- 📊 **Dashboard 窗口**：完整的分析仪表板，显示详细数据和校准功能

🔗 **直接 MQTT 连接**
- 前端直接订阅 MQTT broker（无需 Flask 中转）
- 实时接收树莓派传感器数据
- 低延迟、高效率

💾 **本地持久化**
- 使用 `localStorage` 保存用户 ID 和设置
- 应用重启后自动恢复状态

📈 **核心功能**
- 实时坐姿检测（入座、平衡、不平衡）
- Emoji 心情反馈（坐姿时长的函数）
- 压力分布可视化（4 个 FSR 传感器）
- Calibration 录制模式（记录校准样本至数据库）
- 原始数据 JSON 显示

---

## 安装

### 1. 安装 Node.js
从 [nodejs.org](https://nodejs.org/) 下载并安装 LTS 版本

### 2. 克隆项目
```bash
cd d:\DeskTOP\531 Seat\electron
```

### 3. 安装依赖
```bash
npm install
```

这会安装：
- `electron` - 桌面应用框架
- `mqtt` - MQTT 客户端库

---

## 运行

### 开发模式（带调试工具）
```bash
npm run dev
```

### 生产模式
```bash
npm start
```

---

## 项目结构

```
electron/
├── package.json              # 项目配置
├── main.js                  # Electron 主进程（窗口管理）
├── preload.js               # 渲染进程安全桥接
├── src/
│   ├── pet/                # 桌宠窗口
│   │   ├── pet.html        # HTML 结构
│   │   ├── pet.js          # 核心逻辑
│   │   └── pet.css         # 样式
│   ├── dashboard/          # 仪表板窗口
│   │   ├── dashboard.html  # HTML 结构
│   │   ├── dashboard.js    # 核心逻辑
│   │   └── dashboard.css   # 样式
│   └── shared/             # 共享模块
│       └── mqtt.js         # MQTT 连接管理（预留）
└── README.md               # 本文件
```

---

## 使用流程

### 1️⃣ 启动应用
```bash
npm start
```
→ 会出现一个小的桌宠浮窗（底部左侧）

### 2️⃣ 设置用户 ID
- 方法 A：在浮窗上**右键菜单（暂未实现）**
- 方法 B：点击浮窗的 **📊 按钮** → 打开 Dashboard 窗口 → 输入用户 ID → Sync

### 3️⃣ 连接树莓派
- 确保**树莓派运行 `mqtt_infer.py` 或 `emulator.py`**
- 应用会自动连接到 `wss://test.mosquitto.org:8081`（WebSocket MQTT）

### 4️⃣ 实时监控
- 浮窗显示实时 **emoji**（根据坐姿时间变化）
- Dashboard 显示详细数据（压力分布、时间、原始 JSON）

### 5️⃣ 校准数据录制（可选）
**在 Dashboard 中：**
1. 切换到 **"Calibration Mode"** 标签页
2. 输入持续时间（如 30 秒）
3. 点击 **"Record Label 0 (Balanced)"** 或 **"Record Label 1 (Unbalanced)"**
4. 在规定时间内摆出相应姿态，系统会自动记录所有数据
5. 数据存储在 `d:\DeskTOP\531 Seat\pi\chair.db` 的 `sensor_data` 表中

### 6️⃣ 查看历史数据
- 运行 `d:\DeskTOP\531 Seat\pi\test_db.ipynb` 来查询数据库中的校准数据

---

## MQTT 主题设计

| 主题 | 发布者 | 订阅者 | 用途 |
|------|--------|--------|------|
| `chair/sensors` | Pi/Emulator | Electron | 实时传感器数据 |
| `chair/user` | Electron | Pi/Emulator | 用户 ID + 校准命令 |

### chair/sensors Payload
```json
{
  "timestamp": 1234567890.123,
  "user_id": "user123",
  "raw_values": [100, 150, 120, 110],
  "norm_values": [0.5, 0.6, 0.55, 0.5],
  "seattype": 1,
  "blc_bad": 0,
  "time_sit": 45,
  "time_blc": 0,
  "record_label": null
}
```

### chair/user Payload (设置用户 ID)
```json
{
  "user_id": "user123"
}
```

### chair/user Payload (启动录制)
```json
{
  "user_id": "user123",
  "recording": true,
  "label": "0",
  "duration": 30
}
```

---

## 配置

### MQTT Broker 地址
在 `src/pet/pet.js` 和 `src/dashboard/dashboard.js` 中修改：

```javascript
const brokerURL = 'wss://test.mosquitto.org:8081';  // WebSocket 地址
```

如果使用自己的 broker（需要支持 WebSocket）：
```javascript
const brokerURL = 'wss://your-broker:8081';
```

---

## 故障排查

### 连接不到 MQTT
- ❌ 确保网络正常
- ❌ 检查 broker 地址是否正确
- ❌ 查看浏览器控制台（F12）的错误信息

### 没有接收到数据
- ❌ 树莓派是否在运行 `mqtt_infer.py` 或 `emulator.py`？
- ❌ 树莓派和电脑是否在同一网络（互联网或局域网）？
- ❌ `chair/sensors` 主题有没有数据？

### 校准数据没有保存
- ❌ 树莓派的 `chair.db` 是否存在且可写？
- ❌ `mqtt_infer.py` 中的 `write_to_database()` 是否被触发？
- ❌ 运行 `test_db.ipynb` 查询数据库

---

## 打包为 .exe（Windows）

安装 `electron-builder`：
```bash
npm install --save-dev electron-builder
```

在 `package.json` 中添加：
```json
"build": {
  "appId": "com.chair-pet.app",
  "productName": "Chair Pet",
  "files": ["main.js", "preload.js", "src/**/*"],
  "win": {
    "target": ["nsis", "portable"]
  }
}
```

打包：
```bash
npm run build
```

→ 生成 `.exe` 文件在 `dist/` 目录

---

## 开发建议

### 添加新功能
1. **Pet 窗口新功能**：编辑 `src/pet/pet.js`
2. **Dashboard 新功能**：编辑 `src/dashboard/dashboard.js`
3. **样式调整**：分别编辑 `.css` 文件

### 调试
按 **F12** 打开开发者工具（Chromium DevTools），查看：
- Console - JavaScript 错误和日志
- Network - MQTT 连接状态

### MQTT 测试
使用命令行 MQTT 客户端进行测试：
```bash
mosquitto_sub -h test.mosquitto.org -t "chair/sensors" -v
```

---

## 参考链接

- [Electron 文档](https://www.electronjs.org/docs)
- [MQTT.js 文档](https://github.com/mqttjs/MQTT.js)
- [test.mosquitto.org](https://test.mosquitto.org/) - 公共 MQTT broker

---

## 许可证

此项目为学习项目。

---

## 常见问题

**Q: 浮窗总是在后面**
A: 这是设计的，点击浮窗会弹出 Dashboard，关闭 Dashboard 后浮窗会再次置顶。

**Q: 能否自定义浮窗大小/位置？**
A: 可以，编辑 `main.js` 中的 `createPetWindow()` 函数，修改 `width`, `height`, `x`, `y` 参数。

**Q: 能否添加更多 emoji？**
A: 可以，编辑 `getEmojiByTimeSit()` 函数，添加更多的时间阈值和 emoji。

**Q: Electron 应用如何自启动？**
A: 需要在系统启动文件夹中添加快捷方式，或使用第三方库（如 `electron-squirrel-startup`）。

---

**问题？建议？** 欢迎反馈！
