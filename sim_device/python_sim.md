test_new_devices.py:
```
#!/usr/bin/env python3
"""
测试震动传感器和捕鼠器 - 简化版

使用线程而非进程，参考 test_complete.py 的架构
"""

import time
import json
import threading
from gateway_mqtt import MQTTGateway
from device import VibrationSensor, MouseTrap
from config import *


def device_thread_runner(device_instance):
    """在线程中运行设备"""
    device_instance.run(telemetry_interval=10, duration=600)


def main():
    print(f"{'='*70}")
    print("测试震动传感器和捕鼠器设备 (简化版)")
    print(f"网关: {THING_NAME}")
    print(f"{'='*70}\n")

    # 从配置中找到震动传感器和捕鼠器
    vibration_device = next((d for d in DEVICES if d['type'] == 'vibration_sensor'), None)
    mousetrap_device = next((d for d in DEVICES if d['type'] == 'mouse_trap'), None)

    if not vibration_device or not mousetrap_device:
        print("❌ 错误: 在 config.py 中未找到震动传感器或捕鼠器配置")
        return

    print(f"📱 震动传感器:")
    print(f"   Device ID: {vibration_device['device_id']}")
    print(f"   Shadow Name: {vibration_device['shadow_name']}")

    print(f"\n🐭 捕鼠器:")
    print(f"   Device ID: {mousetrap_device['device_id']}")
    print(f"   Shadow Name: {mousetrap_device['shadow_name']}")
    print()

    # 1. 初始化网关
    print("📡 步骤1: 初始化网关 (MQTT 连接)\n")

    try:
        gateway = MQTTGateway(
            thing_name=THING_NAME,
            endpoint=IOT_ENDPOINT,
            cert_path=CERT_FILE,
            key_path=KEY_FILE,
            ca_path=ROOT_CA_FILE
        )
    except FileNotFoundError as e:
        print(f"\n❌ 错误: 证书文件未找到!")
        print(f"错误详情: {e}\n")
        return

    print(f"✅ 网关已连接到 AWS IoT Core\n")

    # 2. 注册设备
    print("📱 步骤2: 注册设备到网关\n")

    gateway.register_device(
        device_id=vibration_device['device_id'],
        shadow_name=vibration_device['shadow_name']
    )
    print(f"✅ 震动传感器已注册: {vibration_device['shadow_name']}")

    gateway.register_device(
        device_id=mousetrap_device['device_id'],
        shadow_name=mousetrap_device['shadow_name']
    )
    print(f"✅ 捕鼠器已注册: {mousetrap_device['shadow_name']}\n")

    # 3. 创建设备实例
    print("🚀 步骤3: 创建设备实例\n")

    vibration_sensor = VibrationSensor(
        device_id=vibration_device['device_id'],
        ble_channel=gateway.ble_hub.channels[vibration_device['device_id']]
    )

    mouse_trap = MouseTrap(
        device_id=mousetrap_device['device_id'],
        ble_channel=gateway.ble_hub.channels[mousetrap_device['device_id']]
    )

    print(f"✅ 设备实例已创建\n")

    # 4. 启动设备线程
    print("🔄 步骤4: 启动设备线程\n")

    vibration_thread = threading.Thread(
        target=device_thread_runner,
        args=(vibration_sensor,),
        daemon=True
    )

    mousetrap_thread = threading.Thread(
        target=device_thread_runner,
        args=(mouse_trap,),
        daemon=True
    )

    vibration_thread.start()
    mousetrap_thread.start()

    print(f"✅ 震动传感器线程已启动")
    print(f"✅ 捕鼠器线程已启动\n")

    # 5. 启动网关主循环
    print(f"{'='*70}")
    print(f"🚀 网关和设备已启动！")
    print(f"{'='*70}\n")
    print(f"提示：")
    print(f"1. 打开用户端: http://localhost:5173/")
    print(f"2. 登录并进入设备列表")
    print(f"3. 找到设备: 震动检测传感器-001 和 智能捕鼠器-001")
    print(f"4. 查看实时遥测数据（每10秒更新）")
    print(f"5. 点击\"控制设备\"发送命令测试")
    print(f"\n震动传感器控制命令示例:")
    print(f'  {{"action": "set_threshold", "vibration_threshold": 3.0, "sensitivity": "medium"}}')
    print(f'  {{"action": "reset_counter"}}')
    print(f"\n捕鼠器控制命令示例:")
    print(f'  {{"action": "reset_trap"}}')
    print(f'  {{"action": "set_schedule", "work_schedule": {{"enabled": true, "start_time": "20:00", "end_time": "09:00"}}, "sensitivity": "high"}}')
    print(f'  {{"action": "refill_bait"}}')
    print(f"\n按 Ctrl+C 停止所有设备\n")

    try:
        while True:
            # 从 BLE Hub 采集设备遥测数据
            gateway.collect_device_telemetry()
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n\n⏹️  收到停止信号，关闭所有设备...\n")

        # 停止网关
        gateway.stop()

        print(f"👋 所有设备已停止\n")


if __name__ == "__main__":
    main()

```

