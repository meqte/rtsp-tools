# -*- coding: utf-8 -*-
"""
批量 RTSP 摄像头截图工具 v11

核心功能：
- 提供一个 GUI 界面，用于输入多个 RTSP 地址。
- 使用多线程并发连接到每个 RTSP 流，并优化截图逻辑。
- **v11: 使用 PyAV 替代 OpenCV，提高 RTSP 流兼容性和打包稳定性。**
- **v11: 引入了连接重试和多帧捕获机制，以提高截图成功率和质量。**
- **v11: 捕获多帧并选择最"完整"的一帧进行保存，以解决花屏问题。**
- 将截图文件保存到指定的 IMG 文件夹中。
- 提供实时日志输出，显示每个地址的截图状态。

技术栈：
- GUI 库: tkinter，与之前的工具保持一致。
- 视频处理: PyAV (av)，用于连接 RTSP 流和保存图片。
- 并发处理: threading，用于高效地处理多个任务。

使用方法：
1.  确保已安装 PyAV: `pip install av Pillow`
2.  在"RTSP 地址"文本框中粘贴 RTSP 地址，每行一个。
3.  调整"截图质量"参数（0-100，默认100）。
4.  点击"开始截图"按钮。
5.  截图文件将保存在程序根目录下的 `IMG` 文件夹中。
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

class BatchScreenshotFrame(ttk.Frame):
    """
    主应用程序类，负责创建和管理 GUI 界面。
    现已修改为可嵌入其他框架的子组件，同时保留独立运行能力。
    """
    def __init__(self, parent):
        super().__init__(parent)
        
        self.threads = []
        # 创建一个事件对象，用于在点击“停止”时通知所有线程退出
        self.stop_event = threading.Event()
        self.log_lock = threading.Lock()
        
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
        self.url_text.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
        # 添加默认的示例地址
        self.url_text.insert(tk.END, "rtsp://192.168.16.3/live/1/1")
        
        # 按钮和质量控制区域
        control_frame = ttk.Frame(top_frame)
        control_frame.grid(row=2, column=0, columnspan=2, sticky='w', pady=(5, 0))

        # 截图质量输入
        quality_label = ttk.Label(control_frame, text="截图质量 (0-100):")
        quality_label.pack(side=tk.LEFT, padx=5)
        self.quality_entry = ttk.Entry(control_frame, width=5)
        self.quality_entry.insert(0, "100") # 默认质量100
        self.quality_entry.pack(side=tk.LEFT, padx=5)
        
        # 连接重试次数输入
        retries_label = ttk.Label(control_frame, text="重试次数:")
        retries_label.pack(side=tk.LEFT, padx=(10, 5))
        self.retries_entry = ttk.Entry(control_frame, width=5)
        self.retries_entry.insert(0, "3") # 默认重试3次
        self.retries_entry.pack(side=tk.LEFT, padx=5)

        # 按钮
        self.start_button = ttk.Button(control_frame, text="开始截图", command=self.start_capture)
        self.start_button.pack(side=tk.LEFT, padx=(20, 5))
        
        self.stop_button = ttk.Button(control_frame, text="停止", command=self.stop_capture, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = ttk.Button(control_frame, text="清空地址", command=self.clear_urls)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
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
        
        self.log_text.tag_config('info', foreground='blue')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')

        # 添加右键菜单
        self.add_context_menu()

    def add_context_menu(self):
        """为文本框和日志框添加右键菜单。"""
        # 创建右键菜单
        self.text_menu = tk.Menu(self, tearoff=0)
        self.text_menu.add_command(label="剪切", command=lambda: self.focus_get().event_generate("<<Cut>>"))
        self.text_menu.add_command(label="复制", command=lambda: self.focus_get().event_generate("<<Copy>>"))
        self.text_menu.add_command(label="粘贴", command=lambda: self.focus_get().event_generate("<<Paste>>"))
        self.text_menu.add_separator()
        self.text_menu.add_command(label="全选", command=self.select_all_input)

        self.log_menu = tk.Menu(self, tearoff=0)
        self.log_menu.add_command(label="复制", command=lambda: self.focus_get().event_generate("<<Copy>>"))
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

    def log_to_gui(self, message, tag='info'):
        """
        线程安全的日志输出函数。
        """
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
            
        try:
            quality = int(self.quality_entry.get())
            if not 0 <= quality <= 100:
                raise ValueError
            retries = int(self.retries_entry.get())
            if retries < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "截图质量请输入0到100之间的整数，重试次数请输入非负整数。")
            return

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        
        self.log_to_gui("--- 批量截图任务开始 ---", 'info')
        
        # 确保截图文件夹存在
        screenshot_dir = "IMG"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
            self.log_to_gui(f"已创建截图文件夹: {screenshot_dir}", 'info')
        
        # 重置停止事件，准备开始新任务
        self.stop_event.clear()
        self.threads = []
        
        # 创建一个线程屏障，参与者数量为URL地址的数量
        self.barrier = threading.Barrier(len(urls))

        for i, url in enumerate(urls):
            # 将索引加1，以便从 1.jpg 开始命名
            thread_index = i + 1
            thread = threading.Thread(target=self.capture_worker, args=(url, thread_index, quality, retries))
            self.threads.append(thread)
            thread.start()
        
        # 启动一个新线程来等待所有工作线程完成
        monitor_thread = threading.Thread(target=self.wait_for_threads)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def stop_capture(self):
        """
        设置停止事件，通知所有工作线程停止任务。
        """
        self.log_to_gui("--- 正在终止任务...请稍候 ---", 'info')
        self.stop_event.set()
        self.stop_button.config(state=tk.DISABLED)

    def is_valid_frame(self, frame_array):
        """
        简单地检查一帧图像是否有效，可以根据您的需求扩展。
        这里我们检查图像是否全黑或接近全黑（一个简单的判断，可过滤掉部分花屏）。
        更高级的验证可能涉及分析图像的色彩、边缘信息等。
        """
        # 计算非零像素点的数量
        # frame_array 是 RGB 格式的 numpy 数组
        gray = np.mean(frame_array, axis=2)  # 转换为灰度
        non_zero_pixels = np.count_nonzero(gray > 10)  # 阈值为10，过滤极暗像素
        # 如果非零像素点数量过少，我们认为图像无效（例如全黑或大部分是花屏）
        return non_zero_pixels > 1000

    def capture_worker(self, url, index, quality, retries):
        """
        由子线程执行的截图任务，包含重试和多帧捕获逻辑。
        使用 PyAV 替代 OpenCV。
        """
        
        # 线程开始执行，但首先在屏障处等待
        self.barrier.wait() # 核心：在这里等待所有线程就绪
        
        if self.stop_event.is_set():
            self.log_to_gui(f"[{index}] 任务已终止，跳过。", 'info')
            return

        self.log_to_gui(f"[{index}] 正在连接: {url}", 'info')
        
        # 增加重试循环
        for attempt in range(retries + 1):
            if self.stop_event.is_set():
                break
                
            try:
                # 使用 PyAV 打开流
                container = av.open(url, options={
                    'rtsp_transport': 'tcp',  # 使用 TCP 传输，更稳定
                    'stimeout': '5000000',    # 5秒超时 (微秒)
                    'max_delay': '500000',    # 最大延迟 500ms
                })
                
                video_stream = container.streams.video[0]
                self.log_to_gui(f"[{index}] 连接成功！正在捕获帧...", 'info')
                break
                
            except Exception as e:
                self.log_to_gui(f"[{index}] 连接失败 (第 {attempt+1}/{retries+1} 次尝试): {str(e)}", 'error')
                if attempt < retries:
                    time.sleep(1) # 重试前等待1秒
                continue
        else:
            # 如果重试所有次数都失败，则记录错误并返回
            self.log_to_gui(f"[{index}] 无法连接到流，已达到最大重试次数。", 'error')
            return
            
        if self.stop_event.is_set():
            try:
                container.close()
            except:
                pass
            return

        # 捕获多帧并选择最佳帧
        best_frame = None
        frame_count = 0
        
        try:
            for packet in container.demux(video_stream):
                if self.stop_event.is_set():
                    break
                    
                for frame in packet.decode():
                    frame_count += 1
                    
                    # 将 PyAV 帧转换为 numpy 数组
                    frame_array = frame.to_ndarray(format='rgb24')
                    
                    if self.is_valid_frame(frame_array):
                        best_frame = frame_array
                        break # 找到有效帧，提前退出
                        
                    if frame_count >= 10:  # 最多尝试10帧
                        break
                        
                if best_frame is not None or frame_count >= 10:
                    break
                    
        except Exception as e:
            self.log_to_gui(f"[{index}] 读取帧时出错: {str(e)}", 'error')
        finally:
            try:
                container.close()
            except:
                pass
        
        if best_frame is not None:
            try:
                # 将 numpy 数组转换为 PIL 图像并保存
                image = Image.fromarray(best_frame)
                filename = f"IMG/{index}.jpg"
                
                # 根据质量设置保存参数
                if quality < 100:
                    image.save(filename, 'JPEG', quality=quality, optimize=True)
                else:
                    image.save(filename, 'JPEG', quality=quality)
                    
                self.log_to_gui(f"[{index}] 截图成功，已保存为: {filename} (质量: {quality})", 'success')
            except Exception as e:
                self.log_to_gui(f"[{index}] 保存图片时出错: {str(e)}", 'error')
        else:
            self.log_to_gui(f"[{index}] 无法捕获有效帧，可能视频流质量极差或已停止。", 'error')

    def wait_for_threads(self):
        """
        等待所有线程完成，并更新最终状态。
        """
        for thread in self.threads:
            # 使用 join() 等待线程结束，确保所有子线程都完成
            thread.join()
        
        # 所有线程都结束后，再由主线程调用完成函数
        self.after(100, self.on_capture_complete)

    def on_capture_complete(self):
        """
        所有线程结束后，由主线程调用以恢复 GUI 状态。
        """
        self.log_to_gui("--- 保存截图任务完成 ---", 'info')
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.threads = []
        
    def on_closing(self):
        """处理窗口关闭事件，确保所有线程安全退出。"""
        if self.threads and any(t.is_alive() for t in self.threads):
            if messagebox.askyesno("退出确认", "有正在进行的任务，确定要强制退出吗？"):
                self.stop_event.set()
                self.master.destroy()
        else:
            self.master.destroy()

# ==============================================================================
# 独立的程序入口，只在直接运行此文件时执行
# ==============================================================================
if __name__ == "__main__":
    # 创建一个临时的主窗口，只用于测试本模块
    root = tk.Tk()
    root.title("RTSP 截图工具 (独立模式)")
    root.geometry("800x600")
    
    app = BatchScreenshotFrame(root)
    app.pack(fill=tk.BOTH, expand=True)
    
    # 绑定窗口关闭事件，以便在独立模式下也能正确退出
    def on_closing_standalone():
        app.stop_capture() # 确保在关闭前停止所有子线程
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing_standalone)
    
    root.mainloop()