# Tasmota BLE网关实施计划

## 项目概述

基于Tasmota32S3-MI32固件，实现一个BLE网关，功能对标Python模拟器中的网关部分。该网关：
- **无低功耗需求**（常供电）
- **被动接收BLE设备广播**（使用Tasmota已支持的协议）
- **按需主动GATT连接**（下发指令时）
- **无并发连接需求**（串行处理）
- **支持子设备挂载管理**
- **与AWS IoT Core通信**（Device Shadow机制）

---

## 系统架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      AWS IoT Core                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Thing: ble-gateway-001                              │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  Device Shadow (Classic)                       │  │   │
│  │  │  {                                             │  │   │
│  │  │    "state": {                                  │  │   │
│  │  │      "reported": {                             │  │   │
│  │  │        "gateway": {...},                       │  │   │
│  │  │        "devices": {                            │  │   │
│  │  │          "AA:BB:CC:DD:EE:FF": {...}            │  │   │
│  │  │        }                                       │  │   │
│  │  │      },                                        │  │   │
│  │  │      "desired": {                              │  │   │
│  │  │        "commands": {                           │  │   │
│  │  │          "AA:BB:CC:DD:EE:FF": "lock"           │  │   │
│  │  │        }                                       │  │   │
│  │  │      }                                         │  │   │
│  │  │    }                                           │  │   │
│  │  │  }                                             │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  自定义主题:                                                  │
│  - gateways/{gateway_id}/heartbeat     (心跳)               │
│  - gateways/{gateway_id}/devices       (设备列表)            │
└──────────────────────┬───────────────────────────────────────┘
                       │ MQTT over TLS 1.2
                       │ X.509 Certificate Auth
                       │
┌──────────────────────┴───────────────────────────────────────┐
│              ESP32-S3 BLE Gateway (Tasmota)                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Berry脚本层 (业务逻辑)                                  │ │
│  │  ┌─────────────────┐  ┌──────────────────┐             │ │
│  │  │ AWSDeviceShadow │  │ DeviceManager    │             │ │
│  │  │ - subscribe()   │  │ - devices{}      │             │ │
│  │  │ - update()      │  │ - register()     │             │ │
│  │  │ - handle_delta()│  │ - send_command() │             │ │
│  │  └─────────────────┘  └──────────────────┘             │ │
│  │  ┌─────────────────┐  ┌──────────────────┐             │ │
│  │  │ CommandQueue    │  │ DualHeartbeat    │             │ │
│  │  │ - enqueue()     │  │ - shadow_hb()    │             │ │
│  │  │ - dequeue()     │  │ - custom_hb()    │             │ │
│  │  │ - persist()     │  └──────────────────┘             │ │
│  │  └─────────────────┘                                    │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  C++层 (MI32驱动 + BLE扩展)                              │ │
│  │  - xsns_62_esp32_mi.ino (已有MI32驱动)                  │ │
│  │  - 新增: MI32_ConnectDevice()                           │ │
│  │  - 新增: MI32_WriteGATT()                               │ │
│  │  - 新增: Berry接口 BLE.connect() / BLE.write()          │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  NimBLE Stack (ESP-IDF)                                 │ │
│  │  - BLE扫描 (被动接收广播)                                │ │
│  │  - GATT客户端 (主动连接)                                 │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ BLE 5.0
                       │
        ┌──────────────┴──────────────┐
        │                             │
┌───────┴────────┐          ┌─────────┴────────┐
│  BLE设备1      │          │  BLE设备N        │
│  (温度传感器)   │   ...    │  (智能锁)        │
│  广播UUID:0xfe95│          │  广播UUID:0xfe95 │
└────────────────┘          └──────────────────┘
```

### 数据流示例

#### 1. 子设备状态上报流程

```
BLE设备广播
  → MI32驱动解析
  → Berry: DeviceManager.on_ble_adv()
  → 提取状态(温度/电量等)
  → AWSDeviceShadow.update_reported({devices: {...}})
  → MQTT发布到 $aws/things/gateway-001/shadow/update
  → AWS IoT更新Shadow