gateway_mqtt.py:
```
#!/usr/bin/env python3
"""
真实 MQTT 网关模拟器

使用 AWS IoT SDK 和设备证书，通过 MQTT 协议连接 AWS IoT Core
"""

import json
import time
import threading
from typing import Dict, Callable
from awscrt import mqtt
from awsiot import mqtt_connection_builder
from ble_protocol import BLEHub, BLEMessage, BLEChannel


class MQTTGateway:
    """真实 MQTT 网关"""

    def __init__(
        self,
        thing_name: str,
        endpoint: str,
        cert_path: str,
        key_path: str,
        ca_path: str
    ):
        self.thing_name = thing_name
        self.endpoint = endpoint

        # BLE 设备管理
        self.ble_hub = BLEHub()
        self.device_mappings: Dict[str, str] = {}  # device_id -> shadow_name

        # MQTT 连接
        self.mqtt_connection = None
        self.connected = False
        self.running = False

        # Delta 回调
        self.delta_callbacks: Dict[str, Callable] = {}

        print(f"[GATEWAY] Initializing: {thing_name}")
        print(f"[GATEWAY] Endpoint: {endpoint}")
        print(f"[GATEWAY] Cert: {cert_path}")

        # 建立 MQTT 连接
        self._connect(cert_path, key_path, ca_path)

    def _connect(self, cert_path: str, key_path: str, ca_path: str):
        """建立 MQTT 连接"""
        print(f"[MQTT] Connecting to {self.endpoint}...")

        self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=self.endpoint,
            cert_filepath=cert_path,
            pri_key_filepath=key_path,
            ca_filepath=ca_path,
            client_id=self.thing_name,
            clean_session=False,
            keep_alive_secs=30,
            on_connection_interrupted=self._on_connection_interrupted,
            on_connection_resumed=self._on_connection_resumed
        )

        # 同步连接
        connect_future = self.mqtt_connection.connect()
        connect_future.result()

        self.connected = True
        print(f"[MQTT] ✅ Connected to AWS IoT Core")

    def _on_connection_interrupted(self, connection, error, **kwargs):
        """连接中断回调"""
        print(f"[MQTT] ⚠️ Connection interrupted: {error}")
        self.connected = False

    def _on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """连接恢复回调"""
        print(f"[MQTT] ✅ Connection resumed (return_code={return_code})")
        self.connected = True

        # 重新订阅所有 Delta
        for device_id, shadow_name in self.device_mappings.items():
            self._subscribe_delta(shadow_name)

    def register_device(self, device_id: str, shadow_name: str) -> BLEChannel:
        """注册一个子设备"""
        self.device_mappings[device_id] = shadow_name
        channel = self.ble_hub.register_device(device_id)

        # 订阅该子设备的 Shadow Delta
        self._subscribe_delta(shadow_name)

        # 发送 GET 请求获取当前 Shadow 状态（用于上线补偿）
        self._shadow_get(shadow_name)

        print(f"[GATEWAY] Registered device: {device_id} -> shadow: {shadow_name}")
        return channel

    def _subscribe_delta(self, shadow_name: str):
        """订阅 Named Shadow Delta 主题"""
        topic = f"$aws/things/{self.thing_name}/shadow/name/{shadow_name}/update/delta"

        print(f"[MQTT] Subscribing to: {topic}")

        subscribe_future, packet_id = self.mqtt_connection.subscribe(
            topic=topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=lambda topic, payload, **kwargs: self._on_delta(shadow_name, topic, payload)
        )

        # 等待订阅确认
        subscribe_future.result()
        print(f"[MQTT] ✅ Subscribed to delta for shadow: {shadow_name}")

    def _shadow_get(self, shadow_name: str):
        """获取 Named Shadow 当前状态（上线补偿）"""
        topic = f"$aws/things/{self.thing_name}/shadow/name/{shadow_name}/get"

        # 先订阅 get/accepted
        accepted_topic = f"$aws/things/{self.thing_name}/shadow/name/{shadow_name}/get/accepted"
        subscribe_future, _ = self.mqtt_connection.subscribe(
            topic=accepted_topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=lambda topic, payload, **kwargs: self._on_shadow_get_accepted(shadow_name, payload)
        )
        subscribe_future.result()

        # 发送 GET 请求
        print(f"[MQTT] Getting shadow state: {shadow_name}")
        publish_future, packet_id = self.mqtt_connection.publish(
            topic=topic,
            payload='',
            qos=mqtt.QoS.AT_LEAST_ONCE
        )
        publish_future.result()

    def _on_shadow_get_accepted(self, shadow_name: str, payload: bytes):
        """处理 Shadow GET 响应"""
        shadow = json.loads(payload.decode('utf-8'))
        desired = shadow.get('state', {}).get('desired', {})
        reported = shadow.get('state', {}).get('reported', {})

        # 检查是否有待执行的命令
        desired_req_id = desired.get('reqId')
        reported_req_id = reported.get('lastAckedReqId')

        if desired_req_id and desired_req_id != reported_req_id:
            print(f"[GATEWAY] Found pending command in shadow {shadow_name}")
            # 模拟 Delta（触发命令执行）
            delta = {
                'state': {
                    'cmd': desired.get('cmd'),
                    'reqId': desired_req_id
                }
            }
            self._process_command(shadow_name, delta)

    def _on_delta(self, shadow_name: str, topic: str, payload: bytes):
        """处理 Shadow Delta（命令下发）"""
        delta = json.loads(payload.decode('utf-8'))

        print(f"[DELTA] Shadow: {shadow_name}")
        print(f"[DELTA] Payload: {delta}")

        self._process_command(shadow_name, delta)

    def _process_command(self, shadow_name: str, delta: dict):
        """处理命令"""
        # 找到对应的设备
        device_id = None
        for dev_id, sh_name in self.device_mappings.items():
            if sh_name == shadow_name:
                device_id = dev_id
                break

        if not device_id:
            print(f"[GATEWAY] Unknown shadow: {shadow_name}")
            return

        # 提取命令
        cmd = delta.get('state', {}).get('cmd', {})
        req_id = delta.get('state', {}).get('reqId')

        if not req_id:
            print(f"[GATEWAY] No reqId in delta, skipping")
            return

        print(f"[GATEWAY] New command for {device_id}: {cmd} (reqId={req_id})")

        # 通过 BLE 转发命令到子设备
        message = BLEMessage(
            device_id=device_id,
            message_type='command',
            payload={
                'reqId': req_id,
                'command': cmd
            }
        )

        self.ble_hub.send_to_device(device_id, message)

    def update_shadow_reported(self, shadow_name: str, reported: dict):
        """更新 Named Shadow Reported 状态"""
        topic = f"$aws/things/{self.thing_name}/shadow/name/{shadow_name}/update"

        payload = {
            "state": {
                "reported": reported
            }
        }

        payload_json = json.dumps(payload)

        print(f"[MQTT] Publishing to {topic}")
        print(f"[MQTT] Payload: {payload_json}")

        publish_future, packet_id = self.mqtt_connection.publish(
            topic=topic,
            payload=payload_json,
            qos=mqtt.QoS.AT_LEAST_ONCE
        )

        # 等待发布确认
        publish_future.result()
        print(f"[MQTT] ✅ Published shadow update for: {shadow_name}")

    def collect_device_telemetry(self):
        """收集子设备上报的遥测数据"""
        while True:
            msg = self.ble_hub.receive_from_any(timeout=0.1)
            if not msg:
                break

            device_id = msg.device_id
            shadow_name = self.device_mappings.get(device_id)

            if not shadow_name:
                print(f"[GATEWAY] Unknown device: {device_id}")
                continue

            if msg.message_type == 'telemetry':
                # 上报遥测数据到 Shadow Reported
                print(f"[GATEWAY] Telemetry from {device_id}: {msg.payload}")
                self.update_shadow_reported(shadow_name, msg.payload)

            elif msg.message_type == 'ack':
                # 命令执行确认
                print(f"[GATEWAY] Command ACK from {device_id}: {msg.payload}")
                self.update_shadow_reported(shadow_name, msg.payload)

            elif msg.message_type == 'error':
                # 命令执行失败
                print(f"[GATEWAY] Command ERROR from {device_id}: {msg.payload}")
                self.update_shadow_reported(shadow_name, msg.payload)

    def run(self, duration: int = 60):
        """运行网关主循环"""
        print(f"[GATEWAY] Starting gateway loop for {duration}s")
        self.running = True

        start_time = time.time()

        while self.running and (time.time() - start_time < duration):
            # 收集子设备数据
            self.collect_device_telemetry()

            # 短暂休眠
            time.sleep(0.1)

        print(f"[GATEWAY] Stopped")

    def stop(self):
        """停止网关"""
        self.running = False

        if self.mqtt_connection and self.connected:
            print(f"[MQTT] Disconnecting...")
            disconnect_future = self.mqtt_connection.disconnect()
            disconnect_future.result()
            print(f"[MQTT] Disconnected")

    def __del__(self):
        """析构函数"""
        self.stop()

```

