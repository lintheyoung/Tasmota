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
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from config import (
    SCRIPT_VERSION, GATEWAY_THING, MQTT_ENDPOINT, VIRTUAL_DEVICE,
    TELEMETRY_INTERVAL, LOG_LEVEL
)
from aws_iot_client import AWSIoTClient
from virtual_vibration_sensor import VirtualVibrationSensor


class DeviceSimulatorGUI(ctk.CTk):
    """设备模拟器 GUI 应用"""

    def __init__(self):
        super().__init__()

        self.title(f"AWS IoT 设备模拟器 v{SCRIPT_VERSION}")
        self.geometry("950x750")

        # 应用状态
        self.is_running = False
        self.mqtt_client: Optional[AWSIoTClient] = None
        self.sensor: Optional[VirtualVibrationSensor] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.start_time = 0

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
        # 1. 顶部状态栏
        # ============================================================
        status_frame = ctk.CTkFrame(self, corner_radius=10)
        status_frame.pack(padx=10, pady=10, fill="x")

        # 连接状态
        status_left = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_left.pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(
            status_left,
            text="连接状态:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=5)

        self.status_label = ctk.CTkLabel(
            status_left,
            text="● 未连接",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.status_label.pack(side="left", padx=5)

        # 运行时间
        status_right = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_right.pack(side="right", padx=10, pady=10)

        ctk.CTkLabel(
            status_right,
            text="运行时间:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=5)

        self.uptime_label = ctk.CTkLabel(
            status_right,
            text="00:00:00",
            font=ctk.CTkFont(size=14)
        )
        self.uptime_label.pack(side="left", padx=5)

        # ============================================================
        # 2. 数据显示区域
        # ============================================================
        data_frame = ctk.CTkFrame(self, corner_radius=10)
        data_frame.pack(padx=10, pady=10, fill="x")

        # 左侧：传感器数据
        sensor_frame = ctk.CTkFrame(data_frame)
        sensor_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        ctk.CTkLabel(
            sensor_frame,
            text="传感器数据",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(padx=10, pady=5, anchor="w")

        self.vibration_label = ctk.CTkLabel(
            sensor_frame,
            text="振动值: --",
            font=ctk.CTkFont(size=12)
        )
        self.vibration_label.pack(padx=10, pady=5, anchor="w")

        self.battery_label = ctk.CTkLabel(
            sensor_frame,
            text="电池: --%",
            font=ctk.CTkFont(size=12)
        )
        self.battery_label.pack(padx=10, pady=5, anchor="w")

        self.status_text_label = ctk.CTkLabel(
            sensor_frame,
            text="状态: --",
            font=ctk.CTkFont(size=12)
        )
        self.status_text_label.pack(padx=10, pady=5, anchor="w")

        # 右侧：统计信息
        stats_frame = ctk.CTkFrame(data_frame)
        stats_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        ctk.CTkLabel(
            stats_frame,
            text="统计信息",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(padx=10, pady=5, anchor="w")

        self.telemetry_label = ctk.CTkLabel(
            stats_frame,
            text="遥测: 0",
            font=ctk.CTkFont(size=12)
        )
        self.telemetry_label.pack(padx=10, pady=5, anchor="w")

        self.commands_label = ctk.CTkLabel(
            stats_frame,
            text="命令: 0",
            font=ctk.CTkFont(size=12)
        )
        self.commands_label.pack(padx=10, pady=5, anchor="w")

        self.confirmed_label = ctk.CTkLabel(
            stats_frame,
            text="确认: 0",
            font=ctk.CTkFont(size=12)
        )
        self.confirmed_label.pack(padx=10, pady=5, anchor="w")

        self.success_rate_label = ctk.CTkLabel(
            stats_frame,
            text="成功率: --%",
            font=ctk.CTkFont(size=12)
        )
        self.success_rate_label.pack(padx=10, pady=5, anchor="w")

        self.event_count_label = ctk.CTkLabel(
            stats_frame,
            text="事件: 0",
            font=ctk.CTkFont(size=12)
        )
        self.event_count_label.pack(padx=10, pady=5, anchor="w")

        # 配置列权重
        data_frame.columnconfigure(0, weight=1)
        data_frame.columnconfigure(1, weight=1)

        # ============================================================
        # 3. 日志区域
        # ============================================================
        log_frame = ctk.CTkFrame(self, corner_radius=10)
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)

        ctk.CTkLabel(
            log_frame,
            text="实时日志",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(padx=10, pady=5, anchor="w")

        # 日志文本框
        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Monaco", size=11),
            wrap="word"
        )
        self.log_text.pack(padx=10, pady=10, fill="both", expand=True)

        # ============================================================
        # 4. 控制按钮
        # ============================================================
        control_frame = ctk.CTkFrame(self, corner_radius=10)
        control_frame.pack(padx=10, pady=10, fill="x")

        # 左侧按钮
        left_buttons = ctk.CTkFrame(control_frame, fg_color="transparent")
        left_buttons.pack(side="left", padx=10, pady=10)

        self.start_button = ctk.CTkButton(
            left_buttons,
            text="启动模拟器",
            command=self.start_simulation,
            font=ctk.CTkFont(size=13, weight="bold"),
            width=120,
            height=35
        )
        self.start_button.pack(side="left", padx=5)

        self.stop_button = ctk.CTkButton(
            left_buttons,
            text="停止模拟器",
            command=self.stop_simulation,
            font=ctk.CTkFont(size=13, weight="bold"),
            width=120,
            height=35,
            state="disabled",
            fg_color="red",
            hover_color="darkred"
        )
        self.stop_button.pack(side="left", padx=5)

        # 右侧按钮
        right_buttons = ctk.CTkFrame(control_frame, fg_color="transparent")
        right_buttons.pack(side="right", padx=10, pady=10)

        ctk.CTkButton(
            right_buttons,
            text="清除日志",
            command=self.clear_log,
            font=ctk.CTkFont(size=13),
            width=100,
            height=35
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            right_buttons,
            text="保存日志",
            command=self.save_log,
            font=ctk.CTkFont(size=13),
            width=100,
            height=35
        ).pack(side="left", padx=5)

        # 调试模式开关
        self.debug_var = ctk.BooleanVar(value=False)
        debug_switch = ctk.CTkSwitch(
            right_buttons,
            text="调试模式",
            variable=self.debug_var,
            command=self.toggle_debug_mode,
            font=ctk.CTkFont(size=13)
        )
        debug_switch.pack(side="left", padx=10)

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

            # 创建 AWS IoT MQTT 客户端
            self.mqtt_client = AWSIoTClient()

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
                # 传感器数据（直接访问属性）
                self.vibration_label.configure(text=f"振动值: {self.sensor.vibration_level:.1f}")
                self.battery_label.configure(text=f"电池: {self.sensor.battery}%")
                self.status_text_label.configure(text=f"状态: {self.sensor.status}")

                # 统计信息（直接访问属性）
                self.telemetry_label.configure(text=f"遥测: {self.sensor.telemetry_sent}")
                # 命令和确认统计需要从 sensor 的其他属性获取
                self.commands_label.configure(text=f"命令: 0")  # TODO: 添加命令统计
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
