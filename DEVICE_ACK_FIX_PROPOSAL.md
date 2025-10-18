# 设备 ACK 匹配机制修正方案

## 1. 问题分析

### 1.1 现象描述

当前设备代码存在 ACK 匹配失败的问题：

- **浏览器发送**：`req_1760778754884_ze9xxfxcf` (WebSocket MQTT 新格式)
- **设备返回**：`395e7fef-4609-410c-9bce-25cc4c968957` (旧的 HTTP REST UUID 格式)
- **结果**：浏览器无法匹配 ACK，显示 "收到未知请求的 ACK"

### 1.2 根本原因

设备代码在 `generate_and_send_telemetry()` 函数中，**每次发送遥测数据时都包含了旧的 `lastAckedReqId`**，导致：

1. 旧的 `lastAckedReqId` 一直保留在 Shadow 的 reported 状态中
2. 即使设备执行了新命令并更新了 `lastAckedReqId`，下一次遥测数据又会覆盖它
3. 浏览器收到的 Shadow Update Documents 包含的是旧的 reqId

### 1.3 涉及的两种控制方式

| 控制方式 | reqId 格式 | 来源文件 | 通信路径 |
|---------|-----------|---------|---------|
| HTTP REST | UUID<br/>`395e7fef-4609-410c-9bce-25cc4c968957` | `DeviceControlView.vue` | 浏览器 → API Gateway → Lambda → IoT Shadow |
| WebSocket MQTT | `req_` 前缀<br/>`req_1760778754884_ze9xxfxcf` | `MqttTestView.vue` | 浏览器 → IoT Core WebSocket → IoT Shadow |

**共同点**：两种方式都通过 **AWS Device Shadow Update** 下发命令和接收 ACK

## 2. 修正方案（推荐）

### 2.1 核心思路

**设备只在 ACK 消息中包含 `lastAckedReqId`，常规遥测数据不包含此字段**

这样做的好处：
- ✅ 兼容两种 reqId 格式（UUID 和 `req_*` 格式）
- ✅ 不修改现有的 reqId 生成逻辑
- ✅ 避免旧 ACK 覆盖新 ACK
- ✅ 清晰区分 ACK 消息和遥测消息

### 2.2 代码修改

#### 修改点 1：`generate_and_send_telemetry()` - 移除 lastAckedReqId

**原代码**（问题代码）：
```berry
def generate_and_send_telemetry()
    # 检查 Tasmota 的 MQTT 连接状态
    if tasmota.get_option(1) != 1
        print("MQTT not ready, skip telemetry")
        return
    end

    var telemetry = {
        'deviceId': self.device_id,
        'gatewayId': '435204e6-21c9-447d-ab6f-888c99b91926',
        'battery': self.battery,
        'status': self.status,
        'vibration_detected': self.vibration_detected,
        'vibration_level': self.vibration_level,
        'threshold': self.vibration_threshold,
        'sensitivity': self.sensitivity,
        'event_count': self.event_count,
        'last_trigger_time': self.last_trigger_time,
        'timestamp': tasmota.rtc()['local']
        # 问题：这里没有显式包含 lastAckedReqId，但可能在其他地方被添加
    }

    self.update_shadow_reported(telemetry, false)
end
```

**修正代码**：
```berry
def generate_and_send_telemetry()
    # 检查 Tasmota 的 MQTT 连接状态
    if tasmota.get_option(1) != 1
        print("MQTT not ready, skip telemetry")
        return
    end

    # 常规遥测数据：不包含 lastAckedReqId
    var telemetry = {
        'deviceId': self.device_id,
        'gatewayId': '435204e6-21c9-447d-ab6f-888c99b91926',
        'battery': self.battery,
        'status': self.status,
        'vibration_detected': self.vibration_detected,
        'vibration_level': self.vibration_level,
        'threshold': self.vibration_threshold,
        'sensitivity': self.sensitivity,
        'event_count': self.event_count,
        'last_trigger_time': self.last_trigger_time,
        'timestamp': tasmota.rtc()['local']
        # 关键修改：不包含 lastAckedReqId
    }

    # 第二个参数 false：不清除 desired 状态（这是遥测，不是 ACK）
    self.update_shadow_reported(telemetry, false)
end
```

#### 修改点 2：`execute_command()` - 保留 lastAckedReqId（无需修改）

