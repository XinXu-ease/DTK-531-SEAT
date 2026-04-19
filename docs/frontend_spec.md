这份技术文档旨在为你提供一个清晰的开发蓝图。它将复杂的 IoT 逻辑拆解为前端表现、底层架构与数据通讯三个核心模块。

---

## 🏗️ 智能桌宠系统技术架构文档 (V1.0)

### 1. 项目概述
一款基于 **Electron** 开发的桌面悬浮交互应用，通过 **MQTT** 协议实时接收**树莓派**传感器数据。该产品旨在将枯燥的硬件数据（如压力、环境数据）转化为具有情感反馈的“桌宠”形象，并提供深度的可视化看板。

---

### 2. 技术栈选型
* **前端容器**: Electron (Chromium + Node.js)
* **通讯协议**: MQTT (over WebSockets)
* **UI 渲染**: HTML5, CSS3 (Flex/Grid), JavaScript (ES6+)
* **数据可视化**: Apache ECharts 或 Chart.js
* **后端/硬件**: Raspberry Pi (Python + Paho-MQTT)

---

### 3. 系统架构与文件结构
应用采用**双窗口联动模式**：



* **`main.js` (主进程)**: 管理应用生命周期，创建透明、置顶的桌宠窗口及分析看板窗口。
* **`pet.html/js` (桌宠窗口)**: 
    * **特性**: 背景透明、无边框、置顶。
    * **功能**: 展示 PNG 序列状态、处理 Hover 气泡、接收实时数据。
* **`dashboard.html/js` (分析看板)**:
    * **特性**: 常规 UI 窗口，含背景。
    * **功能**: 渲染历史曲线、用户设置、设备注销、MQTT 指令下发。

---

### 4. 关键交互链路设计

#### **A. 身份绑定与初始化**
1.  **初次启动**: `pet.js` 检测 `localStorage` 是否有 `userID`。
2.  **触发激活**: 若无 ID，弹出 HTML 输入框。
3.  **数据挂载**: 输入 ID 后，前端订阅主题 `pet/data/{userID}`；树莓派识别到该 ID 后开始上传数据。

#### **B. 数据驱动的动画逻辑**
MQTT收到的数据与前端的emoji图片状态切换联通

#### **C. 窗口切换逻辑**
* **Hover**: 触发 `pet.js` 内部的 `div` 气泡显示。
* **Click Dashboard**: 
    * `Renderer` 进程通过 `ipcRenderer.send('open-dashboard')` 通知 `Main` 进程。
    * `Main` 进程创建/展示 `dashboard.html` 窗口。

---

### 5. 数据通讯方案 (MQTT Topic 设计)


---

### 6. 持久化与账户管理
* **存储**: 使用浏览器原生 `localStorage` 存储 `userID` 和用户偏好（如皮肤设置）。
* **注销 (Logout)**: 
    1.  在 Dashboard 点击“注销”。
    2.  清除本地缓存。
    3.  前端执行 `client.unsubscribe()`。
    4.  通知主进程关闭 Dashboard 并重置 `pet.html` 状态。

---

### 7. 部署与分发
1.  **硬件端**: 树莓派运行 Python 守护进程，开机自启。
2.  **云端**: 部署 MQTT Broker (如 EMQX)。
3.  **客户端**: 
    * 使用 `electron-builder` 打包。
    * Windows 导出 `.exe`，macOS 导出 `.dmg`。
    * 静态资源（PNG 皮肤包）可放在 OSS 云存储实现热更新。

---

> **设计要点总结**: 
> 保持**桌宠窗口**的“轻”与**看板窗口**的“深”。桌宠负责提醒和情感链接，看板负责数据分析和系统设置。所有交互通过全局唯一的 `userID` 进行逻辑串联。