"""
AWS IoT Virtual Vibration Sensor Simulator - Configuration
完整复制 autoexec.be v6.2.0 的功能
"""

import os

# ============================================================
# AWS IoT Configuration (与 autoexec.be 完全一致)
# ============================================================

SCRIPT_VERSION = "6.2.0-python"
GATEWAY_THING = "IoT-Gateway-000011"
MQTT_ENDPOINT = "a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com"

# 虚拟 BLE 设备配置 (与 Berry 脚本完全一致)
VIRTUAL_DEVICE = {
    'device_id': '09aa8ad8-f23e-4e75-bcbe-332efeb431ce',
    'shadow_name': 'vibration-sensor-001',
    'type': 'vibration_sensor'
}

# Gateway ID (与 autoexec.be 中的 gatewayId 一致)
GATEWAY_DEVICE_ID = "435204e6-21c9-447d-ab6f-888c99b91926"

# ============================================================
# 证书路径配置
# ============================================================

CERT_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_FILE = os.path.join(CERT_DIR, f"{GATEWAY_THING}.cert.pem")
KEY_FILE = os.path.join(CERT_DIR, f"{GATEWAY_THING}.private.key")
ROOT_CA_FILE = os.path.join(CERT_DIR, "AmazonRootCA1.pem")

# ============================================================
# 传感器配置
# ============================================================

# 遥测间隔（秒）- 与 Berry 脚本一致
TELEMETRY_INTERVAL = 10

# 统计报告间隔（秒）
STATS_INTERVAL = 300  # 5 minutes

# 初始传感器状态
INITIAL_BATTERY = 100
INITIAL_STATUS = "ok"
INITIAL_VIBRATION_THRESHOLD = 5.0
INITIAL_SENSITIVITY = "high"

# ============================================================
# MQTT 配置
# ============================================================

MQTT_PORT = 8883
MQTT_KEEPALIVE = 30

# QoS 配置
# QoS 0 = AT_MOST_ONCE (不等待确认，快速)
# QoS 1 = AT_LEAST_ONCE (等待 PUBACK 确认，可能超时)
MQTT_QOS_TELEMETRY = 0  # 遥测数据使用 QoS 0（高频，允许偶尔丢失）
MQTT_QOS_COMMAND = 0    # 命令响应使用 QoS 0（AWS Shadow 有重试机制）

# ============================================================
# 日志配置
# ============================================================

LOG_LEVEL = "DEBUG"  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
