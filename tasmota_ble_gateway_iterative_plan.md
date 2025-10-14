# Tasmota BLE网关迭代实施计划

## 开发策略

采用**两阶段迭代**开发:
1. **Phase 1**: 网关与AWS通信调试 (使用模拟子设备数据)
2. **Phase 2**: 集成真实BLE硬件通信

这样可以先验证核心数据流转逻辑,降低调试复杂度。

---

## Phase 1: 网关-AWS通信调试 (模拟子设备)

### 目标
- ✅ 网关成功连接AWS IoT Core
- ✅ 定期上报网关自身状态 + 模拟子设备数据
- ✅ 接收AWS下发的指令(打印日志,更新模拟状态)
- ✅ 验证Shadow同步机制

### 架构图

```
┌─────────────────────────────────────────┐
│         AWS IoT Core                     │
│  Thing: ble-gateway-001                  │
│  ┌────────────────────────────────────┐ │
│  │  Device Shadow                     │ │
│  │  {                                 │ │
│  │    "reported": {                   │ │
│  │      "gateway": {...},             │ │
│  │      "devices": {                  │ │
│  │        "AA:BB:CC:DD:EE:FF": {      │ │
│  │          "temperature": 25.3,      │ │
│  │          "humidity": 60            │ │
│  │        }                           │ │
│  │      }                             │ │
│  │    },                              │ │
│  │    "desired": {                    │ │
│  │      "commands": {                 │ │
│  │        "AA:BB:CC:DD:EE:FF": "test" │ │
│  │      }                             │ │
│  │    }                               │ │
│  │  }                                 │ │
│  └────────────────────────────────────┘ │
└─────────────────┬───────────────────────┘
                  │ MQTT/TLS
                  │
┌─────────────────┴───────────────────────┐
│  ESP32-S3 Gateway (Tasmota)              │
│  ┌────────────────────────────────────┐ │
│  │  Berry脚本                         │ │
│  │  - AWSDeviceShadow (核心)          │ │
│  │  - MockDeviceSimulator (模拟器)    │ │
│  │  - GatewayHeartbeat (心跳)         │ │
│  └────────────────────────────────────┘ │
│                                          │
│  模拟设备(内存中的假数据):                │
│  - AA:BB:CC:DD:EE:FF (温度传感器)       │
│  - 11:22:33:44:55:66 (智能锁)           │
│  - 77:88:99:AA:BB:CC (振动传感器)       │
└──────────────────────────────────────────┘
```

---

## Phase 1 详细任务

### Task 1.1: 实现基础Berry版AWS Device Shadow客户端

**文件**: `lib/aws_shadow.be`

**功能**:
- 订阅Shadow相关主题
- 发布reported状态更新
- 接收并解析delta消息
- 提供回调机制给上层业务

**完整代码**:

