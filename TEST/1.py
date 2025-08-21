# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel, filedialog
import threading
import os
import time
import re
import logging
import queue
import logging.handlers
from collections import defaultdict, deque
import psutil
import av
import av.error
import pandas as pd
import datetime

# ==============================================================================
# 全局配置管理
# ==============================================================================
class SettingsManager:
    """管理所有可配置参数的类"""
    def __init__(self):
        self.gui_refresh_interval = 200  # GUI刷新频率，毫秒
        self.rtsp_timeout = 5000000      # PyAV拉流超时，微秒
        self.reconnect_wait_time = 5     # 重连等待时间，秒
        self.sys_monitor_enabled = True  # 是否启用系统性能监控
        self.log_level = logging.INFO
        self.expected_fps = 25
        self.global_threads_count = 1

SETTINGS = SettingsManager()

# ==============================================================================
# 全局状态管理
# ==============================================================================
# 全局字典，用于存储每个线程的状态队列
STATUS_QUEUES = defaultdict(queue.Queue)
# 日志队列，用于子线程与主线程通信
LOG_QUEUE = deque()
# 存储每个线程条目与其URL的映射关系 (现在是扁平化的)
THREAD_TO_URL_MAP = {}
# 存储每个地址的聚合数据
AGGREGATED_DATA = defaultdict(lambda: {
    'threads_count': 0,
    'total_frames': 0,
    'total_bytes': 0,
    'total_reconnects': 0,
    'total_expected_frames': 0,
    'total_lost_frames': 0,
    'fps_list': [],
    'latency_list': [],
})

