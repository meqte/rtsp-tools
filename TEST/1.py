# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel
import threading
import os
import time
import re
import logging
import queue
import logging.handlers
from collections import defaultdict
import psutil
import av

# ==============================================================================
# 全局状态管理
# ==============================================================================
# 全局字典，用于存储每个线程的状态队列
STATUS_QUEUES = defaultdict(queue.Queue)
# 日志队列，用于子线程与主线程通信
LOG_QUEUE = queue.Queue()
# 存储每个地址的汇总数据
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
    """一个线程安全的日志处理器，将日志消息放入队列。"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass

# 设置日志等级为DEBUG，以便显示所有详细信息
logging.basicConfig(level=logging.DEBUG)
logging.getLogger().addHandler(ThreadSafeLogHandler(LOG_QUEUE))

# ==============================================================================
# 多线程视频流监控
# ==============================================================================
class RTSPStreamMonitor(threading.Thread):
    def __init__(self, url, thread_id, tree_item_id, protocol='UDP', expected_fps=25):
        super().__init__()
        self.url = url
        self.thread_id = thread_id
        self.tree_item_id = tree_item_id
        self.protocol = protocol
        self.expected_fps = expected_fps
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
                
                # 使用 PyAV 打开流，动态获取帧率
                options = {'rtsp_transport': self.protocol.lower(), 'buffer_size': '2048000', 'timeout': '5000000'}
                self.container = av.open(self.url, mode='r', options=options)
                
                # 尝试获取视频流的真实帧率
                try:
                    video_stream = self.container.streams.video[0]
                    self.expected_fps = float(video_stream.average_rate)
                    self.logger.info(f"成功获取到流的真实帧率：{self.expected_fps:.2f} FPS")
                except (IndexError, AttributeError):
                    self.logger.warning(f"无法获取视频流的真实帧率，将使用默认值 {self.expected_fps} FPS。")

                self.connect_latency = time.time() - start_time
                self.logger.info(f"连接成功！延迟: {self.connect_latency:.2f}s。开始抓取帧。")

                # 遍历数据包
                for packet in self.container.demux(video=0):
                    if self.stop_event.is_set():
                        break
                    
                    self.total_frames += 1
                    self.total_bytes += packet.size if packet else 0
                    
                    # 实时帧率计算
                    current_time = time.time()
                    elapsed_time = current_time - self.last_frame_time
                    if elapsed_time > 0:
                        self.current_fps = 1 / elapsed_time
                    self.last_frame_time = current_time

                    # 预计帧数和丢失帧数计算
                    total_elapsed_time = current_time - start_time
                    expected_frames = int(total_elapsed_time * self.expected_fps)
                    lost_frames = max(0, expected_frames - self.total_frames)

                    status_info = {
                        'thread_id': self.thread_id,
                        'item_id': self.tree_item_id,
                        'status': "正常",
                        'total_frames': self.total_frames,
                        'received_frames': self.total_frames,
                        'total_bytes': self.total_bytes,
                        'reconnect_count': self.reconnect_count,
                        'connect_latency': self.connect_latency,
                        'current_fps': self.current_fps,
                        'expected_frames': expected_frames,
                        'lost_frames': lost_frames,
                    }
                    if self.thread_id in STATUS_QUEUES:
                        STATUS_QUEUES[self.thread_id].put(status_info)
                    
                    time.sleep(0.001) # 避免忙循环
                
            except (av.AVError, TimeoutError) as e:
                self.reconnect_count += 1
                self.logger.error(f"连接或拉流失败: {e}。第 {self.reconnect_count} 次重试中...")
                status_info = {
                    'thread_id': self.thread_id,
                    'item_id': self.tree_item_id,
                    'status': f"连接失败 (重试{self.reconnect_count})",
                    'total_frames': self.total_frames,
                    'received_frames': self.total_frames,
                    'total_bytes': self.total_bytes,
                    'reconnect_count': self.reconnect_count,
                    'connect_latency': 0.0,
                    'current_fps': 0.0,
                    'expected_frames': 0,
                    'lost_frames': 0,
                }
                if self.thread_id in STATUS_QUEUES:
                    STATUS_QUEUES[self.thread_id].put(status_info)
                time.sleep(5)  # 等待5秒后重试
            except Exception as e:
                self.logger.error(f"发生未知异常: {e}")
                time.sleep(5)
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
    def __init__(self, tree_item_id):
        super().__init__()
        self.tree_item_id = tree_item_id
        self.stop_event = threading.Event()
        self.logger = logging.getLogger("SysMonitor")
        self.p = psutil.Process(os.getpid())
        self.last_net_stats = psutil.net_io_counters()

    def run(self):
        while not self.stop_event.is_set():
            try:
                cpu_percent = self.p.cpu_percent(interval=None)
                mem_info = self.p.memory_info()
                
                current_net_stats = psutil.net_io_counters()
                net_sent = current_net_stats.bytes_sent - self.last_net_stats.bytes_sent
                net_recv = current_net_stats.bytes_recv - self.last_net_stats.bytes_recv
                self.last_net_stats = current_net_stats
                
                status_info = {
                    'thread_id': -1, # 使用特殊ID
                    'item_id': self.tree_item_id,
                    'status': "正常",
                    'cpu_percent': f"{cpu_percent:.2f}",
                    'memory_usage_mb': f"{mem_info.rss / (1024 * 1024):.2f}",
                    'net_sent_mb': f"{net_sent / (1024 * 1024):.2f}",
                    'net_recv_mb': f"{net_recv / (1024 * 1024):.2f}",
                }
                if -1 in STATUS_QUEUES:
                    STATUS_QUEUES[-1].put(status_info)
                
                time.sleep(1) # 每秒更新一次
                
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
        self.url_counter = 0
        self.monitor_threads = []
        self.summary_row_ids = {}
        
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

        ttk.Label(control_frame, text="线程数:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.threads_combobox = ttk.Combobox(control_frame, width=5, values=list(range(1, 11)) + [20, 40, 60, 100], state="readonly")
        self.threads_combobox.set("1")
        self.threads_combobox.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(control_frame, text="协议:").grid(row=0, column=4, padx=5, pady=5, sticky='w')
        self.protocol_combobox = ttk.Combobox(control_frame, width=4, values=['UDP', 'TCP'], state="readonly")
        self.protocol_combobox.set("UDP")
        self.protocol_combobox.grid(row=0, column=5, padx=5, pady=5, sticky='w')

        self.add_button = ttk.Button(control_frame, text="添加", command=self.add_url)
        self.add_button.grid(row=0, column=6, padx=5, pady=5)
        
        self.batch_add_button = ttk.Button(control_frame, text="批量添加", command=self.open_batch_add_window)
        self.batch_add_button.grid(row=0, column=7, padx=5, pady=5)
        
        self.clear_button = ttk.Button(control_frame, text="清空", command=self.clear_list)
        self.clear_button.grid(row=0, column=8, padx=5, pady=5)
        
        # 中间表格展示区
        ttk.Label(self, text="待监控地址列表:").grid(row=1, column=0, padx=10, pady=(10, 0), sticky='w')
        self.address_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=1)
        self.address_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=5)
        self.address_frame.columnconfigure(0, weight=1)
        self.address_frame.rowconfigure(0, weight=1)
        
        columns = ('threads', 'url', 'status', 'fps', 'received_frames', 'expected_frames', 'lost_frames', 'lost_rate', 'total_bytes', 'reconnects', 'latency')
        self.tree = ttk.Treeview(self.address_frame, columns=columns, show='headings')
        self.tree.heading('threads', text='线程', anchor='center')
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
        
        self.tree.column('threads', width=40, anchor='center', stretch=False)
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

        self.start_button = ttk.Button(bottom_frame, text="启动监控", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, padx=5)

        self.stop_button = ttk.Button(bottom_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)
        
        self.status_label = ttk.Label(bottom_frame, text="已停止", foreground="blue")
        self.status_label.grid(row=0, column=2, padx=10)
        
        # 性能监控面板 (在同一行显示)
        self.sys_monitor_label = ttk.Label(bottom_frame, text="CPU: 0.00% | 内存: 0.00 MB | 网络: ↓0.00MB/s ↑0.00MB/s")
        self.sys_monitor_label.grid(row=0, column=3, padx=10, sticky='e')

        # 日志输出区
        ttk.Label(self, text="日志输出:").grid(row=4, column=0, padx=10, pady=(0, 5), sticky='w')
        self.log_text = scrolledtext.ScrolledText(self, height=15, state='disabled', wrap=tk.WORD, font=('Courier', 10))
        self.log_text.grid(row=5, column=0, sticky='nsew', padx=10, pady=(0, 10))

    def show_tree_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item and item not in self.summary_row_ids.values():
            self.tree.selection_set(item)
            menu = tk.Menu(self.tree, tearoff=0)
            menu.add_command(label="移除", command=lambda: self.remove_url(item))
            menu.post(event.x_root, event.y_root)

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
            
        self.url_counter += 1
        item_id = self.tree.insert('', tk.END, values=(0, url, "未启动", "0", "0", "0", "0", "0", "0", "0", "N/A"))
        
        # 插入汇总行
        summary_row_id = self.tree.insert(item_id, tk.END, tags=('summary',))
        self.summary_row_ids[item_id] = summary_row_id
        self.tree.tag_configure('summary', background='#e0e0e0', font=('TkDefaultFont', 9, 'bold'))

        self.url_list_data[item_id] = {
            'url': url,
            'list_index': self.url_counter,
            'summary_row_id': summary_row_id,
        }
        self.url_entry.delete(0, tk.END)

    def remove_url(self, item_id):
        if messagebox.askyesno("确认移除", "确定要移除此项吗？"):
            if item_id in self.url_list_data:
                # 移除汇总行
                self.tree.delete(self.url_list_data[item_id]['summary_row_id'])
                del self.url_list_data[item_id]
            self.tree.delete(item_id)
            self._update_tree_indices()

    def _update_tree_indices(self):
        items = [item for item in self.tree.get_children('') if item not in self.summary_row_ids.values()]
        for i, item in enumerate(items):
            self.tree.set(item, 'threads', 0) # 修正为0
            self.tree.set(item, 'url', self.url_list_data[item]['url'])
            self.tree.set(item, 'status', "未启动")
            self.tree.set(item, 'index', i + 1)
            self.url_list_data[item]['list_index'] = i + 1

    def clear_list(self):
        if messagebox.askyesno("确认清空", "确定要清空列表吗？"):
            self.url_list_data = {}
            self.url_counter = 0
            self.tree.delete(*self.tree.get_children())
            
    def update_statuses(self):
        # 处理日志队列
        while not LOG_QUEUE.empty():
            log_record = LOG_QUEUE.get_nowait()
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, log_record + '\n')
            self.log_text.configure(state='disabled')
            self.log_text.see(tk.END)
        
        # 清空聚合数据
        for key in AGGREGATED_DATA:
            AGGREGATED_DATA[key]['fps_list'] = []
            AGGREGATED_DATA[key]['latency_list'] = []
            AGGREGATED_DATA[key]['total_bytes'] = 0
            AGGREGATED_DATA[key]['total_frames'] = 0
            AGGREGATED_DATA[key]['total_lost_frames'] = 0
            AGGREGATED_DATA[key]['total_reconnects'] = 0
            AGGREGATED_DATA[key]['total_expected_frames'] = 0

        # 处理状态队列并进行聚合
        for thread_id, status_queue in STATUS_QUEUES.items():
            while not status_queue.empty():
                status_info = status_queue.get_nowait()
                if thread_id == -1: # 系统监控信息
                    self.sys_monitor_label.config(text=f"CPU: {status_info['cpu_percent']}% | 内存: {status_info['memory_usage_mb']} MB | 网络: ↓{status_info['net_recv_mb']}MB/s ↑{status_info['net_sent_mb']}MB/s")
                    continue
                
                item_id = status_info['item_id']
                if self.tree.exists(item_id):
                    # 更新单个线程行
                    self.tree.item(item_id, values=(
                        status_info['thread_id'],
                        self.url_list_data[item_id]['url'],
                        status_info['status'],
                        f"{status_info['current_fps']:.2f}",
                        status_info['received_frames'],
                        status_info['expected_frames'],
                        status_info['lost_frames'],
                        f"{(status_info['lost_frames'] / status_info['expected_frames']) * 100:.2f}%" if status_info['expected_frames'] > 0 else "0.00%",
                        f"{status_info['total_bytes'] / (1024*1024):.2f} MB",
                        status_info['reconnect_count'],
                        f"{status_info['connect_latency']:.2f}s"
                    ))
                    
                    # 聚合数据
                    AGGREGATED_DATA[item_id]['threads_count'] += 1
                    AGGREGATED_DATA[item_id]['total_frames'] += status_info['received_frames']
                    AGGREGATED_DATA[item_id]['total_bytes'] += status_info['total_bytes']
                    AGGREGATED_DATA[item_id]['total_reconnects'] += status_info['reconnect_count']
                    AGGREGATED_DATA[item_id]['total_expected_frames'] += status_info['expected_frames']
                    AGGREGATED_DATA[item_id]['total_lost_frames'] += status_info['lost_frames']
                    AGGREGATED_DATA[item_id]['fps_list'].append(status_info['current_fps'])
                    AGGREGATED_DATA[item_id]['latency_list'].append(status_info['connect_latency'])
        
        # 更新汇总行
        for item_id, data in AGGREGATED_DATA.items():
            if item_id in self.url_list_data:
                summary_row_id = self.url_list_data[item_id]['summary_row_id']
                
                # 计算平均值
                avg_fps = sum(data['fps_list']) / len(data['fps_list']) if data['fps_list'] else 0
                avg_latency = sum(data['latency_list']) / len(data['latency_list']) if data['latency_list'] else 0
                total_lost_rate = (data['total_lost_frames'] / data['total_expected_frames']) * 100 if data['total_expected_frames'] > 0 else 0

                self.tree.item(summary_row_id, values=(
                    f"总数({data['threads_count']})",
                    "---- 汇总 ----",
                    "N/A",
                    f"{avg_fps:.2f}",
                    data['total_frames'],
                    data['total_expected_frames'],
                    data['total_lost_frames'],
                    f"{total_lost_rate:.2f}%",
                    f"{data['total_bytes'] / (1024*1024):.2f} MB",
                    data['total_reconnects'],
                    f"{avg_latency:.2f}s"
                ))
                    
        self.after(200, self.update_statuses)

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

        # 清空并重新初始化队列和线程列表
        self.monitor_threads = []
        STATUS_QUEUES.clear()
        
        try:
            threads_count = int(self.threads_combobox.get())
        except ValueError:
            threads_count = 1
        protocol = self.protocol_combobox.get()
        
        # 启动系统监控线程
        sys_monitor_thread = SystemMonitor(tree_item_id='system_info')
        self.monitor_threads.append(sys_monitor_thread)
        STATUS_QUEUES[-1] = queue.Queue()
        sys_monitor_thread.start()

        # 启动 RTSP 监控线程
        task_counter = 0
        for item_id, data in self.url_list_data.items():
            self.tree.set(item_id, 'threads', threads_count)
            for _ in range(threads_count):
                task_counter += 1
                thread = RTSPStreamMonitor(
                    url=data['url'],
                    thread_id=task_counter,
                    tree_item_id=item_id,
                    protocol=protocol
                )
                self.monitor_threads.append(thread)
                STATUS_QUEUES[task_counter] = queue.Queue()
                thread.start()
        
        logging.info(f"已创建 {len(self.monitor_threads)} 个监控线程。")

    def stop_monitoring(self):
        if not self.monitor_threads:
            return

        logging.info("--- 正在发送停止信号... ---")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        
        # 向所有线程发送停止信号
        for thread in self.monitor_threads:
            thread.stop()
        
        # 使用一个线程来等待所有监控线程结束
        wait_thread = threading.Thread(target=self._wait_for_threads_to_join)
        wait_thread.start()

    def _wait_for_threads_to_join(self):
        # 等待所有线程完成
        for thread in self.monitor_threads:
            thread.join()
        
        # 在 GUI 线程中调用收尾函数
        self.after(100, self._on_threads_stopped)

    def _on_threads_stopped(self):
        self.monitor_threads = []
        STATUS_QUEUES.clear()
        
        logging.info("--- 所有监控线程已停止。---")
        self.status_label.config(text="已停止")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.add_button.config(state=tk.NORMAL)
        self.batch_add_button.config(state=tk.NORMAL)
        self.clear_button.config(state=tk.NORMAL)
        
    def on_closing(self):
        self.stop_monitoring()
        self.master.destroy()

# ==============================================================================
# 独立的程序入口，只在直接运行此文件时执行
# ==============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    root.title("RTSP 压测工具")
    root.geometry("800x600")

    app = StressTestFrame(root)
    app.pack(fill=tk.BOTH, expand=True)

    def on_closing():
        app.on_closing()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()