```berry
# lib/aws_shadow.be
class AWSDeviceShadow : Driver
    var thing_name
    var mqtt_connected
    var shadow_topics
    var delta_callback
    var version

    def init(thing_name)
        self.thing_name = thing_name
        self.mqtt_connected = false
        self.version = 0
        self.delta_callback = nil

        # 构造Shadow主题
        var base = "$aws/things/" + thing_name + "/shadow"
        self.shadow_topics = {
            'update': base + '/update',
            'get': base + '/get',
            'update_accepted': base + '/update/accepted',
            'update_rejected': base + '/update/rejected',
            'update_delta': base + '/update/delta',
            'get_accepted': base + '/get/accepted'
        }

        print("AWSDeviceShadow: Initialized for thing:", thing_name)
    end

    # 订阅所有Shadow主题
    def subscribe_all()
        print("AWSDeviceShadow: Subscribing to Shadow topics...")

        tasmota.cmd("Subscribe " + self.shadow_topics['update_accepted'])
        tasmota.cmd("Subscribe " + self.shadow_topics['update_rejected'])
        tasmota.cmd("Subscribe " + self.shadow_topics['update_delta'])
        tasmota.cmd("Subscribe " + self.shadow_topics['get_accepted'])

        print("AWSDeviceShadow: Subscribed to 4 topics")
    end

    # 更新reported状态
    def update_reported(state_dict)
        var payload = {
            "state": {
                "reported": state_dict
            },
            "clientToken": str(tasmota.millis())
        }

        var json_payload = json.dump(payload)
        var topic = self.shadow_topics['update']

        tasmota.publish(topic, json_payload, false)
        print("AWSDeviceShadow: Published update ->", topic)
        print("  Payload size:", size(json_payload), "bytes")
    end

    # 获取当前Shadow
    def get_shadow()
        tasmota.publish(self.shadow_topics['get'], "", false)
        print("AWSDeviceShadow: Requested Shadow state")
    end

    # 注册delta回调
    def set_delta_callback(callback)
        self.delta_callback = callback
        print("AWSDeviceShadow: Delta callback registered")
    end

    # MQTT消息回调 (Tasmota自动调用)
    def mqtt_data(topic, idx, data, data_len)
        # 解析JSON
        var msg = json.load(data)

        # 处理update/accepted
        if string.find(topic, '/update/accepted') > 0
            self.version = msg.get('version', 0)
            print("AWSDeviceShadow: Update accepted, version:", self.version)

        # 处理update/rejected
        elif string.find(topic, '/update/rejected') > 0
            print("AWSDeviceShadow: Update REJECTED!")
            print("  Error:", msg.get('message', 'Unknown error'))

        # 处理delta
        elif string.find(topic, '/update/delta') > 0
            print("AWSDeviceShadow: Delta received!")
            self.version = msg.get('version', 0)

            if msg.contains('state')
                var delta_state = msg['state']
                print("  Delta state:", json.dump(delta_state))

                # 触发回调
                if self.delta_callback != nil
                    self.delta_callback(delta_state)
                end
            end

        # 处理get/accepted
        elif string.find(topic, '/get/accepted') > 0
            self.version = msg.get('version', 0)
            print("AWSDeviceShadow: Current Shadow received, version:", self.version)
            if msg.contains('state')
                print("  Reported:", json.dump(msg['state'].get('reported', {})))
                print("  Desired:", json.dump(msg['state'].get('desired', {})))
            end
        end
    end

    # WiFi连接成功后自动订阅
    def web_add_handler()
        import webserver
        webserver.on("/aws_status", / -> self.web_status())
    end

    def web_status()
        import webserver
        var html = "<h2>AWS Shadow Status</h2>"
        html += "<p>Thing: " + self.thing_name + "</p>"
        html += "<p>Version: " + str(self.version) + "</p>"
        html += "<p>MQTT: " + (self.mqtt_connected ? "Connected" : "Disconnected") + "</p>"
        webserver.content_send(html)
    end
end

return AWSDeviceShadow
```

**测试步骤**:
1. 创建文件 `lib/aws_shadow.be`
2. Berry控制台执行: `AWSDeviceShadow = load("lib/aws_shadow.be")`
3. 创建实例: `shadow = AWSDeviceShadow("test-gateway")`
4. 订阅主题: `shadow.subscribe_all()`
5. 发布测试: `shadow.update_reported({"test": 123})`

---

### Task 1.2: 实现Shadow主题订阅和MQTT消息路由

**文件**: `lib/mqtt_router.be`

确保MQTT消息正确路由到Shadow客户端。

