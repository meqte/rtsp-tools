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
import datetime
import subprocess
import platform

# ==============================================================================
# 全局配置管理
# ==============================================================================
class SettingsManager:
    """管理所有可配置参数的类"""
    def __init__(self):
        # 保存原始默认值，用于重置
        self.defaults = {}
        
        # GUI和系统参数
        self.gui_refresh_interval = 200      # GUI刷新频率，毫秒
        self.reconnect_wait_time = 5         # 重连等待时间，秒
        self.fps_smooth_window = 10          # 父项汇总 FPS 平滑窗口大小
        self.threads_per_url = 1             # 每个URL的监控线程数
        self.sys_monitor_enabled = True      # 是否启用系统监控线程
        
        # 数据质量参数
        self.enable_real_packet_loss = True  # 启用真实丢包检测
        self.enable_frame_analysis = True    # 启用帧类型分析
        self.quality_level = "高级"           # 数据质量等级: 基础/标准/高级
        
        # 核心RTSP参数
        self.rtsp_timeout = 5000000          # PyAV拉流超时，微秒
        self.rtsp_buffer_size = 2097152      # RTSP缓冲区大小，字节
        self.rtsp_user_agent = "LibVLC/3.0.0" # RTSP用户代理
        self.rtsp_max_delay = 500000         # 最大延迟，微秒
        self.rtsp_probe_size = 2097152       # 探测大小，字节
        self.rtsp_analyzeduration = 2000000 # 分析时长，微秒
        self.strict_protocol = True         # 默认严格使用用户选择的协议
        
        # 质量监控参数
        self.rtp_timeout_threshold = 5000    # RTP超时阈值，毫秒
        self.packet_loss_threshold = 5.0     # 丢帧率阈值，百分比
        
        # PTS丢帧检测参数
        self.pts_tolerance_ms = 100          # PTS时间戳容错范围，毫秒
        self.frame_interval_tolerance = 0.15 # 帧间隔容错比例
        self.missing_frame_threshold = 3     # 连续丢帧判断阈值
        self.pts_reset_threshold = 5000      # PTS重置检测阈值，毫秒
        self.enable_pts_smoothing = True     # 启用PTS平滑算法
        self.pts_history_size = 50           # PTS历史缓存大小
        
        # 丢帧统计参数
        self.frame_loss_window_size = 1000   # 丢帧统计窗口大小
        self.frame_loss_report_interval = 10 # 丢帧报告间隔，秒
        self.enable_iframe_priority = True   # I帧丢失优先级检测
        
        # 真实帧率检测参数
        self.fps_detection_method = "自动"    # 帧率检测方法: 自动/手动/混合
        self.fps_calculation_window = 100    # 动态计算窗口大小
        self.fps_update_interval = 5         # 帧率更新频率，秒
        
        # 系统性能参数
        self.max_cpu_usage = 80              # 最大CPU使用率，百分比
        self.max_memory_usage = 70           # 最大内存使用率，百分比
        self.enable_performance_limit = True # 启用性能限制
        self.log_level = "INFO"              # 日志级别
        
        # 保存初始化后的默认值
        self._save_defaults()
    
    def _save_defaults(self):
        """保存当前所有参数值作为默认值"""
        for attr_name in dir(self):
            if not attr_name.startswith('_') and not callable(getattr(self, attr_name)) and attr_name != 'defaults':
                self.defaults[attr_name] = getattr(self, attr_name)
    
    def reset_to_defaults(self):
        """重置所有参数为默认值"""
        for attr_name, default_value in self.defaults.items():
            setattr(self, attr_name, default_value)
    
    def get_quality_config(self):
        """根据质量等级返回对应配置"""
        if self.quality_level == "基础":
            return {
                "enable_real_packet_loss": False,
                "enable_frame_analysis": False
            }
        elif self.quality_level == "标准":
            return {
                "enable_real_packet_loss": True,
                "enable_frame_analysis": False
            }
        else:  # 高级
            return {
                "enable_real_packet_loss": True,
                "enable_frame_analysis": True
            }

SETTINGS = SettingsManager()
SYSTEM_MONITOR_ID = -1

# ==============================================================================
# 全局状态管理
# ==============================================================================
STATUS_QUEUES = defaultdict(queue.Queue)
LOG_QUEUE = deque()
THREAD_TO_URL_MAP = {}
def create_aggregated_data():
    return {
        'total_frames': 0,
        'total_bytes': 0,
        'total_reconnects': 0,
        'total_expected_frames': 0,
        'total_lost_frames': 0,
        'fps_list': deque(maxlen=SETTINGS.fps_smooth_window),
        'latency_list': deque(maxlen=100),
        'start_time': None,
    }

AGGREGATED_DATA = defaultdict(create_aggregated_data)
THREAD_NAME_MAP = {}
STOP_EVENT = threading.Event()
STOP_CHECK_ID = None
SYSTEM_MONITOR_STOP_EVENT = threading.Event()
SYSTEM_MONITOR_THREAD = None