```

#### 2. 云端指令下发流程

```
AWS控制台/App更新Shadow desired
  → AWS IoT推送delta消息到 $aws/things/gateway-001/shadow/update/delta
  → Berry: AWSDeviceShadow.handle_delta()
  → 提取命令(device_mac + command)
  → CommandQueue.enqueue()
  → BLE.connect(device_mac)
  → BLE.write(gatt_handle, command_data)
  → 等待响应
  → 更新reported状态确认执行
```

---

## 实施任务清单

### Phase 1: AWS IoT通信基础 (优先级: P0)

#### Task 1.1: 设计BLE网关与AWS IoT通信架构
- **输出**: 系统架构图 (已完成，见上节)
- **决策**:
  - Shadow结构: 单一Classic Shadow,包含gateway信息和devices字典
  - 主题设计: Shadow主题 + 2个自定义主题
  - 认证方式: X.509证书 (设备证书 + 私钥 + AWS根CA)

#### Task 1.2: 实现Berry版AWS Device Shadow客户端
- **文件**: `lib/aws_shadow.be`
- **功能**:
  - 初始化时订阅Shadow相关主题
  - 提供`update_reported(state_dict)`方法
  - 提供`get_shadow()`方法
  - 提供`handle_delta(callback)`注册回调
- **代码框架**:
```berry
class AWSDeviceShadow : Driver
    var thing_name
    var shadow_topics
    var delta_callback
    var version

    def init(thing_name)
        self.thing_name = thing_name
        self.version = 0
        self.delta_callback = nil
        self.shadow_topics = {
            'update': '$aws/things/' + thing_name + '/shadow/update',
            'get': '$aws/things/' + thing_name + '/shadow/get',
            'update_accepted': '$aws/things/' + thing_name + '/shadow/update/accepted',
            'update_rejected': '$aws/things/' + thing_name + '/shadow/update/rejected',
            'delta': '$aws/things/' + thing_name + '/shadow/update/delta'
        }
    end

    def subscribe_all()
        # 订阅所有Shadow主题
    end

    def update_reported(state)
        # 构造Shadow update消息并发布
    end

    def mqtt_data(topic, idx, data, data_len)
        # 处理接收到的Shadow消息
        if string.find(topic, '/delta') > 0
            # 触发delta回调
        end
    end