```berry
# lib/mqtt_router.be
class MQTTRouter : Driver
    var handlers  # 消息处理器列表

    def init()
        self.handlers = []
        print("MQTTRouter: Initialized")
    end

    # 注册消息处理器
    def register_handler(handler)
        self.handlers.push(handler)
        print("MQTTRouter: Handler registered, total:", size(self.handlers))
    end

    # MQTT连接成功回调
    def mqtt_connected()
        print("MQTTRouter: MQTT connected, notifying handlers...")
        for handler : self.handlers
            if handler.contains('mqtt_connected')
                handler.mqtt_connected()
            end
            if handler.contains('subscribe_all')
                handler.subscribe_all()
            end
        end
    end

    # MQTT消息到达回调
    def mqtt_data(topic, idx, data, data_len)
        # 路由到所有处理器
        for handler : self.handlers
            if handler.contains('mqtt_data')
                handler.mqtt_data(topic, idx, data, data_len)
            end
        end
    end
end

return MQTTRouter
```

---

### Task 1.3: 实现网关自身状态定期上报(模拟数据)

**文件**: `lib/gateway_heartbeat.be`

每30秒上报网关状态到Shadow。

```berry
# lib/gateway_heartbeat.be
class GatewayHeartbeat : Driver
    var shadow
    var last_report_time
    var report_interval  # 毫秒

    def init(shadow_client, interval_sec)
        self.shadow = shadow_client
        self.report_interval = interval_sec * 1000
        self.last_report_time = 0
        print("GatewayHeartbeat: Initialized, interval:", interval_sec, "seconds")
    end

    # Tasmota每秒调用
    def every_second()
        var now = tasmota.millis()

        if now - self.last_report_time >= self.report_interval
            self.report_gateway_status()
            self.last_report_time = now
        end
    end

    def report_gateway_status()
        # 收集网关状态
        var status = tasmota.cmd("Status")
        var status_mem = tasmota.cmd("Status 4")  # 内存状态
        var wifi_info = tasmota.wifi()
        var rtc = tasmota.rtc()

        var gateway_state = {
            "online": true,
            "timestamp": rtc['local'],
            "uptime_sec": rtc['uptime'],
            "wifi_rssi": wifi_info['rssi'],
            "wifi_ssid": wifi_info['ssid'],
            "heap_free": status_mem['StatusMEM']['Heap'],
            "firmware_version": status['Status']['Version'],
            "ip_address": wifi_info['ip']
        }

        # 上报到Shadow
        self.shadow.update_reported({"gateway": gateway_state})

        print("GatewayHeartbeat: Reported gateway status")
        print("  Uptime:", rtc['uptime'], "sec, Heap:", gateway_state['heap_free'], "KB")
    end
end

return GatewayHeartbeat
```

---

### Task 1.4: 实现模拟子设备数据生成器

**文件**: `lib/mock_device_simulator.be`

在内存中模拟3个虚拟BLE设备,生成随机但合理的传感器数据。