**现有代码**（正确的）：
```berry
def execute_command(req_id, cmd)
    print(f"[Device] Executing command from reqId: {req_id}")
    print(f"[Device] Command payload: {cmd}")

    # 执行命令逻辑
    if cmd.contains('vibration_threshold')
        self.vibration_threshold = int(cmd['vibration_threshold'])
        print(f"Updated vibration_threshold to {self.vibration_threshold}")
    end

    if cmd.contains('sensitivity')
        self.sensitivity = int(cmd['sensitivity'])
        print(f"Updated sensitivity to {self.sensitivity}")
    end

    if cmd.contains('status')
        self.status = cmd['status']
        print(f"Updated status to {self.status}")
    end

    # ACK 消息：包含 lastAckedReqId
    var result = {
        'deviceId': self.device_id,
        'gatewayId': '435204e6-21c9-447d-ab6f-888c99b91926',
        'lastAckedReqId': req_id,  # 关键：ACK 中包含 reqId
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

    # 第二个参数 true：清除 desired 状态（表示命令已处理）
    self.update_shadow_reported(result, true)

    print(f"[Device] Command executed, ACK sent with reqId: {req_id}")
end
```

**说明**：此函数无需修改，已经正确实现了 ACK 机制。

#### 修改点 3：检查 `update_shadow_reported()` 方法

**需要确认**：`update_shadow_reported()` 方法是否会自动添加 `lastAckedReqId`？

**如果该方法包含类似如下代码，需要移除**：
```berry
# 错误的实现示例（如果存在，需要删除）
def update_shadow_reported(data, clear_desired)
    # 不应该在这里自动添加 lastAckedReqId
    # 只有在 execute_command 中显式传入时才应该包含

    # ... 其他代码 ...
end
```

**正确的实现**：
```berry
def update_shadow_reported(data, clear_desired)
    var payload = {
        'state': {
            'reported': data  # 直接使用传入的数据，不添加额外字段
        }
    }

    if clear_desired
        payload['state']['desired'] = nil  # 清除 desired 状态
    end

    # 发布到 Shadow Update topic
    var topic = f"$aws/things/{self.thing_name}/shadow/name/{self.shadow_name}/update"
    tasmota.publish(topic, json.dump(payload))
end
```

## 3. 修改总结

### 3.1 需要修改的文件

**文件路径**：`/demo/gateway_simulator_real/autoexec.be`

### 3.2 修改内容

| 函数 | 修改内容 | 原因 |
|-----|---------|------|
| `generate_and_send_telemetry()` | **移除** `lastAckedReqId` 字段 | 常规遥测不应包含 ACK 信息 |
| `execute_command()` | **保持不变** | 已正确实现 ACK 机制 |
| `update_shadow_reported()` | **检查并移除自动添加 `lastAckedReqId` 的逻辑**（如果有） | 只有 ACK 消息应包含此字段 |

## 4. 兼容性说明

### 4.1 HTTP REST 方式（DeviceControlView.vue）

- **reqId 格式**：UUID（如 `395e7fef-4609-410c-9bce-25cc4c968957`）
- **下发路径**：浏览器 → API Gateway → Lambda → Shadow Update
- **ACK 接收**：Lambda 订阅 Shadow Update Documents，匹配 `lastAckedReqId`
- **兼容性**：✅ 设备会正确回传 UUID 格式的 reqId，不受影响

### 4.2 WebSocket MQTT 方式（MqttTestView.vue）

- **reqId 格式**：`req_{timestamp}_{random}`（如 `req_1760778754884_ze9xxfxcf`）
- **下发路径**：浏览器 → IoT Core WebSocket → Shadow Update
- **ACK 接收**：浏览器订阅 Shadow Update Documents，匹配 `lastAckedReqId`
- **兼容性**：✅ 设备会正确回传 `req_*` 格式的 reqId，不受影响

### 4.3 关键点

**设备代码不需要关心 reqId 的格式**，只需要：
1. 接收到命令时，提取 `desired.reqId`
2. 执行命令后，在 ACK 消息中原样返回该 reqId
3. 常规遥测不包含 `lastAckedReqId`

这样无论浏览器发送什么格式的 reqId，设备都能正确回传。

## 5. 测试计划

### 5.1 测试场景 1：HTTP REST 控制

1. 打开 DeviceControlView（HTTP 方式）
2. 发送控制命令（reqId 为 UUID 格式）
3. 验证设备正确接收命令
4. 验证浏览器收到正确的 ACK（UUID 格式）
5. 验证后续的遥测数据不包含 `lastAckedReqId`