end
```

#### Task 1.3: 实现Shadow主题订阅和消息路由
- **功能**:
  - 在WiFi连接成功后自动订阅Shadow主题
  - 路由MQTT消息到对应的处理函数
  - 处理订阅确认和失败情况
- **依赖**: Tasmota内置MQTT客户端
- **测试**: 使用MQTT客户端工具验证订阅成功

#### Task 1.4: 实现网关reported状态上报功能
- **上报内容**:
  - 网关基本信息: `{online, uptime, heap_free, wifi_rssi}`
  - 设备列表: `{devices: {mac: {last_seen, battery, status}}}`
- **上报频率**:
  - 周期性: 每60秒
  - 事件触发: 设备新发现/状态变化时
- **测试**: AWS IoT控制台查看Shadow状态

#### Task 1.5: 实现delta处理(云端desired->本地指令)
- **功能**:
  - 解析delta消息中的commands字段
  - 提取目标设备MAC和命令内容
  - 调用DeviceManager.send_command()
- **错误处理**:
  - 设备不存在: 上报错误状态
  - 设备离线: 加入命令队列
  - 命令格式错误: 拒绝并上报
- **测试**: AWS控制台更新desired，观察日志

---

### Phase 2: 子设备管理 (优先级: P0)

#### Task 2.1: 实现子设备注册和管理机制
- **文件**: `lib/device_manager.be`
- **数据结构**:
```berry
{
    "AA:BB:CC:DD:EE:FF": {
        "mac": "AA:BB:CC:DD:EE:FF",
        "name": "温度传感器-客厅",
        "type": "temperature_sensor",  # 或 smart_lock / vibration_sensor
        "protocol": "mi32",  # Xiaomi协议
        "last_seen": 1234567890,  # 毫秒时间戳
        "rssi": -65,
        "battery": 85,
        "state": {
            "temperature": 25.3,
            "humidity": 60
        },
        "gatt": {
            "service_uuid": "0000fe95...",
            "write_char_uuid": "0000..."
        }
    }
}
```
- **功能**:
  - `register_device(mac, device_info)`: 注册新设备
  - `get_device(mac)`: 获取设备信息
  - `update_device_state(mac, state)`: 更新设备状态
  - `get_all_devices()`: 获取所有设备列表
  - 持久化到文件: `devices.json`

#### Task 2.2: 实现BLE广播监听和设备发现
- **依赖**: MI32驱动已有的BLE扫描功能
- **实现方式**: 注册Berry回调到MI32驱动
- **代码示例**:
```berry
class DeviceManager : Driver
    var devices

    def init()
        self.devices = {}
        self.load_devices()
        # 注册MI32广播回调
        tasmota.add_rule("MI32#ADV", /value -> self.on_ble_adv(value))
    end

    def on_ble_adv(adv_data)
        import MI32
        var device = MI32.get_latest_adv()  # 获取最新广播包
        var mac = device['mac']

        if !self.devices.contains(mac)
            # 新设备,自动注册
            self.register_device(mac, device)
        else
            # 已知设备,更新状态
            self.update_device_state(mac, device['state'])
        end
    end
end
```
- **支持的BLE协议**: 使用Tasmota MI32已支持的协议(UUID: 0xfe95)
- **测试**: 放置测试设备,观察日志中的自动发现

#### Task 2.3: 实现子设备状态通过网关Shadow上报到AWS
- **集成点**: `DeviceManager.update_device_state()` → `AWSDeviceShadow.update_reported()`
- **上报格式**:
```json
{
    "state": {
        "reported": {
            "gateway": {
                "online": true,
                "uptime": 3600
            },
            "devices": {
                "AA:BB:CC:DD:EE:FF": {
                    "type": "temperature_sensor",
                    "last_seen": 1234567890,
                    "rssi": -65,
                    "battery": 85,
                    "temperature": 25.3,
                    "humidity": 60
                }
            }
        }
    }
}
```
- **优化**: 批量上报(每10秒合并一次)避免频繁MQTT发布
- **测试**: 多个设备同时广播,验证状态正确上报

---

### Phase 3: 命令下发机制 (优先级: P1)

#### Task 3.1: 实现命令缓存队列(用于设备离线时)
- **文件**: `lib/command_queue.be`
- **数据结构**:
```berry
[
    {
        "device_mac": "AA:BB:CC:DD:EE:FF",
        "command": "lock",
        "params": {"mode": 1},
        "timestamp": 1234567890,
        "retries": 0,
        "max_retries": 3
    }
]
```
- **功能**:
  - `enqueue(device_mac, command, params)`: 添加命令
  - `get_pending_commands(device_mac)`: 获取设备待处理命令
  - `mark_completed(device_mac, command)`: 标记完成
  - `mark_failed(device_mac, command)`: 标记失败
  - 持久化到文件: `cmd_queue.json`
  - 超时清理: 24小时未执行的命令自动删除
- **测试**: 设备离线时下发命令,设备上线后验证执行

#### Task 3.2: C++扩展 - 添加MI32主动GATT连接接口
- **文件**: `tasmota/tasmota_xsns_sensor/xsns_62_esp32_mi.ino`
- **新增函数**:
```cpp
/**
 * @brief 主动连接BLE设备
 * @param mac 6字节MAC地址
 * @param timeout_ms 连接超时(毫秒)
 * @return NimBLEClient* 连接成功返回客户端指针,失败返回nullptr
 */
