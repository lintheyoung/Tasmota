"""
Virtual Vibration Sensor - 完整复制 autoexec.be 中的 VirtualVibrationSensor 类
"""

import time
import random
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from config import (
    VIRTUAL_DEVICE, GATEWAY_DEVICE_ID, GATEWAY_THING,
    TELEMETRY_INTERVAL, STATS_INTERVAL,
    INITIAL_BATTERY, INITIAL_STATUS, INITIAL_VIBRATION_THRESHOLD, INITIAL_SENSITIVITY,
    MQTT_QOS_TELEMETRY, MQTT_QOS_COMMAND
)

logger = logging.getLogger(__name__)


class VirtualVibrationSensor:
    """
    虚拟振动传感器
    完整复制 Berry 脚本中的 VirtualVibrationSensor 类的所有功能
    """

    def __init__(self, mqtt_client, telemetry_interval: int = TELEMETRY_INTERVAL):
        """
        初始化虚拟传感器

        Args:
            mqtt_client: AWS IoT MQTT 客户端
            telemetry_interval: 遥测间隔（秒）
        """
        self.mqtt_client = mqtt_client

        # 设备信息
        self.device_id = VIRTUAL_DEVICE['device_id']
        self.shadow_name = VIRTUAL_DEVICE['shadow_name']
        self.gateway_thing = getattr(mqtt_client, 'thing_name', GATEWAY_THING)  # 从 mqtt_client 获取或使用默认值
        self.gateway_id = GATEWAY_DEVICE_ID

        # 传感器状态
        self.battery = INITIAL_BATTERY
        self.status = INITIAL_STATUS
        self.vibration_threshold = INITIAL_VIBRATION_THRESHOLD
        self.sensitivity = INITIAL_SENSITIVITY
        self.vibration_level = 0.0
        self.vibration_detected = False
        self.event_count = 0
        self.last_trigger_time = None

        # 时间控制
        self.telemetry_interval = telemetry_interval
        self.last_telemetry_time = time.time() + 20  # 首次遥测延迟 20 秒
        self.start_time = time.time()

        # 统计数据
        self.telemetry_sent = 0
        self.telemetry_confirmed = 0
        self.telemetry_failed = 0
        self.last_stats_time = time.time()
        self.stats_interval = STATS_INTERVAL

        # MQTT 主题
        self.delta_topic = f"$aws/things/{self.gateway_thing}/shadow/name/{self.shadow_name}/update/delta"
        self.update_topic = f"$aws/things/{self.gateway_thing}/shadow/name/{self.shadow_name}/update"
        self.get_topic = f"$aws/things/{self.gateway_thing}/shadow/name/{self.shadow_name}/get"
        self.get_accepted_topic = f"$aws/things/{self.gateway_thing}/shadow/name/{self.shadow_name}/get/accepted"
        self.update_accepted_topic = f"$aws/things/{self.gateway_thing}/shadow/name/{self.shadow_name}/update/accepted"

        # ACK 追踪
        self.need_clear_ack = False
        self.initialized = False

        logger.info("=" * 50)
        logger.info(f"🔧 Virtual Sensor initialized: {self.shadow_name}")
        logger.info(f"   Device ID: {self.device_id}")
        logger.info("=" * 50)

    def mqtt_connected(self):
        """
        MQTT 连接成功后的初始化
        对应 Berry 脚本中的 mqtt_connected() 方法
        """
        logger.info(f"📡 Sending Shadow GET request for: {self.shadow_name}")

        # 发送 GET 请求获取当前 Shadow 状态
        # Berry: tasmota.cmd("Publish") 默认使用 QoS 0
        self.mqtt_client.publish(
            topic=self.get_topic,
            payload="",
            qos=0
        )

        # 清除旧的 lastAckedReqId（防止旧 ACK 问题）
        initial_state = {
            'deviceId': self.device_id,
            'gatewayId': self.gateway_id,
            'status': self.status,
            'battery': self.battery,
            'vibration_detected': self.vibration_detected,
            'vibration_level': self.vibration_level,
            'threshold': self.vibration_threshold,
            'sensitivity': self.sensitivity,
            'event_count': self.event_count,
            'last_trigger_time': self.last_trigger_time,
            'timestamp': int(time.time())
            # NOTE: 不包含 'lastAckedReqId' 以清除旧 ACK
        }

        self.update_shadow_reported(initial_state, clear_desired=False)
        self.initialized = True
        logger.info("✅ Shadow initialized, old ACK cleared")

    def every_second(self):
        """
        每秒执行的逻辑
        对应 Berry 脚本中的 every_second() 方法
        """
        now = time.time()

        # 如果未初始化且已经 10 秒，发送 GET 请求
        if not self.initialized and now - self.start_time >= 10:
            logger.info(f"📡 Sending Shadow GET request for: {self.shadow_name}")
            self.mqtt_client.publish(
                topic=self.get_topic,
                payload="",
                qos=0  # Berry 脚本默认 QoS 0
            )
            self.initialized = True

        # 定时发送遥测数据
        if now - self.last_telemetry_time >= self.telemetry_interval:
            self.generate_and_send_telemetry()
            self.last_telemetry_time = now

        # 定期报告统计数据
        if now - self.last_stats_time >= self.stats_interval:
            self.report_statistics()
            self.last_stats_time = now

    def generate_and_send_telemetry(self):
        """
        生成并发送遥测数据
        完整复制 Berry 脚本中的 generate_and_send_telemetry() 逻辑
        """
        # 根据灵敏度模拟振动级别
        sensitivity_multiplier = 1.0
        if self.sensitivity == 'high':
            sensitivity_multiplier = 1.5
        elif self.sensitivity == 'low':
            sensitivity_multiplier = 0.5

        # 随机振动（10% 概率产生强振动）
        if random.randint(0, 99) < 10:
            self.vibration_level = (3.0 + random.random() * 7.0) * sensitivity_multiplier
        else:
            self.vibration_level = (random.random() * 3.0) * sensitivity_multiplier

        # 检查阈值
        previous_state = self.vibration_detected
        self.vibration_detected = self.vibration_level >= self.vibration_threshold

        # 状态变化时触发事件
        if self.vibration_detected and not previous_state:
            self.event_count += 1
            self.last_trigger_time = int(time.time())
            logger.warning(
                f"⚠️ Vibration detected! Level: {self.vibration_level:.1f} "
                f"(Threshold: {self.vibration_threshold})"
            )

        # 电池缓慢消耗（每 10 次遥测周期消耗 1%）
        if random.randint(0, 9) == 0 and self.battery > 0:
            self.battery -= 1

        # 构建遥测数据（与 Berry 脚本完全一致）
        telemetry = {
            'deviceId': self.device_id,
            'gatewayId': self.gateway_id,
            'battery': self.battery,
            'status': self.status,
            'vibration_detected': self.vibration_detected,
            'vibration_level': round(self.vibration_level, 1),
            'threshold': self.vibration_threshold,
            'sensitivity': self.sensitivity,
            'event_count': self.event_count,
            'last_trigger_time': self.last_trigger_time,
            'timestamp': int(time.time())
            # NOTE: 不包含 'lastAckedReqId' - 只在 ACK 消息中包含
        }

        # 如果刚发送了 ACK，清除 lastAckedReqId
        if self.need_clear_ack:
            telemetry['lastAckedReqId'] = None
            self.need_clear_ack = False
            logger.info("🧹 Clearing lastAckedReqId from Shadow")

        # 更新 Shadow reported 状态
        self.update_shadow_reported(telemetry, clear_desired=False)
        self.telemetry_sent += 1

    def update_shadow_reported(self, reported: Dict[str, Any], clear_desired: bool = False) -> bool:
        """
        更新 Shadow reported 状态

        Args:
            reported: 要报告的状态数据
            clear_desired: 是否清除 desired 状态

        Returns:
            bool: 发布是否成功
        """
        # 构建 Shadow Update payload
        if clear_desired:
            payload = {
                'state': {
                    'reported': reported,
                    'desired': None  # 清除 desired 状态
                }
            }
        else:
            payload = {
                'state': {
                    'reported': reported
                }
            }

        # 选择 QoS 级别
        # ACK 消息（clear_desired=True）使用 COMMAND QoS
        # 普通遥测使用 TELEMETRY QoS
        qos = MQTT_QOS_COMMAND if clear_desired else MQTT_QOS_TELEMETRY

        # 发布到 MQTT
        success = self.mqtt_client.publish(
            topic=self.update_topic,
            payload=json.dumps(payload),
            qos=qos
        )

        # 只在普通遥测时记录简短日志
        if not clear_desired and 'lastAckedReqId' not in reported:
            logger.info(
                f"📤 Telemetry: vibration={reported.get('vibration_level', 0)}, "
                f"events={reported.get('event_count', 0)}"
            )

        return success if success is not None else True

    def handle_shadow_get_accepted(self, payload: str):
        """
        处理 Shadow GET 响应
        检查是否有待执行的命令
        """
        logger.info("📥 Shadow GET response received")

        try:
            shadow = json.loads(payload)
            state = shadow.get('state', {})
            desired = state.get('desired', {})
            reported = state.get('reported', {})

            # 检查待执行命令
            if desired and reported:
                desired_req_id = desired.get('reqId')
                reported_req_id = reported.get('lastAckedReqId')

                if desired_req_id and desired_req_id != reported_req_id:
                    logger.info(f"📋 Found pending command: {desired_req_id}")
                    cmd = desired.get('cmd')
                    if cmd:
                        self.execute_command(desired_req_id, cmd)

        except Exception as e:
            logger.error(f"Error handling Shadow GET response: {e}")

    def handle_shadow_update_accepted(self, payload: str):
        """
        处理 Shadow Update 确认
        """
        logger.debug("✅ Shadow update confirmed")
        self.telemetry_confirmed += 1

    def handle_shadow_delta(self, payload: str):
        """
        处理 Shadow Delta（命令接收）
        完整复制 Berry 脚本中的 mqtt_data() Delta 处理逻辑
        """
        receive_time = time.time()
        receive_time_int = int(receive_time)

        logger.info("=" * 50)
        logger.info("📩 MQTT COMMAND RECEIVED")
        logger.info("=" * 50)
        logger.info(f"📍 Topic: {self.delta_topic}")
        logger.info(f"📦 Raw Payload: {payload}")
        logger.info(f"⏰ Device Time: {receive_time_int} ({int(receive_time * 1000)}ms)")

        try:
            delta = json.loads(payload)

            # 提取 AWS 时间戳并计算延迟
            aws_timestamp = delta.get('timestamp')
            if aws_timestamp:
                # AWS timestamp 是 UTC，需要根据实际时区调整
                latency = receive_time_int - aws_timestamp
                logger.info(f"📡 AWS Timestamp (UTC): {aws_timestamp}")
                logger.info(f"⚡ Network Latency: {latency} seconds")

                if latency < 0:
                    logger.warning("⚠️ Time sync issue detected (negative latency)")
                elif latency < 1:
                    logger.info("✅ Excellent latency (< 1s)")
                elif latency < 2:
                    logger.info("⚠️ Good latency (1-2s)")
                else:
                    logger.warning("❌ High latency (> 2s)")

            # 提取命令和 req_id
            state = delta.get('state')
            if not state:
                logger.warning("⚠️ Missing 'state' field in delta")
                logger.info("=" * 50)
                return

            # 支持 req_id 和 reqId 两种格式
            req_id = state.get('req_id') or state.get('reqId')
            if not req_id:
                logger.warning("⚠️ Missing req_id or reqId in delta")
                logger.info("=" * 50)
                return

            # 整个 state 对象就是命令
            cmd = state

            # 显示命令详情
            logger.info("📋 Command Details:")
            logger.info(f"   └─ reqId: {req_id}")

            action = cmd.get('action')
            if action:
                logger.info(f"   └─ action: {action}")

            threshold = cmd.get('vibration_threshold')
            if threshold is not None:
                logger.info(f"   └─ vibration_threshold: {threshold}")

            sensitivity = cmd.get('sensitivity')
            if sensitivity:
                logger.info(f"   └─ sensitivity: {sensitivity}")

            logger.info(f"🎯 Full Command Object: {cmd}")
            logger.info("=" * 50)

            # 执行命令
            logger.info("⚙️ Executing command...")
            self.execute_command(req_id, cmd)

        except Exception as e:
            logger.error(f"Error handling Shadow Delta: {e}", exc_info=True)
            logger.info("=" * 50)

    def execute_command(self, req_id: str, cmd: Dict[str, Any]):
        """
        执行命令
        完整复制 Berry 脚本中的 execute_command() 逻辑
        """
        action = cmd.get('action', 'unknown')
        logger.info(f"⚙️ Command received: {action} (reqId={req_id})")

        # 应用命令更新到内部状态
        new_threshold = cmd.get('vibration_threshold')
        if new_threshold is not None:
            old_threshold = self.vibration_threshold
            self.vibration_threshold = new_threshold
            logger.info(f"   📝 Updated vibration_threshold: {old_threshold} → {new_threshold}")

        new_sensitivity = cmd.get('sensitivity')
        if new_sensitivity:
            old_sensitivity = self.sensitivity
            self.sensitivity = new_sensitivity
            logger.info(f"   📝 Updated sensitivity: {old_sensitivity} → {new_sensitivity}")

        if action == 'reset_counter':
            self.event_count = 0
            self.last_trigger_time = None
            logger.info(f"   🔄 Event counter reset")

        # 发送 ACK（包含完整状态）
        result = {
            'deviceId': self.device_id,
            'gatewayId': self.gateway_id,
            'lastAckedReqId': req_id,  # 必须包含：浏览器用此匹配 ACK
            'battery': self.battery,
            'status': self.status,
            'vibration_detected': self.vibration_detected,
            'vibration_level': round(self.vibration_level, 1),
            'threshold': self.vibration_threshold,
            'sensitivity': self.sensitivity,
            'event_count': self.event_count,
            'last_trigger_time': self.last_trigger_time,
            'timestamp': int(time.time())
        }

        logger.info("=" * 50)
        logger.info("📨 Sending ACK to AWS IoT Shadow...")
        logger.info(f"   reqId: {req_id}")
        logger.info(f"   lastAckedReqId: {result['lastAckedReqId']}")
        logger.info(f"   Current threshold: {result['threshold']}")
        logger.info(f"   Current sensitivity: {result['sensitivity']}")
        logger.info("=" * 50)

        # 清除 desired 状态（防止 delta 循环）
        success = self.update_shadow_reported(result, clear_desired=True)

        if success:
            # 设置标志以在下次遥测中清除 lastAckedReqId
            self.need_clear_ack = True
            logger.info(f"✅ Command ACK sent successfully: {action} (reqId={req_id})")
        else:
            logger.error(f"❌ Failed to send ACK for: {action} (reqId={req_id})")

        logger.info("=" * 50)

    def report_statistics(self):
        """
        报告统计数据
        对应 Berry 脚本中的 report_statistics() 方法
        """
        success_rate = 0.0
        if self.telemetry_sent > 0:
            success_rate = (self.telemetry_confirmed * 100.0) / self.telemetry_sent

        uptime_sec = time.time() - self.start_time
        uptime_min = uptime_sec / 60

        logger.info("=" * 50)
        logger.info("📊 Communication Statistics Report")
        logger.info("=" * 50)
        logger.info(f"⏱️  Uptime: {uptime_min:.1f} minutes")
        logger.info(f"📤 Telemetry Sent: {self.telemetry_sent}")
        logger.info(f"✅ Confirmed: {self.telemetry_confirmed}")
        logger.info(f"❌ Failed: {self.telemetry_failed}")
        logger.info(f"📈 Success Rate: {success_rate:.1f}%")
        logger.info("=" * 50)
