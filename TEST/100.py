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
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 配置常量
# ==============================================================================
MONITOR_INTERVAL_MS = 200
FPS_CHECK_INTERVAL_S = 1.0
CONNECT_TIMEOUT_S = 10
MAX_WORKERS = 20

# ==============================================================================
# 全局变量和线程池
# ==============================================================================
STATUS_QUEUES = defaultdict(queue.Queue)
executor = None

# ==============================================================================
# 线程池中的工作线程类
# ==============================================================================
class RTSPStreamMonitor(threading.Thread):
    def __init__(self, url, display_alias, log_alias, thread_id, tree_item_id, stop_event=None):
        super().__init__()
        self.url = url
        self.display_alias = display_alias
        self.log_alias = log_alias
        self.thread_id = thread_id
        self.tree_item_id = tree_item_id
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        
        self.reconnect_count = 0
        self.cap = None
        self.connection_attempt_result = {'success': False, 'cap': None}

        self.valid_frames = 0
        self.total_frames = 0
        self.last_check_time = time.time()
        
        self.logger = logging.getLogger(self.log_alias)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
        
        queue_handler = logging.handlers.QueueHandler(logging.getLogger().handlers[0].queue)
        self.logger.addHandler(queue_handler)

        log_path = "LOG"
        os.makedirs(log_path, exist_ok=True)
        log_filename = f"{self.log_alias}.log"
        log_filepath = os.path.join(log_path, log_filename)
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

    def _log(self, level, message):
        self.logger.log(level, message)

    def _update_status(self, status, total_fps=0.0, effective_fps=0.0, drop_rate=0.0):
        if self.tree_item_id in STATUS_QUEUES:
            status_info = {
                'thread_id': self.thread_id,
                'item_id': self.tree_item_id,
                'status': status,
                'total_fps': f"{total_fps:.2f}",
                'effective_fps': f"{effective_fps:.2f}",
                'drop_rate': f"{drop_rate * 100:.2f}%"
            }
            try:
                STATUS_QUEUES[self.tree_item_id].put_nowait(status_info)
            except queue.Full:
                pass

    def _attempt_connect_thread(self, url):
        """在单独的子线程中执行阻塞的连接尝试"""
        try:
            temp_cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            if temp_cap.isOpened():
                ret, _ = temp_cap.read()
                if ret:
                    self.connection_attempt_result['cap'] = temp_cap
                    self.connection_attempt_result['success'] = True
                    return
            
            if temp_cap:
                temp_cap.release()
                
        except Exception as e:
            self.logger.error(f"连接子线程发生异常: {e}")
            
    def connect(self):
        start_time = time.time()
        self._log(logging.INFO, f"正在尝试连接: {self.url}")
        
        self.connection_attempt_result['success'] = False
        self.connection_attempt_result['cap'] = None
        
        # 恢复使用子线程来处理连接超时
        connect_thread = threading.Thread(target=self._attempt_connect_thread, args=(self.url,))
        connect_thread.daemon = True
        connect_thread.start()
        
        connect_thread.join(timeout=CONNECT_TIMEOUT_S)
        
        if connect_thread.is_alive():
            self._log(logging.ERROR, f"连接超时 ({CONNECT_TIMEOUT_S}秒)。")
            self._update_status("连接失败")
            return False
            
        if self.connection_attempt_result['success']:
            self.cap = self.connection_attempt_result['cap']
            self._log(logging.INFO, f"连接成功！耗时: {(time.time() - start_time):.2f} 秒。")
            self._update_status("正常")
            return True
        else:
            self._log(logging.ERROR, "连接失败：无法打开视频流或读取第一帧。")
            self._update_status("连接失败")
            return False

    def disconnect(self):
        if self.cap:
            self.cap.release()
            self.cap = None
            self._log(logging.INFO, "连接断开。")
            self._update_status("已断开")

    def run(self):
        self._log(logging.INFO, "监控线程启动...")
        reconnect_delays = [1, 5, 10, 30, 60]
        reconnect_attempt_index = 0
        self._update_status("连接中...")

        try:
            if not self.connect():
                self._log(logging.ERROR, f"首次连接失败，将在 {reconnect_delays[0]} 秒后重试...")
                self.stop_event.wait(reconnect_delays[0])

            while not self.stop_event.is_set():
                if not self.cap or not self.cap.isOpened():
                    self._log(logging.WARNING, "连接断开或未建立，正在尝试重新连接...")
                    self._update_status("正在重连...")
                    if self.connect():
                        reconnect_attempt_index = 0
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
                    self._log(logging.ERROR, "抓取帧失败，可能连接已断开，正在准备重连...")
                    self._update_status("抓取失败")
                    self.disconnect()

                if time.time() - self.last_check_time >= FPS_CHECK_INTERVAL_S:
                    elapsed_time = time.time() - self.last_check_time
                    if elapsed_time > 0:
                        effective_fps = self.valid_frames / elapsed_time
                        total_fps = self.total_frames / elapsed_time
                        drop_rate = 1 - (effective_fps / total_fps) if total_fps > 0 else 0

                        status_text = "正常"
                        if drop_rate > 0.05:
                            status_text = "警告(丢帧)"
                        if total_fps == 0:
                            status_text = "无数据"

                        self._update_status(status_text, total_fps, effective_fps, drop_rate)

                    self.valid_frames = 0
                    self.total_frames = 0
                    self.last_check_time = time.time()

                self.stop_event.wait(MONITOR_INTERVAL_MS / 1000.0)
        finally:
            self.disconnect()
            self._update_status("已停止")
            self._log(logging.INFO, "监控线程停止。")

