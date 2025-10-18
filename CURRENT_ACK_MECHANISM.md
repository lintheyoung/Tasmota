# 当前 ACK 机制详细说明

## 概述

当前实现使用 **AWS IoT Device Shadow** 作为命令确认（ACK）机制。设备通过更新 Shadow 的 `reported` 状态来确认命令执行。

---

## 完整的命令-响应流程

### 📤 步骤 1: 后端发送命令

**后端操作：更新 Shadow 的 `desired` 状态**

```bash
# AWS CLI 示例
aws iot-data update-thing-shadow \
  --thing-name "IoT-Gateway-000011" \
  --shadow-name "vibration-sensor-001" \
  --payload '{
    "state": {
      "desired": {
        "cmd": {
          "action": "set_threshold",
          "vibration_threshold": 3.0,
          "sensitivity": "high"
        },
        "reqId": "d0ae890b-cf36-4ba0-abd3-ee3ba4e96974"
      }
    }
  }' \
  /dev/stdout
```

**MQTT 主题：**
```
$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update
```

**发送的消息格式：**
```json
{
  "state": {
    "desired": {
      "cmd": {
        "action": "set_threshold",
        "vibration_threshold": 3.0,
        "sensitivity": "high"
      },
      "reqId": "d0ae890b-cf36-4ba0-abd3-ee3ba4e96974"
    }
  }
}
```

---

### 📥 步骤 2: 设备接收 Delta 事件

**AWS IoT 自动发送 Delta（差异）到设备**

**MQTT 主题：**
```
$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/delta
```

**Delta 消息格式：**
```json
{
  "version": 123,
  "timestamp": 1734422880,
  "state": {
    "cmd": {
      "action": "set_threshold",
      "vibration_threshold": 3.0,
      "sensitivity": "high"
    },
    "reqId": "d0ae890b-cf36-4ba0-abd3-ee3ba4e96974"
  },
  "metadata": {
    "cmd": {
      "timestamp": 1734422880
    },
    "reqId": {
      "timestamp": 1734422880
    }
  }
}
```

**设备端处理代码（Berry）：**
```berry
# autoexec.be 第 283-311 行
def mqtt_data(topic, idx, payload_s, payload_b)
    import json

    # 检查是否是 Delta 主题
    if topic == self.delta_topic
        tasmota.log("📩 Delta received for " + self.shadow_name, 2)

        var delta = json.load(payload_s)
        var state = delta.find('state')

        # 提取命令和请求ID
        var cmd = state.find('cmd')
        var req_id = state.find('reqId')

        if cmd == nil || req_id == nil
            tasmota.log("⚠️ Missing cmd or reqId in delta", 2)
            return true
        end

        tasmota.log("🎯 Command: " + str(cmd) + " (reqId=" + req_id + ")", 2)

        # 执行命令
        self.execute_command(req_id, cmd)
        return true
    end

    return false
end
```

---

### ⚙️ 步骤 3: 设备执行命令并发送 ACK

**执行命令的代码（Berry）：**
```berry
# autoexec.be 第 317-361 行
def execute_command(req_id, cmd)
    import json

    var action = cmd.find('action')
    if action == nil
        action = 'unknown'
    end

    tasmota.log("⚙️ Command received: " + action + " (reqId=" + req_id + ")", 2)

    # 1️⃣ 执行命令逻辑
    var new_threshold = cmd.find('vibration_threshold')
    if new_threshold != nil
        self.vibration_threshold = new_threshold  # 更新内部状态
    end

    var new_sensitivity = cmd.find('sensitivity')
    if new_sensitivity != nil
        self.sensitivity = new_sensitivity
    end

    if action == 'reset_counter'
        self.event_count = 0
        self.last_trigger_time = nil
    end

    # 2️⃣ 构建 ACK 响应（包含完整设备状态）
    var result = {
        'deviceId': self.device_id,
        'gatewayId': '435204e6-21c9-447d-ab6f-888c99b91926',
        'lastAckedReqId': req_id,  # 🔥 关键字段：确认的请求ID
        'battery': self.battery,
        'status': self.status,
        'vibration_detected': self.vibration_detected,
        'vibration_level': self.vibration_level,
        'threshold': self.vibration_threshold,
        'sensitivity': self.sensitivity,
        'event_count': self.event_count,
        'last_trigger_time': self.last_trigger_time,
        'timestamp': tasmota.rtc()['local']
    }

    # 3️⃣ 发送 ACK（更新 Shadow reported 状态，并清除 desired）
    self.update_shadow_reported(result, true)  # true = 清除 desired 状态
    tasmota.log("✅ Command ACK sent: " + action, 2)
end
```

