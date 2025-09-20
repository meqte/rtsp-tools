# main.py

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
import ctypes # 导入 ctypes 模块
import datetime
import hashlib
import uuid

# 从现有的功能模块中导入主框架类
# 确保 index.py, jietu.py, ping.py 在同一目录下
from ping import PingToolFrame
from index import StressTestFrame
from jietu import TimedScreenshotFrame 

class LicenseChecker:
    """
    许可证检查器，用于验证程序是否在有效期内
    功能包括：
    1. 基于时间的失效检查
    2. 基于使用次数的限制
    3. 机器绑定防止文件复制
    4. 多重验证防止删除文件绕过
    5. 用户友好的提示信息
    """
    
    def __init__(self):
        # 设置程序失效日期（格式：YYYY-MM-DD）
        # 可根据需要修改此日期
        self.expiry_date = datetime.date(2025, 12, 31)  # 2025年12月31日失效
        
        # 设置程序最大使用次数（可选功能）
        self.max_usage_count = 100
        
        # 获取使用次数记录文件路径
        self.usage_file = self._get_usage_file_path()
        # 新增：备份记录文件路径
        self.backup_file = self._get_backup_file_path()
        # 新增：注册表记录（Windows系统）
        self.registry_key = "SOFTWARE\\TempApp\\License"
    
    def _get_usage_file_path(self):
        """
        获取使用次数记录文件的路径
        存储在系统临时目录中，不在exe同目录下生成文件
        """
        import tempfile
        # 使用系统临时目录
        temp_dir = tempfile.gettempdir()
        # 使用机器ID作为文件名的一部分，防止多用户冲突
        machine_id = self._get_machine_id()
        filename = f".app_usage_{machine_id}"
        return os.path.join(temp_dir, filename)
    
    def _get_backup_file_path(self):
        """
        获取备份记录文件的路径
        存储在系统临时目录中，不在exe同目录下生成文件
        """
        import tempfile
        temp_dir = tempfile.gettempdir()
        machine_id = self._get_machine_id()
        filename = f".app_backup_{machine_id}"
        return os.path.join(temp_dir, filename)
    
    def _get_machine_id(self):
        """
        获取机器唯一标识，防止简单的文件复制绕过限制
        使用MAC地址生成唯一标识
        """
        try:
            # 获取机器的MAC地址作为唯一标识
            mac = uuid.getnode()
            # 使用MD5生成8位标识符
            return hashlib.md5(str(mac).encode()).hexdigest()[:8]
        except Exception:
            # 如果获取失败，使用默认值
            return "default"
    
    def _write_to_registry(self, value):
        """
        将许可证信息写入Windows注册表（仅Windows系统）
        存储使用次数、到期日期和最大使用次数
        """
        try:
            if sys.platform == 'win32':
                import winreg
                # 创建或打开注册表项
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.registry_key)
                
                # 写入加密后的使用次数
                encrypted_value = hashlib.md5(f"{value}_{self._get_machine_id()}".encode()).hexdigest()
                winreg.SetValueEx(key, "usage_data", 0, winreg.REG_SZ, encrypted_value)
                
                # 写入到期日期
                expiry_str = self.expiry_date.strftime('%Y-%m-%d')
                winreg.SetValueEx(key, "expiry_date", 0, winreg.REG_SZ, expiry_str)
                
                # 写入最大使用次数
                winreg.SetValueEx(key, "max_usage", 0, winreg.REG_DWORD, self.max_usage_count)
                
                winreg.CloseKey(key)
        except Exception:
            # 如果注册表操作失败，静默处理
            pass
    
    def _read_from_registry(self):
        """
        从Windows注册表读取使用次数
        """
        try:
            if sys.platform == 'win32':
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.registry_key)
                encrypted_value, _ = winreg.QueryValueEx(key, "usage_data")
                winreg.CloseKey(key)
                return encrypted_value
        except Exception:
            pass
        return None
    
    def _read_usage_count(self):
        """
        读取当前使用次数（多重验证）
        文件格式：machine_id|usage_count|checksum
        """
        machine_id = self._get_machine_id()
        usage_counts = []
        
        # 1. 从主文件读取
        try:
            if os.path.exists(self.usage_file):
                with open(self.usage_file, 'r', encoding='utf-8') as f:
                    data = f.read().strip().split('|')
                    if len(data) == 3:
                        file_machine_id, count, checksum = data
                        # 验证机器ID和校验和
                        expected_checksum = hashlib.md5(f"{file_machine_id}_{count}_{machine_id}".encode()).hexdigest()[:8]
                        if file_machine_id == machine_id and checksum == expected_checksum:
                            usage_counts.append(int(count))
        except Exception:
            pass
        
        # 2. 从备份文件读取
        try:
            if os.path.exists(self.backup_file):
                with open(self.backup_file, 'r', encoding='utf-8') as f:
                    data = f.read().strip().split('|')
                    if len(data) == 3:
                        file_machine_id, count, checksum = data
                        expected_checksum = hashlib.md5(f"{file_machine_id}_{count}_{machine_id}".encode()).hexdigest()[:8]
                        if file_machine_id == machine_id and checksum == expected_checksum:
                            usage_counts.append(int(count))
        except Exception:
            pass
        
        # 3. 从注册表读取（仅Windows）
        registry_data = self._read_from_registry()
        if registry_data:
            # 尝试反向验证注册表数据
            for potential_count in range(0, self.max_usage_count + 10):
                expected_encrypted = hashlib.md5(f"{potential_count}_{machine_id}".encode()).hexdigest()
                if expected_encrypted == registry_data:
                    usage_counts.append(potential_count)
                    break
        
        # 4. 多重验证：如果有多个数据源，取最大值（防止通过删除文件降低使用次数）
        if usage_counts:
            return max(usage_counts)
        
        # 5. 如果所有文件都不存在，说明可能被删除，采用安全策略
        return self._handle_missing_files()
    
    def _handle_missing_files(self):
        """
        处理文件缺失的情况（可能被用户删除）
        采用安全策略：如果检测到文件被删除，使用保守的使用次数
        """
        # 检查程序是否是第一次运行（判断是否曾经创建过记录文件）
        machine_id = self._get_machine_id()
        
        # 在系统临时目录创建首次运行标记文件
        import tempfile
        temp_dir = tempfile.gettempdir()
        first_run_marker = os.path.join(temp_dir, f'.app_first_run_{machine_id[:4]}')
        
        if not os.path.exists(first_run_marker):
            # 第一次运行，创建标记文件
            try:
                with open(first_run_marker, 'w', encoding='utf-8') as f:
                    f.write(f"{datetime.date.today().isoformat()}")
            except Exception:
                pass
            return 0  # 第一次运行，使用次数为0
        else:
            # 不是第一次运行，但记录文件缺失，可能被删除
            # 采用保守策略：假设已经使用了较多次数
            return max(50, self.max_usage_count - 20)  # 返回一个较高的使用次数
    
    def _write_usage_count(self, count):
        """
        写入使用次数到多个位置（多重备份）
        """
        machine_id = self._get_machine_id()
        
        # 生成校验和
        checksum = hashlib.md5(f"{machine_id}_{count}_{machine_id}".encode()).hexdigest()[:8]
        data = f"{machine_id}|{count}|{checksum}"
        
        # 1. 写入主文件
        try:
            with open(self.usage_file, 'w', encoding='utf-8') as f:
                f.write(data)
        except Exception:
            pass
        
        # 2. 写入备份文件
        try:
            with open(self.backup_file, 'w', encoding='utf-8') as f:
                f.write(data)
        except Exception:
            pass
        
        # 3. 写入注册表（仅Windows）
        self._write_to_registry(count)
    
    def check_license(self):
        """
        检查许可证是否有效
        返回：(是否有效, 提示信息)
        """
        current_date = datetime.date.today()
        
        # 1. 检查时间是否过期
        if current_date > self.expiry_date:
            return False, f"程序已于 {self.expiry_date.strftime('%Y年%m月%d日')} 过期\n请联系管理员获取新版本"
        
        # 2. 检查使用次数是否超限
        usage_count = self._read_usage_count()
        if usage_count >= self.max_usage_count:
            return False, f"程序已失效\n请联系管理员获取授权"
        
        # 3. 记录本次使用（使用次数+1）
        self._write_usage_count(usage_count + 1)
        
        # 4. 计算剩余天数和次数（仅用于控制台输出，不显示给用户）
        remaining_days = (self.expiry_date - current_date).days
        remaining_uses = self.max_usage_count - usage_count - 1
        
        # 5. 返回成功状态（不显示任何提示给用户）
        return True, f"程序授权正常\n有效期至：{self.expiry_date.strftime('%Y年%m月%d日')}\n剩余使用次数：{remaining_uses} 次"

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # ============================================
        # 许可证检查 - 程序启动时验证
        # ============================================
        license_checker = LicenseChecker()
        is_valid, message = license_checker.check_license()
        
        if not is_valid:
            # 如果许可证无效，显示错误信息并退出程序
            self.withdraw()  # 隐藏主窗口
            messagebox.showerror("程序已失效", message)
            self.destroy()
            sys.exit(1)
        else:
            # 如果许可证有效，在控制台输出状态（不打扰用户）
            print(f"许可证检查通过: {message}")
        
        # ============================================
        # 初始化主窗口
        # ============================================
        self.title("Jack-工具-202509")
        self.geometry("1000x600")

        # ----------------------------------------------------
        # 新增：设置窗口图标和任务栏图标
        # ----------------------------------------------------
        try:
            # 判断程序是否在打包后的环境中运行
            if getattr(sys, 'frozen', False):
                # 打包环境: 获取 PyInstaller 的临时目录
                base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
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
        self.notebook.add(self.index_tab, text="视频压测")
        self.index_app = StressTestFrame(self.index_tab)
        self.index_app.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 2. 添加 RTSP 截图工具标签页
        # ----------------------------------------------------
        self.jietu_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.jietu_tab, text="批量截图")
        self.jietu_app = TimedScreenshotFrame(self.jietu_tab)
        self.jietu_app.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------
        # 3. 添加 Ping 工具标签页
        # ----------------------------------------------------
        self.ping_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.ping_tab, text="丢包检测")
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