# -*- coding: utf-8 -*-
"""
Jack-2025-压测工具 (带界面与状态监控) - 最终稳定版

核心原理：
- 使用多线程并发拉取多个 RTSP 流，模拟多个客户端连接。
- 每个线程的核心逻辑是调用 `cv2.VideoCapture.grab()` 方法，
  该方法只从网络接收数据，不进行 CPU 密集型的视频解码，从而将资源消耗降至最低。
- 在每个拉流循环中加入可配置的休眠时间（监控间隔），以平衡监控频率和 CPU 占用。
- 持续的拉流请求会给摄像头造成持续的推流压力，从而测试其在长时间运行下的稳定性。

最新修改点：
- **v14: 彻底解决了日志混乱和交错问题。** 引入了线程安全的日志队列（QueueHandler 和 QueueListener）。所有监控线程将日志写入队列，由主GUI线程的监听器顺序地取出并更新界面。这保证了日志的原子性和顺序性，从根本上解决了并发写入导致的日志排版混乱。
- **v15: 优化了停止监控的用户体验。** 在点击“停止监控”后，不再直接阻塞GUI线程，而是使用一个专门的后台线程来等待所有监控线程结束。同时，在界面上动态显示剩余的正在关闭的线程数量，从而提供明确的进度反馈，避免给用户“界面卡死”的错觉。
- **v16: 优化了日志别名显示。** 将日志中的复杂IP别名替换为简洁的数字序号，使日志输出更加整洁美观。同时保留了IP信息用于日志文件的命名，方便追溯和管理。
- **v17: 改进了多实例日志别名显示。** 解决了当存在多个相同RTSP地址时日志别名重复的问题。现在别名采用 `[序号-拉取次数]` 格式，确保每个监控线程都有一个唯一的、易于追溯的别名。
- **v18: 修复了日志别名不连续和鼠标滚轮事件相互干扰的问题。** 现在日志别名采用连续的 `[线程-序号]` 格式，并且日志区和地址列表区的滚动功能互不影响。
- **v19: 修复了日志显示重复线程别名的问题。** 移除日志消息中多余的线程别名，使日志输出更简洁。
- **v20: 移除了GUI日志显示中的线程编号，但文件日志中保留。**
- **v21: 修复了上一版本的问题，现在文件日志中不显示线程编号，而GUI日志中正常显示。**
"""

import cv2
import time
import logging
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel
import sys
import re
import queue
import logging.handlers

