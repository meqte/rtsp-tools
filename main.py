# main.py

import tkinter as tk
from tkinter import ttk

# 从现有的功能模块中导入主框架类
# 确保 index.py, jietu.py, ping.py 在同一目录下
from ping import PingToolFrame
from index import StressTestFrame
from jietu import BatchScreenshotFrame 

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JACK-2025-工具箱")
        self.geometry("800x600")

        # 创建一个 Notebook 组件作为主界面
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 按用户要求调整标签页顺序
        # 1. 添加 RTSP 压测工具标签页 (默认界面)
        # ----------------------------------------------------
        self.index_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.index_tab, text="视频流压测")
        index_app = StressTestFrame(self.index_tab)
        index_app.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 2. 添加 RTSP 截图工具标签页
        # ----------------------------------------------------
        self.jietu_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.jietu_tab, text="批量截图")
        jietu_app = BatchScreenshotFrame(self.jietu_tab)
        jietu_app.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 3. 添加 Ping 工具标签页
        # ----------------------------------------------------
        self.ping_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.ping_tab, text="Ping丢包检测")
        ping_app = PingToolFrame(self.ping_tab)
        ping_app.pack(fill=tk.BOTH, expand=True)

        # 绑定窗口关闭事件，确保所有子线程安全退出
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        # 这是一个退出前的处理示例
        # 可以在这里调用子模块的停止函数，确保子线程安全退出
        self.destroy()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()