NimBLEClient* MI32_ConnectDevice(uint8_t mac[6], uint32_t timeout_ms) {
    NimBLEAddress addr(mac);
    NimBLEClient *pClient = NimBLEDevice::createClient();

    if (!pClient) {
        AddLog(LOG_LEVEL_ERROR, "MI32: Failed to create client");
        return nullptr;
    }

    // 设置连接参数
    pClient->setConnectTimeout(timeout_ms / 1000);

    // 尝试连接
    if (!pClient->connect(addr, false)) {
        AddLog(LOG_LEVEL_ERROR, "MI32: Failed to connect to %s", addr.toString().c_str());
        NimBLEDevice::deleteClient(pClient);
        return nullptr;
    }

    AddLog(LOG_LEVEL_INFO, "MI32: Connected to %s", addr.toString().c_str());
    return pClient;
}

/**
 * @brief 断开并释放BLE连接
 */
void MI32_DisconnectDevice(NimBLEClient *pClient) {
    if (pClient) {
        pClient->disconnect();
        NimBLEDevice::deleteClient(pClient);
    }
}
```

#### Task 3.3: C++扩展 - 导出Berry可调用的BLE.connect()和BLE.write()接口
- **新增Berry原生模块**:
```cpp
extern "C" {
    #include "be_constobj.h"

    // BLE.connect(mac_string, timeout_ms) -> bool
    static int32_t be_ble_connect(bvm *vm) {
        const char *mac_str = be_tostring(vm, 1);
        int32_t timeout_ms = be_toint(vm, 2);

        uint8_t mac[6];
        if (sscanf(mac_str, "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx",
                   &mac[0], &mac[1], &mac[2], &mac[3], &mac[4], &mac[5]) != 6) {
            be_raise(vm, "value_error", "Invalid MAC address format");
        }

        NimBLEClient *client = MI32_ConnectDevice(mac, timeout_ms);
        be_pushbool(vm, client != nullptr);
        be_return(vm);
    }

    // BLE.write(mac_string, service_uuid, char_uuid, data_bytes) -> bool
    static int32_t be_ble_write(bvm *vm) {
        const char *mac_str = be_tostring(vm, 1);
        const char *service_uuid = be_tostring(vm, 2);
        const char *char_uuid = be_tostring(vm, 3);

        // 获取data参数(bytes类型)
        be_getmember(vm, 4, ".p");
        const uint8_t *data = (const uint8_t*)be_tocomptr(vm, -1);
        int32_t data_len = be_strlen(vm, 4);

        // 实现GATT写入逻辑
        bool success = MI32_WriteGATT(mac_str, service_uuid, char_uuid, data, data_len);
        be_pushbool(vm, success);
        be_return(vm);
    }

    // BLE.disconnect(mac_string)
    static int32_t be_ble_disconnect(bvm *vm) {
        const char *mac_str = be_tostring(vm, 1);
        MI32_DisconnectByMAC(mac_str);
        be_return_nil(vm);
    }
}

// 注册到Berry模块
be_native_module_attr_table(ble) {
    be_native_module_function("connect", be_ble_connect),
    be_native_module_function("write", be_ble_write),
    be_native_module_function("disconnect", be_ble_disconnect)
};
be_define_native_module(ble, NULL);
```

#### Task 3.4: 实现指令下发流程(AWS delta -> 队列 -> BLE GATT写入)
- **集成流程**:
```berry
# 在AWSDeviceShadow.handle_delta()中
def handle_delta(delta_state)
    if delta_state.contains('commands')
        var commands = delta_state['commands']
        for device_mac : commands.keys()
            var cmd = commands[device_mac]

            # 检查设备是否在线
            var device = self.device_mgr.get_device(device_mac)
            if device == nil
                print("Device not found:", device_mac)
                continue
            end

            # 检查设备最后见到时间
            var now = tasmota.millis()
            var offline_threshold = 60000  # 60秒
            if now - device['last_seen'] > offline_threshold
                # 设备离线,加入队列
                print("Device offline, enqueue command:", device_mac)
                self.cmd_queue.enqueue(device_mac, cmd)
            else
                # 设备在线,立即发送
                print("Device online, send command:", device_mac)
                self.send_command_now(device_mac, cmd, device)
            end
        end
    end
