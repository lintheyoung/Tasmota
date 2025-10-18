# 优化 MQTT 命令响应延迟

## 问题

当前从 AWS IoT Console 发送命令到设备响应，延迟约 **2-3 秒**，远高于预期的 100-300ms。

---

## 原因分析

### 当前代码问题

**文件：`data/autoexec.be` 第 239 行**

```berry
tasmota.cmd("Publish " + self.update_topic + " " + payload)
```

**问题：**
- 使用 `Publish` 命令发送 MQTT 消息
- 默认 QoS = 0（最多一次交付）
- 没有等待 AWS IoT 确认
- 可能导致消息丢失或延迟

### MQTT QoS 级别对比

| QoS | 说明 | 延迟 | 可靠性 |
|-----|------|------|--------|
| 0 | 最多一次（Fire and Forget） | 最低 | 低 |
| 1 | 至少一次（需要 PUBACK） | 中等 | 高 |
| 2 | 恰好一次（需要 PUBREC/PUBREL/PUBCOMP） | 最高 | 最高 |

**当前使用 QoS 0，建议改为 QoS 1。**

---

## 解决方案

### 方案 1: 使用 MQTT 库直接发送（推荐）

修改 `update_shadow_reported()` 函数，使用 `mqtt.publish()` 替代 `tasmota.cmd("Publish")`。

**优点：**
- 可以指定 QoS
- 更直接，延迟更低
- 可以设置 retain 标志

**修改代码：**

```berry
def update_shadow_reported(reported, clear_desired)
    import json
    import mqtt  # 导入 mqtt 模块

    var payload = nil

    if clear_desired
        # Clear desired state to prevent delta loop
        payload = json.dump({
            'state': {
                'reported': reported,
                'desired': nil  # This clears the desired state
            }
        })
    else
        payload = json.dump({
            'state': {
                'reported': reported
            }
        })
    end

    # 🔥 使用 mqtt.publish() 替代 tasmota.cmd("Publish")
    # 参数：topic, payload, retain=false, start=0, len=0, qos=1
    mqtt.publish(self.update_topic, payload, false, 0, 0, 1)

    tasmota.log("📤 Shadow update sent (QoS 1)", 2)
end
```

**参数说明：**
- `topic`: MQTT 主题
- `payload`: 消息内容
- `retain`: 是否保留消息（Shadow 不需要，设为 false）
- `start`: payload 起始位置（通常为 0）
- `len`: payload 长度（0 = 全部）
- `qos`: QoS 级别（**1 = 至少一次**）

---

### 方案 2: 使用 Backlog 命令批量发送（简单但不推荐）

```berry
def update_shadow_reported(reported, clear_desired)
    import json

    var payload = nil

    if clear_desired
        payload = json.dump({
            'state': {
                'reported': reported,
                'desired': nil
            }
        })
    else
        payload = json.dump({
            'state': {
                'reported': reported
            }
        })
    end

    # 使用 Backlog 命令一次性发送
    tasmota.cmd("Backlog Publish " + self.update_topic + " " + payload)
    tasmota.log("📤 Shadow update sent", 2)
end
```

**注意：** 这个方案可能无法解决 QoS 问题。

---

### 方案 3: 减少 Shadow 更新频率（配合方案 1）

如果周期性遥测也在更新 Shadow，可能会导致 Shadow 服务繁忙，延迟增加。

**优化策略：**

1. **命令 ACK 使用 Shadow**（保持不变）
2. **周期性遥测改用独立主题**（减少 Shadow 压力）

**修改 `generate_and_send_telemetry()`：**

```berry
def generate_and_send_telemetry()
    import math
    import json
    import mqtt

    # ... 生成遥测数据 ...

    # 构建遥测数据（不包含 lastAckedReqId）
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
    }

    # 🔥 改为发送到独立的遥测主题，而不是 Shadow
    var telemetry_topic = "dt/" + self.gateway_thing + "/telemetry"
    var payload = json.dump(telemetry)

    mqtt.publish(telemetry_topic, payload, false, 0, 0, 0)  # QoS 0 即可

    tasmota.log("📤 Telemetry: vibration=" + str(telemetry['vibration_level']) + ", events=" + str(telemetry['event_count']), 2)
    self.telemetry_sent += 1
end
```

**好处：**
- 命令 ACK 走 Shadow（可靠性高）
- 周期性遥测走独立主题（延迟低）
- Shadow 不会被频繁更新

---

## 完整的优化代码

### 修改文件：`data/autoexec.be`

**只需修改两个函数：**

#### 1. 修改 `update_shadow_reported()`（第 218-241 行）

