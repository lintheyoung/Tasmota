#!/usr/bin/env python3
"""
清除 AWS IoT Shadow 中的旧 ACK
解决 "收到未知请求的 ACK" 问题
"""

import sys
import time
import json
import logging
from aws_iot_client import AWSIoTClient
from config import (
    LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT,
    GATEWAY_THING, VIRTUAL_DEVICE
)

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT
)

logger = logging.getLogger(__name__)

def main():
    logger.info("=" * 60)
    logger.info("🧹 清除 Shadow 中的旧 ACK")
    logger.info("=" * 60)

    mqtt_client = AWSIoTClient()

    if not mqtt_client.connect():
        logger.error("❌ Failed to connect to AWS IoT")
        return 1

    time.sleep(2)

    shadow_name = VIRTUAL_DEVICE['shadow_name']
    update_topic = f"$aws/things/{GATEWAY_THING}/shadow/name/{shadow_name}/update"

    # 清除 lastAckedReqId（设置为 null）
    clean_payload = {
        'state': {
            'reported': {
                'lastAckedReqId': None  # 设置为 null 会从 Shadow 中删除这个字段
            }
        }
    }

    logger.info(f"📤 清除 Shadow 中的 lastAckedReqId...")
    logger.info(f"   Shadow: {shadow_name}")
    logger.info(f"   Topic: {update_topic}")

    success = mqtt_client.publish(
        topic=update_topic,
        payload=json.dumps(clean_payload),
        qos=0  # 使用 QoS 0
    )

    if success:
        logger.info("✅ 旧 ACK 已清除")
        logger.info("=" * 60)
        logger.info("💡 现在可以重新运行 main.py 测试")
        logger.info("=" * 60)
    else:
        logger.error("❌ 清除失败")

    time.sleep(1)
    mqtt_client.disconnect()

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