```berry
# lib/mock_device_simulator.be
import math

class MockDeviceSimulator : Driver
    var devices
    var shadow
    var last_update_time
    var update_interval  # 毫秒

    def init(shadow_client, interval_sec)
        self.shadow = shadow_client
        self.update_interval = interval_sec * 1000
        self.last_update_time = 0

        # 初始化3个模拟设备
        self.devices = {
            "AA:BB:CC:DD:EE:FF": {
                "name": "温度传感器-客厅",
                "type": "temperature_sensor",
                "protocol": "mi32",
                "battery": 85,
                "rssi": -65,
                "state": {
                    "temperature": 25.0,
                    "humidity": 60.0
                }
            },
            "11:22:33:44:55:66": {
                "name": "智能锁-前门",
                "type": "smart_lock",
                "protocol": "mi32",
                "battery": 90,
                "rssi": -55,
                "state": {
                    "lock_state": "locked",
                    "last_unlock_time": 0
                }
            },
            "77:88:99:AA:BB:CC": {
                "name": "振动传感器-窗户",
                "type": "vibration_sensor",
                "protocol": "mi32",
                "battery": 78,
                "rssi": -70,
                "state": {
                    "vibration_detected": false,
                    "last_vibration_time": 0
                }
            }
        }

        print("MockDeviceSimulator: Initialized with", size(self.devices), "mock devices")
    end

    # 每秒执行
    def every_second()
        var now = tasmota.millis()

        if now - self.last_update_time >= self.update_interval
            self.update_mock_devices()
            self.report_devices_state()
            self.last_update_time = now
        end
    end

    # 更新模拟设备数据 (生成随机变化)
    def update_mock_devices()
        var rtc = tasmota.rtc()
        var timestamp = rtc['local']

        # 温度传感器: 在25±3度范围内随机波动
        var temp_dev = self.devices["AA:BB:CC:DD:EE:FF"]
        temp_dev['state']['temperature'] = 25.0 + (math.rand() % 60 - 30) / 10.0
        temp_dev['state']['humidity'] = 60.0 + (math.rand() % 40 - 20) / 10.0
        temp_dev['rssi'] = -65 + (math.rand() % 10 - 5)
        temp_dev['battery'] = temp_dev['battery'] > 10 ? temp_dev['battery'] - 0.01 : 10
        temp_dev['last_seen'] = timestamp

        # 智能锁: 保持锁定状态(除非收到指令)
        var lock_dev = self.devices["11:22:33:44:55:66"]
        lock_dev['rssi'] = -55 + (math.rand() % 10 - 5)
        lock_dev['battery'] = lock_dev['battery'] > 10 ? lock_dev['battery'] - 0.005 : 10
        lock_dev['last_seen'] = timestamp

        # 振动传感器: 5%概率检测到振动
        var vib_dev = self.devices["77:88:99:AA:BB:CC"]
        if math.rand() % 100 < 5
            vib_dev['state']['vibration_detected'] = true
            vib_dev['state']['last_vibration_time'] = timestamp
            print("MockDeviceSimulator: Vibration detected!")
        else
            vib_dev['state']['vibration_detected'] = false
        end
        vib_dev['rssi'] = -70 + (math.rand() % 10 - 5)
        vib_dev['battery'] = vib_dev['battery'] > 10 ? vib_dev['battery'] - 0.008 : 10
        vib_dev['last_seen'] = timestamp
    end

    # 上报所有设备状态到Shadow
    def report_devices_state()
        var devices_report = {}

        for mac : self.devices.keys()
            var dev = self.devices[mac]

            # 构造上报数据
            devices_report[mac] = {
                "name": dev['name'],
                "type": dev['type'],
                "protocol": dev['protocol'],
                "last_seen": dev['last_seen'],
                "rssi": dev['rssi'],
                "battery": int(dev['battery'])
            }

            # 合并设备state
            for key : dev['state'].keys()
                devices_report[mac][key] = dev['state'][key]
            end
        end

        # 上报到Shadow
        self.shadow.update_reported({"devices": devices_report})

        print("MockDeviceSimulator: Reported", size(devices_report), "devices")
    end

    # 处理命令 (模拟执行)
    def handle_command(device_mac, command)
        if !self.devices.contains(device_mac)
            print("MockDeviceSimulator: Device not found:", device_mac)
            return false
        end

        var device = self.devices[device_mac]
        print("MockDeviceSimulator: Executing command on", device['name'])
        print("  MAC:", device_mac)
        print("  Command:", command)

        # 根据设备类型处理命令
        if device['type'] == 'smart_lock'
            if command == 'lock'
                device['state']['lock_state'] = 'locked'
                print("  -> Door LOCKED")
            elif command == 'unlock'
                device['state']['lock_state'] = 'unlocked'
                device['state']['last_unlock_time'] = tasmota.rtc()['local']
                print("  -> Door UNLOCKED")
            end
            return true

        elif device['type'] == 'temperature_sensor'
            if command == 'read'
                print("  -> Temperature:", device['state']['temperature'], "°C")
                print("  -> Humidity:", device['state']['humidity'], "%")
            end
            return true

        elif device['type'] == 'vibration_sensor'
            if command == 'reset'
                device['state']['vibration_detected'] = false
                device['state']['last_vibration_time'] = 0
                print("  -> Vibration alert RESET")
            end
            return true
        end

        return false
    end

    # 获取设备信息 (供外部查询)
    def get_device(device_mac)
        return self.devices.get(device_mac, nil)
    end
end

return MockDeviceSimulator
```