```berry
def update_shadow_reported(reported, clear_desired)
    import json
    import mqtt  # 🔥 添加这行

    var payload = nil

    if clear_desired
        # Clear desired state to prevent delta loop
        payload = json.dump({
            'state': {
                'reported': reported,
                'desired': nil  # This clears the desired state
            }
        })
    else
        payload = json.dump({
            'state': {
                'reported': reported
            }
        })
    end

    # 🔥 修改这行：使用 mqtt.publish() 替代 tasmota.cmd()
    mqtt.publish(self.update_topic, payload, false, 0, 0, 1)  # QoS 1
    tasmota.log("📤 Shadow update sent (QoS 1)", 2)
end
```

#### 2. （可选）修改 `generate_and_send_telemetry()`（第 163-216 行）

如果要减少 Shadow 压力，可以改为发送到独立主题：

```berry
def generate_and_send_telemetry()
    import math
    import json
    import mqtt  # 🔥 添加这行

    # ... 前面的代码保持不变 ...

    # Build telemetry payload
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
    }

    # 🔥 改为独立遥测主题（可选）
    var telemetry_topic = "dt/" + self.gateway_thing + "/telemetry"
    var payload = json.dump(telemetry)
    mqtt.publish(telemetry_topic, payload, false, 0, 0, 0)  # QoS 0 即可

    tasmota.log("📤 Telemetry: vibration=" + str(self.vibration_level) + ", events=" + str(self.event_count), 2)
    self.telemetry_sent += 1
end
```

---

## 其他优化建议

### 1. 增加 MQTT KeepAlive 时间

在 Tasmota Web Console 执行：

```bash
MqttKeepAlive 60  # 从默认 300 秒改为 60 秒，保持连接活跃
```

### 2. 启用 MQTT 日志

在 Tasmota Web Console 执行：

```bash
SerialLog 4     # 启用详细日志
MqttLog 4       # 启用 MQTT 详细日志
```

### 3. 检查 WiFi 信号

如果 RSSI < -70，考虑：
- 移动设备靠近路由器
- 更换 2.4GHz 信道（避免干扰）
- 使用 WiFi 中继器

### 4. 减少并发 MQTT 消息

确保不要在同一时间发送多条 MQTT 消息，可能导致队列堵塞。

---

## 测试验证

### 步骤 1: 修改代码并上传

```bash
cd /Volumes/DeDeDisk/PestGG-Project/Tasmota-1

# 备份原文件
cp data/autoexec.be data/autoexec.be.backup

# 编辑文件（添加 mqtt.publish）
vim data/autoexec.be

# 上传到设备
pio run -e tasmota32s3-mi32 -t uploadfs
```

### 步骤 2: 监控设备日志

```bash
pio device monitor -e tasmota32s3-mi32
```

### 步骤 3: 发送测试命令

在 AWS IoT Console 发送：

```json
{
  "state": {
    "desired": {
      "cmd": {
        "action": "set_threshold",
        "vibration_threshold": 10.0
      },
      "reqId": "qos-test-001"
    }
  }
}
```

### 步骤 4: 测量延迟

**记录时间：**
1. 点击 Publish 的时间（用秒表或手机录屏）
2. 设备日志显示 `📩 Delta received` 的时间
3. AWS Console 收到 ACK 的时间

**预期结果：**
- 修改前：2-3 秒
- 修改后：< 500ms（理想情况 < 300ms）

---

## 预期延迟改善

| 阶段 | 修改前 (QoS 0) | 修改后 (QoS 1) |
|------|---------------|---------------|
| AWS → 设备 (Delta) | 100-1000ms | 50-200ms |
| 设备处理 | < 10ms | < 10ms |
| 设备 → AWS (ACK) | 100-1000ms | 50-200ms |
| **总延迟** | **200-2000ms** | **100-410ms** |

**改善幅度：延迟可减少 50-80%**

---

## 诊断延迟的详细步骤

### 在 AWS IoT Console 订阅所有相关主题

1. **订阅 Delta 主题：**
   ```
   $aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/delta
   ```

2. **订阅 Update 主题（你发送的命令）：**
   ```
   $aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update
   ```

3. **订阅 Accepted 主题（ACK）：**
   ```
   $aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/accepted
   ```

### 发送命令并记录时间戳

**点击 Publish 后，在订阅页面查看消息顺序：**

```
T+0ms   : [update] 你发送的命令（desired）
T+50ms  : [delta] AWS IoT 生成的 Delta 事件
T+200ms : [update] 设备发送的 ACK（reported）
T+250ms : [accepted] AWS IoT 确认更新成功
```

**这样可以精确定位延迟发生在哪个环节。**

---

## 总结

**主要优化：**
1. ✅ 使用 `mqtt.publish()` 替代 `tasmota.cmd("Publish")`
2. ✅ 设置 QoS = 1（至少一次交付）
3. ✅ （可选）周期性遥测改用独立主题

**预期效果：**
- 延迟从 2-3 秒降低到 < 500ms
- 命令响应更及时
- MQTT 连接更稳定

需要我帮你修改代码并测试吗？