end

def send_command_now(device_mac, command, device_info)
    import BLE

    # 1. 建立GATT连接
    var connected = BLE.connect(device_mac, 5000)  # 5秒超时
    if !connected
        print("Failed to connect:", device_mac)
        self.cmd_queue.enqueue(device_mac, command)  # 失败则加入队列
        return
    end

    # 2. 写入命令数据
    var cmd_data = self.encode_command(command, device_info['type'])
    var success = BLE.write(
        device_mac,
        device_info['gatt']['service_uuid'],
        device_info['gatt']['write_char_uuid'],
        cmd_data
    )

    # 3. 断开连接
    BLE.disconnect(device_mac)

    # 4. 更新Shadow确认执行
    if success
        var reported = {
            'devices': {
                device_mac: {
                    'last_command': command,
                    'last_command_time': tasmota.rtc()['local'],
                    'last_command_status': 'success'
                }
            }
        }
        self.shadow.update_reported(reported)
    else
        print("Failed to write command:", device_mac)
    end
end
```
- **测试**: AWS控制台更新desired,观察BLE连接日志和设备响应

---

### Phase 4: 心跳和监控 (优先级: P2)

#### Task 4.1: 实现双心跳机制(Shadow + 自定义topic)
- **文件**: `lib/dual_heartbeat.be`
- **功能**:
  - **Shadow心跳**: 每60秒更新`reported.gateway.last_heartbeat`
  - **自定义心跳**: 每30秒发布到`gateways/{gateway_id}/heartbeat`
- **心跳内容**:
```json
{
    "timestamp": 1234567890,
    "gateway_id": "ble-gateway-001",
    "status": "online",
    "uptime": 3600,
    "wifi_rssi": -65,
    "connected_devices": 5,
    "heap_free": 123456
}
```
- **实现**:
```berry
class DualHeartbeat : Driver
    var thing_name
    var shadow
    var last_shadow_hb
    var last_custom_hb

    def every_second()
        var now = tasmota.millis()

        # Shadow心跳 (60秒)
        if now - self.last_shadow_hb > 60000
            self.shadow.update_reported({
                'gateway': {
                    'last_heartbeat': tasmota.rtc()['local'],
                    'uptime': tasmota.cmd("Status")['StatusPRM']['Uptime']
                }
            })
            self.last_shadow_hb = now
        end

        # 自定义心跳 (30秒)
        if now - self.last_custom_hb > 30000
            var hb = {
                'timestamp': tasmota.rtc()['local'],
                'gateway_id': self.thing_name,
                'status': 'online',
                'heap_free': tasmota.cmd("Status")['StatusMEM']['Heap']
            }
            tasmota.publish('gateways/' + self.thing_name + '/heartbeat', json.dump(hb), false)
            self.last_custom_hb = now
        end
    end
end
```

---

### Phase 5: 配置和部署 (优先级: P1)

#### Task 5.1: 配置AWS IoT证书和Tasmota MQTT TLS参数
- **AWS IoT准备**:
  1. 创建Thing: `ble-gateway-001`
  2. 创建证书并下载:
     - `gateway-001-certificate.pem.crt`
     - `gateway-001-private.pem.key`
     - `AmazonRootCA1.pem`
  3. 附加策略:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iot:Connect",
        "iot:Publish",
        "iot:Subscribe",
        "iot:Receive"
      ],
      "Resource": [
        "arn:aws:iot:us-east-1:123456789012:client/ble-gateway-001",
        "arn:aws:iot:us-east-1:123456789012:topic/$aws/things/ble-gateway-001/*",
        "arn:aws:iot:us-east-1:123456789012:topic/gateways/ble-gateway-001/*",
        "arn:aws:iot:us-east-1:123456789012:topicfilter/$aws/things/ble-gateway-001/*"
      ]
    }
  ]
}
```

