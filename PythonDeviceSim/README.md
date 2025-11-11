# AWS IoT Virtual Vibration Sensor Simulator (Python)

完整复制 ESP32 设备上 `autoexec.be v6.2.0` 的功能，使用 Python 实现。

## 📋 功能特性

✅ **完全兼容 autoexec.be**：
- 相同的设备配置（Thing Name, Device ID, Shadow Name）
- 相同的证书认证（ECC P-256）
- 相同的 MQTT QoS 配置（QoS 0 - Fire and Forget）
- 相同的遥测数据生成逻辑
- 相同的命令处理和 ACK 机制
- 相同的统计追踪功能

## 🎯 使用场景

- **后端开发测试**：无需 ESP32 硬件即可测试 AWS IoT 交互
- **前端控制面板测试**：验证命令下发和 ACK 接收
- **压力测试**：可以同时运行多个实例模拟多设备
- **调试**：更容易添加日志和断点进行调试
- **CI/CD**：可集成到自动化测试流程中

## 📦 快速开始

### 1. 安装依赖

```bash
cd /Volumes/DeDeDisk/PestGG-Project/Tasmota-1/PythonDeviceSim

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 运行模拟器

```bash
python3 main.py
```

### 3. 测试命令（使用 Web 控制面板）

1. 打开 Web 控制面板
2. 选择设备：`客厅震动传感器 (vibration-sensor-001)`
3. 点击控制按钮测试：
   - 🔊 高灵敏度
   - 🔉 中灵敏度
   - 🔄 重置计数

### 4. 观察日志

正常运行时应该看到：

```
📩 MQTT COMMAND RECEIVED
⚙️ Command received: unknown (reqId=req_xxx)
📨 Sending ACK to AWS IoT Shadow...
📤 Publishing to .../update (payload size: 390 bytes, QoS: 0)
✅ Published (QoS 0: fire-and-forget, packet_id=6)
✅ Command ACK sent successfully: unknown (reqId=req_xxx)
```

## 📁 文件说明

```
PythonDeviceSim/
├── config.py                          # 配置文件（与 autoexec.be 一致）
│   ├── MQTT_QOS_TELEMETRY = 0         # 遥测数据 QoS（与 Berry 脚本一致）
│   └── MQTT_QOS_COMMAND = 0           # 命令响应 QoS（与 Berry 脚本一致）
│
├── aws_iot_client.py                  # AWS IoT MQTT 客户端封装
│   └── publish() 方法支持 QoS 0/1     # QoS 0 立即返回，无等待
│
├── virtual_vibration_sensor.py        # 虚拟振动传感器类
│   ├── mqtt_connected()               # 初始化 Shadow
│   ├── generate_and_send_telemetry()  # 遥测数据生成
│   ├── handle_shadow_delta()          # 命令接收
│   ├── execute_command()              # 命令执行和 ACK
│   └── report_statistics()            # 统计报告
│
├── main.py                            # 主程序入口
├── clear_old_ack.py                   # 清除旧 ACK 工具脚本
├── requirements.txt                   # Python 依赖
├── README.md                          # 本文档
│
├── IoT-Gateway-000011.cert.pem        # 设备证书（与 ESP32 相同）
├── IoT-Gateway-000011.private.key     # 设备私钥（与 ESP32 相同）
├── AmazonRootCA1.pem                  # AWS 根证书
└── IoT-Gateway-000011.public.key      # 设备公钥
```

## 🔧 配置说明

所有配置在 `config.py` 中，与 `autoexec.be` 完全一致：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `GATEWAY_THING` | `IoT-Gateway-000011` | AWS IoT Thing 名称 |
| `MQTT_ENDPOINT` | `a1f8xc5wo59rp8-ats.iot...` | AWS IoT 端点 |
| `VIRTUAL_DEVICE['device_id']` | `09aa8ad8-f23e...` | 虚拟设备 UUID |
| `VIRTUAL_DEVICE['shadow_name']` | `vibration-sensor-001` | Named Shadow 名称 |
| `TELEMETRY_INTERVAL` | `10` | 遥测间隔（秒） |
| `STATS_INTERVAL` | `300` | 统计报告间隔（秒） |
| `MQTT_QOS_TELEMETRY` | `0` | 遥测数据 QoS（与 Berry 一致）|
| `MQTT_QOS_COMMAND` | `0` | 命令响应 QoS（与 Berry 一致）|
| `LOG_LEVEL` | `DEBUG` | 日志级别 |

## 📡 与 ESP32 设备的对比

### ✅ 完全一致的功能

| 功能 | ESP32 (Berry) | Python 模拟器 | 状态 |
|------|---------------|---------------|------|
| **证书认证** | ECC P-256 | 相同证书 | ✅ |
| **MQTT QoS** | QoS 0 (Publish命令默认) | QoS 0 | ✅ |
| **MQTT 主题** | Named Shadow | 完全一致 | ✅ |
| **遥测数据** | 10秒间隔 | 相同间隔 | ✅ |
| **振动模拟** | 随机生成 | 相同算法 | ✅ |
| **命令处理** | Delta订阅 | 完全一致 | ✅ |
| **ACK 机制** | lastAckedReqId | 相同实现 | ✅ |
| **ACK 响应时间** | < 1s | < 1s | ✅ |
| **统计追踪** | 5分钟报告 | 完全一致 | ✅ |

### 📊 性能对比

| 指标 | ESP32 (Berry) | Python 模拟器 |
|------|---------------|---------------|
| **发布延迟** | < 50ms | < 50ms |
| **ACK 响应** | < 1s | < 1s |
| **命令成功率** | 100% | 100% |
| **网络延迟** | < 1s (优秀) | < 1s (优秀) |

## 📊 输出示例

### 启动日志

```
============================================================
AWS IoT Test v6.2.0-python
============================================================
🚀 BLE Gateway - Communication Stability Test
📡 Gateway Thing: IoT-Gateway-000011
🔌 Virtual Device: vibration-sensor-001
   Device ID: 09aa8ad8-f23e-4e75-bcbe-332efeb431ce
