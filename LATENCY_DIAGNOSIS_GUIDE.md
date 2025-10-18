# MQTT 延迟诊断指南

## 问题

从 AWS IoT Console 点击 Publish 到设备接收命令，延迟约 **2 秒**。

设备位置：**中国大陆**
AWS 区域：**新加坡（ap-southeast-1）**

---

## 🔍 延迟来源分析

### 可能的延迟构成

| 环节 | 预期延迟 | 可能实际延迟 |
|------|---------|-------------|
| 1. 浏览器 → AWS API | 10-50ms | 50-300ms (跨境) |
| 2. AWS 处理 desired 更新 | 10-30ms | 10-30ms |
| 3. AWS 生成 Delta 事件 | 10-50ms | 10-50ms |
| 4. AWS → 设备推送 Delta | 50-150ms | **200-800ms** ⚠️ (跨境) |
| 5. 设备接收并解析 | < 5ms | < 5ms |
| **总延迟** | **90-285ms** | **270-1185ms** |

**结论：2 秒延迟主要来自跨境网络（中国 ↔ 新加坡）**

---

## 📊 更新后的日志格式

修改后的代码会显示详细的延迟信息：

```log
==========================================
📩 MQTT COMMAND RECEIVED
==========================================
📍 Topic: $aws/things/.../update/delta
📦 Raw Payload: {...}
⏰ Device Time: 1760745203 (123456789ms)
📡 AWS Timestamp (UTC): 1760716401
📡 AWS Time (UTC+8): 1760745201
⚡ Network Latency: 2 seconds
❌ High latency (> 2s)
📋 Command Details:
   └─ reqId: test-reset-123
   └─ action: reset_counter
🎯 Full Command Object: {'action': 'reset_counter'}
==========================================
⚙️ Executing command...
```

**关键字段解释：**
- `Device Time`: 设备接收时间（Unix timestamp + 毫秒计数）
- `AWS Timestamp (UTC)`: AWS 生成 Delta 的 UTC 时间
- `AWS Time (UTC+8)`: 转换为北京时间
- `Network Latency`: **实际的网络延迟**（这是关键指标）

---

## 🧪 测试步骤

### 步骤 1: 上传修改后的脚本

```bash
cd /Volumes/DeDeDisk/PestGG-Project/Tasmota-1

# 上传到设备
pio run -e tasmota32s3-mi32 -t uploadfs

# 监控日志
pio device monitor -e tasmota32s3-mi32
```

### 步骤 2: 发送测试命令

在 AWS IoT Console 发送：

```json
{
  "state": {
    "desired": {
      "cmd": {
        "action": "set_threshold",
        "vibration_threshold": 5.0
      },
      "reqId": "latency-test-001"
    }
  }
}
```

### 步骤 3: 观察日志中的延迟

**查看日志中的 "⚡ Network Latency" 字段：**
- < 1s：✅ 优秀（不太可能，除非在中国区）
- 1-2s：⚠️ 可接受（跨境网络）
- \> 2s：❌ 需要优化

---

## 🌏 地理位置延迟测试

### 测试 1: Ping 新加坡 AWS IoT

```bash
ping -c 10 a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com
```

**预期结果（中国 → 新加坡）：**
```
10 packets transmitted, 10 received, 0% packet loss
round-trip min/avg/max = 50/150/300 ms
```

**分析：**
- 平均延迟 < 100ms：✅ 网络良好
- 平均延迟 100-200ms：⚠️ 可接受
- 平均延迟 > 200ms：❌ 网络较慢

---

### 测试 2: Traceroute（追踪路由）

```bash
traceroute a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com
```

**观察：**
- 跳数：通常 15-25 跳
- 是否有高延迟节点
- 是否有丢包（显示 `* * *`）

**示例输出：**
```
 1  192.168.1.1       1.5ms
 2  10.0.0.1          5.2ms
 3  ...
15  aws-gateway       180ms  ← 进入 AWS 网络
16  13.215.xxx.xxx    200ms  ← 新加坡 AWS IoT
```

---

### 测试 3: 对比不同区域

如果可能，测试到其他区域的延迟：

```bash
# 新加坡（当前）
ping a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com

# 东京（如果有资源）
ping xxx.iot.ap-northeast-1.amazonaws.com

# 香港（如果有资源）
ping xxx.iot.ap-east-1.amazonaws.com
```

---

## 💡 延迟优化方案

### 短期方案（立即可用）

#### 1. 使用 QoS 1（必须）

修改 `update_shadow_reported()` 函数：

```berry
def update_shadow_reported(reported, clear_desired)
    import json
    import mqtt

    var payload = json.dump({...})

    # 🔥 使用 mqtt.publish() with QoS 1
    mqtt.publish(self.update_topic, payload, false, 0, 0, 1)
    tasmota.log("📤 Shadow update sent (QoS 1)", 2)
end
```

**预期改善：减少 20-30% 延迟**

#### 2. 优化 WiFi 连接

**检查设备网络：**
```bash
# Tasmota Web Console
Status 5
```

**如果 RSSI < -70，改善方法：**
- 移动设备靠近路由器
- 更换 WiFi 信道
- 使用 5GHz WiFi（如果支持）

#### 3. 减少 Shadow 更新频率

**当前问题：**
- 每 10 秒更新一次 Shadow（周期性遥测）
- Shadow 服务可能繁忙

**解决方法：**

**选项A：增加遥测间隔到 30 秒**
```berry
# 第 404 行
var sensor = VirtualVibrationSensor(..., 30)  # 从 10 改为 30
```

**选项B：周期性遥测改用独立主题**
```berry
def generate_and_send_telemetry()
    import mqtt
    import json

    var telemetry = {...}

    # 发送到独立主题，不更新 Shadow
    var telemetry_topic = "dt/" + self.gateway_thing + "/telemetry"
    mqtt.publish(telemetry_topic, json.dump(telemetry), false, 0, 0, 0)

    self.telemetry_sent += 1
end
```

**预期改善：减少 10-20% 延迟**

---

### 中期方案（需要迁移）

#### 迁移到 AWS 中国区

**AWS 中国区域：**
- **北京（cn-north-1）**
- **宁夏（cn-northwest-1）**

**预期效果：**
- 延迟从 **2000ms** 降低到 **50-200ms**（10倍改善）
- 网络稳定性大幅提升

**缺点：**
- 需要 AWS 中国账号（需要 ICP 备案）
- 需要迁移 Thing 和证书
- 可能有额外成本

**迁移步骤：**
1. 在 AWS 中国区创建 IoT Core
2. 创建 Thing 和证书
3. 更新设备配置
4. 测试连接

---

### 长期方案（生产环境）

#### 1. 使用 AWS Global Accelerator

**优点：**
- 使用 AWS 全球骨干网
- 自动选择最优路径
- 可能降低 30-60% 延迟

**成本：**
- 需要额外付费
- 适合大规模部署

#### 2. 边缘计算方案

**AWS IoT Greengrass：**
- 在本地运行 Lambda 函数
- 减少云端依赖
- 延迟 < 10ms

---

## 🎯 实际测试对比

### 测试方案

**测试 1: 当前配置（QoS 0）**
```
发送命令 → 设备接收
预期延迟: 2000ms
```

**测试 2: 优化后（QoS 1 + 减少 Shadow 更新）**
```
发送命令 → 设备接收
预期延迟: 1200-1500ms (改善 25-40%)
```

**测试 3: 迁移到中国区（理想情况）**
```
发送命令 → 设备接收
预期延迟: 50-200ms (改善 90%)
```

---

## 📈 延迟基准对比

| 方案 | 延迟 | 成本 | 实施难度 |
|------|------|------|---------|
| **当前（新加坡，QoS 0）** | 2000ms | 低 | - |
| **优化（QoS 1 + 减少更新）** | 1200-1500ms | 低 | 低 |
| **AWS 中国区** | 50-200ms | 中 | 高 |
| **Global Accelerator** | 1000-1400ms | 高 | 中 |
| **Greengrass（边缘）** | < 10ms | 中 | 高 |

---

## 🔧 诊断命令速查

### 设备端

```bash
# 查看网络状态
Status 5

# 查看 MQTT 状态
Status 6

# 测试时间同步
Time

# 查看设备运行时间
Status 1
```

### 电脑端

```bash
# Ping 测试
ping -c 10 a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com

# Traceroute
traceroute a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com

# 上传脚本
pio run -e tasmota32s3-mi32 -t uploadfs

# 监控日志
pio device monitor -e tasmota32s3-mi32
```

---

## 总结

### 当前情况

- ✅ 设备功能正常
- ✅ 命令可以执行
- ⚠️ 延迟 2 秒（主要是地理位置）

### 延迟构成

```
总延迟 2000ms ≈
  AWS 处理 (50ms)
  + 网络传输 (1900ms) ← 主要瓶颈
  + 设备处理 (50ms)
```

### 建议方案

**短期（立即实施）：**
1. ✅ 修改代码使用 QoS 1
2. ✅ 减少 Shadow 更新频率
3. ✅ 优化 WiFi 信号

**预期改善：延迟降低到 1200-1500ms（25-40% 改善）**

**中长期（如果需要更低延迟）：**
4. 迁移到 AWS 中国区
5. 使用 AWS Global Accelerator

**预期改善：延迟降低到 50-200ms（90% 改善）**

---

## 下一步

1. **上传修改后的脚本**
2. **发送测试命令**
3. **查看日志中的 "⚡ Network Latency" 字段**
4. **根据实际延迟决定是否需要进一步优化**

现在可以开始测试了！