---

### Task 1.5: 实现模拟子设备状态上报到Shadow

这个功能已经包含在 `MockDeviceSimulator.report_devices_state()` 中。

**验证方式**:
- AWS IoT控制台查看Shadow的 `reported.devices` 字段
- 应该看到3个模拟设备的实时数据

---

### Task 1.6: 实现delta消息接收和解析

**文件**: `lib/command_handler.be`

处理来自AWS的delta消息,提取commands字段。

```berry
# lib/command_handler.be
class CommandHandler
    var device_simulator

    def init(simulator)
        self.device_simulator = simulator
        print("CommandHandler: Initialized")
    end

    # Delta回调函数
    def on_delta(delta_state)
        print("CommandHandler: Processing delta...")
        print("  Delta state:", json.dump(delta_state))

        # 提取commands字段
        if delta_state.contains('commands')
            var commands = delta_state['commands']
            print("  Found commands for", size(commands), "device(s)")

            for device_mac : commands.keys()
                var command = commands[device_mac]
                print("  -> Device:", device_mac, "Command:", command)

                # 执行模拟命令
                var success = self.device_simulator.handle_command(device_mac, command)

                if success
                    print("  -> Command executed successfully")
                else
                    print("  -> Command execution FAILED")
                end
            end
        else
            print("  No 'commands' field in delta")
        end
    end
end

return CommandHandler
```

---

### Task 1.7: 实现模拟指令处理(打印日志+更新状态)

这个功能已经包含在 `MockDeviceSimulator.handle_command()` 中。

**功能**:
- 智能锁: 执行 `lock`/`unlock` 命令,更新 `lock_state`
- 温度传感器: 执行 `read` 命令,打印当前数值
- 振动传感器: 执行 `reset` 命令,清除告警

---

### Task 1.8: 配置AWS IoT证书和连接测试

**步骤**:

1. **在AWS IoT控制台创建Thing**
```bash
Thing Name: ble-gateway-dev-001
Thing Type: (可选)
```

2. **创建并下载证书**
- 下载设备证书: `ble-gateway-dev-001.cert.pem`
- 下载私钥: `ble-gateway-dev-001.private.key`
- 下载根CA: `AmazonRootCA1.pem`

3. **附加策略**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:us-east-1:*:client/ble-gateway-dev-001"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iot:Publish",
        "iot:Receive"
      ],
      "Resource": [
        "arn:aws:iot:us-east-1:*:topic/$aws/things/ble-gateway-dev-001/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": [
        "arn:aws:iot:us-east-1:*:topicfilter/$aws/things/ble-gateway-dev-001/*"
      ]
    }
  ]
}
```

4. **上传证书到Tasmota**

方法1: 通过Web界面上传
- 访问 `http://<tasmota-ip>/uf`
- 上传文件:
  - `/aws_cert.pem` (设备证书)
  - `/aws_key.pem` (私钥)
  - `/aws_ca.pem` (根CA)

方法2: 通过Berry脚本嵌入(小文件)
```berry
# 将证书内容写入文件
def upload_cert(filename, content)
    var f = open(filename, "w")
    f.write(content)
    f.close()
    print("Uploaded:", filename)
end

# 使用方法
var cert_content = "-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----"
upload_cert("/aws_cert.pem", cert_content)
```

5. **配置Tasmota MQTT**

在Tasmota控制台执行:
```
Backlog MqttHost xxxxxx-ats.iot.us-east-1.amazonaws.com; MqttPort 8883; MqttClient ble-gateway-dev-001; MqttUser ; MqttPassword ; SetOption103 1
```

或通过Web界面: Configuration -> Configure MQTT