# ==============================================================================
# 线程安全日志处理器
# ==============================================================================
class ThreadSafeLogHandler(logging.Handler):
    """用于将日志发送到GUI队列"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        # 移除RTSP流监控线程的日志，避免刷屏
        # if record.name.startswith("线程-") or record.name == "root":
        #     return
            
        # 修正：将日志名作为前缀，并移除冗余信息，添加日期
        log_time = datetime.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        log_name = record.name if record.name != "root" else "System"
        log_message = f"[{log_time}] - [{log_name}] - [{record.levelname}] - {self.format(record)}"
        self.log_queue.append((record.levelno, log_message))

logging.basicConfig(level=logging.DEBUG)
for handler in logging.getLogger().handlers[:]:
    logging.getLogger().removeHandler(handler)

gui_handler = ThreadSafeLogHandler(LOG_QUEUE)
gui_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger().addHandler(gui_handler)

# ==============================================================================
# 已移除QoE评分相关功能
# ==============================================================================

# ==============================================================================
# PTS丢帧检测类
# ==============================================================================
class PTSFrameLossDetector:
    """基于PTS时间戳的真实丢帧检测器"""
    def __init__(self):
        self.pts_history = deque(maxlen=SETTINGS.pts_history_size)
        self.last_pts = None
        self.expected_frame_interval = None
        self.frame_rate = None
        self.total_frames_detected = 0
        self.total_frames_lost = 0
        self.consecutive_losses = 0
        self.pts_reset_detected = False
        
    def update_frame_rate(self, fps):
        """更新帧率并计算期望帧间隔"""
        if fps and fps > 0:
            self.frame_rate = fps
            self.expected_frame_interval = 1000.0 / fps  # 毫秒
    
    def detect_frame_loss(self, current_pts_ms):
        """检测基于PTS的帧丢失
        Args:
            current_pts_ms: 当前帧的PTS时间戳(毫秒)
        Returns:
            dict: 包含丢帧信息的字典
        """
        result = {
            'frames_lost': 0,
            'pts_reset': False,
            'interval_abnormal': False,
            'total_lost': self.total_frames_lost
        }
        
        if self.last_pts is None:
            # 第一帧，初始化
            self.last_pts = current_pts_ms
            self.pts_history.append(current_pts_ms)
            return result
        
        # 检测PTS重置或回退
        if current_pts_ms < self.last_pts:
            if (self.last_pts - current_pts_ms) > SETTINGS.pts_reset_threshold:
                result['pts_reset'] = True
                self.pts_reset_detected = True
                self._reset_detector()
                return result
        
        # 计算PTS间隔
        pts_interval = current_pts_ms - self.last_pts
        
        # 动态学习帧间隔（如果没有预设帧率）
        if self.expected_frame_interval is None and len(self.pts_history) >= 10:
            self._calculate_expected_interval()
        
        if self.expected_frame_interval:
            # 计算丢失的帧数
            expected_frames = round(pts_interval / self.expected_frame_interval)
            
            # 容错处理
            tolerance_ms = SETTINGS.pts_tolerance_ms
            interval_tolerance = SETTINGS.frame_interval_tolerance
            
            min_expected = self.expected_frame_interval * (1 - interval_tolerance)
            max_expected = self.expected_frame_interval * (1 + interval_tolerance)
            
            if pts_interval > (max_expected + tolerance_ms):
                # 检测到帧丢失
                frames_lost = max(0, expected_frames - 1)
                result['frames_lost'] = frames_lost
                result['interval_abnormal'] = True
                
                self.total_frames_lost += frames_lost
                self.consecutive_losses += 1
                
                # 连续丢帧告警
                if self.consecutive_losses >= SETTINGS.missing_frame_threshold:
                    result['consecutive_loss_alert'] = True
            else:
                self.consecutive_losses = 0
        
        # 更新历史记录
        self.pts_history.append(current_pts_ms)
        self.last_pts = current_pts_ms
        self.total_frames_detected += 1
        result['total_lost'] = self.total_frames_lost
        
        return result
    
    def _calculate_expected_interval(self):
        """从历史PTS数据计算期望帧间隔"""
        if len(self.pts_history) < 2:
            return
            
        intervals = []
        for i in range(1, len(self.pts_history)):
            interval = self.pts_history[i] - self.pts_history[i-1]
            if interval > 0:  # 过滤异常值
                intervals.append(interval)
        
        if intervals:
            # 使用中位数作为期望间隔，更稳定
            intervals.sort()
            median_idx = len(intervals) // 2
            self.expected_frame_interval = intervals[median_idx]
    
    def _reset_detector(self):
        """重置检测器状态"""
        self.pts_history.clear()
        self.last_pts = None
        self.consecutive_losses = 0
        self.pts_reset_detected = False
    
    def get_loss_statistics(self):
        """获取丢帧统计信息"""
        if self.total_frames_detected == 0:
            return {'loss_rate': 0.0, 'total_detected': 0, 'total_lost': 0}
        
        loss_rate = (self.total_frames_lost / (self.total_frames_detected + self.total_frames_lost)) * 100
        return {
            'loss_rate': loss_rate,
            'total_detected': self.total_frames_detected,
            'total_lost': self.total_frames_lost,
            'expected_interval': self.expected_frame_interval
        }

# ==============================================================================
# 真实帧率检测类  
# ==============================================================================
class RealTimeFrameRateDetector:
    """真实帧率检测器"""
    def __init__(self):
        self.detection_method = SETTINGS.fps_detection_method
        self.calculation_window = SETTINGS.fps_calculation_window
        self.frame_timestamps = deque(maxlen=self.calculation_window)
        self.last_calculated_fps = None
        
    def get_real_framerate(self, container):
        """获取真实帧率"""
        try:
            # 方法1: 从流元数据获取
            if container and container.streams.video:
                video_stream = container.streams.video[0]
                
                if video_stream.average_rate and video_stream.average_rate > 0:
                    fps = float(video_stream.average_rate)
                    if 1 <= fps <= 120:  # 合理范围检查
                        return fps
                
                # 方法2: 从编码器信息获取
                if hasattr(video_stream, 'codec_context') and video_stream.codec_context.framerate:
                    fps = float(video_stream.codec_context.framerate)
                    if 1 <= fps <= 120:
                        return fps
                
                # 方法3: 从时间基获取
                if video_stream.time_base and video_stream.duration:
                    time_base_fps = 1.0 / float(video_stream.time_base)
                    if 1 <= time_base_fps <= 120:
                        return time_base_fps
                        
        except Exception:
            pass
        
        # 方法4: 动态计算(基于帧时间戳)
        return self.calculate_fps_from_timestamps()
    
    def add_frame_timestamp(self, pts_ms):
        """添加帧时间戳用于动态计算"""
        current_time = time.time() * 1000  # 转换为毫秒
        self.frame_timestamps.append(current_time)
    
    def calculate_fps_from_timestamps(self):
        """基于时间戳动态计算帧率"""
        if len(self.frame_timestamps) < 10:
            return self.last_calculated_fps
        
        try:
            # 计算时间跨度和帧数
            time_span = self.frame_timestamps[-1] - self.frame_timestamps[0]
            frame_count = len(self.frame_timestamps) - 1
            
            if time_span > 0:
                fps = (frame_count * 1000.0) / time_span  # 转换为秒
                if 1 <= fps <= 120:
                    self.last_calculated_fps = fps
                    return fps
                    
        except Exception:
            pass
            
        return self.last_calculated_fps

# ==============================================================================
# 流监控线程
# ==============================================================================
class RTSPStreamMonitor(threading.Thread):
    def __init__(self, url, thread_id, parent_item_id, parent_url_id, thread_idx, total_threads, protocol='UDP'):
        super().__init__()
        self.url = url
        self.thread_id = thread_id
        self.parent_item_id = parent_item_id
        self.protocol = protocol
        self.stop_event = STOP_EVENT
        self.container = None
        
        log_name = f"线程-{parent_url_id:02d}-{thread_idx+1:02d}"
        self.logger = logging.getLogger(log_name)
        
        self.total_frames = 0
        self.total_bytes = 0
        self.reconnect_count = 0
        
        self.connect_latency = 0.0
        self.fps_frames_count = 0
        self.fps_start_time = time.time()
        self.start_time = time.time()
        self.last_fps = 0.0
        
        self.rtp_sequence = 0
        self.last_rtp_timestamp = 0
        self.i_frame_lost_detected = False
        self.packets_lost_count = 0  # 保留作为兼容性字段，不再使用模拟数据
        
        # 真实丢包检测变量
        self.real_rtp_sequence = 0
        self.expected_rtp_sequence = 0
        self.real_packet_loss_count = 0
        self.last_packet_time = 0.0
        
        # 帧类型分析变量
        self.i_frame_count = 0
        self.p_frame_count = 0
        self.b_frame_count = 0
        self.last_frame_type = None
        self.frame_analysis_enabled = SETTINGS.enable_frame_analysis
        
        # 新增变量，用于控制日志打印频率
        self.last_log_time = time.time()
        
        # 初始化PTS丢帧检测器和真实帧率检测器
        self.pts_detector = PTSFrameLossDetector()
        self.fps_detector = RealTimeFrameRateDetector()
        self.real_fps = None
        self.pts_frame_loss_count = 0

    def validate_and_fix_rtsp_url(self, url):
        """验证和修复RTSP URL格式"""
        if not url:
            return None
            
        # 去除空格和特殊字符
        url = url.strip()
        
        # 检查是否包含rtsp://前缀
        if not url.lower().startswith('rtsp://'):
            url = 'rtsp://' + url
        
        # 更严格的URL验证和修复
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            
            # 确保协议正确
            if parsed.scheme.lower() != 'rtsp':
                parsed = parsed._replace(scheme='rtsp')
            
            # 确保有主机名
            if not parsed.hostname:
                return None
            
            # 设置默认端口
            if not parsed.port:
                # 重构netloc包含端口
                if ':' not in parsed.netloc:
                    parsed = parsed._replace(netloc=f"{parsed.netloc}:554")
            
            # 确保路径不为空
            if not parsed.path or parsed.path == '/':
                parsed = parsed._replace(path='/stream')
            
            # 重构URL
            fixed_url = urlunparse(parsed)
            return fixed_url
            
        except Exception:
            # 如果解析失败，使用简单的修复逻辑
            if '://' in url:
                parts = url.split('://', 1)
                if len(parts) == 2:
                    protocol, rest = parts
                    if '/' in rest:
                        host_port, path = rest.split('/', 1)
                        # 如果没有端口，添加默认端口554
                        if ':' not in host_port:
                            host_port += ':554'
                        url = f"{protocol}://{host_port}/{path}"
                    else:
                        # 没有路径，添加默认端口和路径
                        if ':' not in rest:
                            rest += ':554'
                        url = f"{protocol}://{rest}/stream"
            
            return url

    def analyze_rtp_packet_loss(self, packet):
        """分析RTP包损失情况"""
        try:
            # 检查packet是否有效
            if not packet:
                return False
                
            # 检查packet是否有必要的属性
            if not hasattr(packet, 'size') or packet.size is None or packet.size < 12:
                return False
                
            # 尝试从PyAV packet获取原始数据
            try:
                # 对于PyAV packet，使用其内部的to_bytes()方法或直接访问
                if hasattr(packet, 'to_bytes'):
                    packet_data = packet.to_bytes()
                elif hasattr(packet, 'buffer_ptr') and hasattr(packet, 'buffer_size'):
                    # 直接从内存缓冲区读取
                    import ctypes
                    packet_data = ctypes.string_at(packet.buffer_ptr, min(packet.buffer_size, 64))
                else:
                    # 尝试标准bytes转换
                    packet_data = bytes(packet)
            except Exception:
                # 如果所有方法都失败，跳过RTP分析
                return False
                
            if len(packet_data) < 12:
                return False
                
            # 提取RTP序列号 (bytes 2-3)
            seq_num = int.from_bytes(packet_data[2:4], byteorder='big')
            
            # 初始化或序列号检查
            if not hasattr(self, 'last_rtp_seq') or self.last_rtp_seq is None:
                self.last_rtp_seq = seq_num
                return False
            
            # 检查序列号是否连续（考虑16位序列号回绕）
            expected_seq = (self.last_rtp_seq + 1) & 0xFFFF
            if seq_num != expected_seq:
                # 检测到丢包
                if hasattr(self, 'real_packet_loss_count'):
                    self.real_packet_loss_count += 1
                self.last_rtp_seq = seq_num
                return True
            
            self.last_rtp_seq = seq_num
            return False
            
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"RTP包分析错误: {e}")
            return False
    
    def analyze_frame_type(self, frame):
        """分析帧类型信息 - 完全基于真实数据"""
        if not self.frame_analysis_enabled or not frame:
            return None
            
        try:
            # 使用PyAV获取真实帧类型信息
            if hasattr(frame, 'pict_type') and frame.pict_type:
                pict_type = frame.pict_type
                frame_type = str(pict_type)
                
                # 统计不同类型的帧（只基于真实数据）
                if 'I' in frame_type.upper():
                    self.i_frame_count += 1
                    self.last_frame_type = 'I'
                elif 'P' in frame_type.upper():
                    self.p_frame_count += 1
                    self.last_frame_type = 'P'
                elif 'B' in frame_type.upper():
                    self.b_frame_count += 1
                    self.last_frame_type = 'B'
                else:
                    self.last_frame_type = 'Unknown'
                
                return self.last_frame_type
            
            # 无法获取真实帧类型时，不使用模拟数据，直接返回None
            # 这确保数据的真实性和一致性
            return None
            
        except Exception as e:
            self.logger.debug(f"帧类型分析失败: {e}")
            return None

    def run(self):
        # 获取真实帧率，不再使用预设值
        self.real_fps = None
        
        # 验证和修复URL格式
        validated_url = self.validate_and_fix_rtsp_url(self.url)
        if not validated_url:
            self.logger.error(f"RTSP URL格式无效: {self.url}")
            return
        
        if validated_url != self.url:
            # 静默修复URL，不输出日志
            self.url = validated_url

        while not self.stop_event.is_set():
            try:
                self.logger.debug(f"正在尝试连接: {self.url}...")
                start_time = time.time()
                
                # 优化RTSP连接参数，使用用户选择的协议
                options = {
                    'rtsp_transport': self.protocol.lower(),
                    'buffer_size': str(SETTINGS.rtsp_buffer_size),
                    'timeout': str(SETTINGS.rtsp_timeout),
                    'stimeout': '10000000',  # 10秒socket超时
                    'user_agent': SETTINGS.rtsp_user_agent,
                    'allowed_media_types': 'video',  # 只处理视频流
                    'analyzeduration': str(SETTINGS.rtsp_analyzeduration),
                    'probesize': str(SETTINGS.rtsp_probe_size),
                    'max_delay': str(SETTINGS.rtsp_max_delay),
                    'reorder_queue_size': '0',  # 禁用重排序队列
                    'fflags': 'nobuffer+fastseek+flush_packets',  # 优化标志
                    'flags': 'low_delay',  # 低延迟标志
                    'strict': 'experimental'  # 允许实验性功能
                }
                
                # 根据协议类型设置特定参数
                if self.protocol.upper() == 'TCP':
                    options['rtsp_flags'] = 'prefer_tcp'
                    options['rtsp_transport'] = 'tcp'
                else:
                    # UDP协议优化配置 - 使用最简化成功配置
                    options['rtsp_transport'] = 'udp'
                    options.pop('rtsp_flags', None)  # UDP不需要rtsp_flags
                    # 使用测试成功的最简化UDP配置
                    options['timeout'] = '30000000'  # 30秒超时（测试成功的配置）
                    # 移除可能导致问题的复杂参数，保持简洁
                    options.pop('fifo_size', None)
                    options.pop('overrun_nonfatal', None)
                    options.pop('protocol_whitelist', None)
                    # 保留基础必要参数
                    options['reorder_queue_size'] = '0'  # 禁用重排序队列
                    options['stimeout'] = '20000000'  # socket超时
                    options['buffer_size'] = str(SETTINGS.rtsp_buffer_size)  # 使用设置的缓冲区大小
                
                # 根据是否严格协议模式决定重试策略
                if SETTINGS.strict_protocol:
                    # 严格模式：仅使用用户选择的协议，不重试其他协议
                    max_retries = 3  # 只重试3次，都使用相同协议
                else:
                    # 兼容模式：允许尝试不同协议
                    max_retries = 5
                
                retry_delay = 0.5  # 初始延迟0.5秒
                
                connection_successful = False
                current_options = options  # 初始化current_options
                for retry in range(max_retries):
                    try:
                        if SETTINGS.strict_protocol:
                            # 严格模式：始终使用用户选择的协议
                            current_options = options.copy()
                            self.logger.debug(f"尝试连接 {retry + 1}/{max_retries}，使用{self.protocol}协议")
                        else:
                            # 兼容模式：尝试不同的连接参数
                            if retry == 0:
                                # 第一次尝试：使用用户选择的协议
                                current_options = options.copy()
                            elif retry == 1:
                                # 第二次尝试：如果用户选UDP，尝试TCP
                                current_options = options.copy()
                                if self.protocol.upper() == 'UDP':
                                    current_options['rtsp_transport'] = 'tcp'
                                    current_options['rtsp_flags'] = 'prefer_tcp'
                                else:
                                    current_options['rtsp_transport'] = 'udp'
                                    current_options.pop('rtsp_flags', None)
                            elif retry == 2:
                                # 第三次尝试：使用HTTP tunnel
                                current_options = options.copy()
                                current_options['rtsp_transport'] = 'http'
                                current_options['rtsp_flags'] = 'prefer_tcp'
                            elif retry == 3:
                                # 第四次尝试：最小参数配置
                                current_options = {
                                    'rtsp_transport': self.protocol.lower(),
                                    'timeout': '30000000',
                                    'user_agent': 'VLC/3.0.0'
                                }
                            else:
                                # 最后一次尝试：简化配置
                                current_options = {
                                    'timeout': '15000000'
                                }
                            
                            transport_info = current_options.get('rtsp_transport', self.protocol.lower())
                            self.logger.debug(f"尝试连接 {retry + 1}/{max_retries}，使用参数: {transport_info}")
                        self.container = av.open(self.url, mode='r', options=current_options)
                        connection_successful = True
                        break
                        
                    except Exception as e:
                        error_str = str(e)
                        
                        if retry < max_retries - 1:
                # 根据错误类型调整重试延迟
                            if "Invalid argument" in error_str or "Errno 22" in error_str or "Errno 10049" in error_str:
                                retry_delay = 0.2  # URL格式错误或地址无效快速重试
                            elif "timed out" in error_str.lower() or "timeout" in error_str.lower():
                                retry_delay = 3.0  # 超时错误等待更久
                            elif "connection refused" in error_str.lower() or "refused" in error_str.lower():
                                retry_delay = 2.0  # 连接被拒绝中等延迟
                            elif "unauthorized" in error_str.lower() or "401" in error_str:
                                retry_delay = 1.0  # 认证问题短延迟
                            elif "10049" in error_str:  # 专门处理UDP连接问题
                                if self.protocol.upper() == 'UDP':
                                    retry_delay = 2.0  # UDP地址问题增加重试延迟
                                    # 在严格模式下，优先使用测试成功的最简化配置
                                    if SETTINGS.strict_protocol:
                                        if retry == 0:
                                            # 第一次重试：直接使用最简化成功配置
                                            current_options = {
                                                'rtsp_transport': 'udp',
                                                'timeout': '30000000'  # 测试成功的配置
                                            }
                                        elif retry == 1:
                                            # 第二次重试：添加基础参数
                                            current_options = {
                                                'rtsp_transport': 'udp',
                                                'timeout': '30000000',
                                                'stimeout': '20000000',
                                                'reorder_queue_size': '0'
                                            }
                                        elif retry == 2:
                                            # 第三次重试：添加缓冲区设置
                                            current_options = {
                                                'rtsp_transport': 'udp',
                                                'timeout': '30000000',
                                                'buffer_size': str(SETTINGS.rtsp_buffer_size)
                                            }
                                else:
                                    retry_delay = 1.0  # 非UDP协议较短延迟
                            else:
                                retry_delay = 1.5  # 其他错误中等延迟
                            
                            transport_type = current_options.get('rtsp_transport', 'default')
                            self.logger.warning(f"连接尝试 {retry + 1} 失败 ({transport_type}): {e}, {retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                        else:
                            # 最后一次尝试失败，抛出异常
                            raise e
                
                if not connection_successful:
                    raise Exception(f"所有连接尝试都失败，无法连接到RTSP流: {self.url}")
                
                try:
                    # 使用真实帧率检测器获取帧率
                    self.real_fps = self.fps_detector.get_real_framerate(self.container)
                    if self.real_fps and self.real_fps > 0:
                        self.logger.info(f"成功获取到流的真实帧率：{self.real_fps:.2f} FPS")
                        # 更新PTS检测器的帧率
                        self.pts_detector.update_frame_rate(self.real_fps)
                    else:
                        self.logger.warning("无法获取视频流的真实帧率，将使用动态计算")
                except Exception as e:
                    self.logger.warning(f"获取真实帧率失败: {e}，将使用动态计算")

                self.connect_latency = time.time() - start_time
                
                # 根据协议类型显示不同的连接成功信息
                if self.protocol.upper() == 'UDP':
                    self.logger.info(f"UDP连接成功！延迟: {self.connect_latency:.1f}s。使用优化UDP配置。开始抓取帧。")
                else:
                    self.logger.info(f"TCP连接成功！延迟: {self.connect_latency:.1f}s。开始抓取帧。")

                self.start_time = time.time()
                self.fps_frames_count = 0
                
                self.rtp_sequence = 0
                self.last_rtp_timestamp = 0
                self.i_frame_lost_detected = False
                self.packets_lost_count = 0
                self.last_log_time = time.time() # 重置日志时间
                
                # 重置PTS检测器
                self.pts_detector = PTSFrameLossDetector()
                if self.real_fps:
                    self.pts_detector.update_frame_rate(self.real_fps)

                # 如果容器存在，开始处理视频包
                if self.container:
                    try:
                        for packet in self.container.demux(video=0):
                            if self.stop_event.is_set():
                                break
                            
                            # 真实丢包检测
                            real_packet_lost = self.analyze_rtp_packet_loss(packet)
                            if real_packet_lost:
                                self.real_packet_loss_count += 1
                            
                            # 保留原有的序列号计数，但不再做模拟丢包
                            self.rtp_sequence += 1
                            
                            # 去除I帧监控，不再使用解码模式
                            self.i_frame_lost_detected = False

                            self.total_bytes += packet.size if packet and packet.size is not None else 0

                            # 统一按包计数，去除解码功能
                            self.total_frames += 1
                            self.fps_frames_count += 1
                            self.fps_detector.add_frame_timestamp(time.time() * 1000)
                            
                            current_time = time.time()
                            elapsed_time = current_time - self.fps_start_time
                            
                            if elapsed_time >= 0.5:
                                self.last_fps = self.fps_frames_count / elapsed_time
                                self.fps_frames_count = 0
                                self.fps_start_time = current_time
                            
                            total_elapsed_time = current_time - self.start_time
                            
                            # 使用真实帧率或动态计算的帧率
                            current_fps = self.real_fps or self.fps_detector.calculate_fps_from_timestamps() or 25.0
                            expected_frames = int(total_elapsed_time * current_fps)
                            
                            # 使用PTS检测的丢帧数据，如果没有则使用传统计算
                            pts_stats = self.pts_detector.get_loss_statistics()
                            if pts_stats['total_lost'] > 0:
                                lost_frames = pts_stats['total_lost']
                                lost_rate_percent = pts_stats['loss_rate']
                            else:
                                # 传统计算方式作为备用
                                lost_frames = max(0, expected_frames - self.total_frames)
                                lost_rate_percent = (lost_frames / expected_frames * 100) if expected_frames > 0 else 0.0

                            status_info = {
                                'thread_id': self.thread_id,
                                'parent_item_id': self.parent_item_id,
                                'status': "运行中",
                                'total_frames': self.total_frames,
                                'received_frames': self.total_frames,
                                'total_bytes': self.total_bytes,
                                'reconnect_count': self.reconnect_count,
                                'connect_latency': self.connect_latency,
                                'current_fps': self.last_fps,
                                'expected_frames': expected_frames,
                                'lost_frames': lost_frames,
                                'real_fps': current_fps,
                                'pts_frame_loss': self.pts_frame_loss_count
                            }
                            # 优化状态推送频率，减少GUI更新压力
                            try:
                                if STATUS_QUEUES[self.thread_id].qsize() < 10:  # 队列不满时才推送
                                    STATUS_QUEUES[self.thread_id].put(status_info)
                            except:
                                # 队列异常时直接推送
                                STATUS_QUEUES[self.thread_id].put(status_info)
                            
                            # 修复：改为基于时间的判断，防止日志刷屏
                            if current_time - self.last_log_time >= 10:
                                self.logger.info(
                                    f"收到帧: {self.total_frames} | 理论帧: {expected_frames} | 丢失帧: {lost_frames} | 丢帧率: {lost_rate_percent:.1f}% | "
                                    f"帧率: {int(current_fps)}FPS"
                                )
                                self.last_log_time = current_time
                    except Exception as demux_error:
                        self.logger.error(f"处理视频包时发生错误: {demux_error}")
                    
                if not self.stop_event.is_set():
                    raise Exception("流结束或中断")
            
            except (av.error.HTTPUnauthorizedError, av.error.InvalidDataError, av.error.ExitError, av.error.FFmpegError, OSError, ConnectionError) as e:
                self.reconnect_count += 1
                error_msg = str(e)
                original_url = self.url
                
                # 针对[Errno 22] Invalid argument错误的特殊处理
                if "Error number -138" in error_msg:
                    error_msg = "RTSP服务器无响应或网络不可达"
                elif "Invalid argument" in error_msg or "Errno 22" in error_msg:
                    # 尝试修复URL并重新尝试
                    fixed_url = self.validate_and_fix_rtsp_url(self.url)
                    if fixed_url and fixed_url != self.url:
                        self.url = fixed_url
                        # 静默修复URL，不输出日志
                    else:
                        # 提供更详细的诊断信息
                        diagnostic_msg = f"RTSP URL参数错误。\n原始URL: {original_url}\n"
                        diagnostic_msg += "请检查：\n"
                        diagnostic_msg += "1. URL格式是否正确 (rtsp://ip:port/path)\n"
                        diagnostic_msg += "2. IP地址和端口是否可达\n"
                        diagnostic_msg += "3. RTSP服务是否正常运行\n"
                        diagnostic_msg += "4. 网络防火墙设置"
                        error_msg = diagnostic_msg
                elif "10049" in error_msg:
                    if self.protocol.upper() == 'UDP':
                        # UDP特有的[Errno 10049]错误诊断 - 增强版
                        error_msg = f"UDP连接失败[地址无效]: {original_url}\n"
                        error_msg += "=== UDP连接诊断分析 ===\n"
                        error_msg += "UDP连接失败的可能原因：\n"
                        error_msg += "1. ⚠️ RTSP服务器不支持UDP协议（最常见）\n"
                        error_msg += "2. 🚫 Windows防火墙阻止UDP连接\n"
                        error_msg += "3. 🌐 网络NAT或路由器配置问题\n"
                        error_msg += "4. 🔌 RTSP服务器仅支持TCP模式\n"
                        error_msg += "\n💡 建议解决方案：\n"
                        error_msg += "✅ 1. 在主程序中切换为TCP协议（推荐）\n"
                        error_msg += "🔧 2. 检查RTSP服务器配置，确认是否支持UDP\n"
                        error_msg += "🚫 3. 检查Windows防火墙，允许UDP端口通信\n"
                        error_msg += "🌐 4. 联系网络管理员检查路由器设置\n"
                        error_msg += "\n📊 诊断信息：\n"
                        error_msg += f"• 错误代码: [Errno 10049]\n"
                        error_msg += f"• 协议类型: UDP\n"
                        error_msg += f"• 目标地址: {original_url}\n"
                        error_msg += f"• 重试次数: {self.reconnect_count}"
                    else:
                        error_msg = f"地址无效错误: {original_url}"
                elif "timed out" in error_msg.lower():
                    error_msg = f"RTSP连接超时 - 服务器: {original_url}"
                elif "connection refused" in error_msg.lower():
                    error_msg = f"RTSP服务器拒绝连接 - 服务器: {original_url}"
                elif "unauthorized" in error_msg.lower():
                    error_msg = f"RTSP身份验证失败 - 服务器: {original_url}"
                elif "Protocol not found" in error_msg:
                    error_msg = f"RTSP协议不支持或URL格式错误 - URL: {original_url}"
                else:
                    error_msg = f"连接失败: {error_msg} - URL: {original_url}"
                
                self.logger.error(f"连接或拉流失败: {error_msg}。第 {self.reconnect_count} 次重试中...")
                status_info = {
                    'thread_id': self.thread_id,
                    'parent_item_id': self.parent_item_id,
                    'status': "重连中",
                    'total_frames': self.total_frames,
                    'received_frames': self.total_frames,
                    'total_bytes': self.total_bytes,
                    'reconnect_count': self.reconnect_count,
                    'connect_latency': self.connect_latency,
                    'current_fps': 0.0,
                    'expected_frames': 0,
                    'lost_frames': 0,
                    'packets_lost_count': self.packets_lost_count
                }
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

        final_fps = self.total_frames / (time.time() - self.start_time) if self.start_time and (time.time() - self.start_time) > 0 else 0.0
        
        # 使用真实帧率计算最终的丢帧数
        final_real_fps = self.real_fps or self.fps_detector.calculate_fps_from_timestamps() or final_fps
        final_expected_frames = int((time.time() - self.start_time) * final_real_fps) if self.start_time else self.total_frames
        final_lost_frames = max(0, final_expected_frames - self.total_frames)
        
        final_status = {
            'thread_id': self.thread_id,
            'parent_item_id': self.parent_item_id,
            'status': "已停止",
            'total_frames': self.total_frames,
            'received_frames': self.total_frames,
            'total_bytes': self.total_bytes,
            'reconnect_count': self.reconnect_count,
            'connect_latency': self.connect_latency,
            'current_fps': final_fps,
            'expected_frames': final_expected_frames,
            'lost_frames': final_lost_frames,
            'packets_lost_count': self.packets_lost_count,
            'real_fps': final_real_fps
        }
        STATUS_QUEUES[self.thread_id].put(final_status)
        self.logger.info("监控线程已停止。")
        
    def stop(self):
        self.stop_event.set()
        
# ==============================================================================
# 系统性能监控线程
# ==============================================================================
class SystemMonitor(threading.Thread):
    def __init__(self, thread_id):
        super().__init__()
        self.stop_event = SYSTEM_MONITOR_STOP_EVENT
        self.thread_id = thread_id
        self.last_net_counters = psutil.net_io_counters()
    
    def run(self):
        while not self.stop_event.is_set():
            try:
                cpu_percent = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory()
                current_net_counters = psutil.net_io_counters()

                net_recv = current_net_counters.bytes_recv - self.last_net_counters.bytes_recv
                
                self.last_net_counters = current_net_counters
                
                status_info = {
                    'thread_id': SYSTEM_MONITOR_ID,
                    'parent_item_id': SYSTEM_MONITOR_ID,
                    'status': 'OK',
                    'cpu_percent': cpu_percent,
                    'mem_percent': mem.percent,
                    'net_recv_mbps': (net_recv * 8) / (1024*1024) / 0.5,
                }
                STATUS_QUEUES[SYSTEM_MONITOR_ID].put(status_info)
                time.sleep(0.5)
            except Exception:
                time.sleep(0.5)

    def stop(self):
        self.stop_event.set()

# ==============================================================================
# GUI 主框架
# ==============================================================================
class StressTestFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.last_counters = {}
        self.url_list_data = {}
        self.monitor_threads = []
        self.thread_counter = 0
        self.url_counter = 0
        self.last_sys_info = {
            'cpu_percent': 0.0,
            'mem_percent': 0.0,
            'net_recv_mbps': 0.0,
        }
        # 用于保存停止后的最终统计数据
        self.final_stats = {}
        self.final_parent_stats = {}
        
        global SYSTEM_MONITOR_THREAD
        if SETTINGS.sys_monitor_enabled and not SYSTEM_MONITOR_THREAD:
            SYSTEM_MONITOR_THREAD = SystemMonitor(SYSTEM_MONITOR_ID)
            SYSTEM_MONITOR_THREAD.start()

        self.create_widgets()
        self.after(SETTINGS.gui_refresh_interval, self.update_statuses)
        self.after(SETTINGS.gui_refresh_interval, self.update_logs)
        
    def create_widgets(self):
        self.rowconfigure(2, weight=1)  # 地址框权重20，占主要空间
        self.rowconfigure(3, weight=1)   # 日志框权重1，最小化显示
        self.columnconfigure(0, weight=1)

        control_frame = ttk.Frame(self, padding="5 5 5 2")
        control_frame.grid(row=0, column=0, sticky='ew')
        control_frame.columnconfigure(1, weight=1)

        ttk.Label(control_frame, text="RTSP 地址:").grid(row=0, column=0, padx=2, pady=2, sticky='w')
        self.url_entry = ttk.Entry(control_frame, width=50)
        self.url_entry.insert(0, "rtsp://192.168.16.3/live/1/1")
        self.url_entry.grid(row=0, column=1, padx=2, pady=2, sticky='ew')
        self.url_entry.bind('<Button-3>', self.show_entry_context_menu)

        ttk.Label(control_frame, text="协议:").grid(row=0, column=2, padx=2, pady=2, sticky='w')
        self.protocol_combobox = ttk.Combobox(control_frame, width=4, values=['UDP', 'TCP'], state="readonly")
        self.protocol_combobox.current(0)
        self.protocol_combobox.grid(row=0, column=3, padx=2, pady=2, sticky='w')
        
        # ---- 界面布局调整：将“线程”移动到“协议”右边 ----
        ttk.Label(control_frame, text="线程:").grid(row=0, column=4, padx=2, pady=2, sticky='w')
        self.threads_per_url_combobox = ttk.Combobox(control_frame, width=4, values=[str(i) for i in range(1, 11)], state="readonly")
        self.threads_per_url_combobox.set(str(SETTINGS.threads_per_url))
        self.threads_per_url_combobox.grid(row=0, column=5, padx=2, pady=2, sticky='w')
        
        self.add_button = ttk.Button(control_frame, text="添加地址", command=self.add_url)
        self.add_button.grid(row=0, column=6, padx=2, pady=2, sticky='w')
        
        button_frame = ttk.Frame(self, padding="5 2 5 2")
        button_frame.grid(row=1, column=0, sticky='ew')
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

        self.start_button = ttk.Button(button_frame, text="启动监控", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, padx=2, sticky='w')
        self.stop_button = ttk.Button(button_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=2, sticky='w')
        self.clear_button = ttk.Button(button_frame, text="清空地址", command=self.clear_urls)
        self.clear_button.grid(row=0, column=2, padx=2, sticky='e')
        self.settings_button = ttk.Button(button_frame, text="参数设置", command=self.open_settings)
        self.settings_button.grid(row=0, column=3, padx=2, sticky='w')
        self.export_button = ttk.Button(button_frame, text="导出报表", command=self.export_report)
        self.export_button.grid(row=0, column=4, padx=2, sticky='w')
        self.download_log_button = ttk.Button(button_frame, text="下载日志", command=self.download_logs)
        self.download_log_button.grid(row=0, column=5, padx=2, sticky='w')
        self.batch_add_button = ttk.Button(button_frame, text="批量添加", command=self.open_batch_add_dialog)
        self.batch_add_button.grid(row=0, column=6, pady=2, padx=2, sticky='w')
        
        self.address_frame = ttk.Frame(self, padding="5 0 5 0")
        self.address_frame.grid(row=2, column=0, sticky='nsew')
        self.address_frame.rowconfigure(0, weight=1)
        self.address_frame.columnconfigure(0, weight=1)
        
        columns = ('id', 'url', 'status', 'fps', 'expected_frames', 'received_frames', 'lost_frames', 'lost_rate', 'total_bytes', 'reconnects', 'latency')
        self.tree = ttk.Treeview(self.address_frame, columns=columns, show='headings')
        self.tree.heading('id', text='ID', anchor='center')
        self.tree.heading('url', text='URL', anchor='center')
        self.tree.heading('status', text='状态', anchor='center')

        self.tree.heading('fps', text='FPS', anchor='center')
        self.tree.heading('expected_frames', text='理论帧', anchor='center')
        self.tree.heading('received_frames', text='已收帧', anchor='center')
        self.tree.heading('lost_frames', text='丢失帧', anchor='center')
        self.tree.heading('lost_rate', text='丢帧率', anchor='center')
        self.tree.heading('total_bytes', text='流量', anchor='center') # 修改为“流量”
        self.tree.heading('reconnects', text='重连', anchor='center')
        self.tree.heading('latency', text='延迟', anchor='center')
        
        self.tree.column('id', width=60, anchor='center', stretch=False)
        self.tree.column('url', minwidth=200, anchor='w', stretch=True) 
        self.tree.column('status', width=120, anchor='center', stretch=False)

        self.tree.column('fps', width=80, anchor='center', stretch=False)
        self.tree.column('expected_frames', width=80, anchor='center', stretch=False)
        self.tree.column('received_frames', width=80, anchor='center', stretch=False)
        self.tree.column('lost_frames', width=80, anchor='center', stretch=False)
        self.tree.column('lost_rate', width=80, anchor='center', stretch=False)
        self.tree.column('total_bytes', width=100, anchor='center', stretch=False)
        self.tree.column('reconnects', width=80, anchor='center', stretch=False)
        self.tree.column('latency', width=80, anchor='center', stretch=False)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.tree_scrollbar = ttk.Scrollbar(self.address_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scrollbar.set)
        self.tree_scrollbar.grid(row=0, column=1, sticky='ns')
        
        # 新增横向滑动条
        self.tree_x_scrollbar = ttk.Scrollbar(self.address_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=self.tree_x_scrollbar.set)
        self.tree_x_scrollbar.grid(row=1, column=0, sticky='ew')
        
        self.tree.bind("<Button-3>", self.show_tree_context_menu)
        


        log_frame = ttk.Frame(self, padding="5 0 5 5")
        log_frame.grid(row=3, column=0, sticky='nsew')
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', height=3)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        self.log_text.bind('<Button-3>', self.show_log_context_menu)

        status_frame = ttk.Frame(self, padding="6")
        status_frame.grid(row=4, column=0, sticky='ew', padx=5, pady=(2, 5))
        status_frame.columnconfigure(0, weight=1)
        status_frame.columnconfigure(1, weight=1)
        
        self.status_label = ttk.Label(status_frame, text="已停止", foreground="black")
        self.status_label.grid(row=0, column=0, padx=5, sticky='w')
        
        perf_frame = ttk.Frame(status_frame)
        perf_frame.grid(row=0, column=1, sticky='e')
        
        self.cpu_label = ttk.Label(perf_frame, text="CPU: --%", foreground="black")
        self.cpu_label.pack(side='left', padx=5)
        self.mem_label = ttk.Label(perf_frame, text="内存: --%", foreground="black")
        self.mem_label.pack(side='left', padx=5)
        self.net_label = ttk.Label(perf_frame, text="网络: ↓--Mbps", foreground="black")
        self.net_label.pack(side='left', padx=5)
        
    def show_entry_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="全选", command=lambda: self.url_entry.select_range(0, 'end'))
        menu.add_command(label="复制", command=lambda: self.master.clipboard_append(self.url_entry.selection_get()))
        menu.add_command(label="粘贴", command=lambda: self.url_entry.insert(tk.INSERT, self.master.clipboard_get()))
        menu.add_command(label="删除", command=lambda: self.url_entry.delete(0, 'end'))
        menu.tk_popup(event.x_root, event.y_root)

    def show_tree_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            parent_iid = self.tree.parent(iid)
            if not parent_iid:
                self.tree.selection_set(iid)
                menu = tk.Menu(self, tearoff=0)
                menu.add_command(label="全选", command=self.select_all_tree_items)
                menu.add_command(label="复制", command=self.copy_selected_tree_items)
                menu.add_command(label="粘贴", command=self.paste_to_batch_add)
                menu.add_command(label="删除", command=self.delete_selected_tree_items)
                menu.tk_popup(event.x_root, event.y_root)
        
    def show_log_context_menu(self, event):
        self.log_text.tag_add(tk.SEL, "1.0", tk.END)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="全选", command=lambda: self.log_text.tag_add(tk.SEL, "1.0", tk.END))
        menu.add_command(label="复制", command=lambda: self.master.clipboard_append(self.log_text.selection_get()))
        menu.add_command(label="清空", command=self.clear_logs)
        menu.tk_popup(event.x_root, event.y_root)
    
    def clear_logs(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')

    def select_all_tree_items(self):
        self.tree.selection_set(self.tree.get_children())
        for item_id in self.tree.get_children():
            self.tree.selection_add(self.tree.get_children(item_id))
    
    def copy_selected_tree_items(self):
        selected_text = ""
        for iid in self.tree.selection():
            parent_iid = self.tree.parent(iid)
            if not parent_iid and iid in self.url_list_data:
                url_value = self.url_list_data[iid]['url']
                if url_value:
                    selected_text += url_value + "\n"
        if selected_text:
            self.master.clipboard_clear()
            self.master.clipboard_append(selected_text)

    def paste_to_batch_add(self):
        clipboard_content = self.master.clipboard_get()
        if clipboard_content:
            self.open_batch_add_dialog(initial_text=clipboard_content)

    def delete_selected_tree_items(self):
        if not self.tree.selection():
            return
        if messagebox.askyesno("确认删除", "确定要删除选中的项吗？"):
            parent_iids = []
            for iid in self.tree.selection():
                parent_iid = self.tree.parent(iid)
                if not parent_iid:
                    parent_iids.append(iid)
                else:
                    parent_iids.append(parent_iid)
            for iid in list(set(parent_iids)):
                self.remove_url(iid)

    def add_url(self, url=None):
        if url is None:
            url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "RTSP 地址不能为空！")
            return
        
        # 直接使用validate_and_fix_rtsp_url方法，而不是创建临时实例
        original_url = url
        validated_url = self.validate_rtsp_url(url)
        
        if not validated_url:
            messagebox.showerror("错误", f"RTSP URL格式错误，无法修复: {url}")
            return
        
        url = validated_url
        
        if url != original_url:
            # 仅记录到日志，不显示弹窗提醒
            logging.debug(f"URL自动修复: {original_url} -> {url}")
        
        display_url = re.sub(r'^rtsp://', '', url)
        self.url_counter += 1
        item_id = self.tree.insert('', tk.END, iid=f"url_{self.url_counter}", values=(
            f"#{self.url_counter}",
            display_url,
            "未启动",
            "0.0",  # FPS
            "0",    # 理论帧
            "0",    # 已收帧
            "0",    # 丢失帧
            "0.0%", # 丢包率
            "0.00 MB", # 流量
            "0",    # 重连
            "0.0s"  # 延迟
        ), tags=('url_row',))
        
        self.tree.tag_configure('url_row', font=('TkDefaultFont', 9, 'bold'))
        self.tree.tag_configure('thread_row', font=('TkDefaultFont', 9))
        self.tree.tag_configure('warning', background='#ffcccb')
        self.tree.tag_configure('normal', background='')

        self.url_list_data[item_id] = {
            'id': self.url_counter,
            'url': url,
            'children': []
        }
        self.url_entry.delete(0, tk.END)

    def validate_rtsp_url(self, url):
        """验证和修复RTSP URL格式"""
        if not url:
            return None
            
        # 去除空格和特殊字符
        url = url.strip()
        
        # 检查是否包含rtsp://前缀
        if not url.lower().startswith('rtsp://'):
            url = 'rtsp://' + url
        
        # 更严格的URL验证和修复
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            
            # 确保协议正确
            if parsed.scheme.lower() != 'rtsp':
                parsed = parsed._replace(scheme='rtsp')
            
            # 确保有主机名
            if not parsed.hostname:
                return None
            
            # 设置默认端口
            if not parsed.port:
                # 重构netloc包含端口
                if ':' not in parsed.netloc:
                    parsed = parsed._replace(netloc=f"{parsed.netloc}:554")
            
            # 确保路径不为空
            if not parsed.path or parsed.path == '/':
                parsed = parsed._replace(path='/stream')
            
            # 重构URL
            fixed_url = urlunparse(parsed)
            return fixed_url
            
        except Exception:
            # 如果解析失败，使用简单的修复逻辑
            if '://' in url:
                parts = url.split('://', 1)
                if len(parts) == 2:
                    protocol, rest = parts
                    if '/' in rest:
                        host_port, path = rest.split('/', 1)
                        # 如果没有端口，添加默认端口554
                        if ':' not in host_port:
                            host_port += ':554'
                        url = f"{protocol}://{host_port}/{path}"
                    else:
                        # 没有路径，添加默认端口和路径
                        if ':' not in rest:
                            rest += ':554'
                        url = f"{protocol}://{rest}/stream"
            
            return url

    def open_batch_add_dialog(self, initial_text=""):
        win = Toplevel(self)
        win.title("批量添加地址")
        win.geometry("450x300")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill='both', expand=True)

        ttk.Label(frm, text="在此粘贴RTSP地址 (每行/逗号/空格分割):").pack(fill='x', pady=(0, 5))
        address_text = scrolledtext.ScrolledText(frm, height=10, wrap=tk.WORD)
        address_text.pack(fill='both', expand=True, pady=(0, 5))
        
        default_batch_urls = "rtsp://192.168.16.3/live/1/1\nrtsp://192.168.16.3/live/1/2\nrtsp://192.168.16.3/live/1/3\nrtsp://192.168.16.3/live/1/4\nrtsp://192.168.16.3/live/1/5\nrtsp://192.168.16.3/live/1/6\nrtsp://192.168.16.3/live/1/7\nrtsp://192.168.16.3/live/1/8"
        if not initial_text:
            initial_text = default_batch_urls
        address_text.insert(tk.END, initial_text)

        def show_batch_menu(event):
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="全选", command=lambda: address_text.tag_add(tk.SEL, "1.0", tk.END))
            menu.add_command(label="复制", command=lambda: self.master.clipboard_append(address_text.get(tk.SEL_FIRST, tk.SEL_LAST)))
            menu.add_command(label="粘贴", command=lambda: address_text.insert(tk.INSERT, self.master.clipboard_get()))
            menu.add_command(label="删除", command=lambda: address_text.delete(tk.SEL_FIRST, tk.SEL_LAST))
            menu.tk_popup(event.x_root, event.y_root)
        address_text.bind("<Button-3>", show_batch_menu)

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill='x', pady=5)

        def process_and_add():
            text_content = address_text.get('1.0', tk.END).strip()
            if not text_content:
                messagebox.showerror("错误", "内容为空！")
                return
            urls = re.split(r'[\s,，]+', text_content)
            urls = [url.strip() for url in urls if url.strip()]
            urls = list(dict.fromkeys(urls))
            for url in urls:
                self.add_url(url)
            win.destroy()

        def import_file():
            file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        urls = [line.strip() for line in f.readlines() if line.strip()]
                        urls = list(dict.fromkeys(urls))
                        for url in urls:
                            self.add_url(url)
                    win.destroy()
                except Exception as e:
                    messagebox.showerror("错误", f"读取文件失败: {e}")

        ttk.Button(btn_frame, text="导入文件", command=import_file).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="全部添加", command=process_and_add).pack(side='right', padx=5)
    
    def remove_url(self, item_id):
        if item_id in self.url_list_data:
            # Clean up child thread data
            for thread_id in self.url_list_data[item_id]['children']:
                STATUS_QUEUES.pop(thread_id, None)
                THREAD_NAME_MAP.pop(thread_id, None)

            AGGREGATED_DATA.pop(item_id, None)
            keys_to_del = [k for k in list(self.last_counters.keys()) if k[0] == item_id]
            for k in keys_to_del:
                self.last_counters.pop(k, None)
            
            self.tree.delete(item_id)
            del self.url_list_data[item_id]

    def clear_urls(self):
        for item_id in list(self.url_list_data.keys()):
            self.remove_url(item_id)

    def open_settings(self):
        """打开参数设置窗口"""
        win = Toplevel(self)
        win.title("参数设置")
        win.geometry("600x400")
        win.resizable(True, True)
        
        # 设置窗口居中显示
        win.transient(self.master)
        win.grab_set()
        
        # 主框架
        main_frame = ttk.Frame(win, padding=20)
        main_frame.pack(fill='both', expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 顶部按钮框
        top_frame = ttk.Frame(main_frame)
        top_frame.grid(row=0, column=0, sticky='ew', pady=(0, 20))
        top_frame.columnconfigure(1, weight=1)
        
        # 默认恢复按钮
        reset_btn = ttk.Button(top_frame, text="恢复默认设置", 
                              command=lambda: self.reset_to_defaults(win))
        reset_btn.grid(row=0, column=0, sticky='w')
        
        # 说明文字
        info_label = ttk.Label(top_frame, text="提示：所有参数修改后即时生效，关闭窗口后保持当前设置", 
                                 foreground="#666666", font=('TkDefaultFont', 9))
        info_label.grid(row=0, column=2, sticky='e')
        
        # 创建Notebook控件
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky='nsew', pady=(0, 20))
        
        # 创建各个Tab页面
        self.create_basic_tab(notebook)
        self.create_rtsp_tab(notebook)
        self.create_quality_tab(notebook)
        self.create_system_tab(notebook)
        
        # 底部按钮框
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, sticky='ew')
        button_frame.columnconfigure(0, weight=1)
        
        # 创建一个分隔线
        separator = ttk.Separator(button_frame, orient='horizontal')
        separator.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 15))
        
        # 按钮容器，居中放置
        btn_container = ttk.Frame(button_frame)
        btn_container.grid(row=1, column=0, columnspan=3)
        
        # 取消按钮（左侧）
        cancel_button = ttk.Button(btn_container, text="取消", width=12,
                                  command=win.destroy)
        cancel_button.grid(row=0, column=0, padx=(0, 20))
        
        # 保存设置按钮（右侧，突出显示）
        save_button = ttk.Button(btn_container, text="保存设置", width=12,
                                command=lambda: self.save_settings(win, notebook))
        save_button.grid(row=0, column=1, padx=(20, 0))
        
        # 设置保存按钮为默认按钮（回车键触发）
        win.bind('<Return>', lambda e: self.save_settings(win, notebook))
        save_button.configure(style='Accent.TButton')
        
        # 设置焦点在保存按钮上
        save_button.focus_set()
        
    def create_basic_tab(self, notebook):
        """创建基础设置页面"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="基础设置")
        
        # 创建滚动框
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 参数设置
        row = 0
        
        # GUI参数
        self._create_section_label(scrollable_frame, row, "GUI 设置")
        row += 1
        
        self.gui_entry = self._create_labeled_entry(scrollable_frame, row, "GUI 刷新间隔 (ms)", 15, SETTINGS.gui_refresh_interval, "控制界面更新频率，较小值更流畅但耗CPU更多")
        row += 1
        
        self.reconnect_entry = self._create_labeled_entry(scrollable_frame, row, "重连等待时间 (s)", 15, SETTINGS.reconnect_wait_time, "连接失败后重试的间隔时间，较短时间重试更频繁")
        row += 1
        
        self.fps_smooth_entry = self._create_labeled_entry(scrollable_frame, row, "FPS平滑窗口", 15, SETTINGS.fps_smooth_window, "父项汇总FPS平滑窗口大小")
        row += 1
        
        # 系统监控设置
        self.sys_monitor_var = tk.BooleanVar(value=SETTINGS.sys_monitor_enabled)
        self._create_checkbox(scrollable_frame, row, "启用系统监控", self.sys_monitor_var, "监控CPU、内存、网络等系统资源使用情况")
        row += 1
        
        frame.basic_controls = {
            'gui_entry': self.gui_entry,
            'reconnect_entry': self.reconnect_entry,
            'fps_smooth_entry': self.fps_smooth_entry,
            'sys_monitor_var': self.sys_monitor_var
        }
        
    def _create_section_label(self, parent, row, text):
        """创建节标题的通用方法"""
        label = ttk.Label(parent, text=text, font=('TkDefaultFont', 10, 'bold'))
        label.grid(row=row, column=0, columnspan=3, sticky='w', pady=(15, 5))
        return label
        
    def _create_labeled_entry(self, parent, row, label_text, width, default_value, help_text):
        """创建带标签和帮助文本的输入框"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky='w', pady=3)
        entry = ttk.Entry(parent, width=width)
        entry.insert(0, str(default_value))
        entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(parent, text=help_text, foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        return entry
        
    def _create_checkbox(self, parent, row, text, variable, help_text):
        """创建复选框的通用方法"""
        checkbox = ttk.Checkbutton(parent, text=text, variable=variable)
        checkbox.grid(row=row, column=0, columnspan=2, sticky='w', pady=3)
        ttk.Label(parent, text=help_text, foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        return checkbox
        
    def create_system_tab(self, notebook):
        """创建系统性能页面"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="系统性能")
        
        # 创建滚动框
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        row = 0
        
        # 系统性能限制
        self._create_section_label(scrollable_frame, row, "性能限制设置")
        row += 1
        
        self.performance_limit_var = tk.BooleanVar(value=SETTINGS.enable_performance_limit)
        self._create_checkbox(scrollable_frame, row, "启用性能限制", self.performance_limit_var, "防止系统过载")
        row += 1
        
        self.max_cpu_entry = self._create_labeled_entry(scrollable_frame, row, "最大CPU使用率 (%)", 15, SETTINGS.max_cpu_usage, "CPU使用率上限")
        row += 1
        
        self.max_memory_entry = self._create_labeled_entry(scrollable_frame, row, "最大内存使用率 (%)", 15, SETTINGS.max_memory_usage, "内存使用率上限")
        row += 1
        
        # 日志设置
        self._create_section_label(scrollable_frame, row, "日志设置")
        row += 1
        
        ttk.Label(scrollable_frame, text="日志级别").grid(row=row, column=0, sticky='w', pady=3)
        self.log_level_combobox = ttk.Combobox(scrollable_frame, width=12, 
                                               values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly")
        self.log_level_combobox.set(SETTINGS.log_level)
        self.log_level_combobox.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="日志详细程度", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        
        frame.system_controls = {
            'performance_limit_var': self.performance_limit_var,
            'max_cpu_entry': self.max_cpu_entry,
            'max_memory_entry': self.max_memory_entry,
            'log_level_combobox': self.log_level_combobox
        }
        

    def create_rtsp_tab(self, notebook):
        """创建RTSP参数页面"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="RTSP参数")
        
        # 创建滚动框
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        row = 0
        
        # 核心RTSP参数
        label = ttk.Label(scrollable_frame, text="核心RTSP参数", font=('TkDefaultFont', 10, 'bold'))
        label.grid(row=row, column=0, columnspan=3, sticky='w', pady=(10, 5))
        row += 1
        
        ttk.Label(scrollable_frame, text="RTSP超时 (微秒)").grid(row=row, column=0, sticky='w', pady=3)
        self.rtsp_timeout_entry = ttk.Entry(scrollable_frame, width=15)
        self.rtsp_timeout_entry.insert(0, str(SETTINGS.rtsp_timeout))
        self.rtsp_timeout_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="RTSP连接的超时时间，1秒=1000000微秒", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="缓冲区大小 (字节)").grid(row=row, column=0, sticky='w', pady=3)
        self.buffer_size_entry = ttk.Entry(scrollable_frame, width=15)
        self.buffer_size_entry.insert(0, str(SETTINGS.rtsp_buffer_size))
        self.buffer_size_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="接收缓冲区大小，较大值可减少丢包但增加延迟", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="最大延迟 (微秒)").grid(row=row, column=0, sticky='w', pady=3)
        self.max_delay_entry = ttk.Entry(scrollable_frame, width=15)
        self.max_delay_entry.insert(0, str(SETTINGS.rtsp_max_delay))
        self.max_delay_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="允许的最大网络延迟，超过后丢弃数据包", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="探测大小 (字节)").grid(row=row, column=0, sticky='w', pady=3)
        self.probe_size_entry = ttk.Entry(scrollable_frame, width=15)
        self.probe_size_entry.insert(0, str(SETTINGS.rtsp_probe_size))
        self.probe_size_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="流信息探测的数据大小，影响流信息获取速度", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="分析时长 (微秒)").grid(row=row, column=0, sticky='w', pady=3)
        self.analyze_duration_entry = ttk.Entry(scrollable_frame, width=15)
        self.analyze_duration_entry.insert(0, str(SETTINGS.rtsp_analyzeduration))
        self.analyze_duration_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="流信息分析的时间长度，影响启动时间", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        
        frame.rtsp_controls = {
            'rtsp_timeout_entry': self.rtsp_timeout_entry,
            'buffer_size_entry': self.buffer_size_entry,
            'max_delay_entry': self.max_delay_entry,
            'probe_size_entry': self.probe_size_entry,
            'analyze_duration_entry': self.analyze_duration_entry
        }
        
    def create_quality_tab(self, notebook):
        """创建数据质量页面"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="数据质量")
        
        # 创建滚动框
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        row = 0
        
        # 数据质量等级
        label = ttk.Label(scrollable_frame, text="数据质量设置", font=('TkDefaultFont', 10, 'bold'))
        label.grid(row=row, column=0, columnspan=3, sticky='w', pady=(10, 5))
        row += 1
        
        ttk.Label(scrollable_frame, text="质量等级").grid(row=row, column=0, sticky='w', pady=3)
        self.quality_level_combobox = ttk.Combobox(scrollable_frame, width=12, 
                                                   values=["基础", "标准", "高级"], state="readonly")
        self.quality_level_combobox.set(SETTINGS.quality_level)
        self.quality_level_combobox.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="检测精度等级：高级>标准>基础，CPU负载依次增加", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        # 功能开关
        self.real_packet_loss_var = tk.BooleanVar(value=SETTINGS.enable_real_packet_loss)
        real_loss_check = ttk.Checkbutton(scrollable_frame, text="启用真实丢包检测", 
                                          variable=self.real_packet_loss_var)
        real_loss_check.grid(row=row, column=0, columnspan=2, sticky='w', pady=3)
        ttk.Label(scrollable_frame, text="通过RTP序列号分析检测真实的网络丢包情况", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        self.frame_analysis_var = tk.BooleanVar(value=SETTINGS.enable_frame_analysis)
        frame_check = ttk.Checkbutton(scrollable_frame, text="启用帧类型分析", 
                                      variable=self.frame_analysis_var)
        frame_check.grid(row=row, column=0, columnspan=2, sticky='w', pady=3)
        ttk.Label(scrollable_frame, text="使用PyAV库分析I/P/B帧类型，需要解码模式", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        # 质量监控参数
        label = ttk.Label(scrollable_frame, text="质量监控参数", font=('TkDefaultFont', 10, 'bold'))
        label.grid(row=row, column=0, columnspan=3, sticky='w', pady=(15, 5))
        row += 1
        
        ttk.Label(scrollable_frame, text="RTP超时阈值 (ms)").grid(row=row, column=0, sticky='w', pady=3)
        self.rtp_timeout_entry = ttk.Entry(scrollable_frame, width=15)
        self.rtp_timeout_entry.insert(0, str(SETTINGS.rtp_timeout_threshold))
        self.rtp_timeout_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="超时判断阈值", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        # PTS丢帧检测参数
        label = ttk.Label(scrollable_frame, text="PTS丢帧检测参数", font=('TkDefaultFont', 10, 'bold'))
        label.grid(row=row, column=0, columnspan=3, sticky='w', pady=(15, 5))
        row += 1
        
        ttk.Label(scrollable_frame, text="PTS容错范围 (ms)").grid(row=row, column=0, sticky='w', pady=3)
        self.pts_tolerance_entry = ttk.Entry(scrollable_frame, width=15)
        self.pts_tolerance_entry.insert(0, str(SETTINGS.pts_tolerance_ms))
        self.pts_tolerance_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="PTS时间戳容错范围", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="帧间隔容错比例").grid(row=row, column=0, sticky='w', pady=3)
        self.frame_interval_tolerance_entry = ttk.Entry(scrollable_frame, width=15)
        self.frame_interval_tolerance_entry.insert(0, str(SETTINGS.frame_interval_tolerance))
        self.frame_interval_tolerance_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="帧间隔容错比例", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="连续丢帧阈值").grid(row=row, column=0, sticky='w', pady=3)
        self.missing_frame_threshold_entry = ttk.Entry(scrollable_frame, width=15)
        self.missing_frame_threshold_entry.insert(0, str(SETTINGS.missing_frame_threshold))
        self.missing_frame_threshold_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="连续丢帧判断阈值", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="丢帧率阈值 (%)").grid(row=row, column=0, sticky='w', pady=3)
        self.packet_loss_threshold_entry = ttk.Entry(scrollable_frame, width=15)
        self.packet_loss_threshold_entry.insert(0, str(SETTINGS.packet_loss_threshold))
        self.packet_loss_threshold_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="丢帧告警阈值", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        
        frame.quality_controls = {
            'quality_level_combobox': self.quality_level_combobox,
            'real_packet_loss_var': self.real_packet_loss_var,
            'frame_analysis_var': self.frame_analysis_var,
            'rtp_timeout_entry': self.rtp_timeout_entry,
            'pts_tolerance_entry': self.pts_tolerance_entry,
            'frame_interval_tolerance_entry': self.frame_interval_tolerance_entry,
            'missing_frame_threshold_entry': self.missing_frame_threshold_entry,
            'packet_loss_threshold_entry': self.packet_loss_threshold_entry
        }
        
    def create_system_tab(self, notebook):
        """创建系统性能页面"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="系统性能")
        
        # 创建滚动框
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        row = 0
        
        # 系统性能限制
        label = ttk.Label(scrollable_frame, text="性能限制设置", font=('TkDefaultFont', 10, 'bold'))
        label.grid(row=row, column=0, columnspan=3, sticky='w', pady=(10, 5))
        row += 1
        
        self.performance_limit_var = tk.BooleanVar(value=SETTINGS.enable_performance_limit)
        perf_check = ttk.Checkbutton(scrollable_frame, text="启用性能限制", 
                                     variable=self.performance_limit_var)
        perf_check.grid(row=row, column=0, columnspan=2, sticky='w', pady=3)
        ttk.Label(scrollable_frame, text="防止系统过载", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="最大CPU使用率 (%)").grid(row=row, column=0, sticky='w', pady=3)
        self.max_cpu_entry = ttk.Entry(scrollable_frame, width=15)
        self.max_cpu_entry.insert(0, str(SETTINGS.max_cpu_usage))
        self.max_cpu_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="CPU使用率上限", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        ttk.Label(scrollable_frame, text="最大内存使用率 (%)").grid(row=row, column=0, sticky='w', pady=3)
        self.max_memory_entry = ttk.Entry(scrollable_frame, width=15)
        self.max_memory_entry.insert(0, str(SETTINGS.max_memory_usage))
        self.max_memory_entry.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="内存使用率上限", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        row += 1
        
        # 日志设置
        label = ttk.Label(scrollable_frame, text="日志设置", font=('TkDefaultFont', 10, 'bold'))
        label.grid(row=row, column=0, columnspan=3, sticky='w', pady=(15, 5))
        row += 1
        
        ttk.Label(scrollable_frame, text="日志级别").grid(row=row, column=0, sticky='w', pady=3)
        self.log_level_combobox = ttk.Combobox(scrollable_frame, width=12, 
                                               values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly")
        self.log_level_combobox.set(SETTINGS.log_level)
        self.log_level_combobox.grid(row=row, column=1, sticky='w', pady=3, padx=(10, 5))
        ttk.Label(scrollable_frame, text="日志详细程度", foreground="gray").grid(row=row, column=2, sticky='w', padx=5)
        
        frame.system_controls = {
            'performance_limit_var': self.performance_limit_var,
            'max_cpu_entry': self.max_cpu_entry,
            'max_memory_entry': self.max_memory_entry,
            'log_level_combobox': self.log_level_combobox
        }
        
    def reset_to_defaults(self, win):
        """重置为默认设置"""
        result = messagebox.askyesno("确认重置", "确认要重置为默认设置吗？这将会丢失当前所有修改。")
        if result:
            SETTINGS.reset_to_defaults()
            messagebox.showinfo("成功", "已重置为默认设置。请重新打开设置窗口查看更新后的值。")
            win.destroy()
    
    def save_settings(self, win, notebook):
        """保存设置"""
        try:
            # 保存基础设置
            for i in range(notebook.index('end')):
                tab_frame = notebook.nametowidget(notebook.tabs()[i])
                
                if hasattr(tab_frame, 'basic_controls'):
                    controls = tab_frame.basic_controls
                    SETTINGS.gui_refresh_interval = int(controls['gui_entry'].get())
                    SETTINGS.reconnect_wait_time = int(controls['reconnect_entry'].get())
                    SETTINGS.fps_smooth_window = int(controls['fps_smooth_entry'].get())
                    SETTINGS.sys_monitor_enabled = controls['sys_monitor_var'].get()
                    # 协议设置和线程数设置由GUI主页面管理，不再在参数设置中修改
                
                elif hasattr(tab_frame, 'rtsp_controls'):
                    controls = tab_frame.rtsp_controls
                    SETTINGS.rtsp_timeout = int(controls['rtsp_timeout_entry'].get())
                    SETTINGS.rtsp_buffer_size = int(controls['buffer_size_entry'].get())
                    SETTINGS.rtsp_max_delay = int(controls['max_delay_entry'].get())
                    SETTINGS.rtsp_probe_size = int(controls['probe_size_entry'].get())
                    SETTINGS.rtsp_analyzeduration = int(controls['analyze_duration_entry'].get())
                
                elif hasattr(tab_frame, 'quality_controls'):
                    controls = tab_frame.quality_controls
                    SETTINGS.quality_level = controls['quality_level_combobox'].get()
                    SETTINGS.enable_real_packet_loss = controls['real_packet_loss_var'].get()
                    SETTINGS.enable_frame_analysis = controls['frame_analysis_var'].get()
                    SETTINGS.rtp_timeout_threshold = int(controls['rtp_timeout_entry'].get())
                    SETTINGS.pts_tolerance_ms = int(controls['pts_tolerance_entry'].get())
                    SETTINGS.frame_interval_tolerance = float(controls['frame_interval_tolerance_entry'].get())
                    SETTINGS.missing_frame_threshold = int(controls['missing_frame_threshold_entry'].get())
                    SETTINGS.packet_loss_threshold = float(controls['packet_loss_threshold_entry'].get())
                
                elif hasattr(tab_frame, 'system_controls'):
                    controls = tab_frame.system_controls
                    SETTINGS.enable_performance_limit = controls['performance_limit_var'].get()
                    SETTINGS.max_cpu_usage = int(controls['max_cpu_entry'].get())
                    SETTINGS.max_memory_usage = int(controls['max_memory_entry'].get())
                    SETTINGS.log_level = controls['log_level_combobox'].get()
            
            messagebox.showinfo("保存成功", "参数已保存并即时生效。")
            win.destroy()
            
        except ValueError as e:
            messagebox.showerror("输入错误", f"请输入有效的数字：{e}")
        except Exception as e:
            messagebox.showerror("错误", f"保存设置时发生错误：{e}")
            
    def reset_to_defaults(self, win):
        """重置为默认设置"""
        result = messagebox.askyesno("确认重置", "确认要重置为默认设置吗？这将会丢失当前所有修改。")
        if result:
            SETTINGS.reset_to_defaults()
            messagebox.showinfo("成功", "已重置为默认设置。请重新打开设置窗口查看更新后的值。")
            win.destroy()
    
    def save_settings(self, win, notebook):
        """保存设置"""
        try:
            # 保存基础设置
            for i in range(notebook.index('end')):
                tab_frame = notebook.nametowidget(notebook.tabs()[i])
                
                if hasattr(tab_frame, 'basic_controls'):
                    controls = tab_frame.basic_controls
                    SETTINGS.gui_refresh_interval = int(controls['gui_entry'].get())
                    SETTINGS.reconnect_wait_time = int(controls['reconnect_entry'].get())
                    SETTINGS.fps_smooth_window = int(controls['fps_smooth_entry'].get())
                    SETTINGS.sys_monitor_enabled = controls['sys_monitor_var'].get()
                
                elif hasattr(tab_frame, 'rtsp_controls'):
                    controls = tab_frame.rtsp_controls
                    SETTINGS.rtsp_timeout = int(controls['rtsp_timeout_entry'].get())
                    SETTINGS.rtsp_buffer_size = int(controls['buffer_size_entry'].get())
                    SETTINGS.rtsp_max_delay = int(controls['max_delay_entry'].get())
                    SETTINGS.rtsp_probe_size = int(controls['probe_size_entry'].get())
                    SETTINGS.rtsp_analyzeduration = int(controls['analyze_duration_entry'].get())
                
                elif hasattr(tab_frame, 'quality_controls'):
                    controls = tab_frame.quality_controls
                    SETTINGS.quality_level = controls['quality_level_combobox'].get()
                    SETTINGS.enable_real_packet_loss = controls['real_packet_loss_var'].get()
                    SETTINGS.enable_frame_analysis = controls['frame_analysis_var'].get()
                    SETTINGS.rtp_timeout_threshold = int(controls['rtp_timeout_entry'].get())
                    SETTINGS.pts_tolerance_ms = int(controls['pts_tolerance_entry'].get())
                    SETTINGS.frame_interval_tolerance = float(controls['frame_interval_tolerance_entry'].get())
                    SETTINGS.missing_frame_threshold = int(controls['missing_frame_threshold_entry'].get())
                    SETTINGS.packet_loss_threshold = float(controls['packet_loss_threshold_entry'].get())
                
                elif hasattr(tab_frame, 'system_controls'):
                    controls = tab_frame.system_controls
                    SETTINGS.enable_performance_limit = controls['performance_limit_var'].get()
                    SETTINGS.max_cpu_usage = int(controls['max_cpu_entry'].get())
                    SETTINGS.max_memory_usage = int(controls['max_memory_entry'].get())
                    SETTINGS.log_level = controls['log_level_combobox'].get()
            
            messagebox.showinfo("保存成功", "参数已保存并即时生效。")
            win.destroy()
            
        except ValueError as e:
            messagebox.showerror("输入错误", f"请输入有效的数字：{e}")
        except Exception as e:
            messagebox.showerror("错误", f"保存设置时发生错误：{e}")

    def export_report(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="导出报告"
        )
        if not filename:
            return
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"RTSP 压测报告 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")

                total_url_count = len(self.url_list_data)
                total_threads_count = len(self.monitor_threads)
                
                f.write(f"总监控地址数: {total_url_count}\n")
                f.write(f"总监控线程数: {total_threads_count}\n\n")

                f.write("### 各流监控统计\n")
                f.write("-" * 50 + "\n")
                
                all_status_info = []
                for child_iid in self.tree.get_children():
                    if child_iid.startswith("url_"):
                        # Aggregate data for URL parent items
                        url_data = self.url_list_data.get(child_iid)
                        if url_data:
                            aggregated = AGGREGATED_DATA.get(child_iid)
                            if aggregated:
                                total_duration = (time.time() - aggregated['start_time']) if aggregated.get('start_time') else 0
                                # 使用默认帧率作为备用
                                default_fps = 25.0
                                total_expected_frames = int(total_duration * default_fps * len(url_data['children']))
                                final_lost_rate = (aggregated.get('total_lost_frames', 0) / total_expected_frames * 100) if total_expected_frames > 0 else 0.0
                                qoe_scores = []
                                avg_qoe = 0.0
                                
                                url_status = self.tree.item(child_iid, 'values')
                                url_report_data = {
                                    'url': url_status[1],
                                    'status': url_status[2],
                                    'lost_rate': f"{final_lost_rate:.1f}",
                                    'reconnects': aggregated['total_reconnects'],
                                    'total_bytes': aggregated['total_bytes'],
                                    'total_frames': aggregated['total_frames']
                                }
                                all_status_info.append(url_report_data)
                            
                for item in all_status_info:
                    f.write(f"URL: {item['url']}\n")
                    f.write(f"  状态: {item['status']}\n")
                    f.write(f"  丢包率: {item['lost_rate']}%\n")
                    f.write(f"  总流量: {item['total_bytes'] / 1024 / 1024:.2f} MB\n")
                    f.write(f"  总重连次数: {item['reconnects']}\n")
                    f.write("-" * 50 + "\n")

                f.write("\n\n### 性能指标汇总\n")
                f.write("=" * 60 + "\n")
                f.write(f"CPU 使用率: {self.last_sys_info['cpu_percent']:.1f}%\n")
                f.write(f"内存使用率: {self.last_sys_info['mem_percent']:.1f}%\n")
                f.write(f"网络下载速率: {self.last_sys_info['net_recv_mbps']:.1f} Mbps\n")

                f.write("\n\n### 丢包率最高TOP 3\n")
                f.write("=" * 60 + "\n")
                all_lost_rates = []
                for item_id in AGGREGATED_DATA:
                    aggregated = AGGREGATED_DATA[item_id]
                    if 'start_time' in aggregated and aggregated['start_time']:
                        total_duration = time.time() - aggregated['start_time']
                        # 使用默认帧率作为备用
                        default_fps = 25.0
                        total_expected_frames = int(total_duration * default_fps * len(self.url_list_data[item_id]['children']))
                        lost_rate = (aggregated.get('total_lost_frames', 0) / total_expected_frames * 100) if total_expected_frames > 0 else 0.0
                        all_lost_rates.append({
                            'url': self.url_list_data[item_id]['url'],
                            'lost_rate': lost_rate
                        })

                top_3_lost = sorted(all_lost_rates, key=lambda x: x['lost_rate'], reverse=True)[:3]
                for i, item in enumerate(top_3_lost):
                    f.write(f"  {i+1}. {item['url']} - 丢包率: {item['lost_rate']:.1f}%\n")
                
            messagebox.showinfo("成功", "报表已导出。")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败：{e}")

    def download_logs(self):
        """将日志框的内容保存为文件"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
            title="保存日志"
        )
        if not filename:
            return
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.log_text.get('1.0', tk.END))
            messagebox.showinfo("成功", "日志已成功保存到文件。")
        except Exception as e:
            messagebox.showerror("错误", f"保存日志失败：{e}")


    def on_closing(self):
        global STOP_CHECK_ID, SYSTEM_MONITOR_THREAD
        if self.monitor_threads:
            STOP_EVENT.set()
            if STOP_CHECK_ID is not None:
                self.after_cancel(STOP_CHECK_ID)
                STOP_CHECK_ID = None
            
            for t in self.monitor_threads:
                if t.is_alive():
                    t.join(timeout=1.0)
                    if t.is_alive():
                        logging.warning(f"线程 {t.name} 未能在超时时间内退出。")
        
        if SYSTEM_MONITOR_THREAD and SYSTEM_MONITOR_THREAD.is_alive():
            SYSTEM_MONITOR_THREAD.stop()
            SYSTEM_MONITOR_THREAD.join(timeout=1.0)
            if SYSTEM_MONITOR_THREAD.is_alive():
                logging.warning("系统监控线程未能在超时时间内退出。")
            SYSTEM_MONITOR_THREAD = None

        self.master.destroy()

    def start_monitoring(self):
        if self.monitor_threads:
            messagebox.showinfo("提示", "监控已在运行中。")
            return
        
        if not self.url_list_data:
            messagebox.showinfo("提示", "请先添加要监控的RTSP地址！")
            return

        # 清空旧状态，确保全新开始
        STOP_EVENT.clear()
        self.monitor_threads.clear()
        STATUS_QUEUES.clear()
        AGGREGATED_DATA.clear()
        self.last_counters.clear()
        THREAD_NAME_MAP.clear()
        # 清空最终统计数据
        self.final_stats.clear()
        self.final_parent_stats.clear()
        
        # 记录日志
        logging.info(f"开始启动监控，共{len(self.url_list_data)}个URL，每个URL{SETTINGS.threads_per_url}个线程")
        
        # 清空 Treeview 中的所有子行，避免旧数据干扰
        for item_id in self.tree.get_children():
            children = self.tree.get_children(item_id)
            for child in children:
                self.tree.delete(child)

        # 更新线程数设置
        try:
            threads_count = int(self.threads_per_url_combobox.get())
            if threads_count < 1:
                threads_count = 1
                messagebox.showwarning("警告", "线程数不能小于1，已重置为1。")
            SETTINGS.threads_per_url = threads_count
        except ValueError:
            messagebox.showerror("错误", "线程数输入无效！")
            return

        for item_id, url_data in self.url_list_data.items():
            parent_url = url_data['url']
            parent_url_id = url_data['id']
            protocol = self.protocol_combobox.get()
            
            # 创建 RTSP 监控线程和其 Treeview 子项
            for i in range(SETTINGS.threads_per_url):
                thread_id_str = f"{parent_url_id}-{i+1}"
                
                monitor_thread = RTSPStreamMonitor(
                    url=parent_url,
                    thread_id=thread_id_str,
                    parent_item_id=item_id,
                    parent_url_id=parent_url_id,
                    thread_idx=i,
                    total_threads=SETTINGS.threads_per_url,
                    protocol=protocol
                )
                self.monitor_threads.append(monitor_thread)
                url_data['children'].append(thread_id_str)
                
                log_name = f"线程-{parent_url_id:02d}-{i+1:02d}"
                THREAD_NAME_MAP[thread_id_str] = log_name
                
                # 在此处插入子行
                self.tree.insert(item_id, 'end', iid=f"thread_{thread_id_str}", values=(
                    thread_id_str, 
                    log_name, 
                    '未启动', 
                    '0.0',      # FPS
                    '0',        # 理论帧
                    '0',        # 已收帧
                    '0',        # 丢失帧
                    '0.0%',     # 丢包率
                    '0.00 MB',  # 流量
                    '0',        # 重连
                    '0.0s'      # 延迟
                ), tags=('thread_row',))
                monitor_thread.start()
                logging.info(f"已启动监控线程: {log_name} (ID: {thread_id_str})。URL: {parent_url}")
            
            self.tree.item(item_id, open=True) # 默认展开父级节点

        self.start_button['state'] = tk.DISABLED
        self.stop_button['state'] = tk.NORMAL
        self.status_label['text'] = "正在运行..."
        self.status_label['foreground'] = "green"
        
        # 立即触发一次状态更新，确保UI及时响应
        self.after(100, self.update_statuses)

    def stop_monitoring(self):
        # 1. 发送停止信号
        STOP_EVENT.set()
        self.start_button['state'] = tk.DISABLED
        self.stop_button['state'] = tk.DISABLED
        self.status_label['text'] = "正在停止..."
        self.status_label['foreground'] = "orange"
        
        # 强制刷新界面，显示停止状态
        self.update_idletasks()
        
        # 2. 在停止前保存最后一次的统计数据
        self.final_stats = {}
        for thread_id, status_info in self.last_counters.items():
            self.final_stats[thread_id] = status_info.copy()
        
        # 保存父行的最后统计数据
        self.final_parent_stats = {}
        for item_id in self.tree.get_children():
            if item_id.startswith("url_"):
                parent_values = self.tree.item(item_id, 'values')
                self.final_parent_stats[item_id] = {
                    'status': "已停止",
                    'fps': parent_values[3] if len(parent_values) > 3 else "0.0",
                    'expected_frames': parent_values[4] if len(parent_values) > 4 else "0",
                    'received_frames': parent_values[5] if len(parent_values) > 5 else "0",
                    'lost_frames': parent_values[6] if len(parent_values) > 6 else "0",
                    'lost_rate': parent_values[7] if len(parent_values) > 7 else "0.0%",
                    'total_bytes': parent_values[8] if len(parent_values) > 8 else "0.00 MB",
                    'reconnects': parent_values[9] if len(parent_values) > 9 else "0",
                    'latency': parent_values[10] if len(parent_values) > 10 else "0.0s"
                }
        
        # 3. 异步等待线程退出，避免阻塞界面
        def stop_threads_async():
            for t in self.monitor_threads:
                if t.is_alive():
                    # 使用更短的超时时间，避免长时间阻塞
                    t.join(timeout=0.5)
                    if t.is_alive():
                        logging.warning(f"线程 {t.name} 未能在超时时间内退出，将强制停止。")
        
        # 在单独线程中停止，避免阻塞主线程
        stop_thread = threading.Thread(target=stop_threads_async, daemon=True)
        stop_thread.start()

        # 4. 立即清理线程列表和状态
        self.monitor_threads = []
        STATUS_QUEUES.clear()
        # 注意：不清空 self.last_counters，保留最后的数据
        
        # 清除 url_list_data 中所有子项信息
        for item_id in self.tree.get_children():
            if item_id in self.url_list_data:
                self.url_list_data[item_id]['children'].clear()
        
        # 5. 更新UI显示最后一次的统计数据
        self.update_final_display()
        
        # 6. 重置UI状态
        self.status_label['text'] = "已停止"
        self.status_label['foreground'] = "black"
        self.start_button['state'] = tk.NORMAL
        self.stop_button['state'] = tk.DISABLED
        
    def update_final_display(self):
        """更新停止后的最终显示数据"""
        # 更新所有子线程的显示
        for thread_id, status_info in self.final_stats.items():
            child_iid = f"thread_{thread_id}"
            if self.tree.exists(child_iid):
                current_fps = status_info.get('current_fps', 0.0)
                received_frames = status_info.get('received_frames', 0)
                lost_frames = status_info.get('lost_frames', 0)
                total_bytes_thread = status_info.get('total_bytes', 0)
                reconnects = status_info.get('reconnect_count', 0)
                connect_latency = status_info.get('connect_latency', 0.0)
                expected_frames = received_frames + lost_frames
                lost_rate = (lost_frames / expected_frames * 100) if expected_frames > 0 else 0.0
                
                # 状态显示为已停止
                final_status = "已停止"
                
                # 更新子项的显示
                self.tree.item(child_iid, values=(
                    thread_id,
                    THREAD_NAME_MAP.get(thread_id, 'N/A'),
                    final_status,
                    f"{current_fps:.1f}",
                    expected_frames,
                    received_frames,
                    lost_frames,
                    f"{lost_rate:.1f}%",
                    f"{total_bytes_thread / 1024 / 1024:.2f} MB",
                    reconnects,
                    f"{connect_latency:.1f}s"
                ))
        
        # 更新父行的显示
        for item_id, parent_stats in self.final_parent_stats.items():
            if self.tree.exists(item_id):
                self.tree.item(item_id, values=(
                    self.url_list_data[item_id]['id'],
                    self.url_list_data[item_id]['url'].replace('rtsp://', ''),
                    parent_stats['status'],  # 已停止
                    parent_stats['fps'],
                    parent_stats['expected_frames'],
                    parent_stats['received_frames'],
                    parent_stats['lost_frames'],
                    parent_stats['lost_rate'],
                    parent_stats['total_bytes'],
                    parent_stats['reconnects'],
                    parent_stats['latency']
                ))
        
    def update_statuses(self):
        has_active_threads = False
        
        # 调试信息：检查线程和队列状态
        total_monitor_threads = len(self.monitor_threads)
        total_queues = len(STATUS_QUEUES)
        
        if total_monitor_threads > 0:
            # 只在有线程时输出调试信息
            pass  # 可以在这里加入 logging.debug 信息
        
        for item_id in self.tree.get_children():
            if item_id.startswith("url_"):
                # 获取该 URL 下的所有子线程
                url_data = self.url_list_data.get(item_id, {})
                thread_ids = url_data.get('children', [])
                
                # 检查是否有任何线程仍在运行
                thread_running = False
                for t in self.monitor_threads:
                    if t.thread_id in thread_ids and t.is_alive():
                        thread_running = True
                        break
                
                if thread_running:
                    has_active_threads = True

                # Update child thread status
                all_reconnects = []
                all_frames = []
                all_bytes = []
                all_expected_frames = []
                all_lost_frames = []
                all_latencies = []
                all_fps = []
                
                for thread_id in url_data.get('children', []):
                    child_iid = f"thread_{thread_id}"
                    
                    # 关键修复: 在更新前检查Treeview子项是否存在
                    if not self.tree.exists(child_iid):
                        continue

                    # 检查并获取最新的状态信息
                    if thread_id in STATUS_QUEUES:
                        while not STATUS_QUEUES[thread_id].empty():
                            status_info = STATUS_QUEUES[thread_id].get()
                            self.last_counters[thread_id] = status_info
                    
                    # 获取状态信息，如果没有数据则检查线程状态
                    status_info = self.last_counters.get(thread_id, {})
                    
                    # 如果没有状态信息但线程正在运行，显示连接中状态
                    if not status_info:
                        thread_alive = any(t.thread_id == thread_id and t.is_alive() for t in self.monitor_threads)
                        if thread_alive:
                            status_info = {
                                'status': '连接中...',
                                'current_fps': 0.0,
                                'received_frames': 0,
                                'total_bytes': 0,
                                'reconnect_count': 0,
                                'connect_latency': 0.0
                            }
                        
                    status_info = self.last_counters.get(thread_id, status_info)
                    
                    current_status = status_info.get('status', '未启动')
                    current_fps = status_info.get('current_fps', 0.0)
                    received_frames = status_info.get('received_frames', 0)
                    lost_frames = status_info.get('lost_frames', 0)
                    total_bytes_thread = status_info.get('total_bytes', 0)
                    reconnects = status_info.get('reconnect_count', 0)
                    connect_latency = status_info.get('connect_latency', 0.0)
                    expected_frames = received_frames + lost_frames
                    
                    lost_rate = (lost_frames / expected_frames * 100) if expected_frames > 0 else 0.0

                    # 更新子项的显示
                    self.tree.item(child_iid, values=(
                        thread_id,
                        THREAD_NAME_MAP.get(thread_id, 'N/A'),
                        current_status,
                        f"{int(current_fps)}",
                        expected_frames,
                        received_frames,
                        lost_frames,
                        f"{lost_rate:.1f}%",
                        f"{total_bytes_thread / 1024 / 1024:.2f} MB",
                        reconnects,
                        f"{connect_latency:.1f}s"
                    ))
                    
                    # 汇总数据
                    all_reconnects.append(reconnects)
                    all_frames.append(received_frames)
                    all_bytes.append(total_bytes_thread)
                    all_expected_frames.append(expected_frames)
                    all_lost_frames.append(lost_frames)
                    
                    # 收集FPS数据
                    if current_fps > 0:
                        all_fps.append(current_fps)
                    
                    if connect_latency > 0:
                        all_latencies.append(connect_latency)

                # Update Parent URL status - 计算平均值
                num_threads = len(url_data.get('children', []))
                
                # 检查是否已停止且有最终数据
                if hasattr(self, 'final_parent_stats') and item_id in self.final_parent_stats and num_threads == 0:
                    # 使用最终保存的数据
                    parent_stats = self.final_parent_stats[item_id]
                    self.tree.item(item_id, values=(
                        self.url_list_data[item_id]['id'],
                        self.url_list_data[item_id]['url'].replace('rtsp://', ''),
                        parent_stats['status'],  # 已停止
                        parent_stats['fps'],
                        parent_stats['expected_frames'],
                        parent_stats['received_frames'],
                        parent_stats['lost_frames'],
                        parent_stats['lost_rate'],
                        parent_stats['total_bytes'],
                        parent_stats['reconnects'],
                        parent_stats['latency']
                    ))
                    continue  # 跳过后续计算和更新
                
                # 使用更安全的计算方法，避免除零错误
                avg_reconnects = sum(all_reconnects) / max(1, num_threads)
                avg_frames = sum(all_frames) / max(1, num_threads)
                avg_bytes = sum(all_bytes) / max(1, num_threads)
                avg_expected_frames = sum(all_expected_frames) / max(1, num_threads)
                avg_lost_frames = sum(all_lost_frames) / max(1, num_threads)
                
                avg_fps = sum(all_fps) / len(all_fps) if all_fps else 0.0
                avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
                lost_rate = (avg_lost_frames / avg_expected_frames * 100) if avg_expected_frames > 0 else 0.0
                
                # 状态判断逻辑
                if num_threads == 0:
                    status = "未启动"
                elif avg_frames == 0 and avg_reconnects > 0:
                    status = "重连中..."
                elif avg_frames == 0 and avg_reconnects == 0:
                    # 检查是否有线程正在运行（可能正在连接）
                    any_thread_alive = any(t.thread_id in thread_ids and t.is_alive() for t in self.monitor_threads)
                    if any_thread_alive:
                        status = "连接中..."
                    else:
                        status = "未启动"
                else:
                    status = "运行中"

                self.tree.item(item_id, values=(
                    self.url_list_data[item_id]['id'],
                    self.url_list_data[item_id]['url'].replace('rtsp://', ''),
                    status,
                    f"{int(avg_fps)}",
                    int(avg_expected_frames),
                    int(avg_frames),
                    int(avg_lost_frames),
                    f"{lost_rate:.1f}%",
                    f"{avg_bytes / 1024 / 1024:.2f} MB",
                    int(avg_reconnects),
                    f"{avg_latency:.1f}s"
                ))
                
                # Update aggregated data (for reports)
                if not 'start_time' in AGGREGATED_DATA[item_id] or AGGREGATED_DATA[item_id]['start_time'] is None:
                    AGGREGATED_DATA[item_id]['start_time'] = time.time()
                AGGREGATED_DATA[item_id]['total_reconnects'] = sum(all_reconnects)
                AGGREGATED_DATA[item_id]['total_frames'] = sum(all_frames)
                AGGREGATED_DATA[item_id]['total_bytes'] = sum(all_bytes)
                AGGREGATED_DATA[item_id]['total_expected_frames'] = sum(all_expected_frames)
                AGGREGATED_DATA[item_id]['total_lost_frames'] = sum(all_lost_frames)
                
                # 确保列表类型正确
                if not isinstance(AGGREGATED_DATA[item_id]['fps_list'], deque):
                    AGGREGATED_DATA[item_id]['fps_list'] = deque(maxlen=SETTINGS.fps_smooth_window)
                if not isinstance(AGGREGATED_DATA[item_id]['latency_list'], deque):
                    AGGREGATED_DATA[item_id]['latency_list'] = deque(maxlen=100)
                
                # 安全扩展数据
                for fps in all_fps:
                    AGGREGATED_DATA[item_id]['fps_list'].append(fps)
                for latency in all_latencies:
                    AGGREGATED_DATA[item_id]['latency_list'].append(latency)
                
        # Update system info
        if SYSTEM_MONITOR_ID in STATUS_QUEUES:
            while not STATUS_QUEUES[SYSTEM_MONITOR_ID].empty():
                self.last_sys_info = STATUS_QUEUES[SYSTEM_MONITOR_ID].get()
        
        # 始终显示系统信息，即使队列为空也显示最后的数据
        self.cpu_label['text'] = f"CPU: {self.last_sys_info['cpu_percent']:.1f}%"
        self.mem_label['text'] = f"内存: {self.last_sys_info['mem_percent']:.1f}%"
        self.net_label['text'] = f"网络: ↓{self.last_sys_info['net_recv_mbps']:.1f}Mbps"

        # 动态调整更新间隔，多线程时降低更新频率
        active_thread_count = total_monitor_threads
        if active_thread_count > 10:
            update_interval = SETTINGS.gui_refresh_interval * 2  # 多线程时降低频率
        elif active_thread_count > 5:
            update_interval = int(SETTINGS.gui_refresh_interval * 1.5)
        else:
            update_interval = SETTINGS.gui_refresh_interval
        
        # 检查是否所有线程都已停止 - 只有在明确停止且有最终数据时才停止更新
        if not has_active_threads and hasattr(self, 'final_stats') and self.final_stats and not self.monitor_threads:
            # 如果已停止且有最终统计数据，使用最终数据显示
            self.update_final_display()
            return

        self.after(update_interval, self.update_statuses)

    def update_logs(self):
        while LOG_QUEUE:
            level, message = LOG_QUEUE.popleft()
            self.log_text.configure(state='normal')
            if level == logging.ERROR:
                self.log_text.tag_config('error', foreground='red')
                self.log_text.insert(tk.END, message + "\n", 'error')
            elif level == logging.WARNING:
                self.log_text.tag_config('warning', foreground='orange')
                self.log_text.insert(tk.END, message + "\n", 'warning')
            else:
                self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state='disabled')
        self.after(SETTINGS.gui_refresh_interval, self.update_logs)

if __name__ == '__main__':
    root = tk.Tk()
    root.title("RTSP 流媒体压测与监控工具 V1.3 - 2025.08.23")
    root.geometry("900x600")
    
    # 获取屏幕尺寸以计算窗口位置
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = 1000
    window_height = 800
    x_pos = (screen_width - window_width) // 2
    y_pos = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")

    app = StressTestFrame(root)
    app.pack(fill='both', expand=True)

    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()