# ==============================================================================
# 核心功能：RTSP流监控线程
# ==============================================================================
class RTSPStreamMonitor(threading.Thread):
    """
    负责在一个独立的线程中监控单个 RTSP 流。
    使用 cv2.VideoCapture 的 grab() 方法，只抓取帧而不解码，以最小化资源占用。
    """
    def __init__(self, url, display_alias, log_alias, stop_event=None, monitor_interval_ms=1000, fps_check_interval_s=30.0):
        super().__init__()
        self.url = url
        self.display_alias = display_alias # 用于日志显示的简洁别名
        self.log_alias = log_alias # 用于文件命名的别名
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.monitor_interval_ms = monitor_interval_ms
        self.reconnect_count = 0
        self.cap = None

        # 用于计算有效帧率
        self.frame_count = 0
        self.fps_check_interval = fps_check_interval_s  # 每隔X秒计算一次帧率
        self.last_fps_check_time = time.time()
        
        # 为每个线程创建独立的日志记录器，日志将通过 QueueHandler 发送到主队列
        self.logger = logging.getLogger(self.display_alias)
        self.logger.setLevel(logging.INFO)
        # 移除可能存在的旧处理器
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
        
        # 为每个线程设置独立的文件处理器，使用 log_alias 作为文件名
        log_path = "LOG"
        os.makedirs(log_path, exist_ok=True)
        log_filename = f"{self.log_alias}.log"
        log_filepath = os.path.join(log_path, log_filename)
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        # 文件日志格式：不包含线程编号
        file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        # 将文件处理器存储起来以便在线程停止时移除
        self.file_handler = file_handler


    def _log(self, level, message):
        """将日志信息发送给记录器，由记录器通过队列分发。"""
        # 线程日志使用独立的记录器写入文件和队列
        self.logger.log(level, message)

    def connect(self):
        """尝试连接到 RTSP 流。"""
        start_time = time.time()
        try:
            # 使用 cv2.CAP_FFMPEG 作为后端，这在 Windows 上通常效果更好
            self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            
            if not self.cap.isOpened():
                self._log(logging.ERROR, "连接失败：无法打开视频流。")
                return False
                
            # 尝试读取第一帧来验证连接是否真正可用
            ret, _ = self.cap.read()
            if not ret:
                self._log(logging.WARNING, "连接成功但无法读取第一帧，可能流已断开或URL无效。")
                self.disconnect()
                return False
            
            end_time = time.time()
            self.reconnect_count += 1
            self._log(logging.INFO, f"连接成功！耗时: {(end_time - start_time):.2f} 秒。")
            return True
        except Exception as e:
            self._log(logging.ERROR, f"连接时发生异常: {e}")
            return False

    def disconnect(self):
        """断开 RTSP 连接。"""
        if self.cap:
            self.cap.release()
            self.cap = None
            self._log(logging.INFO, "连接断开。")
            
    def cleanup_logger(self):
        """在线程结束时，清理日志处理器。"""
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)
            self.file_handler.close()
            
    def run(self):
        """线程的主循环。"""
        self._log(logging.INFO, "监控线程启动...")
        reconnect_delays = [1, 5, 10, 30, 60]  # 增加重连的尝试间隔
        reconnect_attempt_index = 0
        
        # 将毫秒转换为秒，用于 time.sleep()
        sleep_interval = self.monitor_interval_ms / 1000.0

        while not self.stop_event.is_set():
            if not self.cap or not self.cap.isOpened():
                self._log(logging.WARNING, "连接断开或未建立，正在尝试重新连接...")
                if self.connect():
                    reconnect_attempt_index = 0
                else:
                    delay = reconnect_delays[min(reconnect_attempt_index, len(reconnect_delays) - 1)]
                    self._log(logging.ERROR, f"连接失败，将在 {delay} 秒后重试...")
                    self.stop_event.wait(delay)
                    continue

            # 持续拉取数据，使用 grab() 方法只抓取帧，不解码
            if self.cap.grab():
                self.frame_count += 1
            else:
                self._log(logging.ERROR, "抓取帧失败，可能连接已断开，正在准备重连...")
                self.disconnect()

            # 检查是否需要更新帧率
            if time.time() - self.last_fps_check_time >= self.fps_check_interval:
                elapsed_time = time.time() - self.last_fps_check_time
                if elapsed_time > 0:
                    fps = self.frame_count / elapsed_time
                    self._log(logging.INFO, f"监控正常进行中... 有效帧率: {fps:.2f} FPS")
                self.frame_count = 0
                self.last_fps_check_time = time.time()
            
            # 引入休眠时间，降低CPU占用
            self.stop_event.wait(sleep_interval)

        self.disconnect()
        self.cleanup_logger()
        self._log(logging.INFO, "监控线程停止。")