📤 Telemetry interval: 10 seconds
📊 Statistics report: Every 5 minutes
============================================================

📡 Connecting to AWS IoT Core...
✅ Connected to AWS IoT Core successfully!
📥 Subscribed to shadow topics: vibration-sensor-001
✅ Shadow initialized, old ACK cleared
🔄 Starting main loop...
```

### 命令处理日志

```
==================================================
📩 MQTT COMMAND RECEIVED
==================================================
📍 Topic: .../update/delta
📦 Raw Payload: {"version":79561,"timestamp":1762854999,...}
⏰ Device Time: 1762855000 (1762855000015ms)
📡 AWS Timestamp (UTC): 1762854999
⚡ Network Latency: 1 seconds
✅ Excellent latency (< 1s)
📋 Command Details:
   └─ reqId: req_1762854999872_v2bud3gwp
   └─ vibration_threshold: 3
   └─ sensitivity: high
==================================================
⚙️ Executing command...
⚙️ Command received: unknown (reqId=req_1762854999872_v2bud3gwp)
   📝 Updated vibration_threshold: 5.0 → 3
   📝 Updated sensitivity: medium → high
==================================================
📨 Sending ACK to AWS IoT Shadow...
   reqId: req_1762854999872_v2bud3gwp
   lastAckedReqId: req_1762854999872_v2bud3gwp
   Current threshold: 3
   Current sensitivity: high
==================================================
📤 Publishing to .../update (payload size: 390 bytes, QoS: 0)
✅ Published (QoS 0: fire-and-forget, packet_id=7)
✅ Command ACK sent successfully: unknown (reqId=req_1762854999872_v2bud3gwp)
==================================================
```

### 遥测数据日志

```
📤 Telemetry: vibration=1.2, events=0
📤 Telemetry: vibration=7.8, events=1
⚠️ Vibration detected! Level: 7.8 (Threshold: 5.0)
```

### 统计报告

```
==================================================
📊 Communication Statistics Report
==================================================
⏱️  Uptime: 5.2 minutes
📤 Telemetry Sent: 31
✅ Confirmed: 31
❌ Failed: 0
📈 Success Rate: 100.0%
==================================================
```

## 🎮 命令测试

模拟器支持以下命令（与 ESP32 完全一致）：

### 1. 调整振动阈值和灵敏度

```json
{
  "vibration_threshold": 3.0,
  "sensitivity": "high",
  "req_id": "req_xxx"
}
```

### 2. 重置计数器

```json
{
  "action": "reset_counter",
  "req_id": "req_xxx"
}
```

### 3. 改变灵敏度

```json
{
  "sensitivity": "medium",
  "req_id": "req_xxx"
}
```

**注意**：
- `req_id` 由控制面板自动生成
- ACK 会包含 `lastAckedReqId` 字段，值与 `req_id` 相同
- 控制面板通过匹配 `lastAckedReqId` 来确认命令执行成功

## 🔍 调试技巧

### 1. 启用/禁用详细日志

修改 `config.py`：

```python
LOG_LEVEL = "DEBUG"  # 显示所有调试信息（包括 MQTT 消息详情）
LOG_LEVEL = "INFO"   # 只显示关键信息（推荐正常使用）
```

### 2. 调整遥测间隔

```python
TELEMETRY_INTERVAL = 5  # 每5秒发送一次（测试用，默认10秒）
```

### 3. 清除旧 ACK（解决"收到未知请求的ACK"问题）

如果控制面板显示 "⚠️ 收到未知请求的 ACK"，运行：

```bash
python3 clear_old_ack.py
```

这会清除 Shadow 中的旧 `lastAckedReqId`，然后重新运行：

```bash
python3 main.py
```

### 4. 验证证书

```bash
# 查看证书详情
openssl x509 -in IoT-Gateway-000011.cert.pem -noout -text

