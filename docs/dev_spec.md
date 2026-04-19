## 1. 项目概述
基于 Raspberry Pi、FSR 压力传感器、MQTT 通信和远端网页界面的智能坐姿检测与提醒系统。

系统采用“边缘设备优先”的架构设计：

* 树莓派负责实时采集、归一化、推理、振动反馈和本地状态存储。
* 远端电脑负责用户交互、可视化展示、控制指令发送，以及可选的 LLM 总结能力。
* MQTT 作为树莓派与远端界面之间的通信层。

这种设计可以保证核心反馈闭环始终在树莓派本地完成，不依赖网络延迟或远端界面是否在线。

---

## 2. 目标目录结构

```text
DTK-531-SEAT/
├── pi/
│   ├── mqtt_infer.py
│   ├── model_blc.pkl
│   ├── chair.db
│   └── latest_result.json
├── remote/
│   ├── app.py
│   └── llm_utils.py
├── docs/
├── requirements.txt
└── README.md
```

该结构将边缘运行层和远端 UI 层分开，使部署职责更加清晰。

---

## 3. 设计原则

系统遵循以下四个核心设计原则。

### 3.1 实时闭环留在树莓派本地

树莓派应独立完成关键实时链路：

* 读取传感器输入
* 归一化压力值
* 判断入座与坐姿状态
* 触发振动电机

这样即使远端网页断开，坐姿提醒功能仍可正常工作。

### 3.2 MQTT 是通信层，不是内部依赖链

MQTT 用于树莓派与远端界面之间的通信。

### 3.3 状态字典是主输出，JSON 文件是辅助缓存

系统主输出应该是一个 Python 状态字典，并通过 MQTT 发布。
`latest_result.json` 应被视为本地缓存或调试产物，而不是模块之间实时协同的主桥梁。

### 3.4 远端负责控制，树莓派负责执行

远端界面负责发送如下控制命令：

* set user
* calibrate

树莓派负责执行这些命令，并维护系统的实时运行状态。


---

## 4. 总体架构

系统可分为三层。

### 4.1 树莓派边缘运行层

负责：

* 传感器输入
* 数据归一化
* 推理判断
* motor 控制
* 本地存储
* MQTT 发布与订阅

### 4.2 MQTT 通信层

负责：

* 将树莓派运行状态发送到远端
* 将远端控制命令发送到树莓派

### 4.3 远端交互层

负责：

* 用户控制
* 校准控制
* 数据显示
* LLM 总结输出

---

## 5. 模块职责说明

## 5.1 `pi/mqtt_infer.py`

### 所在位置

树莓派端

### 模块角色

这是树莓派上的核心运行服务。

### 主要职责

* 初始化 MQTT client
* 订阅远端控制类 topic
* 读取 FSR 传感器数值
* 对原始传感器数值进行归一化
* 使用规则或模型进行坐姿判断 (seattype, bad_blc)
* 判断是否应触发电机振动 (time_blc>threshold)
* 本地直接控制 vibration motor
* 将处理后的实时状态发布到 MQTT (chair/sensors)
* 将最新状态写入本地 JSON 缓存
* 在满足记录条件时，将运行数据写入 SQLite 数据库
* 维护运行变量，例如：

  * `current_user_id`
  * `is_running`
  * `recording`
  * `record_label`
  * `record_end_ts`
  * 坐姿计时变量，如 time_sit 和 blc_time

### 关键说明

这个文件应成为树莓派侧运行状态的唯一主服务。

* 直接计算当前状态
* 直接用于 motor 控制
* 直接作为 MQTT payload 发布
* 同时可选写本地缓存和数据库

其中，数据库写入不应默认持续开启，而应由user_id是否输入或 calibration 状态触发。也就是说，实时检测主链路始终运行，而 SQLite 记录链路仅在用户显式触发后开启。

---

## 5.2 `pi/model_blc.pkl`

### 所在位置

树莓派端

### 模块角色

存放训练好的坐姿分类模型。

### 主要职责