device.py:
```
#!/usr/bin/env python3
"""
子设备模拟器

模拟一个 BLE 子设备:
1. 连接到网关 (BLE)
2. 定期发送遥测数据
3. 接收并执行命令
4. 返回执行结果
"""

import time
import random
from typing import Optional
from ble_protocol import BLEChannel, BLEMessage


class Device:
    """子设备模拟器基类"""

    def __init__(self, device_id: str, device_type: str, ble_channel: BLEChannel):
        self.device_id = device_id
        self.device_type = device_type
        self.ble_channel = ble_channel

        # 设备状态
        self.battery = 100
        self.status = "ok"
        self.running = False

        print(f"[DEVICE {device_id}] Initialized: type={device_type}")

    def generate_telemetry(self) -> dict:
        """生成遥测数据 (子类重写)"""
        return {
            'battery': self.battery,
            'status': self.status,
            'timestamp': int(time.time())
        }

    def execute_command(self, req_id: str, command: dict) -> dict:
        """执行命令 (子类重写)"""
        print(f"[DEVICE {self.device_id}] Received command: {command}")
        return {
            'lastAckedReqId': req_id,
            'status': 'ok',
            'timestamp': int(time.time())
        }

    def send_telemetry(self):
        """发送遥测数据到网关"""
        data = self.generate_telemetry()
        message = BLEMessage(
            device_id=self.device_id,
            message_type='telemetry',
            payload=data
        )
        self.ble_channel.send_to_gateway(message)
        print(f"[DEVICE {self.device_id}] Sent telemetry: {data}")

    def listen_for_commands(self):
        """监听网关下发的命令"""
        msg = self.ble_channel.receive_from_gateway(timeout=0.1)

        if msg and msg.message_type == 'command':
            req_id = msg.payload.get('reqId')
            command = msg.payload.get('command')

            try:
                # 执行命令
                result = self.execute_command(req_id, command)

                # 发送 ACK
                ack_msg = BLEMessage(
                    device_id=self.device_id,
                    message_type='ack',
                    payload=result
                )
                self.ble_channel.send_to_gateway(ack_msg)
                print(f"[DEVICE {self.device_id}] Command executed: {result}")

            except Exception as e:
                # 发送错误
                error_msg = BLEMessage(
                    device_id=self.device_id,
                    message_type='error',
                    payload={
                        'lastError': {
                            'reqId': req_id,
                            'code': 'EXECUTION_ERROR',
                            'message': str(e)
                        }
                    }
                )
                self.ble_channel.send_to_gateway(error_msg)
                print(f"[DEVICE {self.device_id}] Command failed: {e}")

    def run(self, telemetry_interval: int = 10, duration: int = 60):
        """运行设备主循环"""
        print(f"[DEVICE {self.device_id}] Starting device loop for {duration}s")
        self.running = True

        start_time = time.time()
        last_telemetry = 0

        while self.running and (time.time() - start_time < duration):
            current_time = time.time()

            # 定期发送遥测数据
            if current_time - last_telemetry >= telemetry_interval:
                self.send_telemetry()
                last_telemetry = current_time

                # 模拟电池消耗
                self.battery = max(0, self.battery - random.randint(0, 2))

            # 监听命令
            self.listen_for_commands()

            # 短暂休眠
            time.sleep(0.5)

        print(f"[DEVICE {self.device_id}] Stopped")

    def stop(self):
        """停止设备"""
        self.running = False


class SmartLock(Device):
    """智能门锁设备"""

    def __init__(self, device_id: str, ble_channel: BLEChannel):
        super().__init__(device_id, 'smart_lock', ble_channel)
        self.lock_status = 'locked'

    def generate_telemetry(self) -> dict:
        data = super().generate_telemetry()
        data['lock_status'] = self.lock_status
        return data

    def execute_command(self, req_id: str, command: dict) -> dict:
        action = command.get('action')

        if action == 'lock':
            self.lock_status = 'locked'
            print(f"[LOCK {self.device_id}] 🔒 Locked")

        elif action == 'unlock':
            self.lock_status = 'unlocked'
            print(f"[LOCK {self.device_id}] 🔓 Unlocked")

        else:
            raise ValueError(f"Unknown action: {action}")

        return {
            'lastAckedReqId': req_id,
            'action': action,
            'lock_status': self.lock_status,
            'status': 'ok',
            'timestamp': int(time.time())
        }


class TemperatureSensor(Device):
    """温度传感器设备"""

    def __init__(self, device_id: str, ble_channel: BLEChannel):
        super().__init__(device_id, 'temperature_sensor', ble_channel)
        self.temperature = 22.0
        self.humidity = 50.0

    def generate_telemetry(self) -> dict:
        # 模拟温湿度变化
        self.temperature += random.uniform(-0.5, 0.5)
        self.humidity += random.uniform(-1, 1)

        data = super().generate_telemetry()
        data['temperature'] = round(self.temperature, 1)
        data['humidity'] = round(self.humidity, 1)
        return data

    def execute_command(self, req_id: str, command: dict) -> dict:
        action = command.get('action')

        if action == 'calibrate':
            self.temperature = command.get('temperature', 22.0)
            self.humidity = command.get('humidity', 50.0)
            print(f"[TEMP {self.device_id}] 🌡️ Calibrated: {self.temperature}°C, {self.humidity}%")

        else:
            raise ValueError(f"Unknown action: {action}")

        return {
            'lastAckedReqId': req_id,
            'action': action,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'status': 'ok',
            'timestamp': int(time.time())
        }


class VibrationSensor(Device):
    """震动检测传感器设备"""

    def __init__(self, device_id: str, ble_channel: BLEChannel):
        super().__init__(device_id, 'vibration_sensor', ble_channel)
        self.vibration_threshold = 5.0  # 默认阈值
        self.sensitivity = 'high'  # high, medium, low
        self.vibration_level = 0.0
        self.vibration_detected = False
        self.event_count = 0
        self.last_trigger_time = None

    def generate_telemetry(self) -> dict:
        # 模拟震动级别变化
        # 根据灵敏度调整震动幅度
        sensitivity_multiplier = {
            'high': 1.5,
            'medium': 1.0,
            'low': 0.5
        }.get(self.sensitivity, 1.0)

        # 随机产生震动（10% 概率产生较强震动）
        if random.random() < 0.1:
            self.vibration_level = random.uniform(3.0, 10.0) * sensitivity_multiplier
        else:
            self.vibration_level = random.uniform(0.0, 3.0) * sensitivity_multiplier

        # 检测是否超过阈值
        previous_state = self.vibration_detected
        self.vibration_detected = self.vibration_level >= self.vibration_threshold

        # 如果刚触发（从未检测到变为检测到）
        if self.vibration_detected and not previous_state:
            self.event_count += 1
            self.last_trigger_time = int(time.time())
            print(f"[VIBRATION {self.device_id}] ⚠️ Vibration detected! Level: {self.vibration_level:.1f} (Threshold: {self.vibration_threshold})")

        data = super().generate_telemetry()
        data.update({
            'vibration_detected': self.vibration_detected,
            'vibration_level': round(self.vibration_level, 1),
            'threshold': self.vibration_threshold,
            'sensitivity': self.sensitivity,
            'event_count': self.event_count,
            'last_trigger_time': self.last_trigger_time
        })
        return data

    def execute_command(self, req_id: str, command: dict) -> dict:
        action = command.get('action')

        if action == 'set_threshold':
            new_threshold = command.get('vibration_threshold')
            if new_threshold is not None:
                self.vibration_threshold = float(new_threshold)
                print(f"[VIBRATION {self.device_id}] 🎚️ Threshold updated: {self.vibration_threshold}")

            new_sensitivity = command.get('sensitivity')
            if new_sensitivity in ['high', 'medium', 'low']:
                self.sensitivity = new_sensitivity
                print(f"[VIBRATION {self.device_id}] 🎚️ Sensitivity updated: {self.sensitivity}")

        elif action == 'reset_counter':
            self.event_count = 0
            self.last_trigger_time = None
            print(f"[VIBRATION {self.device_id}] 🔄 Event counter reset")

        else:
            raise ValueError(f"Unknown action: {action}")

        return {
            'lastAckedReqId': req_id,
            'action': action,
            'vibration_threshold': self.vibration_threshold,
            'sensitivity': self.sensitivity,
            'event_count': self.event_count,
            'status': 'ok',
            'timestamp': int(time.time())
        }


class MouseTrap(Device):
    """智能捕鼠器设备"""

    def __init__(self, device_id: str, ble_channel: BLEChannel):
        super().__init__(device_id, 'mouse_trap', ble_channel)
        self.trap_status = 'armed'  # armed, triggered, resetting
        self.kill_count = 0
        self.last_kill_time = None
        self.work_schedule = {
            'enabled': True,
            'start_time': '20:00',
            'end_time': '09:00'
        }
        self.sensitivity = 'medium'  # high, medium, low
        self.bait_level = 100  # 诱饵剩余百分比
        self.is_working = True

    def _is_in_work_schedule(self) -> bool:
        """检查当前时间是否在工作时间段内"""
        if not self.work_schedule['enabled']:
            return True  # 如果未启用时间表，则始终工作

        from datetime import datetime
        now = datetime.now()
        current_time = now.strftime('%H:%M')

        start = self.work_schedule['start_time']
        end = self.work_schedule['end_time']

        # 处理跨天的情况（如 20:00 到次日 09:00）
        if start > end:
            return current_time >= start or current_time <= end
        else:
            return start <= current_time <= end

    def generate_telemetry(self) -> dict:
        # 检查是否在工作时间段
        self.is_working = self._is_in_work_schedule()

        # 只有在工作时间且状态为 armed 时才可能触发
        if self.is_working and self.trap_status == 'armed':
            # 根据灵敏度调整触发概率
            trigger_probability = {
                'high': 0.05,    # 5% 概率
                'medium': 0.03,  # 3% 概率
                'low': 0.01      # 1% 概率
            }.get(self.sensitivity, 0.03)

            # 随机触发捕鼠事件
            if random.random() < trigger_probability:
                self.trap_status = 'triggered'
                self.kill_count += 1
                self.last_kill_time = int(time.time())
                self.bait_level = max(0, self.bait_level - random.randint(10, 20))
                print(f"[MOUSETRAP {self.device_id}] 🎯 Mouse trapped! Total kills: {self.kill_count}")

        # 如果触发后自动重置（模拟 5% 概率完成重置）
        elif self.trap_status == 'triggered':
            if random.random() < 0.05:
                self.trap_status = 'armed'
                print(f"[MOUSETRAP {self.device_id}] 🔄 Trap auto-reset to armed")

        # 模拟诱饵缓慢消耗
        if self.is_working and random.random() < 0.1:
            self.bait_level = max(0, self.bait_level - 1)

        data = super().generate_telemetry()
        data.update({
            'trap_status': self.trap_status,
            'kill_count': self.kill_count,
            'last_kill_time': self.last_kill_time,
            'work_schedule': self.work_schedule,
            'is_working': self.is_working,
            'sensitivity': self.sensitivity,
            'bait_level': self.bait_level
        })
        return data

    def execute_command(self, req_id: str, command: dict) -> dict:
        action = command.get('action')

        if action == 'reset_trap':
            self.trap_status = 'armed'
            print(f"[MOUSETRAP {self.device_id}] 🔄 Trap manually reset to armed")

        elif action == 'set_schedule':
            schedule = command.get('work_schedule')
            if schedule:
                self.work_schedule.update(schedule)
                print(f"[MOUSETRAP {self.device_id}] ⏰ Schedule updated: {self.work_schedule}")

            new_sensitivity = command.get('sensitivity')
            if new_sensitivity in ['high', 'medium', 'low']:
                self.sensitivity = new_sensitivity
                print(f"[MOUSETRAP {self.device_id}] 🎚️ Sensitivity updated: {self.sensitivity}")

        elif action == 'refill_bait':
            self.bait_level = 100
            print(f"[MOUSETRAP {self.device_id}] 🍖 Bait refilled to 100%")

        else:
            raise ValueError(f"Unknown action: {action}")

        return {
            'lastAckedReqId': req_id,
            'action': action,
            'trap_status': self.trap_status,
            'work_schedule': self.work_schedule,
            'sensitivity': self.sensitivity,
            'bait_level': self.bait_level,
            'status': 'ok',
            'timestamp': int(time.time())
        }

```

