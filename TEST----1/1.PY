# -*- coding: utf-8 -*-
"""
批量 RTSP 摄像头截图工具

核心功能：
- 提供一个 GUI 界面，用于输入多个 RTSP 地址。
- 使用多线程并发连接到每个 RTSP 流，捕获第一帧。
- 按照顺序将截图文件保存到指定的 IMG 文件夹中。
- 提供实时日志输出，显示每个地址的截图状态。

技术栈：
- GUI 库: tkinter，与之前的工具保持一致。
- 视频处理: OpenCV (cv2)，用于连接 RTSP 流和保存图片。
- 并发处理: threading，用于高效地处理多个任务。

使用方法：
1.  确保已安装 OpenCV: `pip install opencv-python`
2.  将 RTSP 地址粘贴到左侧的文本框中，每行一个。
3.  点击“开始截图”按钮。
4.  截图文件将保存在程序根目录下的 `IMG` 文件夹中。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import cv2
import sys
import time

class BatchScreenshotApp(tk.Tk):
    """
    主应用程序类，负责创建和管理 GUI 界面。
    """
    def __init__(self):
        super().__init__()
        self.title("批量 RTSP 截图工具")
        self.geometry("800x600")
        
        # 存储所有线程的列表
        self.threads = []
        # 创建一个线程锁，用于在主线程和子线程之间同步 GUI 更新
        self.log_lock = threading.Lock()
        
        self.create_widgets()

    def create_widgets(self):
        """创建界面上的所有控件。"""
        # 主框架
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧输入区
        input_frame = ttk.LabelFrame(main_frame, text="RTSP 地址列表 (每行一个)", padding="10")
        input_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.url_text = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, width=40, font=('Courier', 10))
        self.url_text.pack(fill=tk.BOTH, expand=True)
        # 添加一些默认的示例地址
        self.url_text.insert(tk.END, "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4\n")
        self.url_text.insert(tk.END, "rtsp://184.72.239.149/vod/mp4:BigBuckBunny_115k.mov\n")
        self.url_text.insert(tk.END, "rtsp://invalid.rtsp.url/live/stream")
        
        # 右侧控制和日志区
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 按钮控制区
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.start_button = ttk.Button(button_frame, text="开始截图", command=self.start_capture)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(button_frame, text="清空地址", command=self.clear_urls)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        # 日志区
        log_label = ttk.Label(right_frame, text="日志输出:")
        log_label.pack(pady=(0, 5), anchor='w')
        
        self.log_text = scrolledtext.ScrolledText(right_frame, state='disabled', wrap=tk.WORD, font=('Courier', 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 为不同类型的日志信息配置标签
        self.log_text.tag_config('info', foreground='blue')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')

    def log_to_gui(self, message, tag='info'):
        """
        线程安全的日志输出函数，使用 self.after 将更新调度到主线程。
        """
        # 使用锁确保一次只有一个线程更新日志
        with self.log_lock:
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, message + "\n", tag)
            self.log_text.configure(state='disabled')
            self.log_text.see(tk.END)
    
    def clear_urls(self):
        """清空输入框中的所有 RTSP 地址。"""
        self.url_text.delete('1.0', tk.END)

    def start_capture(self):
        """
        主控函数，解析地址并启动多个线程进行截图。
        """
        urls = self.url_text.get('1.0', tk.END).strip().split('\n')
        urls = [url.strip() for url in urls if url.strip()]

        if not urls:
            messagebox.showwarning("警告", "请先输入至少一个 RTSP 地址！")
            return
            
        self.start_button.config(state=tk.DISABLED)
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        
        self.log_to_gui("--- 批量截图任务开始 ---", 'info')
        
        # 确保截图文件夹存在
        screenshot_dir = "IMG"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
            self.log_to_gui(f"已创建截图文件夹: {screenshot_dir}", 'info')
        
        # 启动线程
        self.threads = []
        for i, url in enumerate(urls):
            # 将索引加1，以便从 1.jpg 开始命名
            thread_index = i + 1
            thread = threading.Thread(target=self.capture_worker, args=(url, thread_index))
            self.threads.append(thread)
            thread.start()
        
        # 启动一个新线程来等待所有工作线程完成
        monitor_thread = threading.Thread(target=self.wait_for_threads)
        monitor_thread.daemon = True # 设置为守护线程，以便主程序退出时自动终止
        monitor_thread.start()

    def capture_worker(self, url, index):
        """
        由子线程执行的截图任务。
        """
        filename = f"IMG/{index}.jpg"
        
        self.log_to_gui(f"[{index}] 正在连接: {url}", 'info')
        
        try:
            # 尝试连接 RTSP 流
            # cv2.CAP_FFMPEG 用于在 Windows 上提高兼容性
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            
            # 设置超时时间（例如 5 秒），避免长时间阻塞
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            
            if not cap.isOpened():
                self.log_to_gui(f"[{index}] 连接失败或超时: {url}", 'error')
                return
            
            # 尝试读取一帧
            ret, frame = cap.read()
            
            if ret:
                # 成功读取，保存文件
                cv2.imwrite(filename, frame)
                self.log_to_gui(f"[{index}] 截图成功，已保存为: {filename}", 'success')
            else:
                self.log_to_gui(f"[{index}] 无法读取视频帧: {url}", 'error')
                
        except Exception as e:
            self.log_to_gui(f"[{index}] 发生异常: {e}", 'error')
            
        finally:
            # 确保无论成功失败，都释放资源
            if 'cap' in locals() and cap.isOpened():
                cap.release()

    def wait_for_threads(self):
        """
        等待所有线程完成，并更新最终状态。
        """
        for thread in self.threads:
            if thread.is_alive():
                thread.join()
        
        # 所有线程完成后，更新 GUI 状态
        self.after(100, self.on_capture_complete)

    def on_capture_complete(self):
        """
        所有线程结束后，由主线程调用以恢复 GUI 状态。
        """
        self.log_to_gui("--- 批量截图任务完成 ---", 'info')
        self.start_button.config(state=tk.NORMAL)
        self.threads = []


if __name__ == "__main__":
    app = BatchScreenshotApp()
    app.mainloop()