- **Tasmota配置 (通过Web控制台或命令行)**:
```
# 1. MQTT基本配置
MqttHost <your-aws-iot-endpoint>.iot.us-east-1.amazonaws.com
MqttPort 8883
MqttClient ble-gateway-001
MqttUser (留空)
MqttPassword (留空)

# 2. 启用TLS
SetOption103 1

# 3. 上传证书到LittleFS
# 方法1: 使用Web界面上传
#   - 访问 http://<tasmota-ip>/uf
#   - 上传: /aws_cert.pem, /aws_key.pem, /aws_ca.pem
# 方法2: 使用Berry脚本转换为base64并写入

# 4. 配置TLS证书路径 (在Berry中)
import mqtt
mqtt.tlsconfig("/aws_cert.pem", "/aws_key.pem", "/aws_ca.pem")
```

- **验证连接**:
```berry
# 在Berry控制台执行
tasmota.cmd("MqttHost")  # 查看配置
tasmota.cmd("Status 6")  # 查看MQTT状态
```

---

### Phase 6: 集成测试 (优先级: P0)

#### Task 6.1: 集成测试 - 网关连接AWS IoT Core
- **测试步骤**:
  1. 烧录固件,上传Berry脚本和证书
  2. 配置WiFi和MQTT参数
  3. 重启设备
  4. 观察串口日志: `MQTT: Connected to AWS IoT`
  5. AWS IoT控制台查看连接状态
- **预期结果**: 设备在控制台显示为已连接
- **调试**: 使用`MqttLog 4`启用详细日志

#### Task 6.2: 集成测试 - 子设备广播发现和注册
- **测试步骤**:
  1. 放置BLE测试设备(如小米温湿度计)在网关附近
  2. 观察串口日志: `DeviceManager: New device discovered: AA:BB:CC:DD:EE:FF`
  3. 查看`devices.json`文件内容
  4. AWS Shadow中查看`reported.devices`字段
- **预期结果**: 设备自动发现并注册,状态上报到云端

#### Task 6.3: 集成测试 - 子设备状态上报到Shadow
- **测试步骤**:
  1. 等待设备广播(通常1-10秒间隔)
  2. 观察日志: `DeviceManager: Device state updated`
  3. AWS Shadow查看`reported.devices.{mac}.temperature`等字段
  4. 修改设备状态(如改变温度),验证更新
- **预期结果**: 状态实时同步到Shadow

#### Task 6.4: 集成测试 - AWS下发指令到子设备
- **测试步骤**:
  1. AWS IoT控制台打开Shadow
  2. 编辑`desired`字段:
```json
{
  "commands": {
    "AA:BB:CC:DD:EE:FF": "lock"
  }
}
```
  3. 观察串口日志:
     - `AWSDeviceShadow: Delta received`
     - `BLE: Connecting to AA:BB:CC:DD:EE:FF`
     - `BLE: Command sent successfully`
  4. 设备执行动作(如智能锁上锁)
  5. 查看Shadow `reported.devices.{mac}.last_command_status`
- **预期结果**: 指令成功下发并执行

#### Task 6.5: 集成测试 - 设备离线时命令缓存和重发
- **测试步骤**:
  1. 关闭测试设备(或移出范围)
  2. AWS下发指令
  3. 观察日志: `CommandQueue: Device offline, enqueued command`
  4. 查看`cmd_queue.json`文件
  5. 打开设备(或移回范围)
  6. 等待设备广播
  7. 观察日志: `CommandQueue: Sending cached command`
- **预期结果**: 设备上线后自动执行缓存的命令

