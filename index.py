# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel
import threading
import os
import cv2
import sys
import time
import re
import numpy as np
import logging
import queue
import logging.handlers

class RTSPStreamMonitor(threading.Thread):
    def __init__(self, url, display_alias, log_alias, stop_event=None, monitor_interval_ms=1000, fps_check_interval_s=30.0):
        super().__init__()
        self.url = url
        self.display_alias = display_alias
        self.log_alias = log_alias
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.monitor_interval_ms = monitor_interval_ms
        self.reconnect_count = 0
        self.cap = None

        self.frame_count = 0
        self.fps_check_interval = fps_check_interval_s
        self.last_fps_check_time = time.time()
        
        self.logger = logging.getLogger(self.display_alias)
        self.logger.setLevel(logging.INFO)
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
        
        log_path = "LOG"
        os.makedirs(log_path, exist_ok=True)
        log_filename = f"{self.log_alias}.log"
        log_filepath = os.path.join(log_path, log_filename)
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        self.file_handler = file_handler

    def _log(self, level, message):
        self.logger.log(level, message)

    def connect(self):
        start_time = time.time()
        try:
            self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            
            if not self.cap.isOpened():
                self._log(logging.ERROR, "连接失败：无法打开视频流。")
                return False
                
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
        if self.cap:
            self.cap.release()
            self.cap = None
            self._log(logging.INFO, "连接断开。")
            
    def cleanup_logger(self):
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)
            self.file_handler.close()
            
    def run(self):
        self._log(logging.INFO, "监控线程启动...")
        reconnect_delays = [1, 5, 10, 30, 60]
        reconnect_attempt_index = 0
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

            if self.cap.grab():
                self.frame_count += 1
            else:
                self._log(logging.ERROR, "抓取帧失败，可能连接已断开，正在准备重连...")
                self.disconnect()

            if time.time() - self.last_fps_check_time >= self.fps_check_interval:
                elapsed_time = time.time() - self.last_fps_check_time
                if elapsed_time > 0:
                    fps = self.frame_count / elapsed_time
                    self._log(logging.INFO, f"监控正常进行中... 有效帧率: {fps:.2f} FPS")
                self.frame_count = 0
                self.last_fps_check_time = time.time()
            
            self.stop_event.wait(sleep_interval)

        self.disconnect()
        self.cleanup_logger()
        self._log(logging.INFO, "监控线程停止。")

class StressTestFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.monitor_threads = []
        self.stop_events = {}
        self.url_counter = 0
        self.thread_counter = 0

        self.log_queue = queue.Queue()
        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        logging.getLogger().addHandler(queue_handler)

        self.log_listener = logging.handlers.QueueListener(self.log_queue, self._gui_log_handler())
        self.log_listener.start()
        
        self.create_widgets()
        
    def _gui_log_handler(self):
        handler = logging.Handler()
        handler.setLevel(logging.INFO)
        handler.emit = self._log_to_gui_via_handler
        return handler

    def _log_to_gui_via_handler(self, record):
        try:
            # 核心修改：在日志消息前添加时间戳
            timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]", time.localtime(record.created))
            message = f"{timestamp} [{record.name}] {record.getMessage()}"
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
            self.update_idletasks()
        except Exception as e:
            print(f"Error updating GUI log: {e}")

    def create_widgets(self):
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="RTSP 地址:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.url_entry = ttk.Entry(control_frame, width=50)
        self.url_entry.insert(0, "rtsp://192.168.16.3/live/1/1")
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        ttk.Label(control_frame, text="拉取次数:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.count_combobox = ttk.Combobox(control_frame, values=list(range(1, 11)), width=5, state="readonly")
        self.count_combobox.set(1)
        self.count_combobox.grid(row=0, column=3, padx=5, pady=5)

        self.add_button = ttk.Button(control_frame, text="添加地址", command=self.add_url)
        self.add_button.grid(row=0, column=4, padx=5, pady=5)
        
        ttk.Label(control_frame, text="监控间隔 (ms):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.interval_entry = ttk.Entry(control_frame, width=10)
        self.interval_entry.insert(0, "1000")
        self.interval_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        ttk.Label(control_frame, text="帧率统计间隔 (s):").grid(row=1, column=2, padx=5, pady=5, sticky='w')
        self.fps_interval_entry = ttk.Entry(control_frame, width=5)
        self.fps_interval_entry.insert(0, "30.0")
        self.fps_interval_entry.grid(row=1, column=3, padx=5, pady=5, sticky='w')

        self.batch_add_button = ttk.Button(control_frame, text="批量添加", command=self.open_batch_add_window)
        self.batch_add_button.grid(row=1, column=4, padx=5, pady=5)

        control_frame.columnconfigure(1, weight=1)

        self.bind_right_click_menu(self.url_entry)

        ttk.Label(self, text="待监控地址列表:").pack(pady=(10, 0), padx=10, anchor='w')
        self.address_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=1, height=150)
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
        
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.url_list_data = {}

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
        
        self.progress_bar = ttk.Progressbar(bottom_frame, mode='determinate', length=100)
        self.progress_bar.pack(side=tk.LEFT, padx=10, pady=5, expand=True, fill=tk.X)
        self.progress_bar.pack_forget()

        ttk.Label(self, text="日志输出:").pack(pady=(0, 5), padx=10, anchor='w')
        self.log_text = scrolledtext.ScrolledText(self, height=25, state='disabled', wrap=tk.WORD, font=('Courier', 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log_text.tag_config('warning', foreground='orange')
        self.log_text.tag_config('error', foreground='red')

    def bind_right_click_menu(self, widget):
        def show_menu(event):
            menu = tk.Menu(widget, tearoff=0)
            menu.add_command(label="剪切", command=lambda: widget.event_generate("<<Cut>>"))
            menu.add_command(label="复制", command=lambda: widget.event_generate("<<Copy>>"))
            menu.add_command(label="粘贴", command=lambda: widget.event_generate("<<Paste>>"))
            menu.post(event.x_root, event.y_root)
        widget.bind("<Button-3>", show_menu)
        
    def _on_mousewheel(self, event):
        if sys.platform == "win32" or sys.platform == "darwin":
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        elif sys.platform.startswith('linux'):
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")

    def open_batch_add_window(self):
        batch_window = Toplevel(self.winfo_toplevel())
        batch_window.title("批量添加 RTSP 地址")
        batch_window.geometry("500x300")
        batch_window.resizable(False, False)

        frame = ttk.Frame(batch_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="请在下方粘贴 RTSP 地址列表，每行一个地址:").pack(pady=5, anchor='w')
        
        batch_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, height=10)
        batch_text.pack(fill=tk.BOTH, expand=True)

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
        if url is None:
            url = self.url_entry.get().strip()
        
        if count is None:
            count_str = self.count_combobox.get()
            if not url or not count_str:
                messagebox.showerror("错误", "RTSP 地址和拉取次数不能为空！")
                return
            count = int(count_str)
        
        match = re.search(r'//(.*?)(?::|$|/)', url)
        log_alias_base = match.group(1) if match else "unknown"

        self.url_counter += 1
        unique_url_key = f"url_{self.url_counter}"
        
        self.url_list_data[unique_url_key] = {
            'url': url,
            'count': count,
            'log_alias_base': log_alias_base,
            'list_index': self.url_counter
        }
        if not is_batch:
            self.update_address_list_gui()
            self.url_entry.delete(0, tk.END)

    def update_address_list_gui(self):
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
        if alias in self.url_list_data:
            del self.url_list_data[alias]
            self.update_address_list_gui()

    def clear_list(self):
        self.url_list_data = {}
        self.url_counter = 0
        self.update_address_list_gui()

    def start_monitoring(self):
        if not self.url_list_data:
            messagebox.showwarning("警告", "请先添加至少一个 RTSP 地址！")
            return

        self.stop_monitoring()

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.add_button.config(state=tk.DISABLED)
        self.batch_add_button.config(state=tk.DISABLED)
        self.clear_button.config(state=tk.DISABLED)
        
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        logging.info("--- 监控任务启动 ---")
        self.status_label.config(text="监控中...")
        
        self.progress_bar.pack(side=tk.LEFT, padx=10, pady=5, expand=True, fill=tk.X)
        self.progress_bar.stop()
        
        self.thread_counter = 0

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
            
            self.stop_events[unique_url_key] = []
            
            for i in range(1, count + 1):
                self.thread_counter += 1
                display_alias = f"线程-{self.thread_counter}"
                log_alias = f"{log_alias_base}_{self.thread_counter}"
                
                stop_event = threading.Event()
                monitor_thread = RTSPStreamMonitor(
                    url=url,
                    display_alias=display_alias,
                    log_alias=log_alias,
                    stop_event=stop_event,
                    monitor_interval_ms=monitor_interval,
                    fps_check_interval_s=fps_check_interval
                )
                self.monitor_threads.append(monitor_thread)
                self.stop_events[unique_url_key].append(stop_event)
                monitor_thread.start()
    
    def stop_monitoring(self):
        if not self.monitor_threads:
            return

        logging.info("--- 正在发送停止信号... ---")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.add_button.config(state=tk.DISABLED)
        self.batch_add_button.config(state=tk.DISABLED)
        self.clear_button.config(state=tk.DISABLED)
        
        self.progress_bar.pack(side=tk.LEFT, padx=10, pady=5, expand=True, fill=tk.X)
        self.progress_bar.config(mode='indeterminate')
        self.progress_bar.start(10)

        for unique_url_key in self.stop_events:
            for stop_event in self.stop_events[unique_url_key]:
                stop_event.set()
        
        join_thread = threading.Thread(target=self._shutdown_worker)
        join_thread.start()

    def _shutdown_worker(self):
        while any(t.is_alive() for t in self.monitor_threads):
            alive_count = sum(1 for t in self.monitor_threads if t.is_alive())
            self.after(500, lambda: self.status_label.config(text=f"正在停止... ({alive_count} 个线程)"),)
            time.sleep(0.5)

        for thread in self.monitor_threads:
            if thread.is_alive():
                thread.join()
        
        self.after(100, self._on_threads_stopped)

    def _on_threads_stopped(self):
        self.monitor_threads = []
        self.stop_events = {}
        
        logging.info("--- 所有监控线程已停止。---")
        self.status_label.config(text="已停止")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.add_button.config(state=tk.NORMAL)
        self.batch_add_button.config(state=tk.NORMAL)
        self.clear_button.config(state=tk.NORMAL)
        
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        
    def on_closing(self):
        self.stop_monitoring()
        self.log_listener.stop()

# ==============================================================================
# 独立的程序入口，只在直接运行此文件时执行
# ==============================================================================
if __name__ == "__main__":
    # 创建一个临时的主窗口，只用于测试本模块
    root = tk.Tk()
    root.title("RTSP 压测工具 (独立模式)")
    root.geometry("800x600")

    # 实例化我们的压测模块，并将其作为内容添加到窗口中
    app = StressTestFrame(root)
    app.pack(fill=tk.BOTH, expand=True)

    # 绑定窗口关闭事件，确保子线程正常退出
    def on_closing():
        app.on_closing()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()