# Tasmota Berry 脚本开发指南

## 重要：Berry 脚本文件位置

### ⚠️ 关键规则

**要让 Berry 脚本在设备上执行，必须将文件放在 `data/` 目录下！**

```
Tasmota-1/
├── data/                          ← ✅ 在这里修改！uploadfs 会上传这个目录
│   ├── autoexec.be               ← ✅ 设备启动时自动执行
│   ├── preinit.be                ← ✅ 在 autoexec.be 之前执行（可选）
│   └── lib/                      ← ✅ 自定义 Berry 模块
│       ├── aws_shadow.be
│       ├── mqtt_router.be
│       └── ...
│
├── tasmota/berry_scripts/        ← ⚠️ 只有 custom_files_upload 中指定的文件会被复制
│   ├── autoexec.be               ← 需要在 platformio_tasmota_cenv.ini 中明确指定
│   └── improv.be
│
└── tasmota32/littlefs_data/      ← ❌ 这个目录不会被使用，忽略它！
```

## 文件系统上传流程

### 1. 编辑 Berry 脚本

在 `data/` 目录下创建或修改文件：

```bash
# 编辑主启动脚本
vim data/autoexec.be

# 编辑自定义模块
vim data/lib/my_module.be
```

### 2. 上传到设备

```bash
# 上传文件系统到设备
pio run -e tasmota32s3-mi32 -t uploadfs
```

**上传过程说明**：
1. PlatformIO 读取 `data/` 目录
2. 将所有文件打包成 `littlefs.bin`
3. 通过 esptool 烧录到设备的 LittleFS 分区（0x003b0000）
4. 设备自动重启
5. Tasmota 加载 Berry 脚本

### 3. 验证执行

设备重启后，在串口监视器或 Web 控制台查看日志：

```
00:00:00.090 BRY: Berry initialized, RAM used 3401 bytes
00:00:00.096 BRY: No 'preinit.be'                    ← preinit.be 不存在
00:00:00.157 BRY: Successfully loaded 'autoexec.be'  ← autoexec.be 成功加载
```

## 常见 Berry 脚本文件

### `autoexec.be` - 主启动脚本

设备启动时自动执行。用于：
- 初始化硬件
- 配置 MQTT
- 加载自定义模块
- 注册驱动和规则

示例：
```berry
# data/autoexec.be
import my_module

tasmota.log("System initializing...", 2)

# 配置 MQTT
tasmota.cmd("MqttHost my-broker.com")
tasmota.cmd("MqttPort 1883")

# 添加驱动
var driver = my_module.MyDriver()
tasmota.add_driver(driver)
```

### `preinit.be` - 预初始化脚本（可选）

在 `autoexec.be` 之前执行，通常用于：
- 设置系统级配置
- 初始化硬件引脚
- 加载核心模块

### `lib/` - 自定义模块目录

存放可重用的 Berry 模块：

```
data/lib/
├── aws_shadow.be          ← AWS IoT Device Shadow 客户端
├── mqtt_router.be         ← MQTT 消息路由
├── gateway_heartbeat.be   ← 心跳管理
└── util_map.be            ← 工具函数
```

在 `autoexec.be` 中导入：
```berry
import aws_shadow as AWSDeviceShadow
import mqtt_router as MQTTRouter

var shadow = AWSDeviceShadow("my-thing")
var router = MQTTRouter()
```

## 文件系统调试

### 查看设备上的文件

在 Tasmota Web 控制台执行：

```
Ufs
```

输出示例：
```json
{
  "UFS": {
    "Size": 320,
    "Used": 12,
    "Free": 308,
    "Files": ["autoexec.be", "lib/aws_shadow.be"]
  }
}
```

### 删除文件

```
UfsDelete autoexec.be
```

### 读取文件内容

```
UfsType autoexec.be
```

## `custom_files_upload` 配置（高级）

在 `platformio_tasmota_cenv.ini` 中配置：

