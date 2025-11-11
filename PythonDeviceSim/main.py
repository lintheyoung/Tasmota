#!/usr/bin/env python3
"""
AWS IoT Virtual Vibration Sensor Simulator
完整复制 autoexec.be v6.2.0 的功能

使用方式:
    python3 main.py
"""

import sys
import time
import logging
import signal
from threading import Thread, Event

from config import (
    SCRIPT_VERSION, GATEWAY_THING, MQTT_ENDPOINT, VIRTUAL_DEVICE,
    TELEMETRY_INTERVAL, LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT
)
from aws_iot_client import AWSIoTClient
from virtual_vibration_sensor import VirtualVibrationSensor

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT
)
logger = logging.getLogger(__name__)

# 全局停止事件
stop_event = Event()


def signal_handler(sig, frame):
    """处理 Ctrl+C 信号"""
    logger.info("\n\n⏹️  Received stop signal, shutting down...")
    stop_event.set()


def main():
    """主程序入口"""
    # 打印欢迎信息
    logger.info("=" * 60)
    logger.info(f"AWS IoT Test v{SCRIPT_VERSION}")
    logger.info("=" * 60)
    logger.info("🚀 BLE Gateway - Communication Stability Test")
    logger.info(f"📡 Gateway Thing: {GATEWAY_THING}")
    logger.info(f"🔌 Virtual Device: {VIRTUAL_DEVICE['shadow_name']}")
    logger.info(f"   Device ID: {VIRTUAL_DEVICE['device_id']}")
    logger.info(f"📤 Telemetry interval: {TELEMETRY_INTERVAL} seconds")
    logger.info(f"📊 Statistics report: Every 5 minutes")
    logger.info("=" * 60)

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 创建 AWS IoT MQTT 客户端
    mqtt_client = AWSIoTClient()

    # 创建虚拟传感器
    sensor = VirtualVibrationSensor(
        mqtt_client=mqtt_client,
        telemetry_interval=TELEMETRY_INTERVAL
    )

    # 设置 MQTT 连接回调
    def on_connected():
        """MQTT 连接成功后的处理"""
        logger.info("📥 MQTT connected, subscribing to shadow topics...")

        # 调试回调：记录所有收到的消息
        def debug_callback(topic, payload, **kwargs):
            logger.debug(f"🔔 Received message on topic: {topic}")
            logger.debug(f"   Payload size: {len(payload)} bytes")

        # 订阅 Shadow 主题
        mqtt_client.subscribe(
            topic=sensor.delta_topic,
            qos=1,
            callback=lambda topic, payload, **kwargs: (
                debug_callback(topic, payload),
                sensor.handle_shadow_delta(payload.decode('utf-8'))
            )
        )

        mqtt_client.subscribe(
            topic=sensor.get_accepted_topic,
            qos=1,
            callback=lambda topic, payload, **kwargs: (
                debug_callback(topic, payload),
                sensor.handle_shadow_get_accepted(payload.decode('utf-8'))
            )
        )

        mqtt_client.subscribe(
            topic=sensor.update_accepted_topic,
            qos=1,
            callback=lambda topic, payload, **kwargs: (
                debug_callback(topic, payload),
                sensor.handle_shadow_update_accepted(payload.decode('utf-8'))
            )
        )

        logger.info(f"📥 Subscribed to shadow topics: {VIRTUAL_DEVICE['shadow_name']}")
        logger.info(f"   Delta: {sensor.delta_topic}")
        logger.info(f"   GET Accepted: {sensor.get_accepted_topic}")
        logger.info(f"   Update Accepted: {sensor.update_accepted_topic}")

        # 初始化传感器
        sensor.mqtt_connected()

    mqtt_client.set_on_connected_callback(on_connected)

    # 连接到 AWS IoT Core
    if not mqtt_client.connect():
        logger.error("❌ Failed to connect to AWS IoT Core. Exiting...")
        sys.exit(1)

    # 主循环：每秒执行传感器逻辑
    logger.info("\n✅ Configuration complete")
    logger.info("🔄 Starting main loop...\n")

    try:
        while not stop_event.is_set():
            # 每秒执行传感器逻辑（对应 Berry 的 every_second）
            sensor.every_second()

            # 等待 1 秒
            stop_event.wait(1.0)

    except Exception as e:
        logger.error(f"❌ Error in main loop: {e}", exc_info=True)

    finally:
        # 清理资源
        logger.info("\n🧹 Cleaning up...")
        mqtt_client.disconnect()
        logger.info("👋 Shutdown complete\n")


if __name__ == "__main__":
    main()
