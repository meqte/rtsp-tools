# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel
import threading
import os
import cv2
import time
import re
import logging
import asyncio
import queue
import logging.handlers
from collections import defaultdict

# ==============================================================================
# 全局状态管理
# ==============================================================================
# 主事件循环
event_loop = None
# 异步任务列表
async_tasks = []
# 用于停止所有异步任务的信号
stop_event = threading.Event()
# 状态更新队列，用于主线程与异步任务通信
STATUS_QUEUES = defaultdict(queue.Queue)
# 日志队列，用于异步任务与主线程通信
LOG_QUEUE = queue.Queue()

# ==============================================================================
# 日志配置
# ==============================================================================
class AsyncioLogHandler(logging.Handler):
    """一个线程安全的日志处理器，将日志消息放入队列。"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass

# ==============================================================================
# 异步视频流监控协程
# ==============================================================================
async def monitor_stream(url, thread_id, tree_item_id, delay_s, protocol, loop):
    logger = logging.getLogger(f"monitor-{thread_id}")
    logger.setLevel(logging.DEBUG)

    def _update_status(status, connect_latency=None, total=None, valid=None, dropped=None, drop_rate=None):
        status_info = {
            'thread_id': thread_id,
            'item_id': tree_item_id,
            'status': status,
            'connect_latency': f"{connect_latency:.2f}" if connect_latency is not None else 'N/A',
            'total_frames_count': total if total is not None else 'N/A',
            'valid_frames_count': valid if valid is not None else 'N/A',
            'dropped_frames_count': dropped if dropped is not None else 'N/A',
            'drop_rate': f"{drop_rate:.2f}%" if drop_rate is not None else 'N/A',
        }
        try:
            if thread_id in STATUS_QUEUES:
                STATUS_QUEUES[thread_id].put_nowait(status_info)
        except queue.Full:
            pass

    cap = None
    # 最终修复：仅通过在 URL 中显式指定传输协议来解决兼容性问题
    rtsp_url = url
    if protocol == 'TCP':
        if '?' in rtsp_url:
            rtsp_url += "&rtsp_transport=tcp"
        else:
            rtsp_url += "?rtsp_transport=tcp"
    elif protocol == 'UDP':
        if '?' in rtsp_url:
            rtsp_url += "&rtsp_transport=udp"
        else:
            rtsp_url += "?rtsp_transport=udp"

    try:
        _update_status("连接中...")
        logger.debug(f"尝试连接: {rtsp_url} (协议: {protocol})")
        
        # 使用 run_in_executor 避免阻塞事件循环
        start_time = time.time()
        # 移除 cap.set()，仅依赖 URL 参数
        cap = await loop.run_in_executor(None, lambda: cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG))
        connect_latency = time.time() - start_time
        
        if not cap.isOpened():
            logger.error("连接失败：无法打开视频流。")
            _update_status("连接失败", connect_latency)
            return
            
        logger.info(f"连接成功！耗时: {connect_latency:.2f} 秒。")
        
        total_frames = 0
        valid_frames = 0

        while not stop_event.is_set():
            total_frames += 1
            
            # 使用 run_in_executor 异步调用阻塞方法
            ret = await loop.run_in_executor(None, cap.grab)
            
            if ret:
                valid_frames += 1
                dropped_frames = total_frames - valid_frames
                drop_rate = (dropped_frames / total_frames) * 100 if total_frames > 0 else 0
                
                if valid_frames % 100 == 0:
                    logger.debug(f"成功抓取 {valid_frames} 帧。")
                    
                _update_status("正常", connect_latency, total_frames, valid_frames, dropped_frames, drop_rate)
            else:
                logger.error(f"抓取帧失败，可能连接已断开，正在准备退出...")
                _update_status("抓取失败", connect_latency, total_frames, valid_frames, total_frames-valid_frames, 100)
                break
            
            await asyncio.sleep(delay_s)

    except asyncio.CancelledError:
        logger.info("任务已取消。")
        _update_status("已停止")
    except Exception as e:
        logger.error(f"发生异常: {e}")
        _update_status("发生异常")
    finally:
        if cap and cap.isOpened():
            cap.release()
            logger.info("连接已断开。")

# ==============================================================================
# GUI 框架
# ==============================================================================
class StressTestFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.url_list_data = {}
        self.url_counter = 0
        
        # 日志配置
        logging.basicConfig(level=logging.INFO)
        log_format = logging.Formatter("[%(asctime)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        log_handler = AsyncioLogHandler(LOG_QUEUE)
        log_handler.setFormatter(log_format)
        logging.getLogger().addHandler(log_handler)
        
        self.create_widgets()
        self.update_statuses()

    def update_statuses(self):
        # 处理状态更新
        try:
            for thread_id, status_queue in STATUS_QUEUES.items():
                while not status_queue.empty():
                    status_info = status_queue.get_nowait()
                    item_id = status_info['item_id']
                    if self.tree.exists(item_id):
                        status = status_info['status']
                        is_abnormal = status in ["连接失败", "抓取失败", "已断开", "发生异常"]
                        
                        if is_abnormal:
                            self.tree.item(item_id, tags=('abnormal',))
                        else:
                            self.tree.item(item_id, tags=())

                        self.tree.set(item_id, 'status', status)
                        self.tree.set(item_id, 'connect_latency', status_info.get('connect_latency', 'N/A'))
                        self.tree.set(item_id, 'total_frames_count', status_info.get('total_frames_count', 'N/A'))
                        self.tree.set(item_id, 'valid_frames_count', status_info.get('valid_frames_count', 'N/A'))
                        self.tree.set(item_id, 'dropped_frames_count', status_info.get('dropped_frames_count', 'N/A'))
                        self.tree.set(item_id, 'drop_rate', status_info.get('drop_rate', 'N/A'))
        except Exception as e:
            print(f"Error in status updater: {e}")

        # 处理日志更新
        try:
            while not LOG_QUEUE.empty():
                message = LOG_QUEUE.get_nowait()
                self.log_text.configure(state='normal')
                self.log_text.insert(tk.END, f"{message}\n")
                self.log_text.configure(state='disabled')
                self.log_text.see(tk.END)
        except Exception as e:
            print(f"Error in log updater: {e}")

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
        self.url_entry.insert(0, "rtsp://192.168.0.3/live/1/1")
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        ttk.Label(control_frame, text="线程:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.threads_combobox = ttk.Combobox(control_frame, width=4, values=list(range(1, 11)))
        self.threads_combobox.set("1")
        self.threads_combobox.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(control_frame, text="延迟(秒):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.delay_combobox = ttk.Combobox(control_frame, width=4, values=list(range(1, 11)))
        self.delay_combobox.set("1")
        self.delay_combobox.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        ttk.Label(control_frame, text="协议:").grid(row=1, column=2, padx=5, pady=5, sticky='w')
        self.protocol_combobox = ttk.Combobox(control_frame, width=4, values=['TCP', 'UDP'])
        self.protocol_combobox.set("UDP")
        self.protocol_combobox.grid(row=1, column=3, padx=5, pady=5)
        
        self.add_button = ttk.Button(control_frame, text="添加地址", command=self.add_url)
        self.add_button.grid(row=0, column=4, padx=5, pady=5)
        
        self.batch_add_button = ttk.Button(control_frame, text="批量添加", command=self.open_batch_add_window)
        self.batch_add_button.grid(row=0, column=5, padx=5, pady=5)

        control_frame.columnconfigure(1, weight=1)

        self.bind_right_click_menu(self.url_entry)
        
        ttk.Label(self, text="待监控地址列表:").pack(pady=(10, 0), padx=10, anchor='w')
        self.address_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=1, height=150)
        self.address_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.address_frame.pack_propagate(False)

        self.tree = ttk.Treeview(self.address_frame, columns=('index', 'url', 'status', 'total_frames_count', 'valid_frames_count', 'dropped_frames_count', 'drop_rate', 'connect_latency'), show='headings')
        self.tree.tag_configure('abnormal', foreground='red')

        self.tree.heading('index', text='序号', anchor='center')
        self.tree.heading('url', text='RTSP 地址', anchor='w')
        self.tree.heading('status', text='状态', anchor='center')
        self.tree.heading('total_frames_count', text='总尝试数', anchor='center')
        self.tree.heading('valid_frames_count', text='总接收数', anchor='center')
        self.tree.heading('dropped_frames_count', text='总丢失数', anchor='center')
        self.tree.heading('drop_rate', text='丢帧率', anchor='center')
        self.tree.heading('connect_latency', text='耗时', anchor='center')
        
        self.tree.column('index', width=40, anchor='center', stretch=False)
        self.tree.column('url', minwidth=120, anchor='w', stretch=True) 
        self.tree.column('status', width=60, anchor='center', stretch=False)
        self.tree.column('total_frames_count', width=60, anchor='center', stretch=False)
        self.tree.column('valid_frames_count', width=60, anchor='center', stretch=False)
        self.tree.column('dropped_frames_count', width=60, anchor='center', stretch=False)
        self.tree.column('drop_rate', width=60, anchor='center', stretch=False)
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
        
        default_urls = """rtsp://192.168.0.3/live/1/1
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

        self.url_counter += 1
        item_id = self.tree.insert('', tk.END, values=(self.url_counter, url, "未启动", "N/A", "N/A", "N/A", "N/A", "N/A"))
        
        self.url_list_data[item_id] = {
            'url': url,
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

    # 创建并启动监控任务的异步函数
    async def _create_and_start_tasks(self, url, threads_count, delay_s, protocol, row_count, event_loop_ref, tree_instance):
        global async_tasks
        
        for i in range(1, threads_count + 1):
            row_count += 1
            thread_counter = len(async_tasks) + 1 # Use current length for unique ID
            
            new_item_id = tree_instance.insert('', tk.END, values=(row_count, url, "正在启动...", "N/A", "N/A", "N/A", "N/A", "N/A"))
            STATUS_QUEUES[thread_counter] = queue.Queue()
            
            task = event_loop_ref.create_task(monitor_stream(
                url=url,
                thread_id=thread_counter,
                tree_item_id=new_item_id,
                delay_s=delay_s,
                protocol=protocol,
                loop=event_loop_ref
            ))
            async_tasks.append(task)
        
        return row_count

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
        
        global async_tasks
        global STATUS_QUEUES
        global stop_event
        
        async_tasks = []
        STATUS_QUEUES.clear()
        stop_event.clear()
        
        try:
            global_threads_count = int(self.threads_combobox.get())
            if global_threads_count < 1:
                messagebox.showwarning("警告", "线程数不能小于1，已自动设置为1。")
                global_threads_count = 1
            
            delay_s = int(self.delay_combobox.get())
            if delay_s < 1:
                messagebox.showwarning("警告", "延迟时间不能小于1，已自动设置为1。")
                delay_s = 1
            
            protocol = self.protocol_combobox.get()
            if not protocol in ['TCP', 'UDP']:
                messagebox.showwarning("警告", "协议选择无效，已自动设置为TCP。")
                protocol = 'TCP'

        except ValueError:
            messagebox.showwarning("警告", "线程数或延迟时间输入无效，已自动设置为1。")
            global_threads_count = 1
            delay_s = 1
            protocol = 'TCP'

        self.tree.delete(*self.tree.get_children())
        row_count = 0
        
        for item_id, data in self.url_list_data.items():
            url = data['url']
            
            # 使用 call_soon_threadsafe 安全地在 asyncio 线程中创建任务，并传入所有必要参数
            event_loop.call_soon_threadsafe(
                asyncio.create_task,
                self._create_and_start_tasks(
                    url=url,
                    threads_count=global_threads_count,
                    delay_s=delay_s,
                    protocol=protocol,
                    row_count=row_count,
                    event_loop_ref=event_loop,
                    tree_instance=self.tree
                )
            )

    def stop_monitoring(self):
        if not async_tasks:
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

        # 设置停止事件，让所有正在运行的协程在下次循环时优雅退出
        stop_event.set()

        # 显式取消所有正在运行的任务，以便更快地停止
        for task in async_tasks:
            task.cancel()
        
        self.after(100, self._shutdown_worker)

    def _shutdown_worker(self):
        # 检查所有任务是否已完成
        if any(not task.done() for task in async_tasks):
            self.after(500, self._shutdown_worker)
        else:
            self._on_threads_stopped()

    def _on_threads_stopped(self):
        global async_tasks
        async_tasks = []
        STATUS_QUEUES.clear()
        
        logging.info("--- 所有监控任务已停止。---")
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
        # 安全地停止 asyncio 事件循环
        event_loop.call_soon_threadsafe(event_loop.stop)
        
# ==============================================================================
# 独立的程序入口，只在直接运行此文件时执行
# ==============================================================================
def main():
    global event_loop
    # 创建并启动一个单独的线程来运行 asyncio 事件循环
    def run_asyncio_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    event_loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=run_asyncio_loop, args=(event_loop,), daemon=True)
    loop_thread.start()

    root = tk.Tk()
    root.title("RTSP 压测工具 - 异步版")
    root.geometry("1000x600")

    app = StressTestFrame(root)
    app.pack(fill=tk.BOTH, expand=True)

    def on_closing():
        app.on_closing()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()

if __name__ == "__main__":
    main()