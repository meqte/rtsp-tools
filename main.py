# main.py

import tkinter as tk
from tkinter import ttk
import sys
import os
import ctypes # 导入 ctypes 模块

# 从现有的功能模块中导入主框架类
# 确保 index.py, jietu.py, ping.py 在同一目录下
from ping import PingToolFrame
from index import StressTestFrame
from jietu import BatchScreenshotFrame 

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Jack-工具-202509")
        self.geometry("1000x600")

        # ----------------------------------------------------
        # 新增：设置窗口图标和任务栏图标
        # ----------------------------------------------------
        try:
            # 判断程序是否在打包后的环境中运行
            if getattr(sys, 'frozen', False):
                # 打包环境: 获取 PyInstaller 的临时目录
                base_path = sys._MEIPASS
            else:
                # 开发环境: 使用当前工作目录
                base_path = os.path.abspath(".")
            
            # 构建图标文件的正确路径
            icon_path = os.path.join(base_path, 'tmp', 'ico.ico')
            
            # 使用 iconbitmap 设置窗口图标
            self.iconbitmap(icon_path)
            
            # 对于 Windows，设置任务栏图标（可选，但推荐）
            # 这通常能解决任务栏图标显示不正确的问题
            myappid = 'mycompany.myproduct.subproduct.version' # 替换为你的唯一ID
            try:
                if sys.platform == 'win32':
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except AttributeError:
                pass

        except tk.TclError:
            # 如果图标文件加载失败，打印错误信息
            print("无法加载图标文件，请确保 'ico.ico' 存在于 'tmp' 文件夹且路径正确。")
            pass
        except Exception as e:
            print(f"设置图标时发生未知错误: {e}")
            pass

        # ----------------------------------------------------
        # 创建一个 Notebook 组件作为主界面
        # ----------------------------------------------------
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 1. 添加 RTSP 压测工具标签页
        # ----------------------------------------------------
        self.index_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.index_tab, text="视频流压测")
        self.index_app = StressTestFrame(self.index_tab)
        self.index_app.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 2. 添加 RTSP 截图工具标签页
        # ----------------------------------------------------
        self.jietu_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.jietu_tab, text="批量截图")
        self.jietu_app = BatchScreenshotFrame(self.jietu_tab)
        self.jietu_app.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 3. 添加 Ping 工具标签页
        # ----------------------------------------------------
        self.ping_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.ping_tab, text="Ping丢包检测")
        self.ping_app = PingToolFrame(self.ping_tab)
        self.ping_app.pack(fill=tk.BOTH, expand=True)

        # 绑定窗口关闭事件，确保所有子线程安全退出
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """
        窗口关闭时的处理函数，确保所有子线程安全退出
        """
        try:
            # 1. 停止 RTSP 压测模块的所有线程
            if hasattr(self, 'index_app'):
                self.index_app.on_closing()
                
            # 2. 停止批量截图模块的所有线程  
            if hasattr(self, 'jietu_app'):
                self.jietu_app.stop_capture()
                
            # 3. 停止 Ping 模块的所有线程
            if hasattr(self, 'ping_app'):
                self.ping_app.stop_ping()
                
        except Exception as e:
            print(f"关闭应用时发生错误: {e}")
        finally:
            # 强制退出程序，确保所有线程都被终止
            self.destroy()
            sys.exit(0)

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()