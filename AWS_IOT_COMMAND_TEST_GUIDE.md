# AWS IoT 下发控制指令测试指南

## 测试目标

验证从 AWS IoT Console 下发命令到设备，并观察设备的 ACK 响应。

---

## 前置准备

### 1. 确认设备在线

**方法1：查看设备日志**
```bash
cd /Volumes/DeDeDisk/PestGG-Project/Tasmota-1
pio device monitor -e tasmota32s3-mi32
```

**预期日志：**
```
06:42:16.753 MQT: Connected
06:42:16.764 MQT: tele/tasmota_76DBC4/LWT = Online
```

**方法2：AWS IoT Console 查看连接状态**
1. 打开 AWS IoT Console: https://console.aws.amazon.com/iot/
2. 导航到 **Manage → Things**
3. 找到 `IoT-Gateway-000011`
4. 查看 **Connectivity** 状态应该是 **Connected**

---

## 测试步骤

### 步骤 1: 订阅 ACK 主题（观察响应）

**在 AWS IoT Console：**

1. 进入 **Test → MQTT test client**
2. 在 **Subscribe to a topic** 标签页
3. 输入主题名称：
   ```
   $aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/accepted
   ```
4. 点击 **Subscribe**

**说明：**
- 这个主题会收到设备发送的 ACK 响应
- 订阅后，页面会保持打开，等待消息

---

### 步骤 2: 发送测试命令（方法A：AWS IoT Console）

**在 AWS IoT Console：**

1. 在同一个 **MQTT test client** 页面
2. 切换到 **Publish to a topic** 标签页
3. 输入主题名称：
   ```
   $aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update
   ```
4. 输入消息内容（JSON格式）：

#### 测试命令 1: 修改振动阈值

```json
{
  "state": {
    "desired": {
      "cmd": {
        "action": "set_threshold",
        "vibration_threshold": 8.0,
        "sensitivity": "high"
      },
      "reqId": "test-cmd-001"
    }
  }
}
```

5. 点击 **Publish**

---

### 步骤 3: 观察 ACK 响应

**在订阅的主题页面，应该看到类似的消息：**

```json
{
  "state": {
    "reported": {
      "deviceId": "09aa8ad8-f23e-4e75-bcbe-332efeb431ce",
      "gatewayId": "435204e6-21c9-447d-ab6f-888c99b91926",
      "lastAckedReqId": "test-cmd-001",
      "battery": 100,
      "status": "ok",
      "vibration_detected": false,
      "vibration_level": 1.5,
      "threshold": 8.0,
      "sensitivity": "high",
      "event_count": 3,
      "last_trigger_time": 1734422890,
      "timestamp": 1734422895
    }
  },
  "metadata": {
    "reported": {
      "lastAckedReqId": {
        "timestamp": 1734422895
      },
      "threshold": {
        "timestamp": 1734422895
      },
      "sensitivity": {
        "timestamp": 1734422895
      }
    }
  },
  "version": 25,
  "timestamp": 1734422895
}
```

**关键字段验证：**
- ✅ `lastAckedReqId` = `"test-cmd-001"` （与发送的 reqId 匹配）
- ✅ `threshold` = `8.0` （已更新为新值）
- ✅ `sensitivity` = `"high"` （已更新）

---

### 步骤 4: 查看设备端日志

**在串口监视器应该看到：**

```log
06:43:25.123 📩 Delta received for vibration-sensor-001
06:43:25.125 🎯 Command: {"action":"set_threshold","vibration_threshold":8.0,"sensitivity":"high"} (reqId=test-cmd-001)
06:43:25.127 ⚙️ Command received: set_threshold (reqId=test-cmd-001)
06:43:25.135 📤 Shadow update sent
06:43:25.145 ✅ Command ACK sent: set_threshold
06:43:25.250 ✅ Shadow update confirmed
```

**关键日志：**
- ✅ `📩 Delta received` - 设备收到命令
- ✅ `🎯 Command: ...` - 解析命令内容
- ✅ `⚙️ Command received` - 开始执行
- ✅ `✅ Command ACK sent` - ACK 发送成功