config.py:
```
"""
真实网关模拟器配置
"""

import os

# AWS IoT 配置
REGION = os.getenv('AWS_REGION', 'ap-southeast-1')
IOT_ENDPOINT = os.getenv('IOT_ENDPOINT', 'a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com')

# 网关配置（新创建的设备 - ECC 证书）
THING_NAME = "IoT-Gateway-000011"
GATEWAY_DEVICE_ID = "435204e6-21c9-447d-ab6f-888c99b91926"

# 证书路径（使用新生成的完整 SEC1 格式证书，包含曲线参数）
CERT_DIR = "./certificates_new_new"
CERT_FILE = f"{CERT_DIR}/{THING_NAME}.cert.pem"
KEY_FILE = f"{CERT_DIR}/{THING_NAME}.private.key"
ROOT_CA_FILE = f"{CERT_DIR}/AmazonRootCA1.pem"

# Lambda 配置
CONTROL_FUNCTION_NAME = "ApiStack-ControlFn7587F1D5-1SoQWovn0hvA"

# Supabase 配置
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://xinhclevokrrnfbxtarz.supabase.co')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhpbmhjbGV2b2tycm5mYnh0YXJ6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjA3MjcsImV4cCI6MjA3NDczNjcyN30.BOmYxZqZSmOBza7e000DWBGidV-7m0-1y-Ui4ND7sa4')

# 测试设备配置 (使用 Supabase 中的实际 UUID)
DEVICES = [
    {
        'device_id': '2ca8de14-075b-4edf-9e14-47351158b547',  # 智能门锁 UUID
        'shadow_name': 'lock-real-001',
        'type': 'lock'
    },
    {
        'device_id': '85fe4ed6-4df0-4221-8e08-a8619e995b3d',  # 温度传感器 UUID
        'shadow_name': 'temp-real-001',
        'type': 'temperature'
    },
    {
        'device_id': '12da81b1-0b37-4e42-a25c-1e7a1078ad53',  # 震动传感器 UUID
        'shadow_name': 'vibration-sensor-001',
        'type': 'vibration_sensor'
    },
    {
        'device_id': 'd446eca1-c25d-4b15-897b-cd4d26bef995',  # 智能捕鼠器 UUID
        'shadow_name': 'mouse-trap-001',
        'type': 'mouse_trap'
    }
]

```