```ini
[env:tasmota32s3-mi32]
custom_files_upload = tasmota/berry_scripts/improv.be
                      tasmota/berry_scripts/autoexec.be
```

**工作原理**：
1. 指定的文件会在编译时**复制**到 `data/` 目录
2. 然后和 `data/` 中已有的文件一起打包上传
3. 如果 `data/` 中已存在同名文件，会被覆盖

**⚠️ 注意**：
- 这个配置只是"复制文件到 data/"的快捷方式
- 最终上传的仍然是 `data/` 目录的内容
- **推荐直接编辑 `data/` 目录，而不是依赖 `custom_files_upload`**

## 完整开发工作流

### 开发新的 Berry 功能

```bash
# 1. 创建模块文件
vim data/lib/my_new_feature.be

# 2. 在 autoexec.be 中导入
vim data/autoexec.be
# 添加：import my_new_feature

# 3. 上传到设备
pio run -e tasmota32s3-mi32 -t uploadfs

# 4. 监视设备日志
pio device monitor -e tasmota32s3-mi32
```

### 快速测试修改

```bash
# 1. 修改脚本
vim data/autoexec.be

# 2. 上传
pio run -e tasmota32s3-mi32 -t uploadfs

# 3. 设备自动重启，查看日志
```

### 备份当前配置

```bash
# 备份整个 data 目录
cp -r data/ data_backup_$(date +%Y%m%d)/
```

## 常见错误

### ❌ `BRY: No 'autoexec.be'`

**原因**：文件不在 `data/` 目录，或 uploadfs 失败

**解决**：
```bash
# 确认文件存在
ls -la data/autoexec.be

# 重新上传
pio run -e tasmota32s3-mi32 -t uploadfs
```

### ❌ `BRY: Exception> 'import' can't find 'my_module'`

**原因**：模块文件不在 `data/lib/` 目录，或文件名不匹配

**解决**：
```bash
# 确认模块文件存在
ls -la data/lib/my_module.be

# sys.path() 必须包含 "lib"
# 在 autoexec.be 开头添加：
import sys
var p = sys.path()
if p.find("lib") == nil
    p.push("lib")
end
```

### ❌ 修改 `tasmota/berry_scripts/autoexec.be` 但没有生效

**原因**：这个目录的文件不会自动上传，除非在 `custom_files_upload` 中指定

**解决**：直接编辑 `data/autoexec.be`

## 目录对比总结

| 目录                          | 用途                              | 是否上传到设备 |
|-------------------------------|-----------------------------------|----------------|
| `data/`                       | **主要开发目录**，所有文件都会上传 | ✅ 是          |
| `tasmota/berry_scripts/`      | Tasmota 源码示例，仅指定文件上传  | ⚠️ 部分（需配置） |
| `tasmota32/littlefs_data/`    | **无用目录**，忽略                | ❌ 否          |
| `berry_scripts/`（项目根目录）| 自定义脚本存放，不会自动上传      | ❌ 否          |

## 最佳实践

1. ✅ **所有开发工作在 `data/` 目录进行**
2. ✅ **模块放在 `data/lib/` 目录**
3. ✅ **定期备份 `data/` 目录**
4. ✅ **使用版本控制（git）管理 `data/` 目录**
5. ✅ **在脚本中添加版本号和日志，方便调试**

示例版本化脚本：
```berry
# data/autoexec.be
var SCRIPT_VERSION = "1.2.3"
tasmota.log("autoexec.be v" + SCRIPT_VERSION + " starting...", 2)

# 你的代码...

tasmota.log("autoexec.be v" + SCRIPT_VERSION + " loaded successfully", 2)
```

---

**当前项目状态**：
- ✅ Hello World 脚本已在 `data/autoexec.be` 成功运行
- ✅ 设备日志显示脚本正常加载
- ✅ 文件系统上传流程已验证可用

**下一步**：
- 在 `data/autoexec.be` 中开发 AWS IoT 连接功能
- 使用正确的 32 字节 ECC 私钥
- 测试 MQTT TLS 连接稳定性
