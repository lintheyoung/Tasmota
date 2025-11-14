"""
AWS IoT MQTT Client
使用 AWS IoT Python SDK 连接到 AWS IoT Core
"""

import logging
import threading
from typing import Callable, Optional
from awscrt import mqtt
from awsiot import mqtt_connection_builder

from config import (
    GATEWAY_THING, MQTT_ENDPOINT, MQTT_PORT, MQTT_KEEPALIVE,
    CERT_FILE, KEY_FILE, ROOT_CA_FILE
)

logger = logging.getLogger(__name__)


class AWSIoTClient:
    """
    AWS IoT MQTT 客户端封装
    """

    def __init__(self, cert_file: str = None, key_file: str = None, ca_file: str = None, thing_name: str = None):
        """
        初始化 AWS IoT MQTT 客户端

        Args:
            cert_file: 设备证书文件路径（可选，默认使用 config.py 中的配置）
            key_file: 私钥文件路径（可选，默认使用 config.py 中的配置）
            ca_file: CA 证书文件路径（可选，默认使用 config.py 中的配置）
            thing_name: AWS IoT Thing Name（可选，默认使用 config.py 中的配置）
        """
        self.mqtt_connection = None
        self.connected = False
        self.connect_lock = threading.Lock()

        # 证书路径（支持自定义）
        self.cert_file = cert_file or CERT_FILE
        self.key_file = key_file or KEY_FILE
        self.ca_file = ca_file or ROOT_CA_FILE
        self.thing_name = thing_name or GATEWAY_THING

        # 回调函数
        self.on_connected_callback = None
        self.on_disconnected_callback = None
        self.on_message_callback = None

        logger.info("=" * 60)
        logger.info("🔧 Initializing AWS IoT MQTT Client")
        logger.info("=" * 60)
        logger.info(f"Thing Name: {self.thing_name}")
        logger.info(f"Endpoint: {MQTT_ENDPOINT}")
        logger.info(f"Port: {MQTT_PORT}")
        logger.info(f"Certificate: {self.cert_file}")
        logger.info(f"Private Key: {self.key_file}")
        logger.info(f"Root CA: {self.ca_file}")
        logger.info("=" * 60)

    def connect(self) -> bool:
        """
        连接到 AWS IoT Core

        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info("📡 Connecting to AWS IoT Core...")

            # 创建 MQTT 连接（使用 mTLS 认证）
            self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=MQTT_ENDPOINT,
                port=MQTT_PORT,
                cert_filepath=self.cert_file,
                pri_key_filepath=self.key_file,
                ca_filepath=self.ca_file,
                client_id=self.thing_name,
                clean_session=False,
                keep_alive_secs=MQTT_KEEPALIVE,
                on_connection_interrupted=self._on_connection_interrupted,
                on_connection_resumed=self._on_connection_resumed
            )

            # 同步连接
            connect_future = self.mqtt_connection.connect()
            connect_result = connect_future.result()

            self.connected = True
            logger.info("✅ Connected to AWS IoT Core successfully!")
            logger.info(f"Session Present: {connect_result['session_present']}")

            # 触发连接回调
            if self.on_connected_callback:
                self.on_connected_callback()

            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to AWS IoT Core: {e}", exc_info=True)
            self.connected = False
            return False

    def disconnect(self):
        """断开与 AWS IoT Core 的连接"""
        if self.mqtt_connection and self.connected:
            try:
                logger.info("🔌 Disconnecting from AWS IoT Core...")
                disconnect_future = self.mqtt_connection.disconnect()
                disconnect_future.result()
                self.connected = False
                logger.info("✅ Disconnected successfully")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")

    def _on_connection_interrupted(self, connection, error, **kwargs):
        """连接中断回调"""
        logger.warning(f"⚠️ Connection interrupted: {error}")
        self.connected = False

        if self.on_disconnected_callback:
            self.on_disconnected_callback()

    def _on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        """连接恢复回调"""
        logger.info(f"✅ Connection resumed (return_code={return_code}, session_present={session_present})")
        self.connected = True

        if self.on_connected_callback:
            self.on_connected_callback()

    def subscribe(self, topic: str, qos: int, callback: Callable):
        """
        订阅 MQTT 主题

        Args:
            topic: MQTT 主题
            qos: QoS 级别
            callback: 消息回调函数 callback(topic, payload, **kwargs)
        """
        if not self.mqtt_connection:
            logger.error("MQTT connection not initialized")
            return

        try:
            logger.info(f"📥 Subscribing to: {topic}")

            subscribe_future, packet_id = self.mqtt_connection.subscribe(
                topic=topic,
                qos=mqtt.QoS(qos),
                callback=callback
            )

            # 等待订阅确认
            subscribe_result = subscribe_future.result()
            logger.info(f"✅ Subscribed to {topic} (QoS: {subscribe_result['qos']})")

        except Exception as e:
            logger.error(f"❌ Failed to subscribe to {topic}: {e}", exc_info=True)

    def publish(self, topic: str, payload: str, qos: int = 1, timeout: float = 10.0):
        """
        发布消息到 MQTT 主题

        Args:
            topic: MQTT 主题
            payload: 消息内容（字符串）
            qos: QoS 级别（默认 1）
            timeout: 发布超时时间（秒，默认 10.0）
        """
        if not self.mqtt_connection:
            logger.error("MQTT connection not initialized")
            return False

        if not self.connected:
            logger.warning("MQTT connection not ready, message may be queued")

        try:
            # 调试日志：显示要发布的主题和数据大小
            logger.debug(f"📤 Publishing to {topic} (payload size: {len(payload)} bytes, QoS: {qos})")
            logger.debug(f"   Payload preview: {payload[:200]}...")

            publish_future, packet_id = self.mqtt_connection.publish(
                topic=topic,
                payload=payload,
                qos=mqtt.QoS(qos)
            )

            # QoS 0: 不等待确认，立即返回（模拟 Berry 脚本行为）
            # QoS 1: 等待 PUBACK 确认
            if qos == 0:
                logger.debug(f"✅ Published to {topic} (QoS 0: fire-and-forget, packet_id={packet_id})")
                return True
            else:
                logger.debug(f"   Waiting for publish confirmation (timeout={timeout}s, packet_id={packet_id})...")
                try:
                    publish_future.result(timeout=timeout)
                    logger.debug(f"✅ Published to {topic} successfully (packet_id: {packet_id})")
                    return True
                except TimeoutError:
                    logger.error(f"❌ Publish timeout after {timeout}s (packet_id: {packet_id})")
                    logger.error(f"   Topic: {topic}")
                    logger.error(f"   Connection status: {self.connected}")
                    return False

        except Exception as e:
            logger.error(f"❌ Failed to publish to {topic}: {e}", exc_info=True)
            return False

    def set_on_connected_callback(self, callback: Callable):
        """设置连接成功回调"""
        self.on_connected_callback = callback

    def set_on_disconnected_callback(self, callback: Callable):
        """设置连接断开回调"""
        self.on_disconnected_callback = callback

    def is_connected(self) -> bool:
        """��查是否已连接"""
        return self.connected
