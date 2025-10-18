# 修复 Tasmota 设备时间设置

## 问题

当前设备日志显示的时间不正确：
```
16:05:04.324 📤 Telemetry: vibration=1.15, events=196
```

但实际时间应该是北京时间（UTC+8）。

---

## 解决方案

### 方法1: 通过 Tasmota Web Console 配置（推荐）

#### 步骤1: 访问设备 Web UI

浏览器打开设备IP地址（从串口日志或路由器查看）：
```
http://192.168.1.3  # 替换为你的设备IP
```

#### 步骤2: 进入 Console

点击顶部菜单 **Console**

#### 步骤3: 配置时区和NTP服务器

在 Console 中依次执行以下命令：

```bash
# 1. 设置时区为 UTC+8 (北京时间)
Timezone 99
TimeStd 0,0,0,1,8,480    # 标准时间：UTC+8 (480分钟)
TimeDst 0,0,0,1,8,480    # 夏令时：UTC+8 (480分钟，中国不使用夏令时)

# 2. 配置 NTP 服务器（使用中国的NTP服务器）
NtpServer1 ntp.aliyun.com
NtpServer2 ntp1.aliyun.com
NtpServer3 time.pool.aliyun.com

# 3. 立即同步时间
NtpSync
```

#### 步骤4: 验证时间

```bash
# 查看当前时间
Time
```

**预期输出：**
```json
{
  "Time": "2025-10-17T16:30:45+08:00",  # 应该是北京时间
  "Epoch": 1760717445,
  "Sunrise": "06:30",
  "Sunset": "18:00"
}
```

---

### 方法2: 修改 Berry 脚本配置（可选）

如果希望在设备启动时自动配置时区，可以在 `autoexec.be` 中添加配置。

**编辑文件：**
```bash
vim /Volumes/DeDeDisk/PestGG-Project/Tasmota-1/data/autoexec.be
```

**在文件开头（第36行之后）添加：**

```berry
# ============================================================
# Time Zone Configuration (Beijing Time UTC+8)
# ============================================================

# 检查时区是否已配置
var tz_result = tasmota.cmd("Timezone", true)
var current_tz = tz_result != nil && tz_result.find('Timezone') != nil ? tz_result['Timezone'] : 0

if current_tz != 99
    tasmota.log("Configuring timezone to UTC+8...", 2)

    # 设置时区为 UTC+8
    tasmota.cmd("Timezone 99")
    tasmota.cmd("TimeStd 0,0,0,1,8,480")
    tasmota.cmd("TimeDst 0,0,0,1,8,480")

    # 配置中国 NTP 服务器
    tasmota.cmd("NtpServer1 ntp.aliyun.com")
    tasmota.cmd("NtpServer2 ntp1.aliyun.com")
    tasmota.cmd("NtpServer3 time.pool.aliyun.com")

    # 立即同步时间
    tasmota.cmd("NtpSync")

    tasmota.log("✅ Timezone configured to UTC+8", 2)
else
    tasmota.log("Timezone already configured (UTC+8)", 2)
end

tasmota.log("✅ Configuration complete", 2)
```

**注意：** 这会在每次启动时检查并配置时区。

---

### 方法3: 通过配置文件永久保存（高级）

Tasmota 的时区配置会自动保存在 NVS（非易失性存储）中，所以方法1的配置是永久的，重启后仍然有效。

---

## 时区参数说明

### `Timezone` 命令

```bash
Timezone 99  # 使用自定义时区（必须配合 TimeStd 和 TimeDst）
```

**常用值：**
- `0` = UTC
- `8` = UTC+8 (但不支持夏令时调整)
- `99` = 自定义（推荐，灵活控制）

### `TimeStd` 和 `TimeDst` 命令格式

```
TimeStd 0,0,0,1,8,480
       │ │ │ │ │  └─ 时区偏移（分钟）: 480 = +8小时
       │ │ │ │ └──── 月份 (1-12)
       │ │ │ └────── 第几周 (0=最后一周, 1-4)
       │ │ └──────── 星期几 (0=周日, 1-6)
       │ └────────── 时间（小时）
       └──────────── 半球 (0=北半球, 1=南半球)
```

**中国时区配置：**
```bash
TimeStd 0,0,0,1,8,480  # 标准时间：UTC+8
TimeDst 0,0,0,1,8,480  # 夏令时：UTC+8（中国不使用夏令时，所以与标准时间相同）
```

---

## NTP 服务器选择

### 中国境内推荐的 NTP 服务器：

| 服务器 | 说明 | 延迟 |
|--------|------|------|
| `ntp.aliyun.com` | 阿里云 NTP（推荐） | < 10ms |
| `ntp1.aliyun.com` | 阿里云备用 | < 10ms |
| `time.pool.aliyun.com` | 阿里云时间池 | < 15ms |
| `ntp.tencent.com` | 腾讯 NTP | < 10ms |
| `ntp.ntsc.ac.cn` | 国家授时中心 | < 20ms |
| `cn.pool.ntp.org` | NTP 池（中国） | < 50ms |

### 配置命令：

```bash
NtpServer1 ntp.aliyun.com
NtpServer2 ntp1.aliyun.com
NtpServer3 time.pool.aliyun.com
```

---

## 验证配置

### 1. 查看当前时间

```bash
Time
```