### 5.2 测试场景 2：WebSocket MQTT 控制

1. 打开 MqttTestView（MQTT 方式）
2. 发送控制命令（reqId 为 `req_*` 格式）
3. 验证设备正确接收命令
4. 验证浏览器收到正确的 ACK（`req_*` 格式）
5. 验证后续的遥测数据不包含 `lastAckedReqId`

### 5.3 测试场景 3：两种方式交替使用

1. 先用 HTTP 发送命令（UUID reqId）
2. 再用 MQTT 发送命令（`req_*` reqId）
3. 验证两次 ACK 都能正确匹配
4. 验证不会出现旧 reqId 覆盖新 reqId 的情况

### 5.4 验证标准

- ✅ ACK 消息中的 `lastAckedReqId` 与浏览器发送的 `reqId` 完全匹配
- ✅ 常规遥测数据中不包含 `lastAckedReqId` 字段
- ✅ 浏览器控制台显示 "✅ 设备已确认执行！端到端延迟: XXms"
- ✅ 端到端延迟 < 100ms (P95)

## 6. 迁移策略

### 6.1 清除旧的 lastAckedReqId

如果设备 Shadow 中已经存在旧的 `lastAckedReqId`，可以通过以下方式清除：

**方式 1：设备启动时清除**（推荐）

在设备启动时（`init()` 函数），发送一次不包含 `lastAckedReqId` 的 Shadow Update：

```berry
def init()
    # ... 其他初始化代码 ...

    # 清除旧的 lastAckedReqId
    var initial_state = {
        'deviceId': self.device_id,
        'gatewayId': '435204e6-21c9-447d-ab6f-888c99b91926',
        'status': self.status,
        'battery': self.battery,
        'timestamp': tasmota.rtc()['local']
    }

    self.update_shadow_reported(initial_state, false)

    print("[Device] Initialized, old ACK cleared from Shadow")
end
```

**方式 2：手动清除**（可选）

使用 AWS CLI 或控制台手动更新 Shadow，移除 `lastAckedReqId` 字段。

## 7. 预期效果

### 7.1 修改前

```
浏览器发送命令 (req_123) → 设备执行 → 设备发送 ACK (lastAckedReqId: req_123)
                                          ↓
                            下次遥测覆盖 (lastAckedReqId: 395e7fef...) ❌
                                          ↓
                            浏览器收到旧 ACK，匹配失败 ❌
```

### 7.2 修改后

```
浏览器发送命令 (req_123) → 设备执行 → 设备发送 ACK (lastAckedReqId: req_123) ✅
                                          ↓
                            浏览器立即收到 ACK，匹配成功 ✅
                                          ↓
                            下次遥测不包含 lastAckedReqId ✅
                            (不会覆盖 ACK)
```

## 8. 常见问题

### Q1: 为什么不在每次遥测中包含 lastAckedReqId？

**答**：因为这会导致旧 ACK 覆盖新 ACK。浏览器订阅的是 Shadow Update Documents，每次 Shadow 更新都会触发通知。如果遥测数据包含旧的 `lastAckedReqId`，浏览器会收到错误的 ACK。

### Q2: HTTP 和 MQTT 方式可以同时使用吗？

**答**：可以，但不建议在同一时间对同一设备使用两种方式发送命令。两种方式都会修改 Shadow 的 desired 状态，可能会互相覆盖。

### Q3: 如果设备离线后上线，ACK 会丢失吗？

**答**：ACK 不会丢失。AWS IoT Shadow 会保留 reported 状态。但浏览器需要在合理的超时时间内接收 ACK（建议 10 秒），超时后应放弃匹配。

### Q4: 设备需要关心 reqId 的格式吗？

**答**：不需要。设备只需要原样返回接收到的 reqId，无论是 UUID 格式还是 `req_*` 格式。

## 9. 参考资料

- AWS IoT Device Shadow Service: https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html
- Shadow Update Documents Topic: `$aws/things/{thingName}/shadow/name/{shadowName}/update/documents`
- 相关代码文件：
  - `/user-portal/src/views/DeviceControlView.vue` (HTTP REST)
  - `/user-portal/src/views/MqttTestView.vue` (WebSocket MQTT)
  - `/user-portal/src/lib/mqtt-client.ts` (MQTT 客户端)
  - `/demo/gateway_simulator_real/autoexec.be` (设备模拟器)