ble_protocol.py:
```
#!/usr/bin/env python3
"""
BLE 协议模拟

使用 multiprocessing.Queue 模拟 BLE 通信
"""

from dataclasses import dataclass
from typing import Optional, Dict
from multiprocessing import Queue
import queue


@dataclass
class BLEMessage:
    """BLE 消息"""
    device_id: str
    message_type: str  # 'telemetry' | 'command' | 'ack' | 'error'
    payload: dict


class BLEChannel:
    """BLE 通信信道 (单个设备)"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.to_device = Queue()    # 网关 → 设备
        self.from_device = Queue()  # 设备 → 网关

    def send(self, message: BLEMessage):
        """发送消息到设备"""
        self.to_device.put(message)

    def receive(self, timeout: float = None) -> Optional[BLEMessage]:
        """从设备接收消息"""
        try:
            return self.from_device.get(timeout=timeout)
        except queue.Empty:
            return None

    def send_from_device(self, message: BLEMessage):
        """设备发送消息到网关"""
        self.from_device.put(message)

    def receive_from_gateway(self, timeout: float = None) -> Optional[BLEMessage]:
        """设备接收来自网关的消息"""
        try:
            return self.to_device.get(timeout=timeout)
        except queue.Empty:
            return None

    def send_to_gateway(self, message: BLEMessage):
        """设备发送消息到网关 (别名方法)"""
        self.send_from_device(message)


class BLEHub:
    """BLE 中心 (网关侧)"""

    def __init__(self):
        self.channels: Dict[str, BLEChannel] = {}

    def register_device(self, device_id: str) -> BLEChannel:
        """注册一个设备"""
        if device_id not in self.channels:
            channel = BLEChannel(device_id)
            self.channels[device_id] = channel
            print(f"[BLE HUB] Device {device_id} registered")
        return self.channels[device_id]

    def send_to_device(self, device_id: str, message: BLEMessage):
        """发送消息到指定设备"""
        if device_id in self.channels:
            self.channels[device_id].send(message)

    def receive_from_any(self, timeout: float = None) -> Optional[BLEMessage]:
        """从任意设备接收消息 (非阻塞轮询)"""
        for channel in self.channels.values():
            msg = channel.receive(timeout=0)
            if msg:
                return msg
        return None

```

