# 数据结构整理 (2026-04-18)

## 问题回顾
用户反馈: "LLM Error: No data available for today"

原因: llm_utils.py 查询的 `daily_segments` 表从未被创建或填充

## 当前数据流修复

### 1. 数据记录层 (Pi端 - mqtt_infer.py)

**SQLite 表结构**: `sensor_data`
```sql
CREATE TABLE sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL,              -- Unix时间戳
    user_id TEXT,                -- 用户ID
    raw_values TEXT,             -- JSON: [r1, r2, r3, r4]
    norm_values TEXT,            -- JSON: [p1, p2, p3, p4]
    seattype INTEGER,            -- 0=离座, 1=入座
    blc_bad INTEGER,             -- 0=平衡, 1=不平衡
    record_label TEXT            -- 可选: 记录标签 (用于model training)
)
```

**数据写入触发器**:
- ✅ 当 `seattype` 状态改变时 (有人入座/离座) - **自动记录**
- ✅ 当 `recording=True` 时 - 持续记录 (用于model training)

**采样周期**: 100ms (每次seattype变化时至少记录一条记录)

**位置**: `d:\DeskTOP\531 Seat\pi\chair.db`

### 2. 数据查询层 (Electron端 - llm_advice_handler.py)

**查询逻辑**:
1. 连接到 Pi 的 `chair.db`
2. 查询 `sensor_data` 表中今天的数据
3. 聚合计算:
   - `sit_duration_sec`: 记录数 × 0.1秒 (因为采样间隔100ms)
   - `blc_count`: `blc_bad=1` 的记录数
   - `blc_duration_sec`: `blc_bad=1` 的记录数 × 0.1秒

4. 调用 `llm_utils.generate_llm_advice()` 生成建议

**错误处理**:
- 如果查询无数据 → 显示: "No sensor data recorded for user 'XXX' today. Please enable recording in Dashboard."
- 如果LLM API失败 → 降级返回简单统计
- 友好的错误消息指导用户进行操作

### 3. IPC 通信流 (Electron 主进程)

**调用链**:
```
Dashboard ("Get Advice" 按钮)
  ↓
dashboard.js: window.electronAPI.getLLMAdvice(userID)
  ↓
preload.js: electronAPI.getLLMAdvice → ipcRenderer.invoke('get-llm-advice')
  ↓
main.js: ipcMain.handle('get-llm-advice') → spawn Python process
  ↓
llm_advice_handler.py: query sensor_data + call llm_utils.generate_llm_advice()
  ↓
返回 JSON: { success, advice, payload }
```

### 4. 数据库文件位置

- **Pi 数据库**: `d:\DeskTOP\531 Seat\pi\chair.db`
- **Electron 数据库访问**: 通过 Python 子进程读取
- **并发安全**: SQLite 采用文件级锁，支持多进程并发读

## 用户操作流程

### 场景 1: 获取 LLM 建议
1. 用户点击 Dashboard 中 "Get Advice" 按钮
2. Electron 通过 IPC 调用 Python 脚本
3. Python 脚本读取 Pi 的 sensor_data 表
4. 调用 LLM API 生成建议
5. 返回建议到 Dashboard 显示

**前提条件**: Pi 需要有坐姿数据记录
- ✅ 自动: 有人入座/离座时自动记录
- ✅ 手动: Dashboard 开启 "Recording" 模式

### 场景 2: 模型训练
1. Dashboard 启用 "Recording" + 选择标签 (e.g., "balanced", "unbalanced")
2. Pi 持续记录带标签的数据到 sensor_data 表
3. 收集足够数据后，在 Jupyter 中训练 `model_blc.pkl`
4. 部署新模型到 Pi，下次运行时自动加载

## 下一步计划

### 短期 (立即)
- ✅ 自动根据 seattype 变化记录数据
- ✅ 修改 llm_advice_handler 查询实际存在的表
- ✅ 添加友好的错误提示

### 中期 (Optional)
- [ ] 创建真正的 `daily_segments` 表用于优化查询性能
- [ ] 实现每日数据的定时聚合 (晚上11:59 PM)
- [ ] 存储历史建议以便对比分析

### 长期 (Future)
- [ ] 远程数据同步 (Pi → Cloud → Electron)
- [ ] 多用户数据隔离和权限管理
- [ ] 建议的个性化学习

## 测试方法

### 验证数据记录
```bash
# 在 Pi 上运行
sqlite3 chair.db
> SELECT COUNT(*) FROM sensor_data WHERE date(datetime(timestamp, 'unixepoch')) = date('now');
```

### 验证 LLM 集成
1. 启动 Electron app
2. 设置 User ID (Dashboard → sync)
3. 点击 "Get Advice" 按钮
4. 查看 Dashboard 中的建议或错误信息

### 验证数据库连接
```bash
# 从 Electron 目录
python llm_advice_handler.py "test_user"
```

输出应为 JSON:
```json
{
  "success": true,
  "advice": "Based on today's data: 5 min sitting, 2 balance events.",
  "payload": {
    "sit_time_minutes": 5.0,
    "blc_count": 2,
    "blc_time_minutes": 0.3,
    "source": "sensor_data"
  }
}
```
或
```json
{
  "success": false,
  "error": "No sensor data recorded for user 'test_user' today. Please enable recording in Dashboard."
}
```
