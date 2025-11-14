# Thing Name 配置功能

## ✨ 新功能

现在 GUI 版本支持在界面中配置 **AWS IoT Thing Name**，无需修改代码！

## 🎯 使用方法

### 1. 启动 GUI
```bash
python3 gui_main.py
```

### 2. 配置 Thing Name

在顶部 **"🔐 设备配置"** 区域：

```
Thing Name: [IoT-Gateway-000011________]
证书:       [/path/to/cert.pem________] [浏览]
私钥:       [/path/to/key_____________] [浏览]
CA:         [/path/to/ca______________] [浏览]
[验证] [保存]
```

- **Thing Name 输入框**：输入你的 AWS IoT Thing 名称
- 示例：`IoT-Gateway-000011`, `MyDevice-001`, `Sensor-ABC123`

### 3. 保存配置

点击 **"保存"** 按钮，配置会保存到 `gui_config.json`：

```json
{
  "thing_name": "IoT-Gateway-000011",
  "cert_path": "/path/to/IoT-Gateway-000011.cert.pem",
  "key_path": "/path/to/IoT-Gateway-000011.private.key",
  "ca_path": "/path/to/AmazonRootCA1.pem"
}
```

### 4. 启动连接

点击 **"▶ 启动"** 按钮，模拟器会使用你配置的 Thing Name 连接到 AWS IoT。

## 📋 使用场景

### 场景 1：切换不同的设备

如果你有多个 AWS IoT Thing，可以快速切换：

```
设备 A：
Thing Name: IoT-Gateway-000011
证书: IoT-Gateway-000011.cert.pem
私钥: IoT-Gateway-000011.private.key

↓ 切换到

设备 B：
Thing Name: IoT-Gateway-000022
证书: IoT-Gateway-000022.cert.pem
私钥: IoT-Gateway-000022.private.key
```

### 场景 2：测试环境切换

```
开发环境：
Thing Name: Dev-Gateway-001

↓ 切换到

生产环境：
Thing Name: Prod-Gateway-001
```

### 场景 3：多设备同时测试

打开多个 GUI 窗口，每个配置不同的 Thing Name：

- 窗口 1: `IoT-Gateway-000011`
- 窗口 2: `IoT-Gateway-000012`
- 窗口 3: `IoT-Gateway-000013`

## 🔧 技术细节

### 修改的文件

1. **`gui_main.py`**
   - 添加 Thing Name 输入框（第 85-89 行）
   - 配置保存/加载支持 Thing Name（第 402-432 行）
   - 连接时使用动态 Thing Name（第 527-550 行）

2. **`aws_iot_client.py`**
   - `__init__` 新增 `thing_name` 参数（第 25 行）
   - 使用 `self.thing_name` 作为 MQTT client_id（第 78 行）

3. **`virtual_vibration_sensor.py`**
   - 从 mqtt_client 获取 Thing Name（第 41 行）
   - 动态生成 MQTT 主题（第 67-71 行）

### MQTT 主题格式

Thing Name 会用于构建所有 MQTT 主题：

```python
# 示例：Thing Name = "IoT-Gateway-000011"
delta_topic = "$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update/delta"
update_topic = "$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/update"
get_topic = "$aws/things/IoT-Gateway-000011/shadow/name/vibration-sensor-001/get"
```

### 证书匹配

⚠️ **重要**：Thing Name 必须与证书关联！

在 AWS IoT Console 中：
1. Thing: `IoT-Gateway-000011`
2. Certificate: 必须附加到这个 Thing
3. Policy: 必须允许这个 Thing 的操作

## ⚠️ 注意事项

### 1. Thing Name 与证书必须匹配

```
✅ 正确配置：
Thing Name: IoT-Gateway-000011
证书: IoT-Gateway-000011.cert.pem （已在 AWS 中关联）

❌ 错误配置：
Thing Name: IoT-Gateway-000022
证书: IoT-Gateway-000011.cert.pem （未关联，连接失败）
```

### 2. 证书文件命名建议

为了方便管理，建议证书文件名包含 Thing Name：

```
IoT-Gateway-000011.cert.pem
IoT-Gateway-000011.private.key
IoT-Gateway-000011.public.key

IoT-Gateway-000022.cert.pem
IoT-Gateway-000022.private.key
IoT-Gateway-000022.public.key
```

### 3. Policy 权限检查

确保 AWS IoT Policy 允许你的 Thing 操作：

```json
{
  "Effect": "Allow",
  "Action": [
    "iot:Connect",
    "iot:Publish",
    "iot:Subscribe",
    "iot:Receive"
  ],
  "Resource": [
    "arn:aws:iot:region:account:client/IoT-Gateway-*",
    "arn:aws:iot:region:account:topic/$aws/things/IoT-Gateway-*/shadow/*"
  ]
}
```

### 4. 命令行版本

命令行版本 (`main.py`) 仍然使用 `config.py` 中的配置：

```python
# config.py
GATEWAY_THING = "IoT-Gateway-000011"  # 修改这里
```

## 🐛 故障排查

### 问题：连接失败

**可能原因**：
1. Thing Name 拼写错误
2. 证书未关联到该 Thing
3. Policy 权限不足

**解决方法**：
```bash
# 1. 检查 AWS IoT Console
# 验证 Thing Name 是否存在

# 2. 检查证书关联
# Thing → Certificates → 确认证书已附加

# 3. 查看日志
# GUI 日志区域会显示详细错误信息
```

### 问题：Shadow 主题订阅失败

**可能原因**：Thing Name 与 Shadow 不匹配

**解决方法**：
```
确保 Shadow 主题格式正确：
$aws/things/{YourThingName}/shadow/name/vibration-sensor-001/...
                ^^^^^^^^^^^^^^^^
                必须匹配你的 Thing Name
```

## 📚 相关文档

- [证书切换功能](CERTIFICATE_SWITCHING.md)
- [GUI 布局说明](GUI_LAYOUT.md)
- [主 README](README.md)
- [AWS IoT Thing 文档](https://docs.aws.amazon.com/iot/latest/developerguide/thing-registry.html)

## 🎉 功能优势

✅ **灵活切换** - 无需修改代码，界面配置即可
✅ **配置持久化** - 保存到 JSON 文件，下次自动加载
✅ **多设备测试** - 可同时运行多个实例测试不同设备
✅ **完全兼容** - 命令行版本仍然可用，不受影响
✅ **向后兼容** - 不填 Thing Name 则使用默认值

## 📝 版本历史

### v6.2.0-python-thing-config (2025-11-14)
- ✅ 添加 GUI Thing Name 配置功能
- ✅ 支持动态 Thing Name 连接
- ✅ 配置保存/加载支持 Thing Name
- ✅ 完全向后兼容