# ==============================================================================
# 主 GUI 框架
# ==============================================================================
class StressTestFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.monitor_futures = []
        self.stop_events = {}
        self.thread_counter = 0

        self.url_list_data = {}
        self.url_counter = 0

        self.log_queue = queue.Queue(-1)
        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(queue_handler)

        self.log_listener = logging.handlers.QueueListener(self.log_queue, self._create_gui_handler())
        self.create_widgets()
        self.log_listener.start()
        self.update_statuses()

    def _create_gui_handler(self):
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
            for item_id, q in STATUS_QUEUES.items():
                while not q.empty():
                    status_info = q.get_nowait()
                    if self.tree.exists(item_id):
                        self.tree.set(item_id, 'status', status_info['status'])
                        self.tree.set(item_id, 'total_fps', status_info['total_fps'])
                        self.tree.set(item_id, 'effective_fps', status_info['effective_fps'])
                        self.tree.set(item_id, 'drop_rate', status_info['drop_rate'])
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

    def _on_mousewheel(self, event):
        if sys.platform == "win32" or sys.platform == "darwin":
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif sys.platform.startswith('linux'):
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")

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

        self.add_button = ttk.Button(control_frame, text="添加地址",
                                     command=lambda: self.add_url(url=self.url_entry.get().strip(),
                                                                  count=int(self.count_combobox.get())))
        self.add_button.grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(control_frame, text="监控间隔 (ms):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.interval_entry = ttk.Entry(control_frame, width=10)
        self.interval_entry.insert(0, str(MONITOR_INTERVAL_MS))
        self.interval_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        self.interval_entry.config(state="readonly")

        ttk.Label(control_frame, text="帧率统计间隔 (s):").grid(row=1, column=2, padx=5, pady=5, sticky='w')
        self.fps_interval_entry = ttk.Entry(control_frame, width=5)
        self.fps_interval_entry.insert(0, str(FPS_CHECK_INTERVAL_S))
        self.fps_interval_entry.grid(row=1, column=3, padx=5, pady=5, sticky='w')
        self.fps_interval_entry.config(state="readonly")

        self.batch_add_button = ttk.Button(control_frame, text="批量添加", command=self.open_batch_add_window)
        self.batch_add_button.grid(row=1, column=4, padx=5, pady=5)

        control_frame.columnconfigure(1, weight=1)

        self.bind_right_click_menu(self.url_entry)

        ttk.Label(self, text="待监控地址列表:").pack(pady=(10, 0), padx=10, anchor='w')
        self.address_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=1, height=150)
        self.address_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.address_frame.pack_propagate(False)

        self.tree = ttk.Treeview(self.address_frame,
                                 columns=('index', 'url', 'count', 'status', 'total_fps', 'effective_fps', 'drop_rate'),
                                 show='headings')
        self.tree.heading('index', text='序号', anchor='center')
        self.tree.heading('url', text='RTSP 地址', anchor='w')
        self.tree.heading('count', text='拉取次数', anchor='center')
        self.tree.heading('status', text='状态', anchor='center')
        self.tree.heading('total_fps', text='总帧率', anchor='center')
        self.tree.heading('effective_fps', text='有效帧率', anchor='center')
        self.tree.heading('drop_rate', text='丢帧率', anchor='center')

        self.tree.column('index', width=50, anchor='center')
        self.tree.column('url', width=250)
        self.tree.column('count', width=80, anchor='center')
        self.tree.column('status', width=100, anchor='center')
        self.tree.column('total_fps', width=80, anchor='center')
        self.tree.column('effective_fps', width=80, anchor='center')
        self.tree.column('drop_rate', width=80, anchor='center')

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

        def save_and_close():
            urls = batch_text.get("1.0", tk.END).strip().split('\n')
            for url in urls:
                url = url.strip()
                if not url:
                    continue
                count = int(self.count_combobox.get())
                self.add_url(url=url, count=count)
            batch_window.destroy()

        save_button = ttk.Button(frame, text="确认添加", command=save_and_close)
        save_button.pack(pady=10)

    def add_url(self, url=None, count=None):
        if url is None:
            url = self.url_entry.get().strip()
        if count is None:
            count_str = self.count_combobox.get()
            if not url or not count_str:
                messagebox.showerror("错误", "RTSP 地址和拉取次数不能为空！")
                return
            count = int(count_str)

        if not url:
            return

        match = re.search(r'//(.*?)(?::|$|/)', url)
        log_alias_base = match.group(1) if match else "unknown"

        self.url_counter += 1
        item_id = self.tree.insert('', tk.END,
                                   values=(self.url_counter, url, count, "未启动", "0.00", "0.00", "0.00%"))

        self.url_list_data[item_id] = {
            'url': url,
            'count': count,
            'log_alias_base': log_alias_base,
            'list_index': self.url_counter,
        }
        self.url_entry.delete(0, tk.END)

    def remove_url(self, item_id):
        if item_id in self.url_list_data:
            del self.url_list_data[item_id]
            if item_id in STATUS_QUEUES:
                del STATUS_QUEUES[item_id]
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
        STATUS_QUEUES.clear()

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
        logging.info("--- 正在准备启动监控任务... ---")
        self.status_label.config(text="准备启动...")

        self.progress_bar.pack(side=tk.LEFT, padx=10, pady=5, expand=True, fill=tk.X)
        self.progress_bar.config(mode='indeterminate')
        self.progress_bar.start(10)

        STATUS_QUEUES.clear()
        self.tree.delete(*self.tree.get_children())
        self.thread_counter = 0
        
        task_list = []
        for _, data in self.url_list_data.items():
            url = data['url']
            count = data['count']
            log_alias_base = data['log_alias_base']
            for i in range(1, count + 1):
                self.thread_counter += 1
                display_alias = f"线程-{self.thread_counter:02d}"
                log_alias = f"{log_alias_base}_{self.thread_counter}"
                new_item_id = self.tree.insert('', tk.END,
                                               values=(self.thread_counter, url, count, "正在启动...", "0.00", "0.00", "0.00%"))
                STATUS_QUEUES[new_item_id] = queue.Queue(maxsize=1)
                task_list.append({
                    'url': url,
                    'display_alias': display_alias,
                    'log_alias': log_alias,
                    'thread_id': self.thread_counter,
                    'item_id': new_item_id
                })

        global executor
        executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

        self.monitor_futures = []
        self.stop_events = {}
        for task in task_list:
            stop_event = threading.Event()
            self.stop_events[task['item_id']] = stop_event
            monitor_thread = RTSPStreamMonitor(
                url=task['url'],
                display_alias=task['display_alias'],
                log_alias=task['log_alias'],
                thread_id=task['thread_id'],
                tree_item_id=task['item_id'],
                stop_event=stop_event
            )
            future = executor.submit(monitor_thread.run)
            self.monitor_futures.append(future)

        self.after(0, self._on_start_finished)

    def _on_start_finished(self):
        logging.info("--- 监控任务已全部启动 ---")
        self.status_label.config(text="监控中...")
        self.progress_bar.stop()
        self.progress_bar.pack_forget()

    def stop_monitoring(self):
        if not self.monitor_futures:
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

        stop_thread = threading.Thread(target=self._stop_threads_in_background, daemon=True)
        stop_thread.start()

    def _stop_threads_in_background(self):
        for event in self.stop_events.values():
            event.set()

        executor.shutdown(wait=True)
        
        self.after(100, self._on_threads_stopped)

    def _on_threads_stopped(self):
        self.monitor_futures = []
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
    root.geometry("1000x600")

    app = StressTestFrame(root)
    app.pack(fill=tk.BOTH, expand=True)

    def on_closing():
        app.on_closing()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()