**发送 ACK 的实现（Berry）：**
```berry
# autoexec.be 第 218-241 行
def update_shadow_reported(reported, clear_desired)
    import json

    var payload = nil

    if clear_desired
        # 清除 desired 状态，防止 Delta 循环
        payload = json.dump({
            'state': {
                'reported': reported,
                'desired': nil  # 🔥 关键：清除 desired，停止 Delta 事件
            }
        })
    else
        payload = json.dump({
            'state': {
                'reported': reported
            }
        })
    end

    # 发布到 Shadow update 主题
    tasmota.cmd("Publish " + self.update_topic + " " + payload)
    tasmota.log("📤 Shadow update sent", 2)
end
```

---

### 📤 步骤 4: 设备发送 ACK 到 AWS IoT

**MQTT 主题：**
```
$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update
```

**ACK 消息格式（Shadow Update）：**
```json
{
  "state": {
    "reported": {
      "deviceId": "09aa8ad8-f23e-4e75-bcbe-332efeb431ce",
      "gatewayId": "435204e6-21c9-447d-ab6f-888c99b91926",
      "lastAckedReqId": "d0ae890b-cf36-4ba0-abd3-ee3ba4e96974",
      "battery": 100,
      "status": "ok",
      "vibration_detected": false,
      "vibration_level": 1.2,
      "threshold": 3.0,
      "sensitivity": "high",
      "event_count": 5,
      "last_trigger_time": 1734422890,
      "timestamp": 1734422895
    },
    "desired": null
  }
}
```

**关键字段说明：**

| 字段 | 类型 | 说明 | 必需 |
|------|------|------|------|
| `lastAckedReqId` | String | 已确认的请求ID，与命令中的 `reqId` 匹配 | ✅ 是 |
| `deviceId` | String | 设备唯一标识 | ✅ 是 |
| `timestamp` | Number | 设备本地时间戳（Unix timestamp） | ✅ 是 |
| `desired` | null | 清除 desired 状态，防止重复触发 Delta | ✅ 是 |
| 其他字段 | Various | 设备当前完整状态（执行命令后的状态） | ✅ 是 |

---

### ✅ 步骤 5: AWS IoT 确认 Shadow 更新成功

**MQTT 主题：**
```
$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/accepted
```

**消息格式：**
```json
{
  "state": {
    "reported": {
      "deviceId": "09aa8ad8-f23e-4e75-bcbe-332efeb431ce",
      "lastAckedReqId": "d0ae890b-cf36-4ba0-abd3-ee3ba4e96974",
      "battery": 100,
      "status": "ok",
      "vibration_detected": false,
      "vibration_level": 1.2,
      "threshold": 3.0,
      "sensitivity": "high",
      "event_count": 5,
      "last_trigger_time": 1734422890,
      "timestamp": 1734422895
    }
  },
  "metadata": {
    "reported": {
      "deviceId": {
        "timestamp": 1734422895
      },
      "lastAckedReqId": {
        "timestamp": 1734422895
      },
      "timestamp": {
        "timestamp": 1734422895
      }
    }
  },
  "version": 124,
  "timestamp": 1734422895
}
```

**设备端处理代码（Berry）：**
```berry
# autoexec.be 第 275-280 行
# Handle Shadow Update Accepted (confirmation)
if topic == self.update_accepted_topic
    tasmota.log("✅ Shadow update confirmed", 3)  # Debug level
    self.telemetry_confirmed += 1  # 统计成功次数
    return true
end
```