* 被 `mqtt_infer.py` 加载
* 用于判断 balanced / unbalanced 等状态
* 支持轻量级本地推理

### 为什么应放在树莓派

它属于实时推理链路的一部分，应与硬件运行时保持接近。

---

## 5.3 `pi/chair.db`

### 所在位置

树莓派端

### 模块角色

本地结构化记录数据库。

### 主要职责

保存由前端显式触发的记录数据，例如：

* calibration 样本
* 带标签的压力数据
* 与特定 `user_id` 关联的过程数据
* 必要的训练/调试记录

可能保存的字段包括：

* timestamp
* user_id
* 原始压力值
* 归一化后的压力值
* label
* calibration 类型
* 记录时段内的状态信息

### 为什么应放在树莓派

树莓派是整个系统的一手采集节点，因此最适合作为原始与处理后数据的首要记录位置。

### 用途

该数据库主要支持：

* calibration 数据采集
* 标注样本记录
* 用户相关的数据留存
* 后续模型训练或分析
* LLM 总结生成的数据基础

### 重要说明

`chair.db` 不是默认记录所有实时状态的全量日志数据库。
是否写入数据库应由远端命令触发，例如输入 `user_id`。

---

## 5.4 `pi/latest_result.json`

### 所在位置

树莓派端

### 模块角色

保存最新一帧运行状态的本地缓存文件。

### 主要职责

* 存储最近一次处理后的状态快照
* 提供一个人类可读的调试文件
* 支持开发期间快速检查输出
* 必要时可作为 fallback

### 重要设计说明

该文件不应再作为传感器处理链和前端之间的主传递桥梁。

更合理的设计应是：

* MQTT 状态 payload 是主实时输出
* `latest_result.json` 只是可选辅助

---

## 5.5 `remote/app.py`

### 所在位置

远端电脑端

### 模块角色

远端控制面板与实时可视化界面。

### 主要职责

* 提供用户交互界面
* 发送 MQTT 控制命令到树莓派 （chair/user）
* 显示压力值、入座状态、坐姿状态、计时信息和反馈状态
* 提供 calibration 控制
* 提供 user 切换或 user 上下文设置
* 展示LLM summary 生成结果

### 界面功能

* 可选设置 `user_id`
* start / stop monitoring
* 启动 balanced calibration recording
* 启动 unbalanced calibration recording
* 显示 `seattype`
* 显示 sitting duration / bad posture duration
* 显示 alert state

---

## 5.6 `remote/llm_utils.py`

### 所在位置

远端电脑端

### 模块角色

基于 LLM 的总结与建议生成模块。

### 主要职责

* 读取历史数据
* 构建 day summary 或 session-level advice 的 prompt
* 生成自然语言建议
* 输出人类可读的 posture summary 或 wellness advice

### 为什么应放在远端

这类逻辑不是实时控制的一部分，而且依赖网络 API。
将它放在远端可以减少树莓派运行负担，并保持边缘运行层精简。

---

## 5.7 `docs/`

### 所在位置

仓库中的文档目录

### 模块角色

存放系统架构和技术文档。

### 建议内容

* 系统架构图
* MQTT topic 设计说明
* 部署说明
* 数据结构说明
* 架构笔记
* 后续迭代路线

---

## 5.8 `README.md`

### 所在位置

项目根目录

### 模块角色

顶层说明与启动指南。

### 主要职责

应包括：

* 项目功能简介
* 系统结构说明
* 如何启动树莓派端服务
* 如何启动远端页面
* 必需的环境变量说明
* MQTT topics 说明
* 部署说明

---

## 5.9 `requirements.txt`

### 所在位置

项目根目录

### 模块角色

项目依赖说明文件。

### 主要职责

列出树莓派端和远端运行所需的 Python 包，或说明环境安装方式。

### 实际建议

如果后续树莓派和远端依赖差异较大，可以拆分成：

* `pi/requirements.txt`
* `remote/requirements.txt`

当前阶段保留一个根目录 `requirements.txt` 也是可以接受的。

---

## 6. 运行数据流

## 6.1 主感知与反馈链路

