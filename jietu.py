# -*- coding: utf-8 -*-
"""
定时截图工具 v1.0

核心功能：
- 提供一个 GUI 界面，用于输入多个 RTSP 地址。
- 使用多线程并发连接到每个 RTSP 流，并按设定的时间间隔进行截图。
- 支持设置截图间隔时间（2-50分钟）和每次截图数量（1-5张）。
- 截图文件保存到 DS 文件夹中，按 RTSP 地址编号分别保存在不同子文件夹。
- 截图文件按当前时间命名，格式为 YYYY-MM-DD_HH-MM-SS.jpg。

技术栈：
- GUI 库: tkinter，与之前的工具保持一致。
- 视频处理: PyAV (av)，用于连接 RTSP 流和保存图片。
- 并发处理: threading，用于高效地处理多个任务。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import av
from PIL import Image, ImageTk
import sys
import time
import re
import numpy as np
import datetime

class TimedScreenshotFrame(ttk.Frame):
    """
    定时截图工具主类，负责创建和管理 GUI 界面。
    可嵌入其他框架的子组件，同时保留独立运行能力。
    """
    def __init__(self, parent):
        super().__init__(parent)
        
        self.threads = []
        self.stop_event = threading.Event()
        self.log_lock = threading.Lock()
        self.is_running = False
        self.scheduler_thread = None
        
        # 添加日志级别控制变量
        self.current_log_level = 'INFO'  # 默认日志级别
        # 定义日志级别的优先级，数字越大优先级越高
        self.log_level_priority = {
            'DEBUG': 0,
            'INFO': 1,
            'SUCCESS': 2,
            'WARNING': 3,
            'ERROR': 4
        }
        
        self.create_widgets()
        
    def create_widgets(self):
        """创建界面上的所有控件。"""
        # 主框架
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部输入和控制区域
        top_frame = ttk.Frame(main_frame, padding="5")
        top_frame.pack(fill=tk.X)

        # RTSP地址输入框
        url_label = ttk.Label(top_frame, text="RTSP 地址列表 (每行一个):")
        url_label.grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.url_text = scrolledtext.ScrolledText(top_frame, wrap=tk.WORD, height=10, font=('Courier', 10))
        self.url_text.grid(row=1, column=0, columnspan=3, sticky='nsew', padx=5, pady=5)
        # 添加8K测试地址和新的RTSP地址
        self.url_text.insert(tk.END, "rtsp://192.168.10.52:554/pv/262?token=admin_fkt1234\nrtsp://admin:Admin1234!@192.168.10.71:554/cam/realmonitor?channel=1subtype=1")
        
        # 控制参数区域
        control_frame = ttk.Frame(top_frame)
        control_frame.grid(row=2, column=0, columnspan=3, sticky='w', pady=(5, 0))

        # 截图间隔时间下拉框
        interval_label = ttk.Label(control_frame, text="间隔:")
        interval_label.pack(side=tk.LEFT, padx=5)
        self.interval_combobox = ttk.Combobox(control_frame, values=["1", "2", "5", "10", "30"], 
                                            width=8, state="readonly")
        self.interval_combobox.set("10")  # 默认2分钟
        self.interval_combobox.pack(side=tk.LEFT, padx=5)
        
        # 截图数量下拉框
        count_label = ttk.Label(control_frame, text="数量:")
        count_label.pack(side=tk.LEFT, padx=(10, 5))
        self.count_combobox = ttk.Combobox(control_frame, values=["1", "2", "3"], 
                                         width=8, state="readonly")
        self.count_combobox.set("1")  # 默认1张
        self.count_combobox.pack(side=tk.LEFT, padx=5)

        # 日志级别下拉框
        log_level_label = ttk.Label(control_frame, text="日志:")
        log_level_label.pack(side=tk.LEFT, padx=(10, 5))
        self.log_level_combobox = ttk.Combobox(control_frame, values=["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"], 
                                             width=8, state="readonly")
        self.log_level_combobox.set("INFO")  # 默认INFO级别
        self.log_level_combobox.pack(side=tk.LEFT, padx=5)
        self.log_level_combobox.bind("<<ComboboxSelected>>", self.on_log_level_change)

        # 按钮
        self.start_button = ttk.Button(control_frame, text="启动定时截图", command=self.start_timed_capture)
        self.start_button.pack(side=tk.LEFT, padx=(20, 5))
        
        self.stop_button = ttk.Button(control_frame, text="停止截图", command=self.stop_timed_capture, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # 单次截图按钮放在最右侧，与其他按钮分开
        self.single_capture_button = ttk.Button(control_frame, text="单次截图", command=self.single_capture)
        self.single_capture_button.pack(side=tk.RIGHT, padx=(20, 0))
        
        # 使输入文本框可以随窗口缩放
        top_frame.columnconfigure(0, weight=1)
        top_frame.rowconfigure(1, weight=1)

        # 底部日志区
        log_frame = ttk.Frame(main_frame, padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        log_label = ttk.Label(log_frame, text="日志输出:")
        log_label.pack(pady=(0, 5), anchor='w')
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', wrap=tk.WORD, font=('Courier', 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 优化日志颜色配置
        self.log_text.tag_config('debug', foreground='gray')
        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('success', foreground='dark green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('warning', foreground='orange')

        # 添加右键菜单
        self.add_context_menu()

    def add_context_menu(self):
        """为文本框和日志框添加右键菜单。"""
        # 创建右键菜单
        self.text_menu = tk.Menu(self, tearoff=0)
        self.text_menu.add_command(label="剪切", command=lambda: self.url_text.event_generate("<<Cut>>"))
        self.text_menu.add_command(label="复制", command=lambda: self.url_text.event_generate("<<Copy>>"))
        self.text_menu.add_command(label="粘贴", command=lambda: self.url_text.event_generate("<<Paste>>"))
        self.text_menu.add_separator()
        self.text_menu.add_command(label="全选", command=self.select_all_input)

        self.log_menu = tk.Menu(self, tearoff=0)
        self.log_menu.add_command(label="复制", command=lambda: self.log_text.event_generate("<<Copy>>"))
        self.log_menu.add_separator()
        self.log_menu.add_command(label="全选", command=self.select_all_log)

        # 绑定右键点击事件
        self.url_text.bind("<Button-3>", self.show_text_menu)
        self.log_text.bind("<Button-3>", self.show_log_menu)
    
    def show_text_menu(self, event):
        """显示输入框的右键菜单。"""
        self.text_menu.post(event.x_root, event.y_root)

    def show_log_menu(self, event):
        """显示日志框的右键菜单。"""
        self.log_menu.post(event.x_root, event.y_root)

    def select_all_input(self):
        """全选输入框中的文本。"""
        self.url_text.tag_add("sel", "1.0", "end")
        return "break"
    
    def select_all_log(self):
        """全选日志框中的文本。"""
        self.log_text.configure(state='normal')
        self.log_text.tag_add("sel", "1.0", "end")
        self.log_text.configure(state='disabled')
        return "break"

    def on_log_level_change(self, event=None):
        """当日志级别下拉框选择变化时调用"""
        self.current_log_level = self.log_level_combobox.get()
        self.log_to_gui(f"日志级别已设置为: {self.current_log_level}", 'info')

    def should_display_log(self, log_tag):
        """
        判断日志是否应该显示，基于当前选择的日志级别
        只显示等于或高于当前级别的日志
        """
        # 将标签转换为大写进行比较
        log_tag = log_tag.upper()
        
        # 特殊处理SUCCESS级别，将其视为INFO级别
        if log_tag == 'SUCCESS':
            log_tag = 'INFO'
        
        # 如果标签不在优先级字典中，默认显示
        if log_tag not in self.log_level_priority:
            return True
            
        # 获取当前选择的日志级别优先级
        current_level_priority = self.log_level_priority.get(self.current_log_level.upper(), 1)
        
        # 获取日志标签的优先级
        log_tag_priority = self.log_level_priority.get(log_tag, 1)
        
        # 只显示等于或高于当前级别的日志
        return log_tag_priority >= current_level_priority

    def log_to_gui(self, message, tag='info'):
        """
        线程安全的日志输出函数。
        """
        # 添加debug级别的日志示例
        if tag.lower() == 'debug':
            # 可以在这里添加一些调试信息
            pass
            
        # 检查日志级别是否应该显示
        if not self.should_display_log(tag):
            return
            
        with self.log_lock:
            self.log_text.configure(state='normal')
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self.log_text.configure(state='disabled')
            self.log_text.see(tk.END)
    
    def single_capture(self):
        """
        单次截图功能，不使用定时器，直接对所有RTSP地址进行一次截图。
        截图保存到IMG文件夹，按顺序命名为1.jpg、2.jpg等。
        """
        urls = self.url_text.get('1.0', tk.END).strip().split('\n')
        urls = [url.strip() for url in urls if url.strip()]

        if not urls:
            messagebox.showwarning("警告", "请先输入至少一个 RTSP 地址！")
            return
        
        self.log_to_gui("--- 开始单次截图任务 ---", 'info')
        
        # 确保截图文件夹存在
        screenshot_dir = "IMG"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
            self.log_to_gui(f"已创建截图文件夹: {screenshot_dir}", 'info')
        
        # 禁用按钮防止重复操作
        self.single_capture_button.config(state=tk.DISABLED)
        
        # 使用线程池并发处理截图
        threads = []
        for i, url in enumerate(urls):
            thread = threading.Thread(target=self.capture_screenshot, args=(url, i + 1, False))
            threads.append(thread)
            thread.start()
        
        # 启动监控线程等待所有截图完成
        monitor_thread = threading.Thread(target=self.single_capture_monitor, args=(threads,))
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def capture_screenshot(self, url, folder_index, is_timed=False, screenshot_count=1, shot_num=0):
        """
        统一的截图方法，支持单次截图和定时截图。
        
        Args:
            url: RTSP地址
            folder_index: 文件夹编号
            is_timed: 是否为定时截图
            screenshot_count: 截图数量
            shot_num: 当前截图序号
        """
        log_prefix = f"[文件夹{folder_index}]" if is_timed else f"[{folder_index}]"
        self.log_to_gui(f"{log_prefix} 正在连接: {url}", 'info')
        # 添加debug日志
        self.log_to_gui(f"{log_prefix} DEBUG: 开始连接到RTSP流 {url}", 'debug')
        
        try:
            # 针对8K视频优化的连接选项
            rtsp_options = {
                'rtsp_transport': 'tcp',     # 使用 TCP 传输，更稳定
                'stimeout': '5000000',       # 5秒超时 (微秒) - 减少等待时间
                'max_delay': '500000',       # 最大延迟 0.5秒 - 减少缓冲时间
                'buffer_size': '131072',     # 128KB缓冲区 - 减少内存占用
                'rtsp_flags': 'prefer_tcp',  # 强制使用TCP
                'allowed_media_types': 'video', # 只接收视频流
                'reorder_queue_size': '100', # 减少重排序队列大小
                'rw_timeout': '5000000',     # 读写超时5秒
                'timeout': '5000000',        # 连接超时5秒
            }
            
            # 添加debug日志
            self.log_to_gui(f"{log_prefix} DEBUG: 使用连接参数 {rtsp_options}", 'debug')
            
            self.log_to_gui(f"{log_prefix} 使用优化参数连接...", 'debug')
            
            # 使用 PyAV 打开流，添加超时控制
            container = av.open(url, options=rtsp_options, timeout=5)
            
            video_stream = container.streams.video[0]
            self.log_to_gui(f"{log_prefix} 连接成功！正在捕获帧...", 'info')
            # 添加debug日志
            self.log_to_gui(f"{log_prefix} DEBUG: 连接成功，视频流信息 - 宽度: {video_stream.width}, 高度: {video_stream.height}", 'debug')
            
            # 添加debug日志
            self.log_to_gui(f"{log_prefix} DEBUG: 开始调用capture_frame_for_single_shot方法", 'debug')
            
            # 获取视频流信息
            width = video_stream.width or 0
            height = video_stream.height or 0
            self.log_to_gui(f"{log_prefix} 视频流信息: {width}x{height}, 编码: {video_stream.codec}", 'debug')
            
            # 捕获帧 - 使用统一的优化方法
            frame_array = self.capture_frame_for_single_shot(container, video_stream, folder_index)
            
            # 添加debug日志
            self.log_to_gui(f"{log_prefix} DEBUG: capture_frame_for_single_shot返回结果: {frame_array is not None}", 'debug')
            
            if frame_array is not None:
                # 添加debug日志
                self.log_to_gui(f"{log_prefix} DEBUG: 成功获取帧数据，准备保存图片", 'debug')
                
                # 单次截图保存到IMG根目录
                if not is_timed:
                    # 单次截图直接保存在IMG根目录
                    folder_path = "IMG"
                    if not os.path.exists(folder_path):
                        os.makedirs(folder_path)
                    
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    filename = f"{folder_path}/{folder_index}.jpg"
                else:
                    # 定时截图保存到分类文件夹
                    folder_path = f"IMG/{folder_index}"
                    if not os.path.exists(folder_path):
                        os.makedirs(folder_path)
                    
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    if screenshot_count > 1:
                        filename = f"{folder_path}/{timestamp}_{shot_num + 1:02d}.jpg"
                    else:
                        filename = f"{folder_path}/{timestamp}.jpg"
                
                # 添加debug日志
                self.log_to_gui(f"{log_prefix} DEBUG: 准备保存图片到 {filename}", 'debug')
                
                # 将 numpy 数组转换为 PIL 图像并保存
                image = Image.fromarray(frame_array)
                image.save(filename, 'JPEG', quality=100)
                
                # 添加debug日志
                self.log_to_gui(f"{log_prefix} DEBUG: 图片保存完成", 'debug')
                
                if is_timed:
                    self.log_to_gui(f"{log_prefix} 截图成功: {os.path.basename(filename)}", 'success')
                else:
                    self.log_to_gui(f"{log_prefix} 单次截图成功，已保存到IMG根目录: {os.path.basename(filename)}", 'success')
                return True
            else:
                self.log_to_gui(f"{log_prefix} 无法捕获有效帧", 'error')
                return False
                
        except Exception as e:
            self.log_to_gui(f"{log_prefix} 连接失败: {str(e)}", 'error')
            return False
        finally:
            try:
                # 安全地检查和关闭container
                container_ref = locals().get('container')
                if container_ref is not None:
                    container_ref.close()
                    # 添加debug日志
                    self.log_to_gui(f"{log_prefix} DEBUG: 容器已关闭", 'debug')
            except:
                pass
    
    def single_capture_monitor(self, threads):
        """
        监控单次截图线程的完成情况。
        """
        for thread in threads:
            thread.join()
        
        # 所有线程都结束后，重新启用按钮
        self.after(100, self.on_single_capture_complete)
    
    def on_single_capture_complete(self):
        """
        单次截图完成后的处理。
        """
        self.log_to_gui("--- 单次截图任务完成 ---", 'info')
        self.single_capture_button.config(state=tk.NORMAL)

    def start_timed_capture(self):
        """
        启动定时截图任务。
        """
        urls = self.url_text.get('1.0', tk.END).strip().split('\n')
        urls = [url.strip() for url in urls if url.strip()]

        if not urls:
            messagebox.showwarning("警告", "请先输入至少一个 RTSP 地址！")
            return
            
        try:
            interval_minutes = int(self.interval_combobox.get())
            screenshot_count = int(self.count_combobox.get())
        except ValueError:
            messagebox.showerror("错误", "请正确选择截图间隔和数量。")
            return

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        
        self.log_to_gui("--- 定时截图任务开始 ---", 'info')
        self.log_to_gui(f"截图间隔: {interval_minutes} 分钟", 'info')
        self.log_to_gui(f"每次截图数量: {screenshot_count} 张", 'info')
        
        # 确保截图文件夹存在
        screenshot_dir = "IMG"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
            self.log_to_gui(f"已创建截图文件夹: {screenshot_dir}", 'debug')
        
        # 为每个RTSP地址创建对应的文件夹
        for i, url in enumerate(urls):
            folder_path = os.path.join(screenshot_dir, str(i + 1))
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                self.log_to_gui(f"已创建文件夹: {folder_path}", 'debug')
        
        # 重置停止事件，准备开始新任务
        self.stop_event.clear()
        self.is_running = True
        
        # 启动定时器线程
        self.scheduler_thread = threading.Thread(target=self.scheduler_worker, 
                                                args=(urls, interval_minutes, screenshot_count))
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
    
    def stop_timed_capture(self):
        """
        停止定时截图任务。
        """
        self.log_to_gui("--- 正在停止定时截图任务...请稍候 ---", 'warning')
        self.stop_event.set()
        self.is_running = False
        self.stop_button.config(state=tk.DISABLED)
        
        # 等待所有线程结束
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=2)
        
        self.start_button.config(state=tk.NORMAL)
        self.log_to_gui("--- 定时截图任务已停止 ---", 'info')

    def scheduler_worker(self, urls, interval_minutes, screenshot_count):
        """
        定时器工作线程，负责按间隔执行截图任务。
        """
        next_capture_time = time.time()
        
        # 添加debug日志
        self.log_to_gui(f"DEBUG: 定时器工作线程启动，截图间隔: {interval_minutes}分钟，每次截图数量: {screenshot_count}", 'debug')
        
        # 添加连续失败计数器
        consecutive_failures = 0
        max_consecutive_failures = 5  # 最大连续失败次数
        
        while not self.stop_event.is_set() and self.is_running:
            current_time = time.time()
            
            if current_time >= next_capture_time:
                self.log_to_gui(f"开始执行截图任务...", 'info')
                
                # 添加debug日志
                self.log_to_gui(f"DEBUG: 开始执行截图任务，当前时间: {current_time}", 'debug')
                
                try:
                    # 执行截图任务
                    self.execute_capture_batch(urls, screenshot_count)
                    # 重置失败计数器
                    consecutive_failures = 0
                    
                    # 添加debug日志
                    self.log_to_gui(f"DEBUG: 截图任务执行完成，重置失败计数器", 'debug')
                except Exception as e:
                    consecutive_failures += 1
                    self.log_to_gui(f"截图任务执行出错: {str(e)}", 'error')
                    
                    # 添加debug日志
                    self.log_to_gui(f"DEBUG: 截图任务执行出错，连续失败次数: {consecutive_failures}", 'debug')
                    
                    # 如果连续失败次数过多，增加等待时间
                    if consecutive_failures >= max_consecutive_failures:
                        self.log_to_gui(f"连续失败{consecutive_failures}次，增加等待时间以减轻系统负担", 'warning')
                        # 延长下次执行时间
                        next_capture_time = current_time + (interval_minutes * 60) + 60  # 额外等待1分钟
                        consecutive_failures = 0  # 重置计数器
                    else:
                        # 正常计算下次截图时间
                        next_capture_time = current_time + (interval_minutes * 60)
                else:
                    # 正常计算下次截图时间
                    next_capture_time = current_time + (interval_minutes * 60)
                
                next_time_str = datetime.datetime.fromtimestamp(next_capture_time).strftime("%H:%M:%S")
                self.log_to_gui(f"下次截图时间: {next_time_str}", 'info')
                
                # 添加debug日志
                self.log_to_gui(f"DEBUG: 下次截图时间: {next_time_str}", 'debug')
            
            # 每秒检查一次
            time.sleep(1)

    def execute_capture_batch(self, urls, screenshot_count):
        """
        执行一批截图任务。
        """
        threads = []
        
        # 添加debug日志
        self.log_to_gui(f"DEBUG: 开始执行批量截图任务，URL数量: {len(urls)}, 每个URL截图数量: {screenshot_count}", 'debug')
        
        for i, url in enumerate(urls):
            folder_index = i + 1
            thread = threading.Thread(target=self.capture_multiple_screenshots, 
                                    args=(url, folder_index, screenshot_count))
            threads.append(thread)
            thread.start()
            
            # 添加debug日志
            self.log_to_gui(f"DEBUG: 启动线程 {thread.name} 处理URL: {url}", 'debug')
        
        # 等待所有截图线程完成，但设置超时
        for thread in threads:
            thread.join(timeout=30)  # 30秒超时
            if thread.is_alive():
                self.log_to_gui(f"线程 {thread.name} 执行超时，可能已阻塞", 'warning')
                
                # 添加debug日志
                self.log_to_gui(f"DEBUG: 线程 {thread.name} 执行超时", 'debug')
        
        self.log_to_gui("本轮截图任务完成", 'success')
        
        # 添加debug日志
        self.log_to_gui(f"DEBUG: 批量截图任务完成", 'debug')
        
    def capture_multiple_screenshots(self, url, folder_index, screenshot_count):
        """
        为单个RTSP地址拍摄多张截图。
        """
        if self.stop_event.is_set():
            return

        # 添加debug日志
        self.log_to_gui(f"[文件夹{folder_index}] DEBUG: 开始多张截图任务，截图数量: {screenshot_count}", 'debug')

        # 拍摄多张截图
        for shot_num in range(screenshot_count):
            if self.stop_event.is_set():
                break
            
            # 添加debug日志
            self.log_to_gui(f"[文件夹{folder_index}] DEBUG: 开始第 {shot_num + 1} 张截图", 'debug')
            
            # 使用统一的截图方法
            try:
                success = self.capture_screenshot(url, folder_index, True, screenshot_count, shot_num)
                
                if not success:
                    self.log_to_gui(f"[文件夹{folder_index}] 第{shot_num + 1}张截图失败", 'error')
                    
                    # 添加debug日志
                    self.log_to_gui(f"[文件夹{folder_index}] DEBUG: 第 {shot_num + 1} 张截图失败", 'debug')
                else:
                    # 添加debug日志
                    self.log_to_gui(f"[文件夹{folder_index}] DEBUG: 第 {shot_num + 1} 张截图成功", 'debug')
            except Exception as e:
                self.log_to_gui(f"[文件夹{folder_index}] 第{shot_num + 1}张截图异常: {str(e)}", 'error')
                
                # 添加debug日志
                self.log_to_gui(f"[文件夹{folder_index}] DEBUG: 第 {shot_num + 1} 张截图异常: {str(e)}", 'debug')
            
            # 如果需要多张截图，间隔1秒
            if screenshot_count > 1 and shot_num < screenshot_count - 1:
                # 检查是否需要停止
                if self.stop_event.is_set():
                    break
                time.sleep(1)
                
                # 添加debug日志
                self.log_to_gui(f"[文件夹{folder_index}] DEBUG: 等待1秒后继续下一张截图", 'debug')
    
    def capture_frame_for_single_shot(self, container, video_stream, index):
        """
        专门用于单次截图的帧捕获方法，优化了稳定性和成功率。
        """
        try:
            frame_count = 0
            max_attempts = 50  # 减少尝试次数，避免长时间阻塞
            
            # 添加debug日志
            self.log_to_gui(f"[{index}] DEBUG: 开始帧捕获，最大尝试次数: {max_attempts}", 'debug')
            
            # 获取视频流信息
            width = video_stream.width or 0
            height = video_stream.height or 0
            
            # 添加debug日志
            self.log_to_gui(f"[{index}] DEBUG: 视频流分辨率: {width}x{height}", 'debug')
            
            # 根据分辨率调整策略
            if width >= 7680:  # 8K视频
                skip_frames = 20   # 8K视频跳过更多帧，确保获得稳定的视频流
                max_attempts = 100  # 增加尝试次数，提高成功率
                self.log_to_gui(f"[{index}] 检测到8K视频，启用增强处理模式（跳过{skip_frames}帧，最多尝试{max_attempts}帧）", 'info')
            elif width >= 3840:  # 4K视频
                skip_frames = 10
                max_attempts = 50
                self.log_to_gui(f"[{index}] 检测到4K视频", 'info')
            else:  # 1080p及以下
                skip_frames = 5
                max_attempts = 50
                self.log_to_gui(f"[{index}] 检测到标准分辨率视频", 'debug')
            
            self.log_to_gui(f"[{index}] 开始捕获帧，将跳过前 {skip_frames} 帧...", 'debug')
            
            # 添加debug日志
            self.log_to_gui(f"[{index}] DEBUG: 跳过帧数设置为: {skip_frames}", 'debug')
            
            # 尝试多种像素格式
            pixel_formats = ['rgb24', 'bgr24', 'yuv420p']
            
            # 添加debug日志
            self.log_to_gui(f"[{index}] DEBUG: 尝试的像素格式: {pixel_formats}", 'debug')
            
            # 添加时间限制，避免长时间阻塞
            import time
            start_time = time.time()
            timeout_seconds = 10  # 10秒超时
            
            for packet in container.demux(video_stream):
                # 添加debug日志
                self.log_to_gui(f"[{index}] DEBUG: 开始处理数据包", 'debug')
                
                # 检查是否超时
                if time.time() - start_time > timeout_seconds:
                    self.log_to_gui(f"[{index}] 帧捕获超时 ({timeout_seconds}秒)，停止捕获", 'warning')
                    break
                    
                for frame in packet.decode():
                    frame_count += 1
                    
                    # 添加debug日志
                    self.log_to_gui(f"[{index}] DEBUG: 解码帧 {frame_count}", 'debug')
                    
                    # 检查是否超时
                    if time.time() - start_time > timeout_seconds:
                        self.log_to_gui(f"[{index}] 帧捕获超时 ({timeout_seconds}秒)，停止捕获", 'warning')
                        break
                    
                    # 跳过初始帧
                    if frame_count <= skip_frames:
                        if frame_count % 5 == 0:
                            self.log_to_gui(f"[{index}] 跳过第 {frame_count} 帧...", 'debug')
                        continue
                    
                    # 添加debug日志
                    self.log_to_gui(f"[{index}] DEBUG: 开始处理第 {frame_count} 帧", 'debug')
                    
                    # 尝试不同的像素格式
                    for fmt in pixel_formats:
                        try:
                            # 添加debug日志
                            self.log_to_gui(f"[{index}] DEBUG: 尝试像素格式 {fmt}", 'debug')
                            
                            # 将 PyAV 帧转换为 numpy 数组
                            frame_array = frame.to_ndarray(format=fmt)
                            
                            # 添加debug日志
                            self.log_to_gui(f"[{index}] DEBUG: 帧转换成功，格式: {fmt}, 形状: {frame_array.shape}", 'debug')
                            
                            # 如果不是RGB格式，转换为RGB
                            if fmt == 'bgr24':
                                frame_array = frame_array[:, :, ::-1]  # BGR转RGB
                                # 添加debug日志
                                self.log_to_gui(f"[{index}] DEBUG: BGR转RGB完成", 'debug')
                            elif fmt == 'yuv420p':
                                # YUV格式需要特殊处理，如果不是3通道就跳过
                                if len(frame_array.shape) != 3 or frame_array.shape[2] != 3:
                                    continue
                            
                            # 检查帧内容
                            if len(frame_array.shape) == 3 and frame_array.shape[2] == 3:
                                # 添加debug日志
                                self.log_to_gui(f"[{index}] DEBUG: 帧内容检查通过", 'debug')
                                
                                # 简化的验证：只检查不是全黑或全灰
                                gray = np.mean(frame_array, axis=2)
                                avg_brightness = np.mean(gray)
                                std_dev = np.std(gray)
                                
                                self.log_to_gui(f"[{index}] 第 {frame_count} 帧 ({fmt}): 亮度={avg_brightness:.1f}, 标准差={std_dev:.2f}", 'debug')
                                
                                # 添加debug日志
                                self.log_to_gui(f"[{index}] DEBUG: 亮度={avg_brightness:.1f}, 标准差={std_dev:.2f}", 'debug')
                                
                                # 更宽松的验证条件
                                is_valid = False
                                
                                # 条件1: 亮度检查
                                if avg_brightness > 5.0:  # 不是全黑
                                    is_valid = True
                                    self.log_to_gui(f"[{index}]   ✅ 通过亮度检查", 'debug')
                                
                                # 条件2: 标准差检查（放宽条件）
                                elif std_dev > 0.3:  # 大幅降低标准差要求
                                    is_valid = True
                                    self.log_to_gui(f"[{index}]   ✅ 通过标准差检查", 'debug')
                                
                                # 条件3: 对于8K视频，即使看起来是灰色也尝试保存
                                elif width >= 7680 and frame_count > skip_frames + 10:
                                    is_valid = True
                                    self.log_to_gui(f"[{index}]   ⚠️ 8K视频强制接受帧 (可能包含内容)", 'debug')
                                
                                if is_valid:
                                    self.log_to_gui(f"[{index}] 找到有效帧: 第 {frame_count} 帧，格式: {fmt}", 'debug')
                                    return frame_array
                                else:
                                    self.log_to_gui(f"[{index}]   ❌ 帧验证失败", 'debug')
                            
                        except Exception as fmt_error:
                            # 添加debug日志
                            self.log_to_gui(f"[{index}] DEBUG: 像素格式 {fmt} 转换失败: {str(fmt_error)}", 'debug')
                            # 静默跳过格式转换错误，尝试下一种格式
                            continue
                    
                    # 如果所有格式都失败
                    if frame_count > skip_frames and frame_count % 10 == 0:
                        self.log_to_gui(f"[{index}] 已尝试 {frame_count} 帧，继续查找...", 'debug')
                    
                    if frame_count >= max_attempts:
                        self.log_to_gui(f"[{index}] 已达到最大尝试次数 ({max_attempts})，停止捕获", 'warning')
                        break
                        
                if frame_count >= max_attempts:
                    break
            
            # 如果没有找到有效帧，尝试备用方案
            self.log_to_gui(f"[{index}] 在 {frame_count} 帧中未找到理想帧，尝试备用方案...", 'warning')
            
            # 备用方案：重新开始，降低所有标准
            try:
                container.seek(0)  # 重置到开头
                frame_count = 0
                start_time = time.time()  # 重置计时器
                
                for packet in container.demux(video_stream):
                    # 检查是否超时
                    if time.time() - start_time > timeout_seconds:
                        self.log_to_gui(f"[{index}] 备用方案超时 ({timeout_seconds}秒)，停止捕获", 'warning')
                        break
                        
                    for frame in packet.decode():
                        frame_count += 1
                        
                        # 检查是否超时
                        if time.time() - start_time > timeout_seconds:
                            self.log_to_gui(f"[{index}] 备用方案超时 ({timeout_seconds}秒)，停止捕获", 'warning')
                            break
                            
                        if frame_count <= 3:  # 只跳过3帧
                            continue
                        
                        try:
                            # 只使用RGB24格式，降低所有验证标准
                            frame_array = frame.to_ndarray(format='rgb24')
                            
                            if len(frame_array.shape) == 3 and frame_array.shape[2] == 3:
                                # 非常宽松的验证：只要不是全黑就接受
                                if np.mean(frame_array) > 0.5:  # 平均值大于0.5就接受
                                    self.log_to_gui(f"[{index}] 备用方案成功: 第 {frame_count} 帧 (宽松标准)", 'debug')
                                    return frame_array
                        except:
                            continue
                        
                        if frame_count >= 30:  # 备用方案尝试30帧
                            break
                    
                    if frame_count >= 30:
                        break
                        
            except Exception as seek_error:
                self.log_to_gui(f"[{index}] 备用方案失败: {str(seek_error)}", 'error')
            
            self.log_to_gui(f"[{index}] 所有方案都失败，无法获取有效帧", 'error')
            return None
                    
        except Exception as e:
            self.log_to_gui(f"[{index}] 捕获帧时发生严重错误: {str(e)}", 'error')
            import traceback
            self.log_to_gui(f"[{index}] 错误详情: {traceback.format_exc()}", 'error')
        
        return None

    def capture_single_frame(self, container, video_stream):
        """
        从视频流中捕获单个有效帧，专门解决8K视频灰色问题。
        """
        try:
            frame_count = 0
            max_attempts = 100  # 大幅增加尝试次数
            
            # 获取视频流信息
            width = video_stream.width or 0
            height = video_stream.height or 0
            self.log_to_gui(f"视频流信息: {width}x{height}, 编码: {video_stream.codec}", 'debug')
            
            # 针对8K视频的特殊处理
            if width >= 7680:  # 8K分辨率
                self.log_to_gui(f"检测到8K视频，启用特殊处理模式", 'info')
                # 跳过更多初始帧，因为8K视频开始的帧可能不完整
                skip_frames = 20
            else:
                skip_frames = 5
            
            self.log_to_gui(f"开始捕获帧，将跳过前 {skip_frames} 帧...", 'debug')
            
            # 尝试多种像素格式
            pixel_formats = ['rgb24', 'bgr24', 'yuv420p', 'nv12']
            
            for packet in container.demux(video_stream):
                if self.stop_event.is_set():
                    break
                    
                for frame in packet.decode():
                    frame_count += 1
                    
                    if self.stop_event.is_set():
                        break
                    
                    # 跳过初始帧
                    if frame_count <= skip_frames:
                        if frame_count % 5 == 0:
                            self.log_to_gui(f"跳过第 {frame_count} 帧...", 'debug')
                        continue
                    
                    # 尝试不同的像素格式
                    for fmt in pixel_formats:
                        try:
                            # 将 PyAV 帧转换为 numpy 数组
                            frame_array = frame.to_ndarray(format=fmt)
                            
                            # 如果不是RGB格式，转换为RGB
                            if fmt == 'bgr24':
                                frame_array = frame_array[:, :, ::-1]  # BGR转RGB
                            elif fmt in ['yuv420p', 'nv12']:
                                # YUV格式需要特殊处理
                                if len(frame_array.shape) == 3 and frame_array.shape[2] == 3:
                                    # 已经是3通道，可能已经转换了
                                    pass
                                else:
                                    # 跳过YUV格式的复杂转换，优先使用RGB格式
                                    continue
                            
                            # 检查帧内容
                            if len(frame_array.shape) == 3 and frame_array.shape[2] == 3:
                                # 详细分析帧内容
                                gray = np.mean(frame_array, axis=2)
                                avg_brightness = np.mean(gray)
                                std_dev = np.std(gray)
                                min_val = np.min(gray)
                                max_val = np.max(gray)
                                
                                # 检查各通道的分布
                                r_channel = frame_array[:, :, 0]
                                g_channel = frame_array[:, :, 1]
                                b_channel = frame_array[:, :, 2]
                                
                                r_std = np.std(r_channel)
                                g_std = np.std(g_channel)
                                b_std = np.std(b_channel)
                                
                                self.log_to_gui(f"第 {frame_count} 帧 ({fmt}): 亮度={avg_brightness:.1f}, 标准差={std_dev:.2f}", 'debug')
                                self.log_to_gui(f"  RGB标准差: R={r_std:.2f}, G={g_std:.2f}, B={b_std:.2f}", 'debug')
                                
                                # 更宽松的验证条件，针对8K视频优化
                                is_valid = False
                                
                                # 条件1: 亮度检查（大幅降低阈值）
                                if avg_brightness > 1.0:  # 8K视频降低亮度要求
                                    is_valid = True
                                    self.log_to_gui(f"  ✅ 通过亮度检查", 'success')
                                
                                # 条件2: 标准差检查（大幅降低要求）
                                elif std_dev > 0.1:  # 8K视频大幅降低标准差要求
                                    is_valid = True
                                    self.log_to_gui(f"  ✅ 通过标准差检查", 'success')
                                
                                # 条件3: RGB通道差异检查
                                elif max(float(r_std), float(g_std), float(b_std)) > 0.5:
                                    is_valid = True
                                    self.log_to_gui(f"  ✅ 通过RGB通道检查", 'success')
                                
                                # 条件4: 亮度范围检查
                                elif (max_val - min_val) > 5:
                                    is_valid = True
                                    self.log_to_gui(f"  ✅ 通过亮度范围检查", 'success')
                                
                                # 条件5: 8K视频特殊处理 - 即使看起来是灰色也接受
                                elif width >= 7680 and frame_count > skip_frames + 10:
                                    # 对8K视频，只要不是全黑就接受
                                    if avg_brightness > 0.1 or std_dev > 0.05:
                                        is_valid = True
                                        self.log_to_gui(f"  ⚠️ 8K视频强制接受帧 (可能包含内容)", 'warning')
                                
                                # 条件6: 的确是8K视频且尝试了很多帧，强制接受
                                elif width >= 7680 and frame_count > skip_frames + 50:
                                    is_valid = True
                                    self.log_to_gui(f"  🔴 8K视频最后手段：强制接受帧", 'warning')
                                
                                if is_valid:
                                    self.log_to_gui(f"找到有效帧: 第 {frame_count} 帧，格式: {fmt}", 'success')
                                    return frame_array
                                else:
                                    self.log_to_gui(f"  ❌ 帧验证失败", 'warning')
                            
                        except Exception as fmt_error:
                            # 静默跳过格式转换错误，尝试下一种格式
                            continue
                    
                    # 如果所有格式都失败，记录详细信息
                    if frame_count > skip_frames:
                        self.log_to_gui(f"第 {frame_count} 帧: 所有像素格式转换失败", 'error')
                    
                    if frame_count >= max_attempts:
                        self.log_to_gui(f"已达到最大尝试次数 ({max_attempts})，停止捕获", 'warning')
                        break
                        
                if frame_count >= max_attempts:
                    break
            
            # 如果没有找到有效帧，尝试最后的备用方案
            self.log_to_gui(f"在 {frame_count} 帧中未找到理想帧，尝试备用方案...", 'warning')
            
            # 备用方案：重新开始，降低所有标准
            try:
                container.seek(0)  # 重置到开头
                frame_count = 0
                
                for packet in container.demux(video_stream):
                    if self.stop_event.is_set():
                        break
                        
                    for frame in packet.decode():
                        frame_count += 1
                        
                        if frame_count <= skip_frames:
                            continue
                        
                        try:
                            # 只使用RGB24格式，降低所有验证标准
                            frame_array = frame.to_ndarray(format='rgb24')
                            
                            if len(frame_array.shape) == 3 and frame_array.shape[2] == 3:
                                # 非常宽松的验证：只要不是全黑就接受
                                if np.mean(frame_array) > 1.0:  # 平均值大于1就接受
                                    self.log_to_gui(f"备用方案成功: 第 {frame_count} 帧 (宽松标准)", 'success')
                                    return frame_array
                        except:
                            continue
                        
                        if frame_count >= 50:  # 备用方案最多尝试50帧
                            break
                    
                    if frame_count >= 50:
                        break
                        
            except Exception as seek_error:
                self.log_to_gui(f"备用方案失败: {str(seek_error)}", 'error')
            
            self.log_to_gui(f"所有方案都失败，无法获取有效帧", 'error')
            return None
                    
        except Exception as e:
            self.log_to_gui(f"捕获帧时发生严重错误: {str(e)}", 'error')
            import traceback
            self.log_to_gui(f"错误详情: {traceback.format_exc()}", 'error')
        
        return None

    def is_valid_frame(self, frame_array):
        """
        检查一帧图像是否有效，针对8K视频进行优化。
        """
        if frame_array is None or frame_array.size == 0:
            return False
        
        # 获取图像尺寸信息
        height, width = frame_array.shape[:2]
        total_pixels = height * width
        
        # 计算非零像素点的数量
        gray = np.mean(frame_array, axis=2)  # 转换为灰度
        
        # 针对不同分辨率动态调整验证标准
        if width >= 7680:  # 8K及以上分辨率 (7680x4320)
            # 8K视频：更宽松的验证标准
            min_brightness = 5  # 降低亮度阈值
            min_valid_pixels = total_pixels * 0.1  # 至少10%的像素有效
            non_zero_pixels = np.count_nonzero(gray > min_brightness)
            
            # 额外检查：确保不是全灰色
            std_dev = np.std(gray)
            if std_dev < 1.0:  # 标准差太小，可能是全灰色
                self.log_to_gui(f"检测到可能的全灰色帧 (标准差: {std_dev:.2f})", 'warning')
                return False
                
        elif width >= 3840:  # 4K分辨率 (3840x2160)
            min_brightness = 8
            min_valid_pixels = total_pixels * 0.15  # 至少15%的像素有效
            non_zero_pixels = np.count_nonzero(gray > min_brightness)
        else:  # 1080p及以下
            min_brightness = 10
            min_valid_pixels = 1000  # 原有标准
            non_zero_pixels = np.count_nonzero(gray > min_brightness)
        
        is_valid = non_zero_pixels > min_valid_pixels
        
        if not is_valid:
            self.log_to_gui(f"帧验证失败: {width}x{height}, 有效像素: {non_zero_pixels}/{min_valid_pixels}", 'warning')
        
        return is_valid

    def stop_capture(self):
        """对外接口，用于主程序关闭时调用"""
        if self.is_running:
            self.stop_timed_capture()
        
    def on_closing(self):
        """处理窗口关闭事件，确保所有线程安全退出。"""
        if self.is_running:
            if messagebox.askyesno("退出确认", "有正在进行的定时截图任务，确定要强制退出吗？"):
                self.stop_timed_capture()
                if hasattr(self, 'master'):
                    self.master.destroy()
        else:
            if hasattr(self, 'master'):
                self.master.destroy()

# ==============================================================================
# 独立的程序入口，只在直接运行此文件时执行
# ==============================================================================
if __name__ == "__main__":
    # 创建一个临时的主窗口，只用于测试本模块
    root = tk.Tk()
    root.title("RTSP 定时截图工具 (独立模式)")
    root.geometry("800x600")
    
    app = TimedScreenshotFrame(root)
    app.pack(fill=tk.BOTH, expand=True)
    
    # 绑定窗口关闭事件，以便在独立模式下也能正确退出
    def on_closing_standalone():
        app.stop_capture()  # 确保在关闭前停止所有子线程
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing_standalone)
    
    root.mainloop()