**预期输出：**
```json
{
  "Time": "2025-10-17T16:30:45+08:00",
  "Epoch": 1760717445
}
```

### 2. 查看 RTC 状态

```bash
Status 1
```

**预期输出包含：**
```json
{
  "StatusPRM": {
    "Timezone": 99,
    "NtpServer1": "ntp.aliyun.com",
    "NtpServer2": "ntp1.aliyun.com",
    "NtpServer3": "time.pool.aliyun.com"
  }
}
```

### 3. 查看日志时间戳

重新发送命令后，设备日志应该显示正确的时间：

```log
16:30:45.123 📩 Delta received for vibration-sensor-001  # ✅ 正确的北京时间
```

---

## 完整配置脚本（一键执行）

在 Tasmota Web Console 中，复制粘贴以下所有命令：

```bash
Backlog Timezone 99; TimeStd 0,0,0,1,8,480; TimeDst 0,0,0,1,8,480; NtpServer1 ntp.aliyun.com; NtpServer2 ntp1.aliyun.com; NtpServer3 time.pool.aliyun.com; NtpSync
```

**说明：** `Backlog` 命令可以一次执行多个命令（用 `;` 分隔）。

---

## 常见问题

### Q1: 时间仍然不对

**检查网络连接：**
```bash
Status 5
```

**应该看到：**
```json
{
  "StatusNET": {
    "Hostname": "tasmota-76DBC4-7108",
    "IPAddress": "192.168.1.3",
    "Gateway": "192.168.1.1",
    "DNSServer": "192.168.1.1"
  }
}
```

**手动同步时间：**
```bash
NtpSync
```

**查看日志中的 NTP 同步状态：**
```log
RTC: Synced by NTP  # ✅ 成功
RTC: NTP sync failed  # ❌ 失败
```

---

### Q2: NTP 同步失败

**可能原因：**
1. 防火墙阻止 UDP 123 端口
2. 路由器未允许设备访问外网
3. NTP 服务器不可达

**解决方法：**

1. **测试 NTP 服务器连通性（从电脑）：**
   ```bash
   ping ntp.aliyun.com
   ```

2. **检查路由器防火墙设置**

3. **更换 NTP 服务器：**
   ```bash
   NtpServer1 time.windows.com  # 微软 NTP
   NtpServer2 time.google.com   # Google NTP
   ```

---

### Q3: 时区配置后重启失效

**检查配置是否保存：**
```bash
Status 0
```

**查找：**
```json
{
  "Status": {
    "SaveCount": 155,  # 配置保存次数
    "SaveAddress": "0x000F5000"
  }
}
```

**如果配置未保存，手动保存：**
```bash
SaveData
```

---

## 时间相关的 Berry 函数

如果需要在 Berry 脚本中使用时间：

```berry
# 获取当前时间（返回字典）
var rtc = tasmota.rtc()

# 示例输出：
# {
#   "local": 1760717445,      # 本地时间戳（Unix timestamp，秒）
#   "utc": 1760688645,        # UTC时间戳
#   "timezone": 28800,        # 时区偏移（秒，28800 = 8小时）
#   "restart": 123456         # 设备启动以来的秒数
# }

# 使用示例
var local_time = rtc['local']
var utc_time = rtc['utc']
var tz_offset = rtc['timezone']

tasmota.log("Local time: " + str(local_time), 2)
tasmota.log("UTC time: " + str(utc_time), 2)
tasmota.log("Timezone offset: " + str(tz_offset / 3600) + " hours", 2)
```

**在遥测数据中使用：**
```berry
# 当前 autoexec.be 中使用的时间戳
'timestamp': tasmota.rtc()['local']  # 本地时间戳（北京时间）
```

---

## 验证测试

### 测试脚本

配置完成后，发送测试命令并观察时间戳：

```bash
# 在 AWS IoT Console 发送
{
  "state": {
    "desired": {
      "cmd": {
        "action": "set_threshold",
        "vibration_threshold": 5.0
      },
      "reqId": "time-test-001"
    }
  }
}
```

**设备日志应该显示正确的时间：**
```log
16:35:12.123 📩 Delta received for vibration-sensor-001  # ✅ 北京时间
16:35:12.125 🎯 Command: {...} (reqId=time-test-001)
16:35:12.145 ✅ Command ACK sent: set_threshold
```

**ACK 消息中的时间戳也应该正确：**
```json
{
  "state": {
    "reported": {
      "timestamp": 1760717712,  # ✅ 对应北京时间 2025-10-17 16:35:12
      "lastAckedReqId": "time-test-001"
    }
  }
}
```

---

## 总结

**推荐配置步骤：**

1. **在 Tasmota Web Console 执行：**
   ```bash
   Backlog Timezone 99; TimeStd 0,0,0,1,8,480; TimeDst 0,0,0,1,8,480; NtpServer1 ntp.aliyun.com; NtpServer2 ntp1.aliyun.com; NtpServer3 time.pool.aliyun.com; NtpSync
   ```

2. **验证时间：**
   ```bash
   Time
   ```

3. **测试命令并观察日志时间**

**配置后效果：**
- ✅ 设备日志显示北京时间（UTC+8）
- ✅ 遥测数据中的时间戳正确
- ✅ 配置永久保存，重启后仍然有效

现在可以开始配置了！
