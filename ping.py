# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, Toplevel
import threading
import subprocess
import re
import os
import sys
import time

class PingToolFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.ping_threads = []
        self.stop_events = {}
        self.process_map = {}
        self.log_texts = {}
        
        self.create_widgets()

    def create_widgets(self):
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(fill=tk.X)

        input_frame = ttk.Frame(control_frame)
        input_frame.pack(pady=(0, 10), fill=tk.X, expand=True)
        
        input_frame.columnconfigure(0, weight=1)
        input_frame.columnconfigure(1, weight=1)
        input_frame.columnconfigure(2, weight=1)
        input_frame.columnconfigure(3, weight=1)
        input_frame.columnconfigure(4, weight=1)
        input_frame.columnconfigure(5, weight=1)

        self.ip_entries = []
        
        default_ips = ["192.168.16.3", "192.168.16.1", "baidu.com", "sohu.com"]
        
        for i in range(12):
            row = i % 4
            col = (i // 4) * 2
            
            ttk.Label(input_frame, text=f"IP-{i+1}:").grid(row=row, column=col, padx=(5, 0), pady=2, sticky='w')
            
            ip_entry = ttk.Entry(input_frame, width=20)
            ip_entry.grid(row=row, column=col+1, padx=5, pady=2, sticky='ew')
            self.ip_entries.append(ip_entry)

        for i, ip in enumerate(default_ips):
            if i < len(self.ip_entries):
                self.ip_entries[i].insert(0, ip)

        count_frame = ttk.Frame(control_frame)
        count_frame.pack(pady=5)
        
        ttk.Label(count_frame, text="Ping 次数:").pack(side=tk.LEFT, padx=5)
        counts = ["10", "50", "持续"]
        self.count_combobox = ttk.Combobox(count_frame, values=counts, width=8, state="readonly")
        self.count_combobox.set(counts[0])
        self.count_combobox.pack(side=tk.LEFT, padx=5)

        button_frame = ttk.Frame(control_frame)
        button_frame.pack(pady=(10, 0))

        self.start_button = ttk.Button(button_frame, text="开始 Ping", command=self.start_ping)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="停止 Ping", command=self.stop_ping, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(button_frame, text="清空地址", command=self.clear_entries)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        self.log_notebook = ttk.Notebook(self)
        self.log_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def clear_entries(self):
        for entry in self.ip_entries:
            entry.delete(0, tk.END)

    def start_ping(self):
        self.stop_ping()
        
        targets = []
        global_count = self.count_combobox.get()
        
        for i in range(12):
            ip = self.ip_entries[i].get().strip()
            if ip:
                targets.append({'ip': ip, 'count': global_count, 'index': i + 1})

        if not targets:
            messagebox.showwarning("警告", "请至少输入一个目标地址！")
            return
            
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        for tab in self.log_notebook.winfo_children():
            tab.destroy()
        self.log_texts.clear()
        
        for target in targets:
            ip = target['ip']
            
            log_frame = ttk.Frame(self.log_notebook, padding=5)
            self.log_notebook.add(log_frame, text=f"  {ip}  ") 
            
            if sys.platform == 'win32':
                font_name = 'Microsoft YaHei'
            else:
                font_name = 'Monospace'

            log_text = scrolledtext.ScrolledText(log_frame, state='disabled', wrap=tk.WORD, font=(font_name, 10), bg='black')
            log_text.pack(fill=tk.BOTH, expand=True)
            self.log_texts[ip] = log_text
            
            log_text.tag_config('ping_log', foreground='white')
            
            self.log_to_gui(ip, f"--- 开始 Ping {ip}，次数：{target['count']} ---")
            
            stop_event = threading.Event()
            self.stop_events[ip] = stop_event
            
            ping_thread = threading.Thread(target=self.ping_worker, args=(ip, target['count'], stop_event))
            self.ping_threads.append(ping_thread)
            ping_thread.daemon = True
            ping_thread.start()
        
        monitor_thread = threading.Thread(target=self.monitor_completion)
        monitor_thread.daemon = True
        monitor_thread.start()
            
    def stop_ping(self):
        for ip in self.stop_events:
            self.stop_events[ip].set()

        for ip, process in self.process_map.items():
            if process.poll() is None:
                try:
                    if sys.platform == 'win32':
                        subprocess.Popen(['taskkill', '/F', '/T', '/PID', str(process.pid)], creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        os.kill(process.pid, 9)
                except Exception as e:
                    print(f"Error terminating process {ip}: {e}")
        self.process_map.clear()

        for thread in self.ping_threads:
            if thread.is_alive():
                thread.join()
        
        self.ping_threads = []
        self.stop_events = {}
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.log_to_gui(None, "所有 Ping 任务已停止。")
        
    def log_to_gui(self, ip, message, tag=None):
        if ip is None:
            for text_widget in self.log_texts.values():
                text_widget.configure(state='normal')
                text_widget.insert(tk.END, message + "\n", tag or 'ping_log')
                text_widget.configure(state='disabled')
                text_widget.see(tk.END)
        else:
            text_widget = self.log_texts.get(ip)
            if text_widget:
                text_widget.configure(state='normal')
                text_widget.insert(tk.END, message + "\n", tag or 'ping_log')
                text_widget.configure(state='disabled')
                text_widget.see(tk.END)

    def ping_worker(self, target, count_str, stop_event):
        log_dir = "ping_log"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_filename = os.path.join(log_dir, f"{target}_ping_log.txt")
        
        # 匹配失败信息的关键词，确保跨平台兼容
        failure_keywords = ["请求超时", "无法访问", "失败", "请求找不到", "找不到主机", "连接失败", "目标主机不可达",
                             "Request timed out", "Destination host unreachable", "General failure"]

        try:
            if sys.platform == 'win32':
                if count_str == "持续":
                    command = ['ping', '-t', target]
                else:
                    command = ['ping', '-n', count_str, target]
            else:
                if count_str == "持续":
                    command = ['ping', target]
                else:
                    command = ['ping', '-c', count_str, target]
            
            encoding = 'gbk' if sys.platform == 'win32' else 'utf-8'
            
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding=encoding, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            self.process_map[target] = process
            
            with open(log_filename, "a", encoding='utf-8') as f:
                # 记录带时间戳的ping开始信息
                start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                f.write(f"[{start_time_str}] 开始 Ping {target}, 次数: {count_str}\n")
                f.flush()

                while not stop_event.is_set():
                    line = process.stdout.readline()
                    if not line:
                        break
                    
                    self.after(0, self.log_to_gui, target, line.strip())
                    
                    # 只将失败信息写入文件，并添加时间戳
                    if any(keyword in line for keyword in failure_keywords):
                        current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        f.write(f"[{current_time_str}] {line}")
                        f.flush()

            if process.poll() is None and not stop_event.is_set():
                self.after(0, self.log_to_gui, target, "--- Ping 任务完成 ---")
                # 任务完成后也记录带时间戳到文件
                end_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                with open(log_filename, "a", encoding='utf-8') as f:
                    f.write(f"[{end_time_str}] Ping 任务完成。\n\n")

        except FileNotFoundError:
            message = "错误：ping 命令未找到！"
            self.after(0, self.log_to_gui, target, message)
            # 记录带时间戳的错误信息
            current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            with open(log_filename, "a", encoding='utf-8') as f:
                f.write(f"[{current_time_str}] {message}\n")
        except Exception as e:
            message = f"发生错误：{e}"
            self.after(0, self.log_to_gui, target, message)
            # 记录带时间戳的错误信息
            current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            with open(log_filename, "a", encoding='utf-8') as f:
                f.write(f"[{current_time_str}] {message}\n")
        finally:
            if target in self.process_map:
                del self.process_map[target]
                
    def monitor_completion(self):
        while any(thread.is_alive() for thread in self.ping_threads):
            time.sleep(1)
        
        self.after(0, self.on_all_pings_complete)

    def on_all_pings_complete(self):
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

# 独立运行的代码块，方便测试
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Ping 工具 (独立模式)")
    root.geometry("800x600")
    
    app = PingToolFrame(root)
    app.pack(fill=tk.BOTH, expand=True)

    def on_closing():
        app.stop_ping()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()