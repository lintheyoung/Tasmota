#!/bin/bash
# 快速启动脚本

echo "=========================================="
echo "AWS IoT Virtual Vibration Sensor"
echo "=========================================="
echo ""

# 检查证书文件
if [ ! -f "IoT-Gateway-000011.cert.pem" ]; then
    echo "❌ 错误: 证书文件不存在"
    echo "请确保以下文件存在："
    echo "  - IoT-Gateway-000011.cert.pem"
    echo "  - IoT-Gateway-000011.private.key"
    echo "  - AmazonRootCA1.pem"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv

    echo "📥 安装依赖..."
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo ""
echo "🚀 启动模拟器..."
echo ""

python3 main.py
