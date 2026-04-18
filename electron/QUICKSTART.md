# 🚀 5 分钟快速启动

## 准备阶段

### 1. 安装 Node.js（第一次）
↓ 访问 [nodejs.org](https://nodejs.org/) → 下载 LTS → 安装

### 2. 安装依赖（第一次）
```bash
cd d:\DeskTOP\531 Seat\electron
npm install
```

---

## 启动应用

### 方式 A：双击脚本（最简单）
**Windows:** 双击 `start.bat`
**Mac/Linux:** 双击 `start.sh`

### 方式 B：命令行
```bash
cd d:\DeskTOP\531 Seat\electron
npm start
```

---

## 使用步骤

| 步骤 | 操作 | 截图位置 |
|------|------|---------|
| 1 | 程序启动，出现小浮窗 | 屏幕左下角 |
| 2 | 点击浮窗上的 **📊** 按钮 | 打开 Dashboard 窗口 |
| 3 | 输入 User ID（如 `user123`） | Dashboard 顶部 |
| 4 | 点击 **Sync** 按钮 | Dashboard 顶部 |
| 5a | （监测）观察浮窗 emoji 变化 | 浮窗显示实时心情 |
| 5b | （校准）切到 Calibration 标签页 | Dashboard 内 |
| 5c | （校准）点击 Record 按钮 | 开始录制 30 秒 |

---

## 指标检查清单

✓ MQTT 状态 = 🟢（绿色）
✓ User ID 已同步
✓ Dashboard 显示实时数据
✓ 浮窗 emoji 每 5-15 秒切换一次

---

## 常见问题快速答案

**Q: 浮窗在后面看不到**
A: 点击其他窗口，浮窗会自动置顶

**Q: 数据不更新**
A: 检查 MQTT 状态（应该是🟢），确保树莓派在运行

**Q: 校准录制没反应**
A: 确保用户 ID 已填写且 MQTT 已连接

**Q: 要关闭应用**
A: 点击 Dashboard 右上角的 ✕

---

## 树莓派侧（同时运行）

### 方案 1：真实传感器
```bash
python mqtt_infer.py
```

### 方案 2：测试模拟器
```bash
python emulator.py
> 1    # 输入 1 进入 seated 模式
```

---

## 查看校准数据

```bash
cd d:\DeskTOP\531 Seat\pi
jupyter notebook test_db.ipynb
# 然后运行第一个 cell
```

---

**准备好了？双击 `start.bat` 开始！** 🐾
