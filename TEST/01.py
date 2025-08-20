# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel
import threading
import os
import cv2
import sys
import time
import re
import logging
import queue
import logging.handlers
from collections import defaultdict

# 全局字典，用于存储每个线程的状态队列
STATUS_QUEUES = defaultdict(queue.Queue)

class RTSPStreamMonitor(threading.Thread):
    def __init__(self, url, display_alias, log_alias, thread_id, tree_item_id, start_time, stop_event=None, monitor_interval_ms=1000, fps_check_interval_s=1.0):
        super().__init__()
        self.url = url
        self.display_alias = display_alias
        self.log_alias = log_alias
        self.thread_id = thread_id
        self.tree_item_id = tree_item_id
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.monitor_interval_ms = monitor_interval_ms
        
        self.reconnect_count = 0
        self.grab_failure_count = 0
        self.connect_latency = 0.0
        self.actual_fps = 0.0
        self.start_time = start_time
        
        self.cap = None

        # --- 累积统计变量 ---
        self.valid_frames = 0
        self.total_frames = 0
        # --------------------
        self.last_check_time = time.time()
        self.fps_check_interval = fps_check_interval_s
        
        self.logger = logging.getLogger(self.display_alias)
        self.logger.setLevel(logging.INFO)
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
        
        log_path = "LOG"
        os.makedirs(log_path, exist_ok=True)
        log_filename = f"{self.log_alias}.log"
        log_filepath = os.path.join(log_path, log_filename)
        self.file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        self.file_handler.setLevel(logging.ERROR)
        file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.file_handler.setFormatter(file_formatter)
        self.logger.addHandler(self.file_handler)
        
    def _log(self, level, message):
        self.logger.log(level, message)

    def _update_status(self, status, total_frames_count=0, valid_frames_count=0, dropped_frames_count=0, total_fps=0, effective_fps=0, drop_rate=0.0, connect_latency=0.0, reconnect_count=0, grab_failure_count=0, actual_fps=0.0):
        
        status_info = {
            'thread_id': self.thread_id,
            'item_id': self.tree_item_id,
            'status': status,
            'total_frames_count': total_frames_count,
            'valid_frames_count': valid_frames_count,
            'dropped_frames_count': dropped_frames_count,
            'total_fps': f"{total_fps:.2f}",
            'effective_fps': f"{effective_fps:.2f}",
            'drop_rate': f"{drop_rate * 100:.2f}%",
            'connect_latency': f"{connect_latency:.2f}",
            'reconnect_count': reconnect_count,
            'grab_failure_count': grab_failure_count,
            'actual_fps': f"{actual_fps:.2f}"
        }
        if self.thread_id in STATUS_QUEUES:
            STATUS_QUEUES[self.thread_id].put(status_info)

    def connect(self):
        start_time = time.time()
        try:
            self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            
            if not self.cap.isOpened():
                self._log(logging.ERROR, "连接失败：无法打开视频流。")
                self._update_status("连接失败")
                return False
                
            ret, _ = self.cap.read()
            if not ret:
                self._log(logging.ERROR, "连接成功但无法读取第一帧，可能流已断开或URL无效。")
                self.disconnect()
                self._update_status("连接失败")
                return False
            
            end_time = time.time()
            self.connect_latency = end_time - start_time
            self.reconnect_count += 1
            self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            self._log(logging.INFO, f"连接成功！耗时: {self.connect_latency:.2f} 秒。实际帧率: {self.actual_fps:.2f} FPS")
            self._update_status("正常", self.total_frames, self.valid_frames, self.total_frames - self.valid_frames, 0, 0, 0, self.connect_latency, self.reconnect_count, self.grab_failure_count, self.actual_fps)
            return True
        except Exception as e:
            self._log(logging.ERROR, f"连接时发生异常: {e}")
            self._update_status("连接失败")
            return False

    def disconnect(self):
        if self.cap:
            self.cap.release()
            self.cap = None
            self._log(logging.INFO, "连接断开。")
            self._update_status("已断开", self.total_frames, self.valid_frames, self.total_frames - self.valid_frames, 0, 0, 0, self.connect_latency, self.reconnect_count, self.grab_failure_count)
            
    def cleanup_logger(self):
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)
            self.file_handler.close()
            
    def run(self):
        self._log(logging.INFO, "监控线程启动...")
        reconnect_delays = [1, 5, 10, 30, 60]
        reconnect_attempt_index = 0
        sleep_interval = self.monitor_interval_ms / 1000.0

        self._update_status("连接中...")
        if not self.connect():
            self._log(logging.ERROR, f"首次连接失败，将在 {reconnect_delays[0]} 秒后重试...")
            self.stop_event.wait(reconnect_delays[0])
            
        while not self.stop_event.is_set():
            if not self.cap or not self.cap.isOpened():
                self._log(logging.WARNING, "连接断开或未建立，正在尝试重新连接...")
                self._update_status("正在重连...")
                if self.connect():
                    reconnect_attempt_index = 0
                    self.last_check_time = time.time()
                else:
                    delay = reconnect_delays[min(reconnect_attempt_index, len(reconnect_delays) - 1)]
                    self._log(logging.ERROR, f"连接失败，将在 {delay} 秒后重试...")
                    self.stop_event.wait(delay)
                    reconnect_attempt_index += 1
                    continue

            self.total_frames += 1
            if self.cap.grab():
                self.valid_frames += 1
            else:
                self.grab_failure_count += 1
                self._log(logging.ERROR, "抓取帧失败，可能连接已断开，正在准备重连...")
                self._update_status("抓取失败")
                self.disconnect()
            
            if time.time() - self.last_check_time >= self.fps_check_interval:
                elapsed_time = time.time() - self.start_time
                effective_fps = self.valid_frames / elapsed_time if elapsed_time > 0 else 0
                total_fps = self.total_frames / elapsed_time if elapsed_time > 0 else 0
                drop_rate = 1 - (effective_fps / total_fps) if total_fps > 0 else 0
                dropped_frames = self.total_frames - self.valid_frames

                status_text = "正常"
                if drop_rate > 0.05:
                    status_text = "警告(丢帧)"
                if self.total_frames == 0:
                    status_text = "无数据"
                
                self._update_status(status_text, self.total_frames, self.valid_frames, dropped_frames, total_fps, effective_fps, drop_rate, self.connect_latency, self.reconnect_count, self.grab_failure_count, self.actual_fps)
                self.last_check_time = time.time()
            
            self.stop_event.wait(sleep_interval)

        self.disconnect()
        self.cleanup_logger()
        self._update_status("已停止", self.total_frames, self.valid_frames, self.total_frames - self.valid_frames, 0, 0, 0, self.connect_latency, self.reconnect_count, self.grab_failure_count)
        self._log(logging.INFO, "监控线程停止。")

class StressTestFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.monitor_threads = []
        self.stop_events = {}
        self.thread_counter = 0

        self.url_list_data = {}
        self.url_counter = 0

        self.log_queue = queue.Queue()
        self.log_handler = logging.handlers.QueueHandler(self.log_queue)
        logging.getLogger().addHandler(self.log_handler)
        
        self.log_listener = logging.handlers.QueueListener(self.log_queue, self._gui_log_handler())
        self.log_listener.start()
        
        self.create_widgets()
        self.update_statuses()

    def _gui_log_handler(self):
        handler = logging.Handler()
        handler.setLevel(logging.INFO)
        handler.emit = self._log_to_gui_via_handler
        return handler

    def _log_to_gui_via_handler(self, record):
        try:
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

    def update_statuses(self):
        try:
            for thread_id, status_queue in STATUS_QUEUES.items():
                while not status_queue.empty():
                    status_info = status_queue.get_nowait()
                    item_id = status_info['item_id']
                    if self.tree.exists(item_id):
                        
                        status = status_info['status']
                        is_abnormal = status in ["连接失败", "正在重连...", "警告(丢帧)", "抓取失败", "无数据", "已断开"]
                        
                        if is_abnormal:
                            self.tree.item(item_id, tags=('abnormal',))
                        else:
                            self.tree.item(item_id, tags=())

                        self.tree.set(item_id, 'status', status)
                        self.tree.set(item_id, 'actual_fps', status_info['actual_fps'])
                        self.tree.set(item_id, 'total_frames_count', status_info['total_frames_count'])
                        self.tree.set(item_id, 'valid_frames_count', status_info['valid_frames_count'])
                        self.tree.set(item_id, 'dropped_frames_count', status_info['dropped_frames_count'])
                        self.tree.set(item_id, 'effective_fps', status_info['effective_fps'])
                        self.tree.set(item_id, 'drop_rate', status_info['drop_rate'])
                        self.tree.set(item_id, 'reconnect_count', status_info['reconnect_count'])
                        self.tree.set(item_id, 'grab_failures', status_info['grab_failure_count'])
                        self.tree.set(item_id, 'connect_latency', status_info['connect_latency'])
                        
        except Exception as e:
            print(f"Error in status updater: {e}")
        self.after(200, self.update_statuses)

    def bind_right_click_menu(self, widget):
        def show_menu(event):
            menu = tk.Menu(widget, tearoff=0)
            menu.add_command(label="剪切", command=lambda: widget.event_generate("<<Cut>>"))
            menu.add_command(label="复制", command=lambda: widget.event_generate("<<Copy>>"))
            menu.add_command(label="粘贴", command=lambda: widget.event_generate("<<Paste>>"))
            menu.post(event.x_root, event.y_root)
        widget.bind("<Button-3>", show_menu)
        
    def create_widgets(self):
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="RTSP 地址:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.url_entry = ttk.Entry(control_frame, width=50)
        self.url_entry.insert(0, "rtsp://192.168.16.3/live/1/1")
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        ttk.Label(control_frame, text="线程:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.threads_entry = ttk.Entry(control_frame, width=5)
        self.threads_entry.insert(0, "1")
        self.threads_entry.grid(row=0, column=3, padx=5, pady=5)

        self.add_button = ttk.Button(control_frame, text="添加地址", command=self.add_url)
        self.add_button.grid(row=0, column=4, padx=5, pady=5)
        
        ttk.Label(control_frame, text="监控间隔 (ms):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.interval_entry = ttk.Entry(control_frame, width=10)
        self.interval_entry.insert(0, "200")
        self.interval_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        ttk.Label(control_frame, text="帧率统计间隔 (s):").grid(row=1, column=2, padx=5, pady=5, sticky='w')
        self.fps_interval_entry = ttk.Entry(control_frame, width=5)
        self.fps_interval_entry.insert(0, "1.0")
        self.fps_interval_entry.grid(row=1, column=3, padx=5, pady=5, sticky='w')

        self.batch_add_button = ttk.Button(control_frame, text="批量添加", command=self.open_batch_add_window)
        self.batch_add_button.grid(row=1, column=4, padx=5, pady=5)

        control_frame.columnconfigure(1, weight=1)

        self.bind_right_click_menu(self.url_entry)
        self.bind_right_click_menu(self.threads_entry)

        ttk.Label(self, text="待监控地址列表:").pack(pady=(10, 0), padx=10, anchor='w')
        self.address_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=1, height=150)
        self.address_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.address_frame.pack_propagate(False)

        self.tree = ttk.Treeview(self.address_frame, columns=('index', 'url', 'status', 'actual_fps', 'total_frames_count', 'valid_frames_count', 'dropped_frames_count', 'effective_fps', 'drop_rate', 'reconnect_count', 'grab_failures', 'connect_latency'), show='headings')
        self.tree.tag_configure('abnormal', foreground='red')

        self.tree.heading('index', text='序号', anchor='center')
        self.tree.heading('url', text='RTSP 地址', anchor='w')
        self.tree.heading('status', text='状态', anchor='center')
        self.tree.heading('actual_fps', text='帧率', anchor='center')
        self.tree.heading('total_frames_count', text='总尝试数', anchor='center')
        self.tree.heading('valid_frames_count', text='总接收数', anchor='center')
        self.tree.heading('dropped_frames_count', text='总丢失数', anchor='center')
        self.tree.heading('effective_fps', text='有效帧率', anchor='center')
        self.tree.heading('drop_rate', text='丢帧率', anchor='center')
        self.tree.heading('reconnect_count', text='重连', anchor='center')
        self.tree.heading('grab_failures', text='抓帧失败', anchor='center')
        self.tree.heading('connect_latency', text='耗时', anchor='center')
        
        self.tree.column('index', width=40, anchor='center', stretch=False)
        self.tree.column('url', minwidth=120, anchor='w', stretch=True) 
        self.tree.column('status', width=60, anchor='center', stretch=False)
        self.tree.column('actual_fps', width=60, anchor='center', stretch=False)
        self.tree.column('total_frames_count', width=60, anchor='center', stretch=False)
        self.tree.column('valid_frames_count', width=60, anchor='center', stretch=False)
        self.tree.column('dropped_frames_count', width=60, anchor='center', stretch=False)
        self.tree.column('effective_fps', width=60, anchor='center', stretch=False)
        self.tree.column('drop_rate', width=60, anchor='center', stretch=False)
        self.tree.column('reconnect_count', width=40, anchor='center', stretch=False)
        self.tree.column('grab_failures', width=60, anchor='center', stretch=False)
        self.tree.column('connect_latency', width=40, anchor='center', stretch=False)
        
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree_scrollbar = ttk.Scrollbar(self.address_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scrollbar.set)
        self.tree_scrollbar.pack(side="right", fill="y")
        
        self.tree.bind("<Button-3>", self.show_tree_context_menu)
        
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

    def show_tree_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            menu = tk.Menu(self.tree, tearoff=0)
            menu.add_command(label="复制地址", command=lambda: self.copy_tree_url(item))
            menu.add_command(label="移除", command=lambda: self.remove_url(item))
            menu.post(event.x_root, event.y_root)

    def copy_tree_url(self, item_id):
        url = self.tree.item(item_id, 'values')[1]
        self.clipboard_clear()
        self.clipboard_append(url)

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
        
        default_urls = """rtsp://192.168.16.3/live/1/1
rtsp://127.0.0.1:8080/live/1/8"""
        batch_text.insert(tk.END, default_urls)
        
        def save_and_close():
            urls = batch_text.get("1.0", tk.END).strip().split('\n')
            
            for url in urls:
                url = url.strip()
                if not url:
                    continue
                self.add_url(url=url)

            batch_window.destroy()

        save_button = ttk.Button(frame, text="确认添加", command=save_and_close)
        save_button.pack(pady=10)

    def add_url(self, url=None):
        if url is None:
            url = self.url_entry.get().strip()
        
        if not url:
            messagebox.showerror("错误", "RTSP 地址不能为空！")
            return

        match = re.search(r'//(.*?)(?::|$|/)', url)
        log_alias_base = match.group(1) if match else "unknown"

        self.url_counter += 1
        item_id = self.tree.insert('', tk.END, values=(self.url_counter, url, "未启动", "0.00", "0", "0", "0", "0.00", "0.00%", "0", "0", "0.00"))
        
        self.url_list_data[item_id] = {
            'url': url,
            'log_alias_base': log_alias_base,
            'list_index': self.url_counter,
        }
        self.url_entry.delete(0, tk.END)

    def remove_url(self, item_id):
        if messagebox.askyesno("确认移除", "确定要移除此项吗？"):
            if item_id in self.url_list_data:
                del self.url_list_data[item_id]
            self.tree.delete(item_id)
            self._update_tree_indices()

    def _update_tree_indices(self):
        items = self.tree.get_children()
        for i, item in enumerate(items):
            self.tree.set(item, 'index', i + 1)
            if item in self.url_list_data:
                self.url_list_data[item]['list_index'] = i + 1

    def clear_list(self):
        self.url_list_data = {}
        self.url_counter = 0
        self.tree.delete(*self.tree.get_children())

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
        STATUS_QUEUES.clear()
        self.monitor_threads = []
        self.stop_events = {}
        start_time = time.time()

        try:
            global_threads_count = int(self.threads_entry.get())
            if global_threads_count < 1:
                messagebox.showwarning("警告", "线程数不能小于1，已自动设置为1。")
                global_threads_count = 1
        except ValueError:
            messagebox.showwarning("警告", "线程数输入无效，已自动设置为1。")
            global_threads_count = 1

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
        
        self.tree.delete(*self.tree.get_children())
        row_count = 0

        for item_id, data in self.url_list_data.items():
            url = data['url']
            log_alias_base = data['log_alias_base']
            
            for i in range(1, global_threads_count + 1):
                row_count += 1
                self.thread_counter += 1
                display_alias = f"线程-{self.thread_counter:02d}"
                log_alias = f"{log_alias_base}_{self.thread_counter}"
                
                new_item_id = self.tree.insert('', tk.END, values=(row_count, url, "正在启动...", "0.00", "0", "0", "0", "0.00", "0.00%", "0", "0.00", "0"))
                
                stop_event = threading.Event()
                STATUS_QUEUES[self.thread_counter] = queue.Queue()

                monitor_thread = RTSPStreamMonitor(
                    url=url,
                    display_alias=display_alias,
                    log_alias=log_alias,
                    thread_id=self.thread_counter,
                    tree_item_id=new_item_id,
                    stop_event=stop_event,
                    start_time=start_time,
                    monitor_interval_ms=monitor_interval,
                    fps_check_interval_s=fps_check_interval
                )
                self.monitor_threads.append(monitor_thread)
                self.stop_events[new_item_id] = stop_event
                
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

        for item_id in self.stop_events:
            self.stop_events[item_id].set()
        
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
        STATUS_QUEUES.clear()
        
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
    root = tk.Tk()
    root.title("RTSP 压测工具")
    root.geometry("900x600")

    app = StressTestFrame(root)
    app.pack(fill=tk.BOTH, expand=True)

    def on_closing():
        app.on_closing()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()