---

### Phase 7: 文档和交付 (优先级: P2)

#### Task 7.1: 编写项目实施文档和代码注释
- **文档内容**:
  - 架构设计图
  - 部署指南 (证书配置、Berry脚本安装)
  - API文档 (Berry类接口说明)
  - 故障排查指南
  - 扩展新设备类型的教程
- **代码注释**: 每个类和关键函数添加注释

---

## 实施时间线

| Phase | 任务数 | 预计工时 | 依赖关系 |
|-------|-------|---------|---------|
| Phase 1 | 5 | 16小时 | 无 |
| Phase 2 | 3 | 12小时 | Phase 1完成 |
| Phase 3 | 4 | 20小时 | Phase 1+2完成,需C++开发 |
| Phase 4 | 1 | 4小时 | Phase 1完成 |
| Phase 5 | 1 | 4小时 | Phase 1完成 |
| Phase 6 | 5 | 8小时 | Phase 1-5完成 |
| Phase 7 | 1 | 4小时 | 全部完成 |
| **总计** | **20** | **68小时** | **约9个工作日** |

---

## 关键技术点

### 1. Shadow数据结构设计

采用**单一Classic Shadow**包含网关和所有子设备状态:

```json
{
  "state": {
    "reported": {
      "gateway": {
        "online": true,
        "last_heartbeat": 1234567890,
        "uptime": "3h 25m",
        "wifi_rssi": -65,
        "heap_free": 123456,
        "version": "1.0.0"
      },
      "devices": {
        "AA:BB:CC:DD:EE:FF": {
          "name": "温度传感器-客厅",
          "type": "temperature_sensor",
          "protocol": "mi32",
          "last_seen": 1234567890,
          "rssi": -60,
          "battery": 85,
          "temperature": 25.3,
          "humidity": 60,
          "last_command": null,
          "last_command_time": null,
          "last_command_status": null
        },
        "11:22:33:44:55:66": {
          "name": "智能锁-前门",
          "type": "smart_lock",
          "protocol": "mi32",
          "last_seen": 1234567880,
          "rssi": -55,
          "battery": 90,
          "lock_state": "locked",
          "last_command": "lock",
          "last_command_time": 1234567875,
          "last_command_status": "success"
        }
      }
    },
    "desired": {
      "commands": {
        "11:22:33:44:55:66": "unlock"
      }
    }
  }
}
```

### 2. BLE协议支持

使用Tasmota MI32驱动已支持的协议:
- **Xiaomi MI协议** (UUID: 0xfe95) - 大部分小米生态设备
- **BTHome V2** (UUID: 0xfcd2) - 通用BLE传感器协议

如需支持其他协议,可在Berry层解析原始广播包:
```berry
def on_ble_adv(adv_data)
    import MI32
    var raw = MI32.get_raw_adv()  # 获取原始广播数据
    # 自定义解析逻辑
end
```

### 3. GATT连接策略

**串行连接,用后即断**:
```berry
def send_command_now(device_mac, command, device_info)
    import BLE

    # 连接
    BLE.connect(device_mac, 5000)

    # 写入
    BLE.write(device_mac, service_uuid, char_uuid, data)

    # 立即断开,释放资源
    BLE.disconnect(device_mac)
end
```

优点:
- 简化连接管理逻辑
- 避免并发冲突
- 减少功耗和内存占用

### 4. 命令队列持久化

使用LittleFS文件系统确保断电不丢失:
```berry
class CommandQueue
    static QUEUE_FILE = "/cmd_queue.json"

    def save()
        var f = open(self.QUEUE_FILE + ".tmp", "w")
        f.write(json.dump(self.queue))
        f.close()
        # 原子重命名避免写入中断导致损坏
        import path
        path.remove(self.QUEUE_FILE)
        path.rename(self.QUEUE_FILE + ".tmp", self.QUEUE_FILE)
    end
end
```

### 5. Berry性能优化