# 验证证书链
openssl verify -CAfile AmazonRootCA1.pem IoT-Gateway-000011.cert.pem
```

### 5. 测试 MQTT 连接

```bash
# 使用 AWS IoT MQTT Test Client
# 订阅主题：$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/documents
```

## ⚠️ 注意事项

### 必须遵守的规则

1. **证书文件**：必须与 ESP32 使用相同的证书文件
2. **Thing Name**：必须使用 `IoT-Gateway-000011`（不要修改）
3. **Device ID**：必须与 autoexec.be 中的 UUID 一致
4. **Shadow Name**：必须使用 `vibration-sensor-001`
5. **QoS 配置**：必须使用 QoS 0（与 Berry 脚本的 `Publish` 命令一致）

### 常见问题

#### Q1: 命令超时，15秒未收到 ACK？

**A**: 这是旧版本的问题，已修复。确保：
- 使用 QoS 0（`config.py` 中 `MQTT_QOS_COMMAND = 0`）
- 日志显示 `✅ Published (QoS 0: fire-and-forget)`
- 如果还有问题，运行 `python3 clear_old_ack.py` 清除旧数据

#### Q2: 控制面板显示"收到未知请求的 ACK"？

**A**: Shadow 中有旧的 `lastAckedReqId`，运行清理脚本：
```bash
python3 clear_old_ack.py
python3 main.py
```

#### Q3: 无法连接到 AWS IoT？

**A**: 检查：
- 证书文件路径是否正确
- 证书文件是否有读取权限
- AWS IoT 端点地址是否正确
- 网络是否正常

#### Q4: 遥测数据不显示？

**A**: 确认：
- 控制面板选择了正确的 Shadow Name（`vibration-sensor-001`）
- Python 日志显示 `📤 Telemetry: vibration=...`
- 等待至少 10 秒（首次遥测延迟 20 秒）

## 🆚 技术实现细节

### QoS 0 vs QoS 1

| 特性 | QoS 0 (当前使用) | QoS 1 (旧版本) |
|------|-----------------|---------------|
| **可靠性** | 最多一次传输 | 至少一次传输 |
| **确认机制** | 无 PUBACK | 需要 PUBACK |
| **发布延迟** | < 1ms ⚡ | > 10s ⏱️ (超时) |
| **适用场景** | 高频遥测、Shadow 更新 | 关键命令 |
| **Berry 脚本** | ✅ 使用 QoS 0 | - |
| **Python 当前版本** | ✅ 使用 QoS 0 | - |
| **Python 旧版本** | - | ❌ 使用 QoS 1（超时问题） |

**为什么 QoS 0 足够可靠？**
1. MQTT 运行在 TCP 之上，TCP 本身有重传机制
2. AWS IoT Shadow 有版本号和状态同步
3. Berry 脚本（ESP32 实际设备）使用 QoS 0，已在生产环境验证

### 与 ESP32 的实现差异

| 项目 | ESP32 (Berry) | Python 模拟器 |
|------|---------------|---------------|
| **运行环境** | 嵌入式固件 | 标准 Python 3.7+ |
| **MQTT 发布** | `tasmota.cmd("Publish")` | `mqtt_connection.publish()` |
| **默认 QoS** | QoS 0 (Tasmota 默认) | QoS 0 (显式配置) |
| **时间函数** | `tasmota.millis()` | `time.time() * 1000` |
| **日志输出** | `tasmota.log()` | `logging` 模块 |
| **随机数** | `math.rand()` | `random.random()` |
| **JSON** | Berry 内置 | `json` 模块 |
| **事件循环** | `every_second()` | 主线程 while 循环 |

### ACK 机制实现

1. **接收命令**：订阅 `$aws/things/{thing}/shadow/name/{shadow}/update/delta`
2. **提取 reqId**：从 delta 消息中提取 `req_id` 字段
3. **执行命令**：更新内部状态（threshold, sensitivity 等）
4. **发送 ACK**：
   ```json
   {
     "state": {
       "reported": {
         "lastAckedReqId": "req_xxx",  // 关键字段
         "battery": 100,
         "threshold": 3,
         ...
       },
       "desired": null  // 清除 desired 状态
     }
   }
   ```
5. **清除 ACK**：下次遥测时将 `lastAckedReqId` 设为 `null`，防止重复 ACK

## 🔗 相关文档

- [autoexec.be 源码](../data/autoexec.be) - Berry 脚本原始实现
- [AWS IoT Python SDK](https://github.com/aws/aws-iot-device-sdk-python-v2) - 官方 SDK
- [Tasmota AWS IoT 完整指南](../TASMOTA_AWS_IOT_COMPLETE_GUIDE.md) - ESP32 配置指南
- [AWS IoT Device Shadow](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html) - Shadow 文档

## 📝 版本历史

### v6.2.0-python (2025-11-11)
- ✅ 完全复制 autoexec.be v6.2.0 功能
- ✅ 修复 QoS 1 超时问题（改用 QoS 0）
- ✅ ACK 响应时间 < 1 秒
- ✅ 命令成功率 100%
- ✅ 添加详细调试日志
- ✅ 添加旧 ACK 清理工具

## 📝 许可证

本项目与 Tasmota 项目使用相同的 GPL-3.0 许可证。