6. **配置TLS证书路径**

创建 `lib/mqtt_tls_config.be`:
```berry
# lib/mqtt_tls_config.be
import mqtt

# 配置TLS证书
def configure_tls()
    var cert_path = "/aws_cert.pem"
    var key_path = "/aws_key.pem"
    var ca_path = "/aws_ca.pem"

    # 检查文件存在
    import path
    if !path.exists(cert_path)
        print("ERROR: Certificate not found:", cert_path)
        return false
    end
    if !path.exists(key_path)
        print("ERROR: Private key not found:", key_path)
        return false
    end
    if !path.exists(ca_path)
        print("ERROR: CA certificate not found:", ca_path)
        return false
    end

    # 配置MQTT TLS
    mqtt.tlsconfig(cert_path, key_path, ca_path)
    print("MQTT TLS configured successfully")
    return true
end

configure_tls()
```

---

### Task 1.9: 端到端测试 - 网关上报模拟数据

**主启动脚本**: `autoexec.be`

```berry
# autoexec.be - Phase 1 完整启动脚本

print("="*50)
print("BLE Gateway - Phase 1: Mock Devices")
print("="*50)

# 1. 配置MQTT TLS
load("lib/mqtt_tls_config.be")

# 2. 加载模块
AWSDeviceShadow = load("lib/aws_shadow.be")
MQTTRouter = load("lib/mqtt_router.be")
GatewayHeartbeat = load("lib/gateway_heartbeat.be")
MockDeviceSimulator = load("lib/mock_device_simulator.be")
CommandHandler = load("lib/command_handler.be")

# 3. 创建实例
var thing_name = "ble-gateway-dev-001"
var shadow = AWSDeviceShadow(thing_name)
var router = MQTTRouter()
var heartbeat = GatewayHeartbeat(shadow, 30)  # 30秒上报网关状态
var simulator = MockDeviceSimulator(shadow, 15)  # 15秒更新模拟设备
var cmd_handler = CommandHandler(simulator)

# 4. 注册delta回调
shadow.set_delta_callback(/delta -> cmd_handler.on_delta(delta))

# 5. 注册消息路由
router.register_handler(shadow)

# 6. 添加驱动
tasmota.add_driver(router)
tasmota.add_driver(heartbeat)
tasmota.add_driver(simulator)

print("="*50)
print("Gateway initialized successfully!")
print("Thing Name:", thing_name)
print("Waiting for MQTT connection...")
print("="*50)

# 7. 延迟5秒后订阅主题(等待MQTT连接)
tasmota.set_timer(5000, / -> shadow.subscribe_all())

# 8. 延迟10秒后获取当前Shadow
tasmota.set_timer(10000, / -> shadow.get_shadow())
```

**测试步骤**:

1. 重启Tasmota: `Restart 1`
2. 观察串口日志:
```
BLE Gateway - Phase 1: Mock Devices
MQTT TLS configured successfully
AWSDeviceShadow: Initialized for thing: ble-gateway-dev-001
MQTTRouter: Initialized
...
MQTT: Connected to AWS IoT
AWSDeviceShadow: Subscribing to Shadow topics...
GatewayHeartbeat: Reported gateway status
MockDeviceSimulator: Reported 3 devices
```

3. AWS IoT控制台查看:
   - 设备状态: Connected
   - Shadow内容:
```json
{
  "reported": {
    "gateway": {
      "online": true,
      "uptime_sec": 120,
      "wifi_rssi": -65,
      "heap_free": 123456
    },
    "devices": {
      "AA:BB:CC:DD:EE:FF": {
        "name": "温度传感器-客厅",
        "type": "temperature_sensor",
        "temperature": 25.3,
        "humidity": 60,
        "battery": 85
      },
      ...
    }
  }
}
```

---

### Task 1.10: 端到端测试 - AWS下发指令到模拟设备

**测试步骤**:

