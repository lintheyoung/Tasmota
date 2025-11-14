#!/usr/bin/env python3
"""
AWS IoT Virtual Vibration Sensor Simulator - GUI Version
基于 main.py，添加 CustomTkinter 可视化界面
"""

import sys
import time
import logging
import threading
import queue
import json
import os
from datetime import datetime
from typing import Optional
from tkinter import filedialog

import customtkinter as ctk

from config import (
    SCRIPT_VERSION, GATEWAY_THING, MQTT_ENDPOINT, VIRTUAL_DEVICE,
    TELEMETRY_INTERVAL, LOG_LEVEL, CERT_FILE, KEY_FILE, ROOT_CA_FILE
)
from aws_iot_client import AWSIoTClient
from virtual_vibration_sensor import VirtualVibrationSensor


class DeviceSimulatorGUI(ctk.CTk):
    """设备模拟器 GUI 应用"""

    def __init__(self):
        super().__init__()

        self.title(f"AWS IoT 设备模拟器 v{SCRIPT_VERSION}")
        self.geometry("1000x700")

        # 应用状态
        self.is_running = False
        self.mqtt_client: Optional[AWSIoTClient] = None
        self.sensor: Optional[VirtualVibrationSensor] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.start_time = 0

        # 证书配置
        self.config_file = os.path.join(os.path.dirname(__file__), "gui_config.json")
        self.cert_path = CERT_FILE
        self.key_path = KEY_FILE
        self.ca_path = ROOT_CA_FILE
        self.thing_name = GATEWAY_THING  # AWS IoT Thing Name

        # 加载保存的配置
        self.load_config()

        # 日志队列（用于线程安全的日志传递）
        self.log_queue = queue.Queue()

        # 设置 CustomTkinter 外观
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 创建 GUI 组件
        self.create_widgets()

        # 设置日志处理器
        self.setup_logging()

        # 启动 UI 更新定时器
        self.update_ui()

    def create_widgets(self):
        """创建 GUI 组件"""

        # ============================================================
        # 1. 证书配置区域（紧凑布局）
        # ============================================================
        cert_frame = ctk.CTkFrame(self, corner_radius=8)
        cert_frame.pack(padx=8, pady=5, fill="x")

        ctk.CTkLabel(
            cert_frame,
            text="🔐 设备配置",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=3, padx=8, pady=3, sticky="w")

        # Thing Name
        ctk.CTkLabel(cert_frame, text="Thing Name:", font=ctk.CTkFont(size=11)).grid(row=1, column=0, padx=8, pady=2, sticky="w")
        self.thing_entry = ctk.CTkEntry(cert_frame, width=415, font=ctk.CTkFont(size=10))
        self.thing_entry.grid(row=1, column=1, columnspan=2, padx=3, pady=2, sticky="ew")
        self.thing_entry.insert(0, self.thing_name)

        # 证书文件
        ctk.CTkLabel(cert_frame, text="证书:", font=ctk.CTkFont(size=11)).grid(row=2, column=0, padx=8, pady=2, sticky="w")
        self.cert_entry = ctk.CTkEntry(cert_frame, width=350, font=ctk.CTkFont(size=10))
        self.cert_entry.grid(row=2, column=1, padx=3, pady=2)
        self.cert_entry.insert(0, self.cert_path)
        ctk.CTkButton(cert_frame, text="浏览", width=60, height=25, command=self.browse_cert, font=ctk.CTkFont(size=11)).grid(row=2, column=2, padx=5, pady=2)

        # 私钥文件
        ctk.CTkLabel(cert_frame, text="私钥:", font=ctk.CTkFont(size=11)).grid(row=3, column=0, padx=8, pady=2, sticky="w")
        self.key_entry = ctk.CTkEntry(cert_frame, width=350, font=ctk.CTkFont(size=10))
        self.key_entry.grid(row=3, column=1, padx=3, pady=2)
        self.key_entry.insert(0, self.key_path)
        ctk.CTkButton(cert_frame, text="浏览", width=60, height=25, command=self.browse_key, font=ctk.CTkFont(size=11)).grid(row=3, column=2, padx=5, pady=2)

        # CA 证书
        ctk.CTkLabel(cert_frame, text="CA:", font=ctk.CTkFont(size=11)).grid(row=4, column=0, padx=8, pady=2, sticky="w")
        self.ca_entry = ctk.CTkEntry(cert_frame, width=350, font=ctk.CTkFont(size=10))
        self.ca_entry.grid(row=4, column=1, padx=3, pady=2)
        self.ca_entry.insert(0, self.ca_path)
        ctk.CTkButton(cert_frame, text="浏览", width=60, height=25, command=self.browse_ca, font=ctk.CTkFont(size=11)).grid(row=4, column=2, padx=5, pady=2)

        # 验证和保存按钮
        button_frame = ctk.CTkFrame(cert_frame, fg_color="transparent")
        button_frame.grid(row=5, column=0, columnspan=3, padx=8, pady=5)

        ctk.CTkButton(
            button_frame,
            text="验证",
            width=80,
            height=25,
            command=self.validate_certificates,
            fg_color="green",
            hover_color="darkgreen",
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=3)

        ctk.CTkButton(
            button_frame,
            text="保存",
            width=80,
            height=25,
            command=self.save_config,
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=3)

        # ============================================================
        # 2. 状态栏（紧凑）
        # ============================================================
        status_frame = ctk.CTkFrame(self, corner_radius=8)
        status_frame.pack(padx=8, pady=5, fill="x")

        # 连接状态
        status_left = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_left.pack(side="left", padx=8, pady=5)

        ctk.CTkLabel(
            status_left,
            text="状态:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=3)

        self.status_label = ctk.CTkLabel(
            status_left,
            text="● 未连接",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.status_label.pack(side="left", padx=3)

        # 运行时间
        status_right = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_right.pack(side="right", padx=8, pady=5)

        ctk.CTkLabel(
            status_right,
            text="运行:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=3)

        self.uptime_label = ctk.CTkLabel(
            status_right,
            text="00:00:00",
            font=ctk.CTkFont(size=12)
        )
        self.uptime_label.pack(side="left", padx=3)

        # ============================================================
        # 3. 数据显示区域（紧凑，单行布局）
        # ============================================================
        data_frame = ctk.CTkFrame(self, corner_radius=8)
        data_frame.pack(padx=8, pady=5, fill="x")

        # 单行显示所有数据
        data_container = ctk.CTkFrame(data_frame, fg_color="transparent")
        data_container.pack(padx=8, pady=5, fill="x")

        # 传感器数据（左侧）
        self.vibration_label = ctk.CTkLabel(data_container, text="振动: --", font=ctk.CTkFont(size=11))
        self.vibration_label.pack(side="left", padx=5)

        self.battery_label = ctk.CTkLabel(data_container, text="电池: --%", font=ctk.CTkFont(size=11))
        self.battery_label.pack(side="left", padx=5)

        self.status_text_label = ctk.CTkLabel(data_container, text="状态: --", font=ctk.CTkFont(size=11))
        self.status_text_label.pack(side="left", padx=5)

        # 分隔符
        ctk.CTkLabel(data_container, text="|", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left", padx=5)

        # 统计信息（右侧）
        self.telemetry_label = ctk.CTkLabel(data_container, text="遥测: 0", font=ctk.CTkFont(size=11))
        self.telemetry_label.pack(side="left", padx=5)

        self.confirmed_label = ctk.CTkLabel(data_container, text="确认: 0", font=ctk.CTkFont(size=11))
        self.confirmed_label.pack(side="left", padx=5)

        self.success_rate_label = ctk.CTkLabel(data_container, text="成功率: --%", font=ctk.CTkFont(size=11))
        self.success_rate_label.pack(side="left", padx=5)

        self.event_count_label = ctk.CTkLabel(data_container, text="事件: 0", font=ctk.CTkFont(size=11))
        self.event_count_label.pack(side="left", padx=5)

        # 移除 commands_label（不常用）
        self.commands_label = None

        # ============================================================
        # 4. 日志区域（紧凑）
        # ============================================================
        log_frame = ctk.CTkFrame(self, corner_radius=8)
        log_frame.pack(padx=8, pady=5, fill="both", expand=True)

        ctk.CTkLabel(
            log_frame,
            text="实时日志",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(padx=8, pady=3, anchor="w")

        # 日志文本框（减小字体和边距）
        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Monaco", size=10),
            wrap="word"
        )
        self.log_text.pack(padx=8, pady=5, fill="both", expand=True)

        # ============================================================
        # 5. 控制按钮（紧凑）
        # ============================================================
        control_frame = ctk.CTkFrame(self, corner_radius=8)
        control_frame.pack(padx=8, pady=5, fill="x")

        # 左侧按钮
        left_buttons = ctk.CTkFrame(control_frame, fg_color="transparent")
        left_buttons.pack(side="left", padx=8, pady=5)

        self.start_button = ctk.CTkButton(
            left_buttons,
            text="▶ 启动",
            command=self.start_simulation,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=100,
            height=30,
            fg_color="green",
            hover_color="darkgreen"
        )
        self.start_button.pack(side="left", padx=3)

        self.stop_button = ctk.CTkButton(
            left_buttons,
            text="⏹ 停止",
            command=self.stop_simulation,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=100,
            height=30,
            state="disabled",
            fg_color="red",
            hover_color="darkred"
        )
        self.stop_button.pack(side="left", padx=3)

        # 右侧按钮
        right_buttons = ctk.CTkFrame(control_frame, fg_color="transparent")
        right_buttons.pack(side="right", padx=8, pady=5)

        ctk.CTkButton(
            right_buttons,
            text="清除日志",
            command=self.clear_log,
            font=ctk.CTkFont(size=11),
            width=80,
            height=30
        ).pack(side="left", padx=3)

        ctk.CTkButton(
            right_buttons,
            text="保存日志",
            command=self.save_log,
            font=ctk.CTkFont(size=11),
            width=80,
            height=30
        ).pack(side="left", padx=3)

        # 调试模式开关
        self.debug_var = ctk.BooleanVar(value=False)
        debug_switch = ctk.CTkSwitch(
            right_buttons,
            text="调试",
            variable=self.debug_var,
            command=self.toggle_debug_mode,
            font=ctk.CTkFont(size=11)
        )
        debug_switch.pack(side="left", padx=5)

    # ============================================================
    # 证书配置相关方法
    # ============================================================

    def browse_cert(self):
        """浏览选择证书文件"""
        filename = filedialog.askopenfilename(
            title="选择设备证书文件",
            filetypes=[("证书文件", "*.pem *.crt"), ("所有文件", "*.*")],
            initialdir=os.path.dirname(self.cert_path)
        )
        if filename:
            self.cert_entry.delete(0, "end")
            self.cert_entry.insert(0, filename)
            self.cert_path = filename

    def browse_key(self):
        """浏览选择私钥文件"""
        filename = filedialog.askopenfilename(
            title="选择私钥文件",
            filetypes=[("密钥文件", "*.key *.pem"), ("所有文件", "*.*")],
            initialdir=os.path.dirname(self.key_path)
        )
        if filename:
            self.key_entry.delete(0, "end")
            self.key_entry.insert(0, filename)
            self.key_path = filename

    def browse_ca(self):
        """浏览选择CA证书文件"""
        filename = filedialog.askopenfilename(
            title="选择CA证书文件",
            filetypes=[("证书文件", "*.pem *.crt"), ("所有文件", "*.*")],
            initialdir=os.path.dirname(self.ca_path)
        )
        if filename:
            self.ca_entry.delete(0, "end")
            self.ca_entry.insert(0, filename)
            self.ca_path = filename

    def validate_certificates(self):
        """验证证书文件"""
        self.thing_name = self.thing_entry.get()
        self.cert_path = self.cert_entry.get()
        self.key_path = self.key_entry.get()
        self.ca_path = self.ca_entry.get()

        errors = []

        # 检查文件是否存在
        if not os.path.exists(self.cert_path):
            errors.append(f"证书文件不存在: {self.cert_path}")
        if not os.path.exists(self.key_path):
            errors.append(f"私钥文件不存在: {self.key_path}")
        if not os.path.exists(self.ca_path):
            errors.append(f"CA证书文件不存在: {self.ca_path}")

        if errors:
            self.add_log("[错误] 证书验证失败:")
            for error in errors:
                self.add_log(f"  - {error}")
            return

        # 尝试验证证书内容
        try:
            import subprocess
            # 验证证书文件格式
            result = subprocess.run(
                ["openssl", "x509", "-in", self.cert_path, "-noout", "-subject"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                subject = result.stdout.strip()
                self.add_log(f"[成功] 证书验证通过")
                self.add_log(f"  证书主体: {subject}")

                # 验证证书有效期
                result = subprocess.run(
                    ["openssl", "x509", "-in", self.cert_path, "-noout", "-dates"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self.add_log(f"  {result.stdout.strip()}")
            else:
                self.add_log(f"[警告] 证书格式验证失败: {result.stderr}")
        except FileNotFoundError:
            self.add_log("[警告] 未找到 openssl 命令，跳过证书内容验证")
        except Exception as e:
            self.add_log(f"[警告] 证书验证过程出错: {e}")

        self.add_log("[提示] 所有证书文件路径有效")

    def save_config(self):
        """保存配置到文件"""
        self.thing_name = self.thing_entry.get()
        self.cert_path = self.cert_entry.get()
        self.key_path = self.key_entry.get()
        self.ca_path = self.ca_entry.get()

        config = {
            "thing_name": self.thing_name,
            "cert_path": self.cert_path,
            "key_path": self.key_path,
            "ca_path": self.ca_path
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.add_log(f"[成功] 配置已保存到: {self.config_file}")
        except Exception as e:
            self.add_log(f"[错误] 保存配置失败: {e}")

    def load_config(self):
        """从文件加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.thing_name = config.get("thing_name", self.thing_name)
                    self.cert_path = config.get("cert_path", self.cert_path)
                    self.key_path = config.get("key_path", self.key_path)
                    self.ca_path = config.get("ca_path", self.ca_path)
            except Exception as e:
                print(f"[警告] 加载配置失败: {e}")

    # ============================================================
    # 日志相关方法
    # ============================================================

    def setup_logging(self):
        """设置日志处理器"""
        # 创建自定义日志处理器，将日志发送到队列
        class QueueHandler(logging.Handler):
            def __init__(self, log_queue):
                super().__init__()
                self.log_queue = log_queue

            def emit(self, record):
                msg = self.format(record)
                self.log_queue.put(msg)

        # 添加队列处理器到根日志记录器
        gui_handler = QueueHandler(self.log_queue)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))

        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, LOG_LEVEL))
        root_logger.addHandler(gui_handler)

    def toggle_debug_mode(self):
        """切换调试模式"""
        logger = logging.getLogger()
        if self.debug_var.get():
            logger.setLevel(logging.DEBUG)
            self.add_log("[系统] 已启用调试模式")
        else:
            logger.setLevel(logging.INFO)
            self.add_log("[系统] 已关闭调试模式")

    def add_log(self, message: str):
        """添加日志到文本框"""
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    def clear_log(self):
        """清除日志"""
        self.log_text.delete("1.0", "end")
        self.add_log("[系统] 日志已清除")

    def save_log(self):
        """保存日志到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"simulator_log_{timestamp}.txt"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                log_content = self.log_text.get("1.0", "end")
                f.write(log_content)
            self.add_log(f"[系统] 日志已保存到: {filename}")
        except Exception as e:
            self.add_log(f"[错误] 保存日志失败: {e}")

    def start_simulation(self):
        """启动模拟器"""
        if self.is_running:
            return

        self.is_running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_label.configure(text="● 连接中...", text_color="yellow")
        self.start_time = time.time()

        # 在后台线程中运行模拟器
        self.worker_thread = threading.Thread(target=self.run_simulation_thread, daemon=True)
        self.worker_thread.start()

    def stop_simulation(self):
        """停止模拟器"""
        if not self.is_running:
            return

        self.is_running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

        # 断开连接
        if self.mqtt_client:
            self.mqtt_client.disconnect()

        self.status_label.configure(text="● 未连接", text_color="gray")

    def run_simulation_thread(self):
        """在后台线程中运行模拟器（复制 main.py 的逻辑）"""
        logger = logging.getLogger(__name__)

        try:
            # 更新配置（从界面获取）
            self.thing_name = self.thing_entry.get()
            self.cert_path = self.cert_entry.get()
            self.key_path = self.key_entry.get()
            self.ca_path = self.ca_entry.get()

            # 打印欢迎信息
            logger.info("=" * 60)
            logger.info(f"AWS IoT Test v{SCRIPT_VERSION}")
            logger.info("=" * 60)
            logger.info("🚀 BLE Gateway - Communication Stability Test")
            logger.info(f"📡 Gateway Thing: {self.thing_name}")
            logger.info(f"🔌 Virtual Device: {VIRTUAL_DEVICE['shadow_name']}")
            logger.info(f"   Device ID: {VIRTUAL_DEVICE['device_id']}")
            logger.info(f"📤 Telemetry interval: {TELEMETRY_INTERVAL} seconds")
            logger.info(f"📊 Statistics report: Every 5 minutes")
            logger.info("=" * 60)

            # 创建 AWS IoT MQTT 客户端（使用用户选择的配置）
            self.mqtt_client = AWSIoTClient(
                cert_file=self.cert_path,
                key_file=self.key_path,
                ca_file=self.ca_path,
                thing_name=self.thing_name
            )

            # 创建虚拟传感器
            self.sensor = VirtualVibrationSensor(
                mqtt_client=self.mqtt_client,
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
                self.mqtt_client.subscribe(
                    topic=self.sensor.delta_topic,
                    qos=1,
                    callback=lambda topic, payload, **kwargs: (
                        debug_callback(topic, payload),
                        self.sensor.handle_shadow_delta(payload.decode('utf-8'))
                    )
                )

                self.mqtt_client.subscribe(
                    topic=self.sensor.get_accepted_topic,
                    qos=1,
                    callback=lambda topic, payload, **kwargs: (
                        debug_callback(topic, payload),
                        self.sensor.handle_shadow_get_accepted(payload.decode('utf-8'))
                    )
                )

                self.mqtt_client.subscribe(
                    topic=self.sensor.update_accepted_topic,
                    qos=1,
                    callback=lambda topic, payload, **kwargs: (
                        debug_callback(topic, payload),
                        self.sensor.handle_shadow_update_accepted(payload.decode('utf-8'))
                    )
                )

                logger.info(f"📥 Subscribed to shadow topics: {VIRTUAL_DEVICE['shadow_name']}")
                logger.info(f"   Delta: {self.sensor.delta_topic}")
                logger.info(f"   GET Accepted: {self.sensor.get_accepted_topic}")
                logger.info(f"   Update Accepted: {self.sensor.update_accepted_topic}")

                # 初始化传感器
                self.sensor.mqtt_connected()

                # 更新 UI 状态
                self.after(0, lambda: self.status_label.configure(text="● 已连接", text_color="green"))

            self.mqtt_client.set_on_connected_callback(on_connected)

            # 连接到 AWS IoT Core
            if not self.mqtt_client.connect():
                logger.error("❌ Failed to connect to AWS IoT Core")
                self.is_running = False
                self.after(0, lambda: self.status_label.configure(text="● 连接失败", text_color="red"))
                self.after(0, lambda: self.start_button.configure(state="normal"))
                self.after(0, lambda: self.stop_button.configure(state="disabled"))
                return

            # 主循环：每秒执行传感器逻辑
            logger.info("\n✅ Configuration complete")
            logger.info("🔄 Starting main loop...\n")

            while self.is_running:
                # 每秒执行传感器逻辑
                self.sensor.every_second()
                time.sleep(1)

        except Exception as e:
            logger.error(f"❌ Error in simulation: {e}", exc_info=True)
            self.is_running = False
            self.after(0, lambda: self.status_label.configure(text="● 错误", text_color="red"))
            self.after(0, lambda: self.start_button.configure(state="normal"))
            self.after(0, lambda: self.stop_button.configure(state="disabled"))

        finally:
            # 清理资源
            logger.info("\n🧹 Cleaning up...")
            if self.mqtt_client:
                self.mqtt_client.disconnect()
            logger.info("👋 Shutdown complete\n")

    def update_ui(self):
        """更新 UI（定期调用）"""
        try:
            # 处理日志队列
            while not self.log_queue.empty():
                try:
                    log_message = self.log_queue.get_nowait()
                    self.log_text.insert("end", log_message + "\n")
                    self.log_text.see("end")
                except queue.Empty:
                    break

            # 更新运行时间
            if self.is_running and self.start_time > 0:
                elapsed = int(time.time() - self.start_time)
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                seconds = elapsed % 60
                self.uptime_label.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")

            # 更新传感器数据
            if self.sensor:
                # 传感器数据（紧凑显示）
                self.vibration_label.configure(text=f"振动: {self.sensor.vibration_level:.1f}")
                self.battery_label.configure(text=f"电池: {self.sensor.battery}%")
                self.status_text_label.configure(text=f"状态: {self.sensor.status}")

                # 统计信息（紧凑显示）
                self.telemetry_label.configure(text=f"遥测: {self.sensor.telemetry_sent}")
                self.confirmed_label.configure(text=f"确认: {self.sensor.telemetry_confirmed}")

                if self.sensor.telemetry_sent > 0:
                    success_rate = (self.sensor.telemetry_confirmed / self.sensor.telemetry_sent) * 100
                    self.success_rate_label.configure(text=f"成功率: {success_rate:.1f}%")
                else:
                    self.success_rate_label.configure(text="成功率: --%")

                self.event_count_label.configure(text=f"事件: {self.sensor.event_count}")

        except Exception as e:
            print(f"Error updating UI: {e}")

        # 每 100ms 更新一次
        self.after(100, self.update_ui)


def main():
    """主程序入口"""
    app = DeviceSimulatorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