---

## 🔍 后端如何检测 ACK

### 方法 1: 监听 Shadow `update/accepted` 主题（推荐）

**AWS IoT Rule 示例：**
```sql
SELECT
    state.reported.lastAckedReqId as ackReqId,
    state.reported.deviceId as deviceId,
    state.reported.timestamp as ackTimestamp,
    state.reported.battery as battery,
    state.reported.status as status,
    state.reported.vibration_detected as vibration_detected,
    state.reported.vibration_level as vibration_level,
    state.reported.threshold as threshold,
    state.reported.sensitivity as sensitivity,
    state.reported.event_count as event_count,
    timestamp() as receivedAt
FROM '$aws/things/+/shadow/name/+/update/accepted'
WHERE state.reported.lastAckedReqId IS NOT NULL
```

**处理逻辑（伪代码）：**
```javascript
// Lambda 函数处理
function handleAck(event) {
    const ackReqId = event.ackReqId;
    const deviceId = event.deviceId;
    const ackTimestamp = event.ackTimestamp;

    // 1. 查找原始命令
    const originalCommand = await db.getCommand(ackReqId);

    if (!originalCommand) {
        console.log(`Unknown reqId: ${ackReqId}`);
        return;
    }

    // 2. 计算延迟
    const commandSentAt = originalCommand.sentAt;
    const latency = ackTimestamp - commandSentAt;

    // 3. 更新命令状态
    await db.updateCommand(ackReqId, {
        status: 'completed',
        ackReceivedAt: Date.now(),
        latency: latency,
        deviceState: event
    });

    // 4. 通知 APP
    await notifyApp({
        type: 'command_ack',
        reqId: ackReqId,
        deviceId: deviceId,
        status: 'success',
        latency: latency
    });

    console.log(`ACK received for reqId=${ackReqId}, latency=${latency}ms`);
}
```

---

### 方法 2: 查询 Shadow 文档（轮询）

**AWS CLI 示例：**
```bash
aws iot-data get-thing-shadow \
  --thing-name "IoT-Gateway-000011" \
  --shadow-name "vibration-sensor-001" \
  /dev/stdout | jq '.state.reported.lastAckedReqId'
```

**返回值：**
```json
{
  "state": {
    "reported": {
      "lastAckedReqId": "d0ae890b-cf36-4ba0-abd3-ee3ba4e96974",
      "deviceId": "09aa8ad8-f23e-4e75-bcbe-332efeb431ce",
      "timestamp": 1734422895
    },
    "desired": {}
  },
  "metadata": {...},
  "version": 124,
  "timestamp": 1734422895
}
```

**检查逻辑（伪代码）：**
```javascript
async function checkAck(reqId) {
    const shadow = await iotData.getThingShadow({
        thingName: 'IoT-Gateway-000011',
        shadowName: 'vibration-sensor-001'
    }).promise();

    const shadowState = JSON.parse(shadow.payload);
    const lastAckedReqId = shadowState.state.reported.lastAckedReqId;

    if (lastAckedReqId === reqId) {
        console.log(`✅ Command ${reqId} has been ACKed`);
        return true;
    } else {
        console.log(`⏳ Command ${reqId} not yet ACKed (last: ${lastAckedReqId})`);
        return false;
    }
}
```

---

## 📊 完整的消息流示意图