- **批量上报**: 10秒内的多个状态变更合并为一次Shadow更新
- **缓存MAC映射**: 避免重复字符串解析
- **避免频繁JSON序列化**: 缓存不变的部分

---

## 风险和缓解措施

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| Berry脚本性能不足 | 高延迟 | 关键路径用C++实现,Berry只做业务逻辑 |
| NimBLE连接不稳定 | 指令下发失败 | 实现重试机制,最多3次 |
| Shadow更新频率限制 | 消息丢失 | 批量上报,降低频率到10秒/次 |
| 内存不足 | 设备崩溃 | 限制最大设备数50个,命令队列100条 |
| 证书配置复杂 | 部署困难 | 提供自动化配置脚本 |

---

## 扩展性设计

### 支持新设备类型

在`lib/device_types/`下添加新设备类:
```berry
# lib/device_types/smart_plug.be
class SmartPlug : BLEDevice
    def parse_adv(raw_data)
        # 解析广播包
        return {
            'power_state': raw_data[10] & 0x01,
            'current': (raw_data[11] << 8 | raw_data[12]) / 100.0
        }
    end

    def encode_command(command)
        # 编码控制命令
        if command == 'on'
            return bytes('01', 16)
        elif command == 'off'
            return bytes('00', 16)
        end
    end
end

# 在device_manager.be中注册
device_types['smart_plug'] = SmartPlug
```

### 支持Named Shadow

修改`AWSDeviceShadow`类支持为每个子设备创建独立Shadow:
```berry
def update_device_shadow(device_mac, state)
    var shadow_name = "device_" + device_mac.replace(":", "")
    var topic = "$aws/things/" + self.thing_name + "/shadow/name/" + shadow_name + "/update"
    var payload = {"state": {"reported": state}}
    tasmota.publish(topic, json.dump(payload), false)
end
```

---

## 附录

### A. 所需文件列表

```
/
├── autoexec.be                 # 启动脚本
├── lib/
│   ├── aws_shadow.be           # AWS Shadow客户端
│   ├── device_manager.be       # 设备管理器
│   ├── command_queue.be        # 命令队列
│   ├── dual_heartbeat.be       # 双心跳
│   └── device_types/           # 设备类型定义
│       ├── temperature_sensor.be
│       ├── smart_lock.be
│       └── vibration_sensor.be
├── data/
│   ├── devices.json            # 设备注册信息
│   └── cmd_queue.json          # 命令队列持久化
└── certs/
    ├── aws_cert.pem            # AWS设备证书
    ├── aws_key.pem             # 设备私钥
    └── aws_ca.pem              # AWS根CA证书
```

### B. Tasmota命令速查

```
# MQTT相关
MqttHost <endpoint>           # 设置MQTT服务器
MqttPort 8883                 # 设置MQTT端口
MqttClient <client_id>        # 设置客户端ID
SetOption103 1                # 启用TLS

# Berry相关
BrRun <file>                  # 运行Berry脚本
BrLoad <file>                 # 加载Berry脚本(持久)
BrList                        # 列出已加载的脚本

# MI32相关
MI32Option6 1                 # 启用Berry回调
MI32Period <seconds>          # 设置扫描间隔

# 日志相关
MqttLog 4                     # MQTT详细日志
SerialLog 4                   # 串口详细日志
WebLog 4                      # Web详细日志
```

### C. 参考资源

- [Tasmota Berry文档](https://tasmota.github.io/docs/Berry/)
- [AWS IoT Device Shadow](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html)
- [NimBLE API文档](https://h2zero.github.io/esp-nimble-cpp/)
- [MI32驱动源码](https://github.com/arendst/Tasmota/blob/development/tasmota/tasmota_xsns_sensor/xsns_62_esp32_mi.ino)

---

**文档版本**: v1.0
**创建日期**: 2025-01-XX
**最后更新**: 2025-01-XX
**维护者**: [Your Name]