# ==============================================================================
# 日志配置
# ==============================================================================
class ThreadSafeLogHandler(logging.Handler):
    """一个线程安全的日志处理器，将日志消息和日志级别放入队列。"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            log_message = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {self.format(record)}"
            self.log_queue.append((record.levelno, log_message))
        except Exception:
            pass

# 设置日志等级
logging.basicConfig(level=logging.DEBUG)
for handler in logging.getLogger().handlers[:]:
    logging.getLogger().removeHandler(handler)
logging.getLogger().addHandler(ThreadSafeLogHandler(LOG_QUEUE))

# ==============================================================================
# 多线程视频流监控
# ==============================================================================
class RTSPStreamMonitor(threading.Thread):
    def __init__(self, url, thread_id, thread_item_id, protocol='UDP'):
        super().__init__()
        self.url = url
        self.thread_id = thread_id
        self.thread_item_id = thread_item_id
        self.protocol = protocol
        self.stop_event = threading.Event()
        self.container = None
        self.logger = logging.getLogger(f"Stream-{self.thread_id:02d}")
        
        # 累积统计变量
        self.total_frames = 0
        self.total_bytes = 0
        self.reconnect_count = 0
        
        # 实时指标变量
        self.current_fps = 0
        self.connect_latency = 0.0
        self.last_frame_time = time.time()
        
    def run(self):
        while not self.stop_event.is_set():
            try:
                self.logger.info(f"正在尝试连接: {self.url}...")
                start_time = time.time()
                
                options = {
                    'rtsp_transport': self.protocol.lower(), 
                    'buffer_size': '2048000', 
                    'timeout': str(SETTINGS.rtsp_timeout)
                }
                self.container = av.open(self.url, mode='r', options=options)
                
                try:
                    video_stream = self.container.streams.video[0]
                    expected_fps = float(video_stream.average_rate)
                    self.logger.info(f"成功获取到流的真实帧率：{expected_fps:.2f} FPS")
                except (IndexError, AttributeError):
                    expected_fps = SETTINGS.expected_fps
                    self.logger.warning(f"无法获取视频流的真实帧率，将使用默认值 {expected_fps} FPS。")

                self.connect_latency = time.time() - start_time
                self.logger.info(f"连接成功！延迟: {self.connect_latency:.2f}s。开始抓取帧。")

                for packet in self.container.demux(video=0):
                    if self.stop_event.is_set():
                        break
                    
                    self.total_frames += 1
                    self.total_bytes += packet.size if packet and packet.size is not None else 0
                    
                    current_time = time.time()
                    elapsed_time = current_time - self.last_frame_time
                    if elapsed_time > 0:
                        self.current_fps = 1 / elapsed_time
                    self.last_frame_time = current_time

                    total_elapsed_time = current_time - start_time
                    expected_frames = int(total_elapsed_time * expected_fps)
                    lost_frames = max(0, expected_frames - self.total_frames)

                    status_info = {
                        'thread_id': self.thread_id,
                        'thread_item_id': self.thread_item_id,
                        'status': "正常",
                        'total_frames': self.total_frames,
                        'received_frames': self.total_frames,
                        'total_bytes': self.total_bytes,
                        'reconnect_count': self.reconnect_count,
                        'connect_latency': self.connect_latency,
                        'current_fps': self.current_fps,
                        'expected_frames': expected_frames,
                        'lost_frames': lost_frames,
                        'expected_fps': expected_fps,
                    }
                    if self.thread_id in STATUS_QUEUES:
                        STATUS_QUEUES[self.thread_id].put(status_info)
                    
                    time.sleep(0.001)
                
                
            except (av.FFmpegError, TimeoutError) as e:
            
                self.reconnect_count += 1
                self.logger.error(f"连接或拉流失败: {e}。第 {self.reconnect_count} 次重试中...")
                status_info = {
                    'thread_id': self.thread_id,
                    'thread_item_id': self.thread_item_id,
                    'status': f"连接失败 (重试{self.reconnect_count})",
                    'total_frames': self.total_frames,
                    'received_frames': self.total_frames,
                    'total_bytes': self.total_bytes,
                    'reconnect_count': self.reconnect_count,
                    'connect_latency': 0.0,
                    'current_fps': 0.0,
                    'expected_frames': 0,
                    'lost_frames': 0,
                    'expected_fps': SETTINGS.expected_fps,
                }
                if self.thread_id in STATUS_QUEUES:
                    STATUS_QUEUES[self.thread_id].put(status_info)
                time.sleep(SETTINGS.reconnect_wait_time)
            except Exception as e:
                self.logger.error(f"发生未知异常: {e}")
                time.sleep(SETTINGS.reconnect_wait_time)
            finally:
                if self.container:
                    try:
                        self.container.close()
                    except Exception:
                        pass
                self.container = None

        self.logger.info("监控线程已停止。")
        
    def stop(self):
        self.stop_event.set()
        
# ==============================================================================
# 系统性能监控线程
# ==============================================================================
class SystemMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()
        self.logger = logging.getLogger("SysMonitor")
        self.last_net_stats = psutil.net_io_counters()

    def run(self):
        while not self.stop_event.is_set():
            try:
                cpu_percent = psutil.cpu_percent(interval=None)
                mem_info = psutil.virtual_memory()
                memory_usage_mb = mem_info.used / (1280 * 1280)
                
                current_net_stats = psutil.net_io_counters()
                net_sent = current_net_stats.bytes_sent - self.last_net_stats.bytes_sent
                net_recv = current_net_stats.bytes_recv - self.last_net_stats.bytes_recv
                self.last_net_stats = current_net_stats
                
                status_info = {
                    'thread_id': -1, # 使用特殊ID
                    'cpu_percent': cpu_percent,
                    'memory_usage_mb': memory_usage_mb,
                    'net_sent_mb': net_sent / (1024 * 1024),
                    'net_recv_mb': net_recv / (1024 * 1024),
                }
                if -1 in STATUS_QUEUES:
                    STATUS_QUEUES[-1].put(status_info)
                
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"系统监控发生异常: {e}")
                time.sleep(5)
                
        self.logger.info("系统监控线程已停止。")
        
    def stop(self):
        self.stop_event.set()

# ==============================================================================
# GUI 应用类
# ==============================================================================
class StressTestFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.url_list_data = {}
        self.thread_counter = 0 # 用于生成唯一的线程ID
        self.monitor_threads = []
        self.total_threads_count = 0
        
        self.create_widgets()
        self.update_statuses()
        
    def create_widgets(self):
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        # 顶部输入和控制
        control_frame = ttk.Frame(self, padding="10")
        control_frame.grid(row=0, column=0, sticky='ew')
        control_frame.columnconfigure(1, weight=1)

        ttk.Label(control_frame, text="RTSP 地址:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.url_entry = ttk.Entry(control_frame, width=50)
        self.url_entry.insert(0, "rtsp://192.168.0.3/live/1/1")
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        ttk.Label(control_frame, text="协议:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.protocol_combobox = ttk.Combobox(control_frame, width=4, values=['UDP', 'TCP'], state="readonly")
        self.protocol_combobox.set("UDP")
        self.protocol_combobox.grid(row=0, column=3, padx=5, pady=5, sticky='w')
        
        ttk.Label(control_frame, text="线程数:").grid(row=0, column=4, padx=5, pady=5, sticky='w')
        self.threads_combobox = ttk.Combobox(control_frame, width=5, values=list(range(1, 11)) + [20, 40, 60, 100], state="readonly")
        self.threads_combobox.set("1")
        self.threads_combobox.grid(row=0, column=5, padx=5, pady=5)
        self.threads_combobox.bind('<<ComboboxSelected>>', self.update_global_threads_count)

        self.add_button = ttk.Button(control_frame, text="添加", command=self.add_url)
        self.add_button.grid(row=0, column=6, padx=5, pady=5)
        
        self.batch_add_button = ttk.Button(control_frame, text="批量添加", command=self.open_batch_add_window)
        self.batch_add_button.grid(row=0, column=7, padx=5, pady=5)
        
        self.clear_button = ttk.Button(control_frame, text="清空", command=self.clear_list)
        self.clear_button.grid(row=0, column=8, padx=5, pady=5)
        
        self.settings_button = ttk.Button(control_frame, text="参数设置", command=self.open_settings_window)
        self.settings_button.grid(row=0, column=9, padx=5, pady=5)
        
        # 中间表格展示区
        ttk.Label(self, text="待监控地址列表:").grid(row=1, column=0, padx=10, pady=(10, 0), sticky='w')
        self.address_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=1)
        self.address_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=5)
        self.address_frame.columnconfigure(0, weight=1)
        self.address_frame.rowconfigure(0, weight=1)
        
        columns = ('id', 'url', 'status', 'fps', 'received_frames', 'expected_frames', 'lost_frames', 'lost_rate', 'total_bytes', 'reconnects', 'latency')
        self.tree = ttk.Treeview(self.address_frame, columns=columns, show='headings')
        self.tree.heading('id', text='ID', anchor='center')
        self.tree.heading('url', text='RTSP 地址', anchor='w')
        self.tree.heading('status', text='状态', anchor='center')
        self.tree.heading('fps', text='实时FPS', anchor='center')
        self.tree.heading('received_frames', text='有效帧', anchor='center')
        self.tree.heading('expected_frames', text='预计帧', anchor='center')
        self.tree.heading('lost_frames', text='丢失帧', anchor='center')
        self.tree.heading('lost_rate', text='丢失率', anchor='center')
        self.tree.heading('total_bytes', text='总流量', anchor='center')
        self.tree.heading('reconnects', text='重连次数', anchor='center')
        self.tree.heading('latency', text='连接延迟', anchor='center')
        
        self.tree.column('id', width=60, anchor='center', stretch=False)
        self.tree.column('url', minwidth=200, anchor='w', stretch=True) 
        self.tree.column('status', width=120, anchor='center', stretch=False)
        self.tree.column('fps', width=80, anchor='center', stretch=False)
        self.tree.column('received_frames', width=80, anchor='center', stretch=False)
        self.tree.column('expected_frames', width=80, anchor='center', stretch=False)
        self.tree.column('lost_frames', width=80, anchor='center', stretch=False)
        self.tree.column('lost_rate', width=80, anchor='center', stretch=False)
        self.tree.column('total_bytes', width=100, anchor='center', stretch=False)
        self.tree.column('reconnects', width=80, anchor='center', stretch=False)
        self.tree.column('latency', width=80, anchor='center', stretch=False)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.tree_scrollbar = ttk.Scrollbar(self.address_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scrollbar.set)
        self.tree_scrollbar.grid(row=0, column=1, sticky='ns')
        
        self.tree.bind("<Button-3>", self.show_tree_context_menu)
        
        # 底部控制和状态
        bottom_frame = ttk.Frame(self, padding="10")
        bottom_frame.grid(row=3, column=0, sticky='ew')
        bottom_frame.columnconfigure(1, weight=1)
        bottom_frame.columnconfigure(2, weight=1)

        self.start_button = ttk.Button(bottom_frame, text="启动监控", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, padx=5)

        self.stop_button = ttk.Button(bottom_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)
        
        self.export_button = ttk.Button(bottom_frame, text="导出数据", command=self.export_to_excel)
        self.export_button.grid(row=0, column=2, padx=5)
        
        status_and_perf_frame = ttk.Frame(bottom_frame)
        status_and_perf_frame.grid(row=0, column=3, padx=10, sticky='e')
        
        self.status_label = ttk.Label(status_and_perf_frame, text="已停止", foreground="blue")
        self.status_label.grid(row=0, column=0, padx=(10, 5), sticky='w')
        
        self.status_progress = ttk.Progressbar(status_and_perf_frame, orient="horizontal", length=100, mode="indeterminate")
        self.status_progress.grid(row=0, column=1, sticky='w')

        # 性能监控面板 (使用进度条)
        perf_frame = ttk.Frame(status_and_perf_frame)
        perf_frame.grid(row=0, column=2, padx=(20,0), sticky='e')

        self.cpu_label = ttk.Label(perf_frame, text="CPU: 0.00%")
        self.cpu_label.grid(row=0, column=0, sticky='w')
        self.cpu_progress = ttk.Progressbar(perf_frame, orient="horizontal", length=80, mode="determinate")
        self.cpu_progress.grid(row=0, column=1, padx=2, sticky='w')

        self.mem_label = ttk.Label(perf_frame, text="内存: 0.00%")
        self.mem_label.grid(row=0, column=2, padx=(10,0), sticky='w')
        self.mem_progress = ttk.Progressbar(perf_frame, orient="horizontal", length=80, mode="determinate")
        self.mem_progress.grid(row=0, column=3, padx=2, sticky='w')
        
        self.net_label = ttk.Label(perf_frame, text="网络: ↓0.00MB/s ↑0.00MB/s")
        self.net_label.grid(row=0, column=4, padx=(10,0), sticky='w')


        # 日志输出区
        log_frame = ttk.Frame(self, padding="10")
        log_frame.grid(row=4, column=0, sticky='nsew')
        self.rowconfigure(4, weight=1)
        
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.pack(fill='x', expand=False)
        ttk.Label(log_control_frame, text="日志输出:").pack(side='left', padx=(0, 10))
        
        self.log_level_var = tk.StringVar(value='INFO')
        self.log_level_menu = ttk.Combobox(log_control_frame, textvariable=self.log_level_var, values=['DEBUG', 'INFO', 'WARNING', 'ERROR'], state='readonly')
        self.log_level_menu.pack(side='left')
        self.log_level_menu.bind('<<ComboboxSelected>>', self.set_log_level)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state='disabled', wrap=tk.WORD, font=('Courier', 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
    
    def update_global_threads_count(self, event):
        """更新全局线程数，并更新列表中所有地址的显示"""
        try:
            new_threads_count = int(self.threads_combobox.get())
            SETTINGS.global_threads_count = new_threads_count
        except ValueError:
            pass 

    def show_tree_context_menu(self, event):
        menu = tk.Menu(self.tree, tearoff=0)
        
        def paste_from_clipboard():
            try:
                clipboard_content = self.clipboard_get()
                urls = clipboard_content.strip().split('\n')
                for url in urls:
                    url = url.strip()
                    if url:
                        self.url_entry.delete(0, tk.END)
                        self.url_entry.insert(0, url)
                        self.add_url()
            except tk.TclError:
                messagebox.showerror("错误", "剪贴板中不包含文本。")

        def copy_selected():
            selected_items = self.tree.selection()
            if not selected_items:
                return
            
            urls_to_copy = []
            for item in selected_items:
                urls_to_copy.append(self.url_list_data[item]['url'])
            
            if urls_to_copy:
                self.clipboard_clear()
                self.clipboard_append('\n'.join(urls_to_copy))

        def select_all():
            all_items = self.tree.get_children()
            self.tree.selection_set(all_items)

        def delete_selected():
            selected_items = self.tree.selection()
            if not selected_items:
                return
            
            for item in selected_items:
                if item in self.url_list_data:
                    self.remove_url(item)

        menu.add_command(label="全选", command=select_all)
        menu.add_command(label="复制", command=copy_selected)
        menu.add_command(label="粘贴", command=paste_from_clipboard)
        menu.add_command(label="删除", command=delete_selected)
        
        menu.post(event.x_root, event.y_root)

    def set_log_level(self, event):
        level = self.log_level_var.get()
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR
        }
        SETTINGS.log_level = level_map.get(level, logging.INFO)

    def open_settings_window(self):
        settings_window = Toplevel(self.winfo_toplevel())
        settings_window.title("参数设置")
        settings_window.resizable(False, False)

        frame = ttk.Frame(settings_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="GUI刷新频率 (ms):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        refresh_interval_var = tk.StringVar(value=str(SETTINGS.gui_refresh_interval))
        refresh_combobox = ttk.Combobox(frame, textvariable=refresh_interval_var, values=['50', '100', '200', '500', '1000'], state="readonly")
        refresh_combobox.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(frame, text="拉流超时 (ms):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        timeout_var = tk.StringVar(value=str(SETTINGS.rtsp_timeout // 1000))
        timeout_combobox = ttk.Combobox(frame, textvariable=timeout_var, values=['1000', '2000', '5000', '10000', '30000'], state="readonly")
        timeout_combobox.grid(row=1, column=1, padx=5, pady=5, sticky='ew')

        ttk.Label(frame, text="重连等待时间 (s):").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        reconnect_wait_var = tk.StringVar(value=str(SETTINGS.reconnect_wait_time))
        reconnect_combobox = ttk.Combobox(frame, textvariable=reconnect_wait_var, values=['1', '3', '5', '10', '15', '30'], state="readonly")
        reconnect_combobox.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        
        ttk.Label(frame, text="预期帧率 (FPS):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        expected_fps_var = tk.StringVar(value=str(SETTINGS.expected_fps))
        expected_fps_combobox = ttk.Combobox(frame, textvariable=expected_fps_var, values=['15', '20', '25', '30', '50', '60'], state="readonly")
        expected_fps_combobox.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        
        sys_monitor_var = tk.BooleanVar(value=SETTINGS.sys_monitor_enabled)
        sys_monitor_check = ttk.Checkbutton(frame, text="启用系统性能监控", variable=sys_monitor_var)
        sys_monitor_check.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky='w')

        def save_settings():
            try:
                SETTINGS.gui_refresh_interval = int(refresh_interval_var.get())
                SETTINGS.rtsp_timeout = int(timeout_var.get()) * 1000
                SETTINGS.reconnect_wait_time = int(reconnect_wait_var.get())
                SETTINGS.sys_monitor_enabled = sys_monitor_var.get()
                SETTINGS.expected_fps = int(expected_fps_combobox.get())
                settings_window.destroy()
                messagebox.showinfo("提示", "参数已保存，将在下次启动监控时生效。")
            except ValueError:
                messagebox.showerror("错误", "参数输入有误，请确保为整数！")

        save_button = ttk.Button(frame, text="保存", command=save_settings)
        save_button.grid(row=5, column=0, columnspan=2, pady=10)

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
        default_urls = "rtsp://192.168.16.3/live/1/1\nrtsp://192.168.16.3/live/1/2\nrtsp://192.168.16.3/live/1/3"
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
            
        threads_count = int(self.threads_combobox.get())
        
        for i in range(threads_count):
            self.thread_counter += 1
            thread_id = f"thread_{self.thread_counter}"
            item_id = self.tree.insert('', tk.END, iid=thread_id, values=(
                f"#{self.thread_counter}",
                url,
                "未启动", 
                "0.00", "0", "0", "0", "0.00%", "0.00 MB", "0", "0.00s"
            ), tags=('thread_row',))
            
            self.tree.tag_configure('thread_row', font=('TkDefaultFont', 9))
            self.tree.tag_configure('warning', background='#ffcccb')
            self.tree.tag_configure('normal', background='')
            
            self.url_list_data[item_id] = {
                'id': self.thread_counter,
                'url': url,
            }
        self.url_entry.delete(0, tk.END)

    def remove_url(self, item_id):
        if messagebox.askyesno("确认移除", "确定要移除此项吗？"):
            if item_id in self.url_list_data:
                del self.url_list_data[item_id]
                self.tree.delete(item_id)
            if item_id in AGGREGATED_DATA:
                del AGGREGATED_DATA[item_id]

    def clear_list(self):
        self.stop_monitoring()
        self.url_list_data.clear()
        self.thread_counter = 0
        AGGREGATED_DATA.clear()
        self.tree.delete(*self.tree.get_children())
            
    def update_statuses(self):
        # 处理日志队列
        while LOG_QUEUE:
            log_level, log_record = LOG_QUEUE.popleft()
            if log_level >= SETTINGS.log_level:
                self.log_text.configure(state='normal')
                self.log_text.insert(tk.END, log_record + '\n')
                self.log_text.configure(state='disabled')
                self.log_text.see(tk.END)
        
        # 清空聚合数据中的瞬时列表 (虽然扁平化了，但这个结构仍可用于导出)
        for key in AGGREGATED_DATA:
            AGGREGATED_DATA[key]['fps_list'] = []
            AGGREGATED_DATA[key]['latency_list'] = []
        
        # 处理状态队列
        all_updates = []
        for thread_id, status_queue in STATUS_QUEUES.items():
            while not status_queue.empty():
                all_updates.append(status_queue.get_nowait())
                
        rtsp_updates = [u for u in all_updates if u['thread_id'] != -1]
        sys_updates = [u for u in all_updates if u['thread_id'] == -1]

        # 更新系统性能信息（取最新一条）
        if sys_updates and SETTINGS.sys_monitor_enabled:
            sys_info = sys_updates[-1]
            self.cpu_label.config(text=f"CPU: {sys_info['cpu_percent']:.2f}%")
            self.cpu_progress['value'] = sys_info['cpu_percent']
            
            total_memory_mb = psutil.virtual_memory().total / (1024 * 1024)
            mem_percent = (sys_info['memory_usage_mb'] / total_memory_mb) * 100
            self.mem_label.config(text=f"内存: {mem_percent:.2f}%")
            self.mem_progress['value'] = mem_percent

            self.net_label.config(text=f"网络: ↓{sys_info['net_recv_mb']:.2f}MB/s ↑{sys_info['net_sent_mb']:.2f}MB/s")
        
        # 更新每个 RTSP 线程条目
        for update in rtsp_updates:
            thread_item_id = update['thread_item_id']
            if self.tree.exists(thread_item_id):
                lost_rate = (update['lost_frames'] / update['expected_frames']) * 100 if update['expected_frames'] > 0 else 0
                
                self.tree.item(thread_item_id, values=(
                    f"#{update['thread_id']}",
                    THREAD_TO_URL_MAP.get(update['thread_id'], 'N/A'),
                    update['status'],
                    f"{update['current_fps']:.2f}",
                    update['received_frames'],
                    update['expected_frames'],
                    update['lost_frames'],
                    f"{lost_rate:.2f}%",
                    f"{update['total_bytes'] / (1024*1024):.2f} MB",
                    update['reconnect_count'],
                    f"{update['connect_latency']:.2f}s"
                ))

                if lost_rate > 10 or update['reconnect_count'] > 0:
                    self.tree.item(thread_item_id, tags=('warning',))
                else:
                    self.tree.item(thread_item_id, tags=('normal',))

        # 检查是否所有线程都已启动，并更新状态标签
        if self.monitor_threads and all(t.is_alive() for t in self.monitor_threads):
            self.status_label.config(text=f"正在运行({self.total_threads_count}线程)...")
            self.status_progress.stop()
        
        self.after(SETTINGS.gui_refresh_interval, self.update_statuses)

    def export_to_excel(self):
        if not AGGREGATED_DATA:
            messagebox.showwarning("警告", "没有数据可供导出！")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not file_path:
            return

        try:
            data_to_export = []
            for item_id, data in AGGREGATED_DATA.items():
                url = self.url_list_data[item_id]['url']
                avg_fps = sum(data['fps_list']) / len(data['fps_list']) if data['fps_list'] else 0
                avg_latency = sum(data['latency_list']) / len(data['latency_list']) if data['latency_list'] else 0
                total_lost_rate = (data['total_lost_frames'] / data['total_expected_frames']) * 100 if data['total_expected_frames'] > 0 else 0
                
                threads_count = self.url_list_data.get(item_id, {}).get('threads_count', 1)

                data_to_export.append({
                    "RTSP 地址": url,
                    "线程数": threads_count,
                    "总有效帧": data['total_frames'],
                    "总预计帧": data['total_expected_frames'],
                    "总丢失帧": data['total_lost_frames'],
                    "总丢失率": f"{total_lost_rate:.2f}%",
                    "总流量 (MB)": f"{data['total_bytes'] / (1024*1024):.2f}",
                    "总重连次数": data['total_reconnects'],
                    "平均FPS": f"{avg_fps:.2f}",
                    "平均连接延迟 (s)": f"{avg_latency:.2f}"
                })
            
            df = pd.DataFrame(data_to_export)
            df.to_excel(file_path, index=False)
            messagebox.showinfo("成功", f"数据已成功导出到：\n{file_path}")

        except Exception as e:
            messagebox.showerror("错误", f"导出数据失败：{e}")

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
        self.settings_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        
        logging.info("--- 监控任务启动 ---")
        
        self.monitor_threads = []
        STATUS_QUEUES.clear()
        
        self.total_threads_count = len(self.url_list_data)
        
        self.status_label.config(text=f"正在启动({self.total_threads_count}线程)...")
        self.status_progress.start()
        
        # 启动系统监控线程
        if SETTINGS.sys_monitor_enabled:
            sys_monitor_thread = SystemMonitor()
            self.monitor_threads.append(sys_monitor_thread)
            STATUS_QUEUES[-1] = queue.Queue()
            sys_monitor_thread.start()

        # 启动 RTSP 监控线程
        for item_id, data in self.url_list_data.items():
            self.thread_counter = data['id']
            thread_id = self.thread_counter
            THREAD_TO_URL_MAP[thread_id] = data['url']

            thread = RTSPStreamMonitor(
                url=data['url'],
                thread_id=thread_id,
                thread_item_id=item_id,
                protocol=self.protocol_combobox.get()
            )
            self.monitor_threads.append(thread)
            STATUS_QUEUES[thread_id] = queue.Queue()
            thread.start()
        
        logging.info(f"已创建 {len(self.monitor_threads)} 个监控线程。")

    def stop_monitoring(self):
        if not self.monitor_threads:
            return

        logging.info("--- 正在发送停止信号... ---")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text=f"正在停止({self.total_threads_count}线程)...")
        self.status_progress.start()
        
        for thread in self.monitor_threads:
            thread.stop()
        
        wait_thread = threading.Thread(target=self._wait_for_threads_to_join)
        wait_thread.start()

    def _wait_for_threads_to_join(self):
        for thread in self.monitor_threads:
            thread.join()
        
        self.after(100, self._on_threads_stopped)

    def _on_threads_stopped(self):
        self.monitor_threads = []
        STATUS_QUEUES.clear()
        
        logging.info("--- 所有监控线程已停止。---")
        self.status_label.config(text="已停止")
        self.status_progress.stop()

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.add_button.config(state=tk.NORMAL)
        self.batch_add_button.config(state=tk.NORMAL)
        self.clear_button.config(state=tk.NORMAL)
        self.settings_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.NORMAL)
        
    def on_closing(self):
        self.stop_monitoring()
        self.master.destroy()

# ==============================================================================
# 独立的程序入口，只在直接运行此文件时执行
# ==============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    root.title(f"RTSP 压测工具 (线程数: {SETTINGS.global_threads_count})")
    root.geometry("1200x800")

    app = StressTestFrame(root)
    app.pack(fill=tk.BOTH, expand=True)

    def on_closing():
        app.on_closing()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()