---

## 更多测试命令

### 测试命令 2: 修改灵敏度（低）

```json
{
  "state": {
    "desired": {
      "cmd": {
        "action": "set_threshold",
        "vibration_threshold": 3.0,
        "sensitivity": "low"
      },
      "reqId": "test-cmd-002"
    }
  }
}
```

**预期结果：**
- `threshold` 更新为 `3.0`
- `sensitivity` 更新为 `"low"`
- `lastAckedReqId` = `"test-cmd-002"`

---

### 测试命令 3: 重置计数器

```json
{
  "state": {
    "desired": {
      "cmd": {
        "action": "reset_counter"
      },
      "reqId": "test-cmd-003"
    }
  }
}
```

**预期结果：**
- `event_count` 重置为 `0`
- `last_trigger_time` 变为 `null`
- `lastAckedReqId` = `"test-cmd-003"`

---

### 测试命令 4: 修改阈值为高值（测试边界）

```json
{
  "state": {
    "desired": {
      "cmd": {
        "action": "set_threshold",
        "vibration_threshold": 15.0,
        "sensitivity": "high"
      },
      "reqId": "test-cmd-004"
    }
  }
}
```

**预期结果：**
- `threshold` 更新为 `15.0`
- 设备不会频繁触发振动检测（因为阈值很高）

---

## 使用 AWS CLI 发送命令（方法B）

### 安装 AWS CLI

```bash
# macOS
brew install awscli

# 配置 AWS 凭证
aws configure
```

### 发送命令

```bash
aws iot-data update-thing-shadow \
  --thing-name "IoT-Gateway-000011" \
  --shadow-name "vibration-sensor-001" \
  --payload '{
    "state": {
      "desired": {
        "cmd": {
          "action": "set_threshold",
          "vibration_threshold": 6.0,
          "sensitivity": "high"
        },
        "reqId": "cli-test-001"
      }
    }
  }' \
  /dev/stdout
```

**预期输出：**
```json
{
  "payload": {
    "state": {
      "desired": {
        "cmd": {
          "action": "set_threshold",
          "vibration_threshold": 6.0,
          "sensitivity": "high"
        },
        "reqId": "cli-test-001"
      }
    },
    "metadata": {...},
    "version": 26,
    "timestamp": 1734422900
  }
}
```

---

## 验证 ACK 的方法

### 方法 1: 查询 Shadow 文档

```bash
aws iot-data get-thing-shadow \
  --thing-name "IoT-Gateway-000011" \
  --shadow-name "vibration-sensor-001" \
  /dev/stdout | jq '.state.reported.lastAckedReqId'
```

**预期输出：**
```
"cli-test-001"
```

### 方法 2: 订阅 MQTT 主题（实时）

**使用 AWS CLI 订阅：**

```bash
# 订阅 update/accepted 主题
aws iot-data subscribe \
  --topic '$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/accepted'
```

---

## 故障排除

### 问题 1: 设备没有响应

**检查清单：**

1. **设备是否在线？**
   ```bash
   # 查看设备日志
   pio device monitor -e tasmota32s3-mi32

   # 应该看到 "MQT: Connected"
   ```

2. **设备是否订阅了 Delta 主题？**
   ```log
   # 设备启动日志应该包含：
   📥 Subscribed to shadow topics: vibration-sensor-001
   ```

3. **命令格式是否正确？**
   - 检查 JSON 格式是否有效
   - 确认 `reqId` 是唯一的
   - 确认 `cmd` 对象包含 `action` 字段

4. **查看 Shadow 是否更新：**
   ```bash
   aws iot-data get-thing-shadow \
     --thing-name "IoT-Gateway-000011" \
     --shadow-name "vibration-sensor-001" \
     /dev/stdout | jq '.state.desired'
   ```

---

### 问题 2: 收到 Delta 但没有执行

**查看设备日志中的错误：**

```log
⚠️ Missing cmd or reqId in delta  # 命令格式错误
⚠️ Invalid JSON in delta          # JSON 解析失败
```

