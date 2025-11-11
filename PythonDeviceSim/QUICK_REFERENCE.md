# 快速参考 - Python 设备模拟器

## 🚀 快速启动（3 步）

```bash
cd /Volumes/DeDeDisk/PestGG-Project/Tasmota-1/PythonDeviceSim
pip install -r requirements.txt
python3 main.py
```

## ✅ 成功运行的标志

```
✅ Connected to AWS IoT Core successfully!
✅ Subscribed to shadow topics: vibration-sensor-001
✅ Shadow initialized, old ACK cleared
🔄 Starting main loop...
```

## 📤 正常命令处理日志

```
📩 MQTT COMMAND RECEIVED (reqId=req_xxx)
⚙️ Command received: unknown
📨 Sending ACK to AWS IoT Shadow...
📤 Publishing (payload size: 390 bytes, QoS: 0)
✅ Published (QoS 0: fire-and-forget, packet_id=6)
✅ Command ACK sent successfully
```

## ❌ 常见问题速查

| 问题 | 解决方案 |
|------|---------|
| ⏱️ 命令超时 15 秒 | `python3 clear_old_ack.py` 然后重启 |
| ⚠️ 收到未知请求的 ACK | `python3 clear_old_ack.py` 然后重启 |
| ❌ 无法连接 AWS IoT | 检查证书文件和网络 |
| 📊 遥测数据不显示 | 等待 20 秒（首次延迟） |

## 🔧 重要配置

| 文件 | 配置项 | 值 | 说明 |
|------|--------|-----|------|
| config.py | `MQTT_QOS_COMMAND` | `0` | **必须为 0** |
| config.py | `MQTT_QOS_TELEMETRY` | `0` | **必须为 0** |
| config.py | `LOG_LEVEL` | `"DEBUG"` | 调试模式 |
| config.py | `LOG_LEVEL` | `"INFO"` | 生产模式 |

## 📁 核心文件

```
main.py                    # 启动这个
config.py                  # 配置在这里
clear_old_ack.py          # 清理工具
README.md                 # 完整文档
```

## 🎮 Web 控制面板测试

1. 打开控制面板
2. 选择：`客厅震动传感器 (vibration-sensor-001)`
3. 点击任意按钮
4. 观察 Python 日志：应该在 1 秒内显示 `✅ Command ACK sent successfully`

## 📊 性能指标

| 指标 | 预期值 |
|------|-------|
| ACK 响应时间 | < 1 秒 |
| 发布延迟 | < 1ms |
| 网络延迟 | < 1 秒 (优秀) |
| 命令成功率 | 100% |

## 💡 调试命令

```bash
# 清除旧 ACK
python3 clear_old_ack.py

# 查看证书
openssl x509 -in IoT-Gateway-000011.cert.pem -noout -text

# 检查 Python 版本
python3 --version  # 需要 3.7+
```

## 🔗 更多信息

详细文档：[README.md](README.md)