1. 在AWS IoT控制台打开Shadow编辑器
2. 更新 `desired` 字段:
```json
{
  "state": {
    "desired": {
      "commands": {
        "11:22:33:44:55:66": "unlock"
      }
    }
  }
}
```

3. 点击"Update"

4. 观察Tasmota串口日志:
```
AWSDeviceShadow: Delta received!
  Delta state: {"commands":{"11:22:33:44:55:66":"unlock"}}
CommandHandler: Processing delta...
  Found commands for 1 device(s)
  -> Device: 11:22:33:44:55:66 Command: unlock
MockDeviceSimulator: Executing command on 智能锁-前门
  MAC: 11:22:33:44:55:66
  Command: unlock
  -> Door UNLOCKED
  -> Command executed successfully
```

5. 等待下一次模拟设备状态上报(15秒内)

6. AWS Shadow中 `reported.devices.11:22:33:44:55:66.lock_state` 应该变为 `"unlocked"`

**测试其他命令**:
```json
// 温度传感器读取
{"commands": {"AA:BB:CC:DD:EE:FF": "read"}}

// 振动传感器复位
{"commands": {"77:88:99:AA:BB:CC": "reset"}}

// 智能锁上锁
{"commands": {"11:22:33:44:55:66": "lock"}}

// 多设备同时控制
{"commands": {
  "11:22:33:44:55:66": "lock",
  "77:88:99:AA:BB:CC": "reset"
}}
```

---

## Phase 1 完成标准

- ✅ 网关成功连接AWS IoT (MQTT over TLS)
- ✅ Shadow订阅成功(4个主题)
- ✅ 网关状态每30秒上报
- ✅ 模拟设备状态每15秒上报
- ✅ AWS控制台可查看实时Shadow数据
- ✅ AWS下发命令,网关日志显示执行过程
- ✅ 设备状态变更后上报到Shadow

---

## Phase 2: 集成真实BLE硬件

### 目标
- ✅ 替换模拟设备为真实MI32 BLE扫描
- ✅ 解析真实BLE广播包
- ✅ C++实现GATT连接和写入
- ✅ 完整的云端到设备指令下发

### Task 2.1: 集成真实MI32 BLE扫描回调

**修改文件**: `lib/real_device_manager.be`

```berry
# lib/real_device_manager.be
class RealDeviceManager : Driver
    var devices
    var shadow

    def init(shadow_client)
        self.shadow = shadow_client
        self.devices = {}

        # 启用MI32 Berry回调
        tasmota.cmd("MI32Option6 1")

        # 注册BLE广播事件
        tasmota.add_rule("MI32#ADV", /value -> self.on_ble_adv())

        print("RealDeviceManager: Initialized, waiting for BLE devices...")
    end

    def on_ble_adv()
        import MI32
        var adv = MI32.devices()  # 获取所有发现的设备

        for device : adv
            var mac = device['mac']

            if !self.devices.contains(mac)
                # 新设备注册
                self.register_device(device)
            else
                # 更新状态
                self.update_device_state(mac, device)
            end
        end
    end

    def register_device(device)
        var mac = device['mac']
        print("RealDeviceManager: New device discovered:", mac)

        self.devices[mac] = {
            "name": device.get('name', 'Unknown'),
            "type": self.detect_device_type(device),
            "protocol": "mi32",
            "mac": mac
        }
    end

    def detect_device_type(device)
        # 根据设备ID判断类型
        var model = device.get('model', '')
        if model == 'LYWSD03MMC'
            return 'temperature_sensor'
        elif model == 'MJYD2S'
            return 'motion_sensor'
        else
            return 'unknown'
        end
    end

    def update_device_state(mac, device)
        var dev = self.devices[mac]
        dev['rssi'] = device.get('rssi', 0)
        dev['battery'] = device.get('battery', 0)
        dev['last_seen'] = tasmota.rtc()['local']

        # 提取传感器数据
        if device.contains('temperature')
            dev['temperature'] = device['temperature']
        end
        if device.contains('humidity')
            dev['humidity'] = device['humidity']
        end
    end
end

return RealDeviceManager
```