**可能原因：**
- `cmd` 或 `reqId` 字段缺失
- JSON 格式错误（例如缺少引号、逗号）

---

### 问题 3: ACK 发送失败

**查看设备日志：**

```log
📤 Shadow update sent
❌ Shadow update failed  # 如果出现这个，说明发送失败
```

**检查：**
1. MQTT 连接是否稳定
2. TLS 证书是否有效
3. 网络是否正常

---

## 测试脚本（完整测试流程）

创建测试脚本：

```bash
#!/bin/bash
# test_commands.sh

THING_NAME="IoT-Gateway-000011"
SHADOW_NAME="vibration-sensor-001"

echo "=== AWS IoT Command Test ==="
echo ""

# Test 1: Set threshold to 5.0
echo "Test 1: Set threshold to 5.0"
aws iot-data update-thing-shadow \
  --thing-name "$THING_NAME" \
  --shadow-name "$SHADOW_NAME" \
  --payload '{
    "state": {
      "desired": {
        "cmd": {
          "action": "set_threshold",
          "vibration_threshold": 5.0,
          "sensitivity": "high"
        },
        "reqId": "auto-test-001"
      }
    }
  }' \
  /dev/stdout > /dev/null

echo "Waiting for ACK..."
sleep 2

# Check ACK
ACK=$(aws iot-data get-thing-shadow \
  --thing-name "$THING_NAME" \
  --shadow-name "$SHADOW_NAME" \
  /dev/stdout | jq -r '.state.reported.lastAckedReqId')

if [ "$ACK" == "auto-test-001" ]; then
  echo "✅ Test 1 PASSED: ACK received"
else
  echo "❌ Test 1 FAILED: Expected 'auto-test-001', got '$ACK'"
fi

echo ""
sleep 2

# Test 2: Reset counter
echo "Test 2: Reset counter"
aws iot-data update-thing-shadow \
  --thing-name "$THING_NAME" \
  --shadow-name "$SHADOW_NAME" \
  --payload '{
    "state": {
      "desired": {
        "cmd": {
          "action": "reset_counter"
        },
        "reqId": "auto-test-002"
      }
    }
  }' \
  /dev/stdout > /dev/null

echo "Waiting for ACK..."
sleep 2

ACK=$(aws iot-data get-thing-shadow \
  --thing-name "$THING_NAME" \
  --shadow-name "$SHADOW_NAME" \
  /dev/stdout | jq -r '.state.reported.lastAckedReqId')

if [ "$ACK" == "auto-test-002" ]; then
  echo "✅ Test 2 PASSED: ACK received"
else
  echo "❌ Test 2 FAILED: Expected 'auto-test-002', got '$ACK'"
fi

echo ""
echo "=== Test Complete ==="
```

**运行测试：**
```bash
chmod +x test_commands.sh
./test_commands.sh
```

---

## 总结

### 快速测试步骤

1. **打开设备监视器**
   ```bash
   pio device monitor -e tasmota32s3-mi32
   ```

2. **在 AWS IoT Console 订阅 ACK 主题**
   ```
   $aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/accepted
   ```

3. **发送测试命令**
   ```json
   {
     "state": {
       "desired": {
         "cmd": {
           "action": "set_threshold",
           "vibration_threshold": 8.0,
           "sensitivity": "high"
         },
         "reqId": "test-001"
       }
     }
   }
   ```

4. **验证结果**
   - ✅ AWS Console 收到 ACK 消息
   - ✅ 设备日志显示命令执行
   - ✅ `lastAckedReqId` 匹配

---

## 预期测试结果

| 测试项 | 预期结果 | 延迟 |
|-------|---------|------|
| 命令下发 | 设备收到 Delta | < 100ms |
| 命令执行 | 更新内部状态 | < 10ms |
| ACK 发送 | AWS 收到 ACK | < 200ms |
| 状态同步 | Shadow 更新成功 | < 300ms |

**总延迟：< 500ms**

现在可以开始测试了！