推荐的运行流程如下：

1. `mqtt_infer.py` 读取 FSR 原始值
2. 对原始值做归一化
3. 使用规则/模型判断当前坐姿状态
4. 立即决定是否触发 motor
5. 如有需要(time_blc较大)，直接触发 vibration motor,并判断是否关闭vib，逻辑与当前的emoji抖动意昂
6. 构建处理后的状态字典
7. 将该状态发布到 MQTT
8. 将该状态写入 `latest_result.json`

### 重要说明

motor 控制应直接使用内存中的推理结果。
不应依赖重新读取 `latest_result.json` 再决定是否振动。

这条主链路不依赖 `user_id`。
即使用户没有输入 `user_id`，系统也应继续完成实时检测、状态发布和振动反馈。

---

## 6.2 记录链路

系统包含一条与主实时链路并行的“可选记录链路”。

典型流程如下：

1. 用户在远端页面中输入 `user_id`
2. 用户点击 calibration 触发 recording 行为
3. 页面通过 `chair/user` 或 `chair/calib` 发送上下文和记录命令
4. 树莓派更新：

   * `current_user_id`
   * `recording`
   * `record_label`
   * `record_end_ts`
5. 在 recording 窗口内，将压力数据写入 `chair.db`；如果接受calib触发，则需要包括balance标签将压力数据写入 'test_db.ipynb' 这个SQLite，参考原有逻辑


---

## 6.3 总结/分析链路

系统还包含一个更高层的分析流程。

1. 记录数据持续写入 `chair.db`
2. 远端读取或获取历史记录(利用command获取远端信息，现阶段先不做)
3. `llm_utils.py` 构建总结输入
4. LLM 输出人类可读的建议或 session summary

该链路是异步的，不属于主实时反馈链路的一部分。

---


## 7. 推荐的状态 Payload

处理后的实时状态应作为一个完整字典发布。

示例：

```json
{
  "timestamp": 1712345678.12,
  "user_id": "xin",
  "is_running": true,
  "raw_values": [312, 455, 287, 490],
  "norm_values": [0.22, 0.61, 0.18, 0.67],
  "seattype": 1,
  "blc_bad": 1,
  "time_sit": 1240,
  "time_blc": 320,
  "should_vibrate": true
}
```

### 字段含义

* `timestamp`：当前状态时间戳
* `user_id`：当前用户上下文，可为空
* `is_running`：系统是否处于运行状态
* `raw_values`：原始压力传感器值
* `norm_values`：归一化后的压力值
* `seattype`：是否入座
* `blc_bad`：不良平衡状态标记
* `time_sit`：累计坐姿时间
* `time_blc`：累计不良坐姿时间
* `should_vibrate`：当前是否触发振动

### 说明

`user_id` 在状态 payload 中可以保留，但应视为可选元数据。
它主要在用户进入记录/校准流程后才具有明确含义。

---

## 10. 部署模型

## 10.1 树莓派端

建议作为长时间运行的边缘服务。

### 启动方式

建议开机自启动。

### 主入口文件

```text
pi/mqtt_infer.py
```

### 部署职责

* 初始化硬件
* 保持实时循环运行
* 接收 MQTT 控制命令
* 发布实时状态
* 在 recording/calibration 状态下写入数据库

---

## 10.2 远端电脑端

按需运行交互界面。

### 主入口文件

```text
remote/app.py
```

### 部署职责

* 提供用户控制界面
* 展示实时状态
* 触发 calibration 和 user 上下文设置
* 可选生成总结

---

## 11. 后续可扩展方向

当前架构支持以下后续扩展：

### 可扩展项

* 拆分 `pi/requirements.txt` 和 `remote/requirements.txt`
* 增加独立的 calibration manager 模块
* 增加多用户 profile 管理
* 用 Flask/FastAPI 替换或补充 Streamlit 作为远端接口
* 增加 `chair.db` 导出服务
* 增加 daily summary scheduler
* 增加更丰富的 posture 标签和 confidence 输出
* 增加云端同步能力

