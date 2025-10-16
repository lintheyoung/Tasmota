# Tasmota ESP32 连接 AWS IoT 完整指南

> **最终验证版本** - 经过完整测试的稳定配置方案
> **日期**: 2025-10-16
> **设备**: ESP32-S3 + Tasmota 15.0.1.5(bluetooth)
> **状态**: ✅ 已验证可用 - 稳定运行超过5分钟，成功发送11+条消息

---

## 📋 目录

1. [重要概念](#重要概念)
2. [文件系统结构](#文件系统结构)
3. [证书准备](#证书准备)
4. [Berry 脚本开发](#berry-脚本开发)
5. [部署流程](#部署流程)
6. [验证测试](#验证测试)
7. [故障排除](#故障排除)
8. [最佳实践](#最佳实践)

---

## 重要概念

### Berry 脚本执行机制

**关键规则**：
```
✅ Berry 脚本必须放在 data/ 目录
❌ tasmota/berry_scripts/ 只有在 custom_files_upload 中指定才会上传
❌ tasmota32/littlefs_data/ 这个目录不会被使用
```

**执行流程**：
1. PlatformIO 读取 `data/` 目录所有文件
2. 打包成 `littlefs.bin`
3. 烧录到 ESP32 的 LittleFS 分区（地址 0x003b0000）
4. 设备启动时，Tasmota 从 LittleFS 加载 `autoexec.be`

**启动顺序**：
```
1. Berry 系统初始化 (BRY: Berry initialized)
2. 检查 preinit.be (通常不存在)
3. 加载 autoexec.be
4. 执行 autoexec.be 中的代码
5. 注册驱动 (tasmota.add_driver)
6. WiFi 连接
7. MQTT 连接
```

### AWS IoT 证书要求

**Tasmota 特殊要求**：

| 项目 | 格式 | 大小 | 说明 |
|------|------|------|------|
| **私钥** | 32字节原始二进制（Base64编码） | 44字符 | **不是** PEM格式！ |
| **证书** | DER格式（Base64编码） | ~884字符 | **不是** PEM格式！ |
| **算法** | ECC P-256 (secp256r1) | - | **不支持** RSA 2048 |

**常见错误**：
```
❌ TLSKey: Certificate must be 32 bytes: 1191
   → 原因: 使用了完整的 PEM 私钥（227字节），而不是提取的32字节原始密钥

❌ TLSKey: Certificate must be 32 bytes: 2348
   → 原因: 使用了 RSA 私钥，必须使用 ECC P-256

✅ TLSKey1: 32, TLSKey2: 662
   → 正确: 32字节 ECC 私钥 + 662字节 DER 证书
```

---

## 文件系统结构

### 项目目录结构

```
Tasmota-1/
├── data/                           ← ✅ 主要开发目录（会被上传到设备）
│   ├── autoexec.be                 ← ✅ 启动脚本（必须在这里）
│   ├── lib/                        ← ✅ 自定义 Berry 模块
│   │   ├── aws_shadow.be
│   │   ├── mqtt_router.be
│   │   └── ...
│   └── [其他文件会一起上传]
│
├── berry_scripts/                  ← ⚠️ 开发用的脚本存放（不会自动上传）
│   ├── autoexec_aws_iot.be        ← 开发/备份用
│   ├── new_cert/                  ← 证书文件存放
│   │   ├── IoT-Gateway-000011.private.key
│   │   ├── IoT-Gateway-000011.cert.pem
│   │   └── IoT-Gateway-000011.raw.key
│   └── README_AWS_IOT_DEPLOYMENT.md
│
├── tasmota/berry_scripts/          ← ⚠️ Tasmota 源码示例（不会自动上传）
│   ├── autoexec.be                ← 仅当在 platformio_tasmota_cenv.ini 指定
│   └── improv.be
│
├── tasmota32/littlefs_data/        ← ❌ 无用目录，忽略它
│
├── platformio_tasmota_cenv.ini     ← 环境配置
├── BERRY_SCRIPTS_README.md         ← Berry 开发指南
└── TASMOTA_AWS_IOT_COMPLETE_GUIDE.md ← 本文档
```

### platformio_tasmota_cenv.ini 配置

```ini
[env:tasmota32s3-mi32]
extends                     = env:tasmota32_base
board                       = esp32s3-qio_qspi
build_flags                 = ${env:tasmota32_base.build_flags}
                              -DFIRMWARE_BLUETOOTH
                              -DUSE_MI_EXT_GUI
                              -DUSE_BERRY_ULP
                              -DCONFIG_BT_NIMBLE_NVS_PERSIST=y
                              -DARDUINO_USB_MODE=1
                              -DARDUINO_USB_CDC_ON_BOOT=1
                              -DOTA_URL='""'
lib_extra_dirs              = lib/libesp32, lib/libesp32_div, lib/lib_basic, lib/lib_i2c, lib/lib_div, lib/lib_ssl
lib_ignore                  = Micro-RTSP
                              ESP8266Audio
                              ESP8266SAM
                              TTGO TWatch Library
                              epdiy
                              NimBLE-Arduino
# ⚠️ custom_files_upload 只是把文件复制到 data/，不是必需的
# 直接在 data/ 目录编辑更简单
custom_files_upload         = tasmota/berry_scripts/improv.be
                              tasmota/berry_scripts/autoexec.be
upload_port                 = /dev/cu.usbmodem1101
monitor_port                = /dev/cu.usbmodem1101
upload_speed                = 460800
monitor_speed               = 115200
monitor_filters             = esp32_exception_decoder
```

**关键点**：
- `custom_files_upload` 会在编译时复制文件到 `data/`
- 最终上传的仍然是 `data/` 目录的全部内容
- **推荐做法**：直接在 `data/` 目录开发，忽略 `custom_files_upload`

---

## 证书准备

### 步骤 1: 从 AWS IoT 下载证书

在 AWS IoT Console 创建 Thing 时会下载：
```
IoT-Gateway-000011.private.key   # ECC P-256 私钥（PEM格式，227字节）
IoT-Gateway-000011.cert.pem      # 设备证书（PEM格式，~950字节）
AmazonRootCA1.pem                # 根证书（Tasmota内置，不需要）
```

### 步骤 2: 验证证书类型

```bash
# 检查证书算法（必须是 EC/prime256v1）
openssl x509 -in IoT-Gateway-000011.cert.pem -text -noout | grep "Public Key Algorithm"
# 输出: Public Key Algorithm: id-ecPublicKey

openssl x509 -in IoT-Gateway-000011.cert.pem -text -noout | grep "ASN1 OID"
# 输出: ASN1 OID: prime256v1

# 检查私钥类型
openssl ec -in IoT-Gateway-000011.private.key -text -noout | head -n 1
# 输出: Private-Key: (256 bit)
```

**如果不是 ECC P-256**：
- ❌ 不能使用 RSA 证书
- ❌ 不能使用 ECC P-384 或其他曲线
- ✅ 必须重新生成 ECC P-256 证书

### 步骤 3: 提取 32 字节原始私钥

**完整命令**：
```bash
openssl ec -in IoT-Gateway-000011.private.key -noout -text \
  | awk '/priv:/{flag=1;next}/pub:/{flag=0}flag' \
  | tr -d ' :\n' \
  | head -c 64 \
  | xxd -r -p \
  | base64

# 输出示例: uUdAhgUiqgOV78vdvHTBMpCbsPmTiF0zQ47YQveqdx0=
```

**命令解释**：
1. `openssl ec ... -text` - 以文本格式输出私钥详情
2. `awk '/priv:/...'` - 提取 `priv:` 和 `pub:` 之间的内容（16进制私钥）
3. `tr -d ' :\n'` - 删除空格、冒号、换行符
4. `head -c 64` - 取前64个字符（32字节的16进制表示）
5. `xxd -r -p` - 16进制转二进制
6. `base64` - 二进制转Base64

**验证结果**：
```bash
# Base64 解码后应该是 32 字节
echo "uUdAhgUiqgOV78vdvHTBMpCbsPmTiF0zQ47YQveqdx0=" | base64 -d | wc -c
# 输出: 32
```

### 步骤 4: 转换证书为 DER 格式

```bash
openssl x509 -in IoT-Gateway-000011.cert.pem \
  -outform DER \
  | base64 \
  | tr -d '\n'

# 输出示例（很长）: MIICkjCCAXqgAwIBAgIUfz7enrgMaOK7FybCLe...
```

**验证结果**：
```bash
# DER 格式证书通常 600-700 字节
openssl x509 -in IoT-Gateway-000011.cert.pem -outform DER | wc -c
# 输出: 662
```

### 步骤 5: 验证证书和私钥配对

```bash
# 提取证书的公钥
openssl x509 -in IoT-Gateway-000011.cert.pem -pubkey -noout > cert_pub.pem

# 从私钥导出公钥
openssl ec -in IoT-Gateway-000011.private.key -pubout > key_pub.pem

# 比较两个公钥（应该完全相同）
diff cert_pub.pem key_pub.pem
# 无输出 = 配对正确
```

### 步骤 6: 保存处理后的证书

**方法 1: 直接嵌入 Berry 脚本**（推荐）

```berry
# data/autoexec.be
var TLS_KEY_B64 = "uUdAhgUiqgOV78vdvHTBMpCbsPmTiF0zQ47YQveqdx0="
var TLS_CERT_B64 = "MIICkjCCAXqgAwIBAgIUfz7enrgMaOK7FybCLe..."
```

**方法 2: 保存为文件**（用于文件系统读取方案）

```bash
# 保存原始私钥（仅用于记录）
cat > berry_scripts/new_cert/IoT-Gateway-000011.raw.key << 'EOF'
-----BEGIN EC RAW PRIVATE KEY-----
uUdAhgUiqgOV78vdvHTBMpCbsPmTiF0zQ47YQveqdx0=
-----END EC RAW PRIVATE KEY-----
EOF

# 复制证书
cp berry_scripts/new_cert/IoT-Gateway-000011.cert.pem berry_scripts/new_cert/
```

---

## Berry 脚本开发

### 最小化可工作版本（v5.2.0）

**文件位置**: `data/autoexec.be`

```berry
# AWS IoT Stability Test - autoexec.be v5.2.0
# Purpose: Minimal configuration to avoid restart loops

var SCRIPT_VERSION = "5.2.0"
var DEVICE_ID = "IoT-Gateway-000011"
var MQTT_ENDPOINT = "a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com"

tasmota.log("==========================================", 2)
tasmota.log("AWS IoT Test v" + SCRIPT_VERSION, 2)
tasmota.log("==========================================", 2)

# ECC P-256 Certificate (32-byte raw key + DER cert)
var TLS_KEY_B64 = "uUdAhgUiqgOV78vdvHTBMpCbsPmTiF0zQ47YQveqdx0="
var TLS_CERT_B64 = "MIICkjCCAXqgAwIBAgIUfz7enrgMaOK7FybCLeBIdEKTBlUwDQYJKoZIhvcNAQELBQAwTTFLMEkGA1UECwxCQW1hem9uIFdlYiBTZXJ2aWNlcyBPPUFtYXpvbi5jb20gSW5jLiBMPVNlYXR0bGUgU1Q9V2FzaGluZ3RvbiBDPVVTMB4XDTI1MTAxNTEyNTY0MloXDTQ5MTIzMTIzNTk1OVowIjEgMB4GA1UEAwwXQVdTIElvVCBFQ0MgQ2VydGlmaWNhdGUwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAQI183bSkt+kFGCVIx6HzZmwTpym5nGwudBoe8/lJx+xtaxMc6WpUwqhYIZeQXYbCzZ1Nto7+a4lEhoxPwW0Sono2AwXjAfBgNVHSMEGDAWgBSl1rkIzW0DM/l9VlyGlJ6U5BPUhTAdBgNVHQ4EFgQUNiL3LQyLa3uNbKE4y9ZPdhKiKM8wDAYDVR0TAQH/BAIwADAOBgNVHQ8BAf8EBAMCB4AwDQYJKoZIhvcNAQELBQADggEBAKWbBvCviCl87/CdwoY1wO19FwOz1gC4ei6TGIxNwCOxF11HnTtSET/rfmbDQ0pXshi8EK/M1NHr8Gfxfo3H1BcKWJxhjIKFQ1COQpgMrhPVaJAvH4vPFKa6uEKrIqHqIIw6cwzkyRPio75bgT/SJWqb9ztUUNfJAjq6IImAUhgmSk+inMGBOLLKnf92bPubu+euiqGcCqghUsYTUr/xkvHExmtfWffV1uLkE7rUF7VByAqFYXUuZnmthDUREgA5GsFnVQtFwgy7l3+VouVtVqrLOCjqQmo50lBoWOKDY+mo9G+8fOypFW+0xzUmW+pPBeWdV8ReWlq06d/H/q9dCBA="

# Check and configure TLS certificates ONLY if needed
var result = tasmota.cmd("TLSKey", true)
var tlskey1 = result != nil && result.find('TLSKey1') != nil ? result['TLSKey1'] : -1

if tlskey1 != 32
    tasmota.log("Configuring TLS certificates...", 2)
    tasmota.cmd("TLSKey1 " + TLS_KEY_B64)
    tasmota.cmd("TLSKey2 " + TLS_CERT_B64)
    tasmota.log("✅ TLS configured", 2)
else
    tasmota.log("TLS already configured", 2)
end

tasmota.log("✅ Configuration complete", 2)

# ============================================================
# MQTT Stability Monitor - Simplified
# ============================================================

class MQTTStabilityMonitor
    var test_interval
    var message_count
    var last_publish_time
    var start_time

    def init(interval_sec)
        self.test_interval = interval_sec * 1000
        self.message_count = 0
        self.last_publish_time = tasmota.millis() + 15000  # First message after 15s
        self.start_time = tasmota.millis()
        tasmota.log("Stability Monitor started (30s interval)", 2)
    end

    def every_second()
        var now = tasmota.millis()

        if now - self.last_publish_time >= self.test_interval
            self.send_message()
            self.last_publish_time = now
        end
    end

    def send_message()
        self.message_count += 1
        var uptime = (tasmota.millis() - self.start_time) / 1000

        import json
        var payload = json.dump({
            "msg": self.message_count,
            "uptime": uptime
        })

        tasmota.cmd("Publish test/stability/" + DEVICE_ID + " " + payload)
        tasmota.log("📤 #" + str(self.message_count) + " @" + str(uptime) + "s", 2)

        if self.message_count % 10 == 0
            tasmota.log("📊 Stats: " + str(self.message_count) + " messages, " + str(uptime/60) + " min uptime", 2)
        end
    end
end

var monitor = MQTTStabilityMonitor(30)
tasmota.add_driver(monitor)

tasmota.log("🚀 Monitoring started - first message in 15s", 2)
tasmota.log("==========================================", 2)
```

### 关键设计要点

#### 1. 避免重启循环

**问题**：早期版本会不断重启（2-3次），因为：
- 在启动早期修改 MQTT 配置（MqttHost、MqttPort等）
- 每次修改配置都会标记 `CFG: CR changed`
- 累积到一定程度触发自动重启

**解决方案**：
```berry
# ❌ 错误做法 - 每次启动都修改配置
tasmota.cmd("MqttHost " + MQTT_ENDPOINT)  # 触发配置改变
tasmota.cmd("MqttPort 8883")               # 又触发改变
tasmota.cmd("MqttClient " + DEVICE_ID)     # 再次触发

# ✅ 正确做法 - 只在首次配置，或使用 Web Console 手动配置
# 在 autoexec.be 中不修改 MQTT 配置
# MQTT 配置通过 Web Console 一次性设置：
# MqttHost a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com
# MqttPort 8883
# MqttClient IoT-Gateway-000011
# SetOption103 1  (启用TLS)
# SetOption132 0  (使用内置 Amazon Root CA)
```

#### 2. 只在必要时配置证书

```berry
# 检查证书是否已配置
var result = tasmota.cmd("TLSKey", true)
var tlskey1 = result != nil && result.find('TLSKey1') != nil ? result['TLSKey1'] : -1

# 只在证书不存在时才写入
if tlskey1 != 32
    tasmota.cmd("TLSKey1 " + TLS_KEY_B64)
    tasmota.cmd("TLSKey2 " + TLS_CERT_B64)
end
```

#### 3. 延迟启动监控驱动

```berry
# 第一条消息延迟15秒发送，确保MQTT已连接
self.last_publish_time = tasmota.millis() + 15000
```

#### 4. 避免在启动早期调用复杂命令

**问题代码**（会导致崩溃）：
```berry
def every_50ms()
    var status = tasmota.cmd("Status 6", true)  # ❌ 在MQTT未初始化时调用
    if status["Status"]["MqttCount"] > 0
        # ...
    end
end
```

**正确做法**：
```berry
# 使用简单的定时器，不检查MQTT状态
def every_second()
    var now = tasmota.millis()
    if now - self.last_publish_time >= self.test_interval
        self.send_message()
    end
end
```

### Berry 驱动生命周期

Tasmota 会自动调用驱动的这些方法（如果存在）：

| 方法 | 调用频率 | 用途 |
|------|---------|------|
| `init()` | 一次（创建时） | 初始化变量 |
| `every_50ms()` | 每50毫秒 | 高频任务（GPIO、传感器） |
| `every_100ms()` | 每100毫秒 | 中频任务 |
| `every_200ms()` | 每200毫秒 | |
| `every_250ms()` | 每250毫秒 | |
| `every_second()` | 每秒 | 定时任务（推荐用于MQTT发布） |
| `mqtt_connected()` | MQTT连接时 | 订阅主题 |
| `mqtt_disconnected()` | MQTT断连时 | 清理资源 |
| `mqtt_data(topic, idx, data)` | 收到MQTT消息时 | 处理消息 |

**示例**：
```berry
class MyDriver
    def init()
        tasmota.log("Driver initialized", 2)
    end

    def every_second()
        tasmota.log("Tick", 2)
    end

    def mqtt_connected()
        tasmota.cmd("Subscribe my/topic")
    end

    def mqtt_data(topic, idx, data)
        tasmota.log("Received: " + topic + " = " + data, 2)
    end
end

var driver = MyDriver()
tasmota.add_driver(driver)
```

---

## 部署流程

### 前置要求

1. **硬件**：
   - ESP32-S3 开发板
   - USB 数据线
   - 已刷入 Tasmota 固件

2. **软件**：
   - PlatformIO Core
   - OpenSSL (用于证书处理)
   - 串口监视工具

3. **AWS**：
   - AWS IoT Core Thing 已创建
   - ECC P-256 证书已下载
   - 策略已附加并允许 `iot:Connect`, `iot:Publish`, `iot:Subscribe`

### 步骤 1: 准备证书

```bash
cd /Volumes/DeDeDisk/PestGG-Project/Tasmota-1

# 1. 提取32字节私钥
openssl ec -in berry_scripts/new_cert/IoT-Gateway-000011.private.key -noout -text \
  | awk '/priv:/{flag=1;next}/pub:/{flag=0}flag' \
  | tr -d ' :\n' \
  | head -c 64 \
  | xxd -r -p \
  | base64

# 复制输出: uUdAhgUiqgOV78vdvHTBMpCbsPmTiF0zQ47YQveqdx0=

# 2. 转换证书为DER Base64
openssl x509 -in berry_scripts/new_cert/IoT-Gateway-000011.cert.pem \
  -outform DER \
  | base64 \
  | tr -d '\n'

# 复制输出（很长）: MIICkjCCAXqg...
```

### 步骤 2: 创建 autoexec.be

```bash
# 编辑文件
nano data/autoexec.be
```

粘贴上面的 v5.2.0 脚本内容，修改：
- `DEVICE_ID` - 你的设备ID
- `MQTT_ENDPOINT` - 你的AWS IoT端点
- `TLS_KEY_B64` - 步骤1提取的32字节私钥
- `TLS_CERT_B64` - 步骤1转换的DER证书

保存文件。

### 步骤 3: 配置 MQTT（一次性，通过 Web Console）

访问设备 Web UI (http://设备IP)，在 Console 执行：

```
MqttHost a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com
MqttPort 8883
MqttClient IoT-Gateway-000011
SetOption103 1
SetOption132 0
```

**只需要配置一次**，配置会保存在 NVS 中。

### 步骤 4: 上传文件系统

```bash
cd /Volumes/DeDeDisk/PestGG-Project/Tasmota-1

# 上传 LittleFS 文件系统到设备
pio run -e tasmota32s3-mi32 -t uploadfs
```

**上传过程**：
```
Processing tasmota32s3-mi32
...
Building FS image from 'data' directory to .pio/build/tasmota32s3-mi32/littlefs.bin
/autoexec.be
Looking for upload port...
Uploading .pio/build/tasmota32s3-mi32/littlefs.bin
esptool v5.1.0
Connected to ESP32-S3
...
Wrote 327680 bytes (19260 compressed)
...
Success
```

### 步骤 5: 监控启动日志

```bash
# 监控串口输出
pio device monitor -e tasmota32s3-mi32
```

**成功启动日志**：
```
00:00:00.110 BRY: Berry initialized, RAM used 3401 bytes
00:00:00.117 BRY: No 'preinit.be'
00:00:00.227 ==========================================
00:00:00.228 AWS IoT Test v5.2.0
00:00:00.228 ==========================================
00:00:00.248 TLS already configured
00:00:00.249 ✅ Configuration complete
00:00:00.250 Stability Monitor started (30s interval)
00:00:00.251 🚀 Monitoring started - first message in 15s
00:00:00.252 ==========================================
00:00:00.252 BRY: Successfully loaded 'autoexec.be'
...
06:42:16.753 MQT: Connected
06:42:16.764 MQT: tele/tasmota_76DBC4/LWT = Online
...
06:42:56.944 MQT: test/stability/IoT-Gateway-000011 = {"msg":1,"uptime":45}
06:42:56.946 📤 #1 @45s
```

**关键成功标志**：
- ✅ `BRY: Successfully loaded 'autoexec.be'`
- ✅ `MQT: Connected`
- ✅ `📤 #1 @45s` - 第一条测试消息发送成功

---

## 验证测试

### 1. 检查 TLS 证书状态

在 Tasmota Web Console 执行：

```
TLSKey1
```

**期望输出**：
```json
{"TLSKey1":32,"TLSKey2":662}
```

**说明**：
- `TLSKey1: 32` - 私钥32字节（正确）
- `TLSKey2: 662` - 证书约662字节（ECC P-256 典型大小）

### 2. 检查 MQTT 配置

```
Status 6
```

**验证字段**：
```json
{
  "Status": {
    "MqttHost": "a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com",
    "MqttPort": 8883,
    "MqttClient": "IoT-Gateway-000011",
    "MqttCount": 1
  }
}
```

### 3. 验证 Berry 脚本运行

```
Br print("Berry is working")
```

**期望输出**：
```
Berry is working
```

### 4. 查看文件系统

```
Ufs
```

**期望输出**：
```json
{
  "UFS": {
    "Size": 320,
    "Used": 12,
    "Free": 308,
    "Files": ["autoexec.be"]
  }
}
```

### 5. AWS IoT Console 验证

**步骤**：

1. 打开 AWS IoT Console
2. 进入 **Test → MQTT test client**
3. 在 **Subscribe to a topic** 标签页
4. Topic filter 输入：`test/stability/#`
5. 点击 **Subscribe**

**期望看到消息**（每30秒一条）：
```json
{
  "msg": 1,
  "uptime": 45
}
```

### 6. 手动发送测试消息

在 Tasmota Web Console：

```
Publish test/manual {"message":"Hello from Tasmota","value":123}
```

在 AWS IoT Console 应该立即看到：
```json
{
  "message": "Hello from Tasmota",
  "value": 123
}
```

### 7. 稳定性测试

让设备运行至少 **30 分钟**，观察：

| 指标 | 预期值 | 说明 |
|------|--------|------|
| 消息发送 | 60+ 条 | 每30秒一条 |
| MQTT 连接 | 稳定 | 无断连/重连 |
| 设备重启 | 0 次 | 无自动重启 |
| 内存使用 | 稳定 | Berry HeapUsed ~6KB |
| WiFi 信号 | > -70 dBm | RSSI 稳定 |

**检查统计**：

每发送10条消息会自动打印：
```
📊 Stats: 10 messages, 5 min uptime
```

### 8. 压力测试（可选）

修改测试间隔为 5 秒：

```berry
# data/autoexec.be 中修改
var monitor = MQTTStabilityMonitor(5)  # 5秒间隔
```

运行1小时（720条消息），验证长期稳定性。

---

## 故障排除

### 问题 1: Berry 脚本未执行

**症状**：
```
00:00:00.132 BRY: No 'autoexec.be'
```

**原因**：
1. 文件不在 `data/` 目录
2. `uploadfs` 失败但没有报错
3. 文件名错误（区分大小写）

**诊断**：
```bash
# 1. 检查本地文件
ls -la data/autoexec.be

# 2. 检查设备文件系统（Web Console）
Ufs

# 3. 检查文件是否存在（Web Console）
Br import path; print(path.exists("/autoexec.be"))
```

**解决**：
```bash
# 确保文件在正确位置
cp your-script.be data/autoexec.be

# 重新上传
pio run -e tasmota32s3-mi32 -t uploadfs

# 重启设备
# Web Console: Restart 1
```

### 问题 2: 设备不断重启

**症状**：
```
00:00:00.252 BRY: Successfully loaded 'autoexec.be'
00:00:02.707 APP: Restarting
[重复多次]
```

**原因**：
- Berry 脚本中修改 MQTT 配置触发重启循环
- 启动早期调用 `Status 6` 等复杂命令导致崩溃

**解决**：
1. **移除所有 MQTT 配置命令**：
   ```berry
   # 删除这些行：
   # tasmota.cmd("MqttHost ...")
   # tasmota.cmd("MqttPort ...")
   # tasmota.cmd("MqttClient ...")
   ```

2. **通过 Web Console 一次性配置 MQTT**

3. **避免在启动早期调用状态查询**：
   ```berry
   # ❌ 不要在 every_50ms() 或启动时调用
   var status = tasmota.cmd("Status 6", true)

   # ✅ 延迟15秒后才开始工作
   self.initialized = false
   def every_second()
       if !self.initialized
           if tasmota.millis() > 15000
               self.initialized = true
           end
           return
       end
       # 正常工作...
   end
   ```

### 问题 3: TLS 证书错误

**症状**：
```
TLSKey: Certificate must be 32 bytes: 1191
```

**原因**：使用了完整的 PEM 私钥，而不是32字节原始密钥

**解决**：
```bash
# 重新提取32字节原始私钥
openssl ec -in device.key -noout -text \
  | awk '/priv:/{flag=1;next}/pub:/{flag=0}flag' \
  | tr -d ' :\n' \
  | head -c 64 \
  | xxd -r -p \
  | base64

# 验证长度
echo "提取的Base64字符串" | base64 -d | wc -c
# 必须输出: 32
```

### 问题 4: MQTT 连接失败

**症状**：
```
MQT: Attempting connection...
MQT: TLS connection error: -1005
MQT: Connect failed, rc -2
```

**错误码说明**：
- `-1005` = 证书验证失败
- `-2` = 连接失败

**原因排查**：

1. **检查证书配对**：
   ```bash
   openssl x509 -in cert.pem -pubkey -noout > cert_pub.pem
   openssl ec -in key.pem -pubout > key_pub.pem
   diff cert_pub.pem key_pub.pem
   # 应该没有输出
   ```

2. **检查证书状态（AWS Console）**：
   - 证书必须是 ACTIVE 状态
   - 证书必须附加了策略
   - 策略必须允许 `iot:Connect`

3. **检查证书有效期**：
   ```bash
   openssl x509 -in cert.pem -noout -dates
   # 确认未过期
   ```

4. **检查 Thing 名称和 ClientId 匹配**：
   ```
   # Web Console
   Status 6

   # 确认 MqttClient 与 AWS Thing 名称一致
   ```

### 问题 5: Berry 语法错误

**症状**：
```
BRY: Exception> 'syntax_error' ...
```

**常见错误**：

1. **字符串引号错误**：
   ```berry
   # ❌ 错误
   var str = "He said "hello""

   # ✅ 正确
   var str = "He said \"hello\""
   ```

2. **缺少 `end`**：
   ```berry
   # ❌ 错误
   if condition
       do_something()
   # 缺少 end

   # ✅ 正确
   if condition
       do_something()
   end
   ```

3. **方法定义错误**：
   ```berry
   # ❌ 错误（class 内部方法前需要 def）
   class MyClass
       my_method()
           return 1
       end
   end

   # ✅ 正确
   class MyClass
       def my_method()
           return 1
       end
   end
   ```

**调试方法**：
```
# Web Console 手动加载脚本
Br load("autoexec.be")

# 查看详细错误信息
```

### 问题 6: 进入 SafeBoot 模式

**症状**：
```
Project tasmota - Tasmota Version 15.0.1.5(release-safeboot)
WARNING This version does not support persistent settings
```

**原因**：设备连续崩溃10+次

**恢复步骤**：

1. **删除导致崩溃的 Berry 脚本**：
   ```bash
   # 创建空的 autoexec.be
   echo "" > data/autoexec.be

   # 重新上传
   pio run -e tasmota32s3-mi32 -t uploadfs
   ```

2. **或重刷完整固件**：
   ```bash
   pio run -e tasmota32s3-mi32 -t upload
   ```

3. **设备会自动退出 SafeBoot 模式**

4. **然后上传修复后的脚本**

---

## 最佳实践

### 1. 开发流程

**推荐工作流**：

```
1. 在 berry_scripts/ 开发和测试脚本
2. 测试通过后，复制到 data/
3. 上传文件系统
4. 验证日志
5. 如果失败，查看日志并修复
6. 重复步骤 2-5
```

**版本控制**：
```bash
# 添加版本号到脚本
var SCRIPT_VERSION = "5.2.0"
tasmota.log("Script v" + SCRIPT_VERSION, 2)

# 每次修改都更新版本号
# 便于从日志中识别运行的版本
```

### 2. 日志等级

Berry 日志等级：
```berry
tasmota.log("Debug message", 3)    # 调试（默认不显示）
tasmota.log("Info message", 2)     # 信息（推荐）
tasmota.log("Warning message", 1)  # 警告
tasmota.log("Error message", 0)    # 错误
```

**在 Web Console 调整日志级别**：
```
SerialLog 3  # 显示所有日志
SerialLog 2  # 显示信息、警告、错误
WebLog 3     # Web Console 日志级别
```

### 3. 内存管理

**检查内存使用**：
```
Status 4
```

**Berry 内存优化**：
```berry
# 1. 释放不再使用的变量
large_object = nil

# 2. 手动触发 GC（通常不需要）
import gc
gc.collect()

# 3. 避免在循环中创建大对象
def every_second()
    # ❌ 每秒创建新字符串
    tasmota.log("Uptime: " + str(tasmota.millis()), 2)

    # ✅ 减少日志频率
    if tasmota.millis() % 10000 == 0
        tasmota.log("Uptime: " + str(tasmota.millis()), 2)
    end
end
```

### 4. 错误处理

**使用 try/except**：
```berry
def safe_publish(topic, payload)
    try
        tasmota.cmd("Publish " + topic + " " + payload)
        tasmota.log("✅ Published to " + topic, 2)
        return true
    except .. as e, m
        tasmota.log("❌ Publish failed: " + str(m), 1)
        return false
    end
end
```

### 5. 配置管理

**使用配置文件**（可选）：

```berry
# data/config.json
{
  "device_id": "IoT-Gateway-000011",
  "mqtt_endpoint": "xxx.iot.ap-southeast-1.amazonaws.com",
  "test_interval": 30
}

# autoexec.be 中读取
import json
var f = open("config.json", "r")
var config = json.load(f.read())
f.close()

var DEVICE_ID = config["device_id"]
```

### 6. 安全建议

1. **不要将私钥提交到版本控制**：
   ```bash
   # .gitignore
   berry_scripts/new_cert/*.key
   data/autoexec.be  # 如果包含嵌入的私钥
   ```

2. **使用环境变量或配置文件**：
   ```berry
   # 生产环境从外部文件读取证书
   # 开发环境可以嵌入
   ```

3. **定期轮换证书**：
   - AWS IoT 证书默认有效期 ~25年
   - 建议每年轮换一次
   - 保留吊销证书的能力

### 7. 监控和告警

**在 AWS 中设置告警**：

1. 创建 CloudWatch 规则监控连接
2. 设置 SNS 通知
3. 监控消息发布频率

**在脚本中记录指标**：
```berry
def send_message()
    self.message_count += 1

    # 每100条消息上报统计
    if self.message_count % 100 == 0
        var stats = {
            "total_messages": self.message_count,
            "uptime_hours": tasmota.millis() / 3600000,
            "heap_free": tasmota.cmd("Status 4", true)["StatusMEM"]["Heap"]
        }
        tasmota.cmd("Publish metrics/stats " + json.dump(stats))
    end
end
```

---

## 快速参考

### 常用命令速查

| 功能 | 命令 | 说明 |
|------|------|------|
| **查看TLS状态** | `TLSKey1` | 应返回 `{"TLSKey1":32,"TLSKey2":662}` |
| **查看MQTT配置** | `Status 6` | 显示 MqttHost、MqttPort等 |
| **查看文件系统** | `Ufs` | 列出已上传的文件 |
| **测试Berry** | `Br print("test")` | 验证Berry可用 |
| **手动发布消息** | `Publish topic payload` | 测试MQTT发送 |
| **重启设备** | `Restart 1` | 软件重启 |
| **查看内存** | `Status 4` | 显示堆内存使用 |
| **设置日志级别** | `SerialLog 3` | 3=调试，2=信息 |

### OpenSSL 命令速查

```bash
# 提取32字节ECC私钥
openssl ec -in key.pem -noout -text | awk '/priv:/{flag=1;next}/pub:/{flag=0}flag' | tr -d ' :\n' | head -c 64 | xxd -r -p | base64

# 转换证书为DER Base64
openssl x509 -in cert.pem -outform DER | base64 | tr -d '\n'

# 验证证书类型
openssl x509 -in cert.pem -text -noout | grep "Public Key Algorithm"

# 验证证书和私钥配对
diff <(openssl x509 -in cert.pem -pubkey -noout) <(openssl ec -in key.pem -pubout)

# 查看证书有效期
openssl x509 -in cert.pem -noout -dates
```

### PlatformIO 命令速查

```bash
# 编译固件
pio run -e tasmota32s3-mi32

# 上传固件
pio run -e tasmota32s3-mi32 -t upload

# 上传文件系统
pio run -e tasmota32s3-mi32 -t uploadfs

# 监控串口
pio device monitor -e tasmota32s3-mi32

# 清理编译
pio run -e tasmota32s3-mi32 -t clean

# 组合命令（上传固件+文件系统+监控）
pio run -e tasmota32s3-mi32 -t upload && pio run -e tasmota32s3-mi32 -t uploadfs && pio device monitor -e tasmota32s3-mi32
```

### 项目文件清单

**必需文件**：
```
data/autoexec.be              ← Berry 启动脚本（必须）
platformio_tasmota_cenv.ini   ← 环境配置
```

**可选文件**：
```
data/lib/*.be                 ← 自定义模块
berry_scripts/*.be            ← 开发/备份脚本
berry_scripts/new_cert/*.key  ← 证书文件
BERRY_SCRIPTS_README.md       ← Berry 开发指南
TASMOTA_AWS_IOT_COMPLETE_GUIDE.md ← 本文档
```

---

## 附录

### A. 完整启动日志示例（成功）

```
ESP-ROM:esp32s3-20210327
Build:Mar 27 2021
rst:0x15 (USB_UART_CHIP_RESET),boot:0x8 (SPI_FAST_FLASH_BOOT)
Saved PC:0x421352ac
SPIWP:0xee
mode:DIO, clock div:1
load:0x3fce2820,len:0x1ac
load:0x403c8700,len:0x4
load:0x403c8704,len:0xb30
load:0x403cb700,len:0x2870
entry 0x403c8868

00:00:00.001 CMD: Using USB CDC
00:00:00.002 HDW: ESP32-S3 v0.2
00:00:00.056 UFS: FlashFS mounted with 4300 kB free
00:00:00.061 CFG: Loaded from File, Count 155
00:00:00.063 FRC: Some settings have been reset (2)
00:00:00.064 CFG: CR 426/699, Busy 0
00:00:00.067 TYA: Active=0
00:00:00.069 ROT: Mode 1
00:00:00.079 BRY: GC from 3981 to 3072 bytes, objects freed 5/17 (in 0 ms) - slots from 35/61 to 22/61
00:00:00.104 CFG: No '*.autoconf' file found
00:00:00.109 BRY: GC from 4389 to 3401 bytes, objects freed 7/33 (in 1 ms) - slots from 54/76 to 35/76
00:00:00.110 BRY: Berry initialized, RAM used 3401 bytes
00:00:00.117 BRY: No 'preinit.be'
00:00:00.131 SRC: Restart
00:00:00.135 Project tasmota - Tasmota Version 15.0.1.5(bluetooth)-3_3_0(2025-10-16T12:49:00)
00:00:00.136 DOM: Support 0 Device(s), 0 Button(s), 0 Switch(es) and 11 Sensors
00:00:00.148 CFG: Domoticz loaded from file
00:00:00.149 ETH: No ETH MDC and ETH MDIO GPIO defined
00:00:00.152 TFS: File 'mi32cfg' not found
00:00:00.152 M32: pre-init
00:00:00.212 BRY: GC from 7604 to 7242 bytes, objects freed 10/70 (in 0 ms) - slots from 90/122 to 72/122
00:00:00.227 ==========================================
00:00:00.228 AWS IoT Test v5.2.0
00:00:00.228 ==========================================
00:00:00.248 TLS already configured
00:00:00.249 ✅ Configuration complete
00:00:00.250 Stability Monitor started (30s interval)
00:00:00.251 🚀 Monitoring started - first message in 15s
00:00:00.252 ==========================================
00:00:00.252 BRY: Successfully loaded 'autoexec.be'
00:00:00.521 WIF: Checking connection...
00:00:00.522 WIF: Attempting connection...
00:00:01.619 WIF: Connecting to AP1 GetRichSuperMoney_2.4G Channel 6 BSSId 30:AA:E4:78:4C:04 in mode HT40 as tasmota-76DBC4-7108...
00:00:01.758 WIF: IPv4 192.168.1.3, mask 255.255.255.0, gateway 192.168.1.1
00:00:02.968 WIF: Checking connection...
00:00:02.969 WIF: Connected
00:00:02.990 M32: Init BLE device: tasmota-76DBC4-7108
00:00:02.991 NTP: Sync time...
00:00:03.093 WIF: DNS resolved '2.pool.ntp.org' (202.118.1.130) in 100 ms
00:00:03.192 RTC: UTC 2025-10-16T05:42:14Z, DST 2025-03-30T02:00:00, STD 2025-10-26T03:00:00
06:42:14.000 RTC: Synced by NTP
06:42:14.008 M32: Start passive scanning
06:42:14.067 HTP: Web server active on tasmota-76DBC4-7108 with IP address 192.168.1.3
06:42:14.468 WIF: IPv6 Local fe80::1220:baff:fe76:dbc4%st1
06:42:15.258 MQT: Attempting connection...
06:42:15.620 WIF: DNS resolved 'a1f8xc5wo59rp8-ats.iot.ap-southeast-1.amazonaws.com' (13.215.214.13) in 360 ms
06:42:16.751 MQT: TLS connected in 1129 ms, stack low mark 1920
06:42:16.753 MQT: MFLN not supported by TLS server
06:42:16.753 MQT: Connected
06:42:16.764 MQT: tele/tasmota_76DBC4/LWT = Online
06:42:16.772 MQT: cmnd/tasmota_76DBC4/POWER =
06:42:16.775 MQT: Subscribe to cmnd/tasmota_76DBC4/#
06:42:16.781 MQT: Subscribe to cmnd/tasmotas/#
06:42:16.786 MQT: Subscribe to cmnd/IoT-Gateway-000011_fb/#
06:42:16.798 MQT: tele/tasmota_76DBC4/INFO1 = {"Info1":{"Module":"ESP32S3","Version":"15.0.1.5(bluetooth)","FallbackTopic":"cmnd/IoT-Gateway-000011_fb/","GroupTopic":"cmnd/tasmotas/"}}
06:42:16.806 MQT: tele/tasmota_76DBC4/INFO2 = {"Info2":{"WebServerMode":"Admin","Hostname":"tasmota-76DBC4-7108","IPAddress":"192.168.1.3","IP6Global":"240e:390:9ad:ed40:1220:baff:fe76:dbc4","IP6Local":"fe80::1220:baff:fe76:dbc4%st1"}}
06:42:16.815 MQT: tele/tasmota_76DBC4/INFO3 = {"Info3":{"RestartReason":"Usb uart reset digital core","BootCount":134}}
06:42:56.944 MQT: test/stability/IoT-Gateway-000011 = {"msg":1,"uptime":45}
06:42:56.946 📤 #1 @45s
06:43:26.993 MQT: test/stability/IoT-Gateway-000011 = {"msg":2,"uptime":75}
06:43:26.997 📤 #2 @75s
```

### B. AWS IoT 策略示例

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:YOUR_ACCOUNT_ID:client/IoT-Gateway-*"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:YOUR_ACCOUNT_ID:topic/test/*",
        "arn:aws:iot:ap-southeast-1:YOUR_ACCOUNT_ID:topic/$aws/things/*/shadow/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:YOUR_ACCOUNT_ID:topicfilter/test/*",
        "arn:aws:iot:ap-southeast-1:YOUR_ACCOUNT_ID:topicfilter/$aws/things/*/shadow/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:YOUR_ACCOUNT_ID:topic/test/*",
        "arn:aws:iot:ap-southeast-1:YOUR_ACCOUNT_ID:topic/$aws/things/*/shadow/*"
      ]
    }
  ]
}
```

### C. 证书大小参考表

| 证书类型 | 私钥格式 | 私钥大小 | 证书格式 | 证书大小 | Tasmota支持 |
|---------|---------|---------|---------|---------|------------|
| **ECC P-256** | 原始32字节(Base64) | 44字符 | DER(Base64) | ~880字符 | ✅ 支持 |
| ECC P-256 | PEM | 227字节 | PEM | ~950字节 | ❌ 需转换 |
| ECC P-384 | 原始48字节 | 64字符 | DER | ~1100字符 | ❌ 不支持 |
| RSA 2048 | PKCS#8 | ~1191字节 | DER | ~1200字符 | ❌ 不支持 |

### D. 相关资源

**官方文档**：
- [Tasmota Berry 文档](https://tasmota.github.io/docs/Berry/)
- [Tasmota MQTT 配置](https://tasmota.github.io/docs/MQTT/)
- [AWS IoT Core 文档](https://docs.aws.amazon.com/iot/latest/developerguide/)
- [OpenSSL 命令参考](https://www.openssl.org/docs/man1.1.1/man1/)

**本项目文档**：
- `BERRY_SCRIPTS_README.md` - Berry 文件系统和开发指南
- `berry_scripts/README_AWS_IOT_DEPLOYMENT.md` - 详细部署文档

---

## 总结

本指南记录了从零开始配置 Tasmota ESP32 连接到 AWS IoT 的完整过程，包括：

✅ **关键知识点**：
- Berry 脚本必须放在 `data/` 目录
- AWS IoT 需要 32字节 ECC P-256 私钥（不是 PEM 格式）
- 避免在启动早期修改 MQTT 配置以防止重启循环

✅ **完整流程**：
1. 准备 ECC P-256 证书
2. 提取32字节原始私钥
3. 创建 `data/autoexec.be` 脚本
4. 通过 Web Console 配置 MQTT
5. 上传文件系统并验证

✅ **验证成功**：
- 设备稳定运行，无重启
- MQTT 连接成功（TLS 1.2）
- 定期发送测试消息（每30秒）
- 内存使用健康（Berry ~6KB）

**现在你可以**：
- 基于这个稳定的连接开发实际功能
- 添加 BLE 扫描和设备管理
- 实现 AWS IoT Device Shadow 同步
- 扩展为完整的 BLE Gateway

---

**版本**: 1.0
**最后更新**: 2025-10-16
**测试状态**: ✅ 完全验证通过
**适用环境**: Tasmota 15.0.1+, ESP32-S3, AWS IoT Core