# ==============================================================================
# GUI 界面
# ==============================================================================
class Application(tk.Tk):
    """主应用程序类，负责创建和管理 GUI 界面。"""
    def __init__(self):
        super().__init__()
        self.title("Jack-2025-压测工具")
        self.geometry("800x600")

        self.monitor_threads = []
        self.stop_events = {}
        self.url_counter = 0 # 用于URL列表的计数器
        self.thread_counter = 0 # 用于监控线程的计数器，用于生成连续的别名

        # 创建一个线程安全的日志队列
        self.log_queue = queue.Queue()
        # 创建一个 GUI 日志处理器，将日志放入队列
        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        logging.getLogger().addHandler(queue_handler)

        # 创建一个日志监听器，用于从队列中取出消息并更新 GUI
        self.log_listener = logging.handlers.QueueListener(self.log_queue, self._gui_log_handler())
        self.log_listener.start()

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def _gui_log_handler(self):
        """
        创建一个专门用于处理队列日志的处理器。
        此处理器只负责将日志消息派发到 GUI 文本框。
        """
        handler = logging.Handler()
        handler.setLevel(logging.INFO)
        handler.emit = self._log_to_gui_via_handler
        return handler

    def _log_to_gui_via_handler(self, record):
        """将日志记录发送到 GUI 文本框。"""
        try:
            # GUI日志格式：在消息前添加线程编号
            message = f"[{record.name}] {record.getMessage()}"
            level = record.levelno
            tag = None
            if level == logging.INFO:
                tag = 'info'
            elif level == logging.WARNING:
                tag = 'warning'
            elif level == logging.ERROR:
                tag = 'error'

            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, f"{message}\n", tag)
            self.log_text.configure(state='disabled')
            self.log_text.see(tk.END)
            self.update_idletasks() # 使用 update_idletasks 避免阻塞
        except Exception as e:
            # 捕获日志更新过程中的任何异常，并打印到控制台
            print(f"Error updating GUI log: {e}")

    def create_widgets(self):
        """创建界面上的所有控件。"""
        # 顶部输入和控制区域
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="RTSP 地址:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.url_entry = ttk.Entry(control_frame, width=50)
        self.url_entry.insert(0, "rtsp://127.0.0.1/live/1/1") # 添加默认地址
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        ttk.Label(control_frame, text="拉取次数:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.count_combobox = ttk.Combobox(control_frame, values=list(range(1, 11)), width=5, state="readonly")
        self.count_combobox.set(1)
        self.count_combobox.grid(row=0, column=3, padx=5, pady=5)

        self.add_button = ttk.Button(control_frame, text="添加地址", command=self.add_url)
        self.add_button.grid(row=0, column=4, padx=5, pady=5)
        
        ttk.Label(control_frame, text="监控间隔 (ms):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.interval_entry = ttk.Entry(control_frame, width=10)
        self.interval_entry.insert(0, "1000") # 默认1000ms
        self.interval_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        ttk.Label(control_frame, text="帧率统计间隔 (s):").grid(row=1, column=2, padx=5, pady=5, sticky='w')
        self.fps_interval_entry = ttk.Entry(control_frame, width=5)
        self.fps_interval_entry.insert(0, "30.0") # 默认30.0秒
        self.fps_interval_entry.grid(row=1, column=3, padx=5, pady=5, sticky='w')

        # 调整批量添加按钮的位置
        self.batch_add_button = ttk.Button(control_frame, text="批量添加", command=self.open_batch_add_window)
        self.batch_add_button.grid(row=1, column=4, padx=5, pady=5)

        control_frame.columnconfigure(1, weight=1)

        # 绑定右键菜单
        self.bind_right_click_menu(self.url_entry)

        # 中间地址列表区域
        ttk.Label(self, text="待监控地址列表:").pack(pady=(10, 0), padx=10, anchor='w')
        self.address_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=1, height=150) # 高度减半
        self.address_frame.pack(fill=tk.X, expand=False, padx=10, pady=5)
        self.address_frame.pack_propagate(False)

        self.canvas = tk.Canvas(self.address_frame, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self.address_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        # 修复鼠标滚轮无法滚动的问题: 只绑定 canvas，不使用 bind_all
        self.canvas.bind("<MouseWheel>", self._on_mousewheel) # For Windows and macOS
        self.canvas.bind("<Button-4>", self._on_mousewheel)  # For Linux scroll up
        self.canvas.bind("<Button-5>", self._on_mousewheel)  # For Linux scroll down

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.url_list_data = {}

        # 底部控制和日志区域
        bottom_frame = ttk.Frame(self, padding="10")
        bottom_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_button = ttk.Button(bottom_frame, text="启动监控", command=self.start_monitoring)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(bottom_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(bottom_frame, text="清空列表", command=self.clear_list)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(bottom_frame, text="", foreground="blue")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # 进度条
        self.progress_bar = ttk.Progressbar(bottom_frame, mode='determinate', length=100)
        self.progress_bar.pack(side=tk.LEFT, padx=10, pady=5, expand=True, fill=tk.X)
        self.progress_bar.pack_forget() # 默认隐藏

        ttk.Label(self, text="日志输出:").pack(pady=(0, 5), padx=10, anchor='w')
        self.log_text = scrolledtext.ScrolledText(self, height=25, state='disabled', wrap=tk.WORD, font=('Courier', 10)) # 高度增加一半
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log_text.tag_config('warning', foreground='orange')
        self.log_text.tag_config('error', foreground='red')

    def bind_right_click_menu(self, widget):
        """为指定的输入框或文本区绑定右键菜单。"""
        def show_menu(event):
            menu = tk.Menu(widget, tearoff=0)
            menu.add_command(label="剪切", command=lambda: widget.event_generate("<<Cut>>"))
            menu.add_command(label="复制", command=lambda: widget.event_generate("<<Copy>>"))
            menu.add_command(label="粘贴", command=lambda: widget.event_generate("<<Paste>>"))
            menu.post(event.x_root, event.y_root)
        widget.bind("<Button-3>", show_menu)
        
    def _on_mousewheel(self, event):
        """处理鼠标滚轮事件，实现滚动功能。"""
        # For Windows and macOS
        if sys.platform == "win32" or sys.platform == "darwin":
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        # For Linux
        elif sys.platform.startswith('linux'):
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")

    def open_batch_add_window(self):
        """打开批量添加地址的窗口。"""
        batch_window = Toplevel(self)
        batch_window.title("批量添加 RTSP 地址")
        batch_window.geometry("500x300")
        batch_window.resizable(False, False)

        frame = ttk.Frame(batch_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="请在下方粘贴 RTSP 地址列表，每行一个地址:").pack(pady=5, anchor='w')
        
        batch_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, height=10)
        batch_text.pack(fill=tk.BOTH, expand=True)

        # 绑定批量添加窗口的文本区右键菜单
        self.bind_right_click_menu(batch_text)
        
        def save_and_close():
            urls = batch_text.get("1.0", tk.END).strip().split('\n')
            
            added_count = 0
            for url in urls:
                url = url.strip()
                if not url:
                    continue
                
                count = int(self.count_combobox.get())
                self.add_url(url=url, count=count, is_batch=True)
                added_count += 1
            
            if added_count > 0:
                self.update_address_list_gui()

            batch_window.destroy()

        save_button = ttk.Button(frame, text="确认添加", command=save_and_close)
        save_button.pack(pady=10)

    def add_url(self, url=None, count=None, is_batch=False):
        """将用户输入的 RTSP 地址和拉取次数添加到待监控列表。"""
        if url is None:
            url = self.url_entry.get().strip()
        
        if count is None:
            count_str = self.count_combobox.get()
            if not url or not count_str:
                messagebox.showerror("错误", "RTSP 地址和拉取次数不能为空！")
                return
            count = int(count_str)
        
        # 提取IP地址作为别名，用于日志文件命名
        match = re.search(r'//(.*?)(?::|$|/)', url)
        log_alias_base = match.group(1) if match else "unknown"

        # 为每个地址生成唯一的URL别名，以支持添加重复的地址
        self.url_counter += 1
        unique_url_key = f"url_{self.url_counter}"
        
        self.url_list_data[unique_url_key] = {
            'url': url,
            'count': count,
            'log_alias_base': log_alias_base, # 将用于日志文件名
            'list_index': self.url_counter
        }
        if not is_batch:
            self.update_address_list_gui()
            self.url_entry.delete(0, tk.END)

    def update_address_list_gui(self):
        """刷新 GUI 上的地址列表显示。"""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        for unique_url_key, data in self.url_list_data.items():
            url = data['url']
            count = data['count']
            list_index = data['list_index']
            
            row_frame = ttk.Frame(self.scrollable_frame)
            row_frame.pack(fill=tk.X, padx=5, pady=2)
            
            ttk.Label(row_frame, text=f"序号: {list_index} | 地址: {url} | 拉取次数: {count}", anchor='w').pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            remove_button = ttk.Button(row_frame, text="移除", width=5, command=lambda alias=unique_url_key: self.remove_url(alias))
            remove_button.pack(side=tk.RIGHT, padx=(5,0))
            
    def remove_url(self, alias):
        """从列表中移除一个地址。"""
        if alias in self.url_list_data:
            del self.url_list_data[alias]
            self.update_address_list_gui()

    def clear_list(self):
        """清空所有待监控地址。"""
        self.url_list_data = {}
        self.url_counter = 0
        self.update_address_list_gui()

    def start_monitoring(self):
        """启动所有监控线程。"""
        if not self.url_list_data:
            messagebox.showwarning("警告", "请先添加至少一个 RTSP 地址！")
            return

        self.stop_monitoring() # 先停止旧的线程，以防万一

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.add_button.config(state=tk.DISABLED)
        self.batch_add_button.config(state=tk.DISABLED)
        self.clear_button.config(state=tk.DISABLED)
        
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        # 通过 logging.info 发送日志，将被队列处理器捕获
        logging.info("--- 监控任务启动 ---")
        self.status_label.config(text="监控中...")
        
        self.progress_bar.pack(side=tk.LEFT, padx=10, pady=5, expand=True, fill=tk.X)
        self.progress_bar.stop()
        
        self.thread_counter = 0 # 每次启动监控时，重置线程计数器

        try:
            monitor_interval = int(self.interval_entry.get())
            if monitor_interval < 10:
                 messagebox.showwarning("警告", "监控间隔不能小于10ms，已自动设置为10ms。")
                 monitor_interval = 10
        except ValueError:
             messagebox.showwarning("警告", "监控间隔输入无效，已自动设置为1000ms。")
             monitor_interval = 1000

        try:
            fps_check_interval = float(self.fps_interval_entry.get())
            if fps_check_interval <= 0:
                 messagebox.showwarning("警告", "帧率统计间隔必须大于0，已自动设置为1.0秒。")
                 fps_check_interval = 1.0
        except ValueError:
             messagebox.showwarning("警告", "帧率统计间隔输入无效，已自动设置为1.0秒。")
             fps_check_interval = 1.0

        for unique_url_key, data in self.url_list_data.items():
            url = data['url']
            count = data['count']
            log_alias_base = data['log_alias_base']
            list_index = data['list_index']
            
            # 为每个URL的每个线程启动一个stop_event
            self.stop_events[unique_url_key] = []
            
            for i in range(1, count + 1):
                # 日志中显示的别名，使用连续的线程编号
                self.thread_counter += 1
                display_alias = f"线程-{self.thread_counter}"
                # 用于日志文件名的别名，保留IP和连续编号
                log_alias = f"{log_alias_base}_{self.thread_counter}"
                
                stop_event = threading.Event()
                monitor_thread = RTSPStreamMonitor(
                    url=url,
                    display_alias=display_alias, # 传递用于显示的别名
                    log_alias=log_alias, # 传递用于文件名的别名
                    stop_event=stop_event,
                    monitor_interval_ms=monitor_interval,
                    fps_check_interval_s=fps_check_interval
                )
                self.monitor_threads.append(monitor_thread)
                self.stop_events[unique_url_key].append(stop_event)
                monitor_thread.start()
    
    def stop_monitoring(self):
        """
        [优化后] 停止所有监控线程。
        该方法只发送停止信号，然后启动一个新线程来等待旧线程结束，
        避免阻塞主 GUI 线程。
        """
        if not self.monitor_threads:
            return

        logging.info("--- 正在发送停止信号... ---")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.add_button.config(state=tk.DISABLED)
        self.batch_add_button.config(state=tk.DISABLED)
        self.clear_button.config(state=tk.DISABLED)
        
        # 显示进度条并设置为不确定模式
        self.progress_bar.pack(side=tk.LEFT, padx=10, pady=5, expand=True, fill=tk.X)
        self.progress_bar.config(mode='indeterminate')
        self.progress_bar.start(10)

        # 发送停止信号给所有线程
        for unique_url_key in self.stop_events:
            for stop_event in self.stop_events[unique_url_key]:
                stop_event.set()
        
        # 启动一个新线程来等待所有监控线程结束
        join_thread = threading.Thread(target=self._shutdown_worker)
        join_thread.start()

    def _shutdown_worker(self):
        """在新线程中执行阻塞的 join() 操作，并定期更新 GUI。"""
        while any(t.is_alive() for t in self.monitor_threads):
            alive_count = sum(1 for t in self.monitor_threads if t.is_alive())
            # 使用 self.after 将 GUI 更新调度回主线程
            self.after(500, lambda: self.status_label.config(text=f"正在停止... ({alive_count} 个线程)"),)
            time.sleep(0.5)

        # 等待所有线程真正退出，这一步是阻塞的，但它在后台线程中运行
        for thread in self.monitor_threads:
            if thread.is_alive():
                thread.join()
        
        # 所有线程都停止后，调度最终的 GUI 更新
        self.after(100, self._on_threads_stopped)

    def _on_threads_stopped(self):
        """在所有线程停止后，由主线程调用以更新 GUI 状态。"""
        self.monitor_threads = []
        self.stop_events = {}
        
        logging.info("--- 所有监控线程已停止。---")
        self.status_label.config(text="已停止")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.add_button.config(state=tk.NORMAL)
        self.batch_add_button.config(state=tk.NORMAL)
        self.clear_button.config(state=tk.NORMAL)
        
        # 停止并隐藏进度条
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        
    def on_closing(self):
        """处理窗口关闭事件，确保所有线程安全退出。"""
        self.stop_monitoring()
        # 停止日志监听器以进行干净关闭
        self.log_listener.stop()
        self.destroy()

if __name__ == "__main__":
    app = Application()
    app.mainloop()