```
┌─────────────┐                                 ┌─────────────┐
│   后端/APP   │                                 │  IoT设备    │
│  (Python)   │                                 │  (Berry)    │
└─────────────┘                                 └─────────────┘
      │                                                 │
      │ 1️⃣ Update Shadow (desired)                     │
      │────────────────────────────────────────────────>│
      │   Topic: .../shadow/update                     │
      │   {                                             │
      │     "state": {                                  │
      │       "desired": {                              │
      │         "cmd": {...},                           │
      │         "reqId": "xxx"                          │
      │       }                                         │
      │     }                                           │
      │   }                                             │
      │                                                 │
      │                2️⃣ AWS IoT 自动发送 Delta        │
      │                ─────────────────────────────────>│
      │                   Topic: .../shadow/update/delta│
      │                   { "state": { "cmd": {...} } } │
      │                                                 │
      │                                   3️⃣ 执行命令    │
      │                                   - 更新阈值     │
      │                                   - 更新灵敏度   │
      │                                                 │
      │ 4️⃣ Update Shadow (reported + clear desired)    │
      │<────────────────────────────────────────────────│
      │   Topic: .../shadow/update                     │
      │   {                                             │
      │     "state": {                                  │
      │       "reported": {                             │
      │         "lastAckedReqId": "xxx",  ← 🔥 ACK     │
      │         "threshold": 3.0,                       │
      │         "sensitivity": "high",                  │
      │         ...                                     │
      │       },                                        │
      │       "desired": null  ← 清除 desired           │
      │     }                                           │
      │   }                                             │
      │                                                 │
      │ 5️⃣ Update Accepted                              │
      │<────────────────────────────────────────────────│
      │   Topic: .../shadow/update/accepted            │
      │   { "state": { "reported": {...} } }           │
      │                                                 │
      │ 6️⃣ IoT Rule 触发 Lambda                         │
      │ - 提取 lastAckedReqId                           │
      │ - 匹配原始命令                                   │
      │ - 更新命令状态为 'completed'                     │
      │ - 通知 APP                                      │
      │                                                 │
```

---

## 🎯 关键特性

### ✅ 优点

1. **状态同步**：Shadow 自动保持 desired 和 reported 状态同步
2. **持久化**：即使设备离线，命令也会保存在 Shadow 中
3. **重连恢复**：设备重连后通过 GET 请求获取待处理命令
4. **幂等性**：通过 `lastAckedReqId` 防止重复执行
5. **完整状态**：ACK 包含执行后的完整设备状态
6. **自动清理**：通过 `desired: null` 清除已处理的命令

### ⚠️ 注意事项

1. **延迟**：ACK 通过 Shadow 返回，延迟约 100-500ms
2. **频率限制**：Shadow 更新频率有限制（建议 < 10次/秒）
3. **依赖 Shadow**：必须使用 Named Shadow 或 Classic Shadow
4. **reqId 唯一性**：必须为每个命令生成唯一的 `reqId`

---

## 🔧 调试和监控

### 查看设备日志

```
00:00:15.123 📩 Delta received for vibration-sensor-001
00:00:15.125 🎯 Command: {"action":"set_threshold","vibration_threshold":3.0} (reqId=d0ae890b-cf36-4ba0-abd3-ee3ba4e96974)
00:00:15.127 ⚙️ Command received: set_threshold (reqId=d0ae890b-cf36-4ba0-abd3-ee3ba4e96974)
00:00:15.135 📤 Shadow update sent
00:00:15.145 ✅ Command ACK sent: set_threshold
00:00:15.250 ✅ Shadow update confirmed
```

### AWS IoT MQTT Test Client

**订阅主题查看 ACK：**
```
$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/accepted
```

**预期消息：**
```json
{
  "state": {
    "reported": {
      "lastAckedReqId": "d0ae890b-cf36-4ba0-abd3-ee3ba4e96974",
      "threshold": 3.0,
      "sensitivity": "high"
    }
  },
  "version": 124,
  "timestamp": 1734422895
}
```

---

## 总结

当前实现使用 **Shadow-based ACK** 机制：

| 特性 | 实现方式 |
|------|---------|
| **ACK 标识** | `lastAckedReqId` 字段 |
| **ACK 渠道** | Shadow `reported` 状态 |
| **ACK 主题** | `$aws/things/.../shadow/update/accepted` |
| **ACK 内容** | 完整设备状态 + `lastAckedReqId` |
| **后端检测** | 监听 `update/accepted` 或查询 Shadow 文档 |
| **状态清理** | 通过 `desired: null` 清除命令 |

这是一个成熟、稳定的 ACK 实现方式，适合你当前的遥测频率（10秒/次）和业务场景。