### Task 2.3: C++扩展 - 添加MI32 GATT连接和写入接口

**修改文件**: `tasmota/tasmota_xsns_sensor/xsns_62_esp32_mi.ino`

在文件末尾添加:

```cpp
/*********************************************************************************************\
 * Berry接口扩展 - GATT连接和写入
\*********************************************************************************************/

#ifdef USE_BERRY

extern "C" {
    #include "be_constobj.h"

    // BLE.connect(mac_string, timeout_ms) -> bool
    int32_t be_mi32_connect(bvm *vm) {
        const char *mac_str = be_tostring(vm, 1);
        int32_t timeout_ms = be_toint(vm, 2);

        uint8_t mac[6];
        if (sscanf(mac_str, "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx",
                   &mac[5], &mac[4], &mac[3], &mac[2], &mac[1], &mac[0]) != 6) {
            be_raise(vm, "value_error", "Invalid MAC format");
        }

        NimBLEAddress addr(mac);
        NimBLEClient *pClient = NimBLEDevice::createClient();

        if (!pClient) {
            be_pushbool(vm, false);
            be_return(vm);
        }

        pClient->setConnectTimeout(timeout_ms / 1000);
        bool connected = pClient->connect(addr, false);

        if (connected) {
            AddLog(LOG_LEVEL_INFO, "BLE: Connected to %s", mac_str);
        } else {
            NimBLEDevice::deleteClient(pClient);
        }

        be_pushbool(vm, connected);
        be_return(vm);
    }

    // BLE.write(mac, service_uuid, char_uuid, data_bytes) -> bool
    int32_t be_mi32_write(bvm *vm) {
        // 实现GATT写入...
        be_pushbool(vm, true);
        be_return(vm);
    }
}

// 注册到Berry
be_native_module_attr_table(mi32_ble) {
    be_native_module_function("connect", be_mi32_connect),
    be_native_module_function("write", be_mi32_write)
};
be_define_native_module(mi32_ble, NULL);

#endif  // USE_BERRY
```

---

## Phase 2 完成标准

- ✅ 真实BLE设备自动发现并注册
- ✅ 真实设备数据解析并上报Shadow
- ✅ AWS下发命令,网关通过GATT连接发送
- ✅ 设备响应后状态同步到Shadow

---

## 项目文件结构

```
/
├── autoexec.be                    # 主启动脚本
├── lib/
│   ├── aws_shadow.be              # AWS Shadow客户端(核心)
│   ├── mqtt_router.be             # MQTT消息路由
│   ├── mqtt_tls_config.be         # TLS证书配置
│   ├── gateway_heartbeat.be       # 网关心跳
│   ├── mock_device_simulator.be   # 模拟设备(Phase 1)
│   ├── command_handler.be         # 指令处理器
│   └── real_device_manager.be     # 真实设备管理(Phase 2)
├── certs/
│   ├── aws_cert.pem               # AWS设备证书
│   ├── aws_key.pem                # 私钥
│   └── aws_ca.pem                 # 根CA
└── data/
    └── devices.json               # 设备持久化(Phase 2)
```

---

## 预计时间

| Phase | 任务数 | 预计工时 |
|-------|-------|---------|
| Phase 1 | 10 | 16小时 (2个工作日) |
| Phase 2 | 5 | 20小时 (2.5个工作日) |
| **总计** | **15** | **36小时 (4.5个工作日)** |

---

## 下一步行动

1. ✅ 确认AWS IoT账号和区域
2. ✅ 创建Thing并下载证书
3. ✅ 开始实施 Task 1.1: 创建 `lib/aws_shadow.be`
4. ✅ 逐步完成Phase 1的10个任务
5. ✅ Phase 1验证通过后,进入Phase 2
