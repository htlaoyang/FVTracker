# 标准库
import sys 
import os
import re
import json
import shutil

import datetime
import time
import threading

from contextlib import contextmanager
from typing import List, Optional, Tuple

# 第三方库
import configparser
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests
from bs4 import BeautifulSoup
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.font_manager import FontProperties
import sqlite3
from packaging import version
from utils.notif_send import NotificationSender
from utils.news_fetcher import get_news_list, play_audio_from_url

# GUI 相关
import tkinter as tk
import tkinter.font as tkfont  
from tkinter import filedialog, messagebox, ttk


# 本地工具模块
from utils.stock_index_fetcher import StockIndexFetcher
from utils.sys_chinese_font import get_best_chinese_font
from config import CONFIG_FILE, DB_FILE
from utils.db.database import db_connection, init_database, secure_reset_database
from module.fund_manager import FundManager  # 新增：导入独立基金管理类
from utils.db.db_upgrade_manager import DBUpgradeManager
from utils.logger import write_log

# 配置中文字体
AVAILABLE_CHINESE_FONT = get_best_chinese_font()
plt.rcParams["font.family"] = [AVAILABLE_CHINESE_FONT]
plt.rcParams["axes.unicode_minus"] = False


class FVTracker:
    def __init__(self, root):
        # 软件版本配置
        self.software_version = "V1.2.2   by htlaoyang"
        self.version_update_log = """
V1.2.2 更新内容：
1. 增加基金历史估值下载更新，只有每天的估值，无每天详细估值;【增加功能】
2. 优化加仓策略分析;【优化功能】
3. 增加月季度分析;
V1.2.1 更新内容：
  1. 增加托盘功能
  2. 增加钛媒体新闻快讯获取及自动播报功能
  3. 基金历史估值查询默认为5年内的数据
V1.2.0 更新内容：
  1. 增加计算工具
  2. 增加涨跌浮邮件提醒功能
V1.1.9 更新内容：
  1. 界面字体及位置调整		
V1.1.8 更新内容：
  1. 基金监控列表增加汇总盈亏
  2. 修正导出后导入报错
  3. 删除基金，基金监控列表同步刷新
  4. 修正重置数据库后，没有备份库及初始库 		
V1.1.7 更新内容：
  1. 增加版本升级控制
  2. 增加基金涨跌监控提醒
V1.1.6 更新内容：
  1. 代码功能拆分
V1.1.5 更新内容：
  2. 增加基金估值历史查询功能
  2. 修正关闭软件报错；
V1.1.4 更新内容：
  1. 修复非交易时段强制刷新无效问题，支持收盘后获取当日最终估值
  2. 新增收盘数据标记，确保15:00等关键时间点数据留存
  3. 优化历史明细加载逻辑，非交易时段正常显示当日所有数据
  4. 增强状态显示稳定性，修复刷新状态不更新问题
  5. 优化时间计算逻辑，适配非交易时段数据存储
V1.1.3 更新内容：
1. 修复基金数据刷新时出现的基金数据混乱问题
2. 强化基金代码与数据的关联，确保数据准确性
V1.1.2 更新内容：
3. 优化多线程数据处理逻辑，避免数据竞争
4. 改进时间点生成算法，确保全天9:30-15:00都能按设定间隔刷新
V1.1.1 更新内容：
1. 增加定时刷新间隔
2. 增加基金数据的导入，导出功能
        """
		
        self.log_prefix = "fund_monitor"  # 统一前缀
        self.log_dir = "logs"            # 可配置
		
        self.default_headers = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
        self._now_func = None
        self.summary_item_id = "TOTAL_SUMMARY_ROW" 
        
        # === 快讯系统）===
        self.news_display_queue = []      # 待显示/播报的快讯列表 [item1, item2, ...]

        self.current_display_index = 0    # 当前显示的索引（用于轮播）
        self.news_paused = False          # 鼠标悬停暂停
        self.news_cycle_job = None        # 轮播定时器
        self.news_fetch_job = None        # 拉取定时器
        
        self.last_end_ts = int(time.time()) - 300  # 首次拉取：5分钟前
        
		
        # 常用指数列表
        self.indices = [
            {"code": "000001", "name": "上证指数", "value": 0, "change": 0, "change_rate": 0},
            {"code": "399001", "name": "深证成指", "value": 0, "change": 0, "change_rate": 0},
            {"code": "399006", "name": "创业板指", "value": 0, "change": 0, "change_rate": 0},
            {"code": "000016", "name": "上证50", "value": 0, "change": 0, "change_rate": 0},
            {"code": "000300", "name": "沪深300", "value": 0, "change": 0, "change_rate": 0},
            {"code": "000905", "name": "中证500", "value": 0, "change": 0, "change_rate": 0},
        ]

        # 创建指数获取器实例
        self.index_fetcher = StockIndexFetcher()
        
        # 状态与锁初始化
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        self.refresh_lock = threading.Lock()  # 刷新操作锁
        self.is_refreshing_indices = False    # 指数刷新状态
		
		# 记录上一次排序的列和顺序
        self.last_sorted_col = None
        self.last_sorted_reverse = False
        
        # 数据存储初始化
        init_database()
        self.root = root
        # 初始化主窗口标题（含版本号）
        root.title(f"FVTracker-基金估值监控工具 - {self.software_version}")
        # 从配置文件加载窗口设置
        self.load_window_settings()
		
        self.notif_sender = NotificationSender()  # 单例 邮件发送
        
        # 基金数据存储
        self.funds = []  # 存储所有基金信息
        self.selected_fund = None  # 当前选中的基金
        self.is_monitoring = False  # 是否正在监控
        self.first_refresh_done = False  # 首次刷新是否完成
        self.current_display_date = datetime.date.today().strftime('%Y-%m-%d') # 默认显示当天数据
        
		
        # 新增：缓存当前显示的数据，用于比对差异
        self.current_display_data = {}  # 格式: {fund_code: {column_index: value, ...}}
        self.code_to_item_id = {}  # 基金代码与Treeview行ID的映射
		
        # 实例化FundManager 回调注册
        self.fund_manager = FundManager(
            root=self.root,
            status_var=self.status_var,
            refresh_funds_cb=self._refresh_funds_callback,
            update_main_list_cb=self._update_main_list_callback
        )


        # 加载基金数据（通过FundManager）
        self._refresh_funds_callback()  # 加载数据
        self.load_settings()
        self.initialize_main_table_if_empty()  # 初始化主表空数据

        # 创建界面
        self.create_widgets()
        self._now_func = None  # 用于测试时替换时间

        self.root.after(100, self.start_core_threads_async)
        self.root.after(200, lambda: self.center_window(1200, 800))
        #self.root.after(300, self.force_center_window)
        # 启动服务
        self._start_auto_fetch()           # 启动自动拉取
    def get_now(self) -> datetime.datetime:
        """获取当前时间，支持测试时 mock"""
        return self._now_func() if self._now_func else datetime.datetime.now()

    def set_now_func(self, func):
        """设置当前时间函数（用于测试）"""
        self._now_func = func
		
    def _refresh_funds_callback(self):
        self.funds = self.fund_manager.load_funds_data()
    def center_window(self, default_width=1600, default_height=900):
        self.root.update_idletasks()
    
        # Tkinter 获取的“逻辑”屏幕尺寸（受 DPI 缩放影响）
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
    
        # 限制最大窗口为屏幕的 90%
        max_width = int(screen_width * 0.9)
        max_height = int(screen_height * 0.9)
    
        window_width = min(default_width, max_width)
        window_height = min(default_height, max_height)
    
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
    
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.deiconify()
    
        #print(f"窗口已居中: {window_width}x{window_height}+{x}+{y}")
        #print(f"Tkinter 屏幕尺寸: {screen_width}x{screen_height}")
        #print(f"真实屏幕尺寸: 2560x1600 (您提供的)")

    def _update_main_list_callback(self):
        self.update_fund_list()
		
    def initialize_main_table_if_empty(self):
        """初始化主表空数据（确保每日有基础记录）"""
        today = datetime.date.today().strftime('%Y-%m-%d')
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
        try:
            with db_connection() as conn:
                for fund in self.funds:
                    fund_code = fund["code"]
                    
                    # 检查今日是否已有记录
                    result = conn.execute(
                        'SELECT id FROM fund_estimate_main WHERE fund_code = ? AND trade_date = ?',
                        (fund_code, today)
                    ).fetchone()
                    
                    if not result:  # 今日无记录
                        # 获取最大 ID（可选：如果不用 AUTOINCREMENT）
                        max_id_result = conn.execute(
                            'SELECT MAX(id) FROM fund_estimate_main WHERE fund_code = ?',
                            (fund_code,)
                        ).fetchone()
                        max_id = max_id_result[0]
                        new_id = 1 if max_id is None else max_id + 1
    
                        # 处理 rise_alert
                        rise_alert = fund.get("rise_alert")
                        if rise_alert is None or rise_alert == "":
                            rise_alert = 0.0
                        else:
                            rise_alert = float(rise_alert)
    
                        # 处理 fall_alert：转为负数
                        fall_alert = fund.get("fall_alert")
                        if fall_alert is None or fall_alert == "":
                            fall_alert = 0.0
                        else:
                            fall_alert = -abs(float(fall_alert))
    
                        # 插入初始记录
                        conn.execute('''
                            INSERT INTO fund_estimate_main 
                            (id, fund_code, fund_name, trade_date, trade_time,
                             unit_net_value, realtime_estimate, change_rate,
                             is_hold, hold_cost, hold_shares, realtime_profit,
                             rise_alert, fall_alert)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            new_id, fund_code, fund["name"], today, now,
                            None, None, None,
                            1 if fund["is_hold"] else 0, fund["cost"], fund["shares"], None,
                            rise_alert, fall_alert
                        ))
    
                        #print(f"为基金 {fund_code} 初始化主表数据，上涨提醒={rise_alert}%，下跌提醒={fall_alert}%")
    
        except Exception as e:
            #print(f"[FundManager] 初始化主表失败: {str(e)}")
            self.status_var.set(f"初始化主表失败: {str(e)}")   
    def load_window_settings(self):

        # 默认大小（也应限制）
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1600, screen_width)
        height = min(900, screen_height - 100)
        self.root.geometry(f"{width}x{height}")
        print(f"使用默认窗口大小: {width}x{height}")

    def save_window_settings(self):
        """保存窗口配置"""
        config = configparser.ConfigParser()
        try:
            if os.path.exists(CONFIG_FILE):
                config.read(CONFIG_FILE, encoding='utf-8')
            if 'Settings' not in config:
                config.add_section('Settings')
            
            # 获取当前窗口参数
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            
            config['Settings']['window_x'] = str(x)
            config['Settings']['window_y'] = str(y)
            config['Settings']['window_width'] = str(width)
            config['Settings']['window_height'] = str(height)
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                config.write(f)
        except Exception as e:
            print(f"保存窗口设置错误: {e}")

    def create_widgets(self):
        # 创建主标签页控件
        self.tab_control = ttk.Notebook(self.root)
        
        # 创建主界面标签页
        self.main_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.main_tab, text="基金监控")
        
        # 创建添加基金标签页
        self.add_fund_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.add_fund_tab, text="基金管理")
        
        # 创建设置标签页
        self.settings_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.settings_tab, text="设置")
        self.tab_control.pack(expand=1, fill="both")
        
        # 初始化各标签页
        self.init_main_tab()
        self.fund_manager.init_add_fund_tab(self.add_fund_tab)
        self.init_settings_tab()
		
    def init_main_tab(self):
        """初始化基金监控主界面（优化布局+手动刷新按钮）"""
        self.setup_styles()
        
        # 主容器
        main_frame = ttk.Frame(self.main_tab, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_tab.columnconfigure(0, weight=1)
        self.main_tab.rowconfigure(0, weight=1)
    
        # --- 1. 顶部状态条 ---
        status_bar = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            style="Status.TLabel"
        )
        status_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        main_frame.rowconfigure(0, weight=0)  # 固定高度
    
        # --- 2. 常用指数区域 ---
        self.indices_frame = ttk.Frame(main_frame, padding="5 0 5 0")
        self.indices_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        main_frame.rowconfigure(1, weight=0)  # 固定高度
        self.indices_frame.configure(height=50)
        self.indices_frame.pack_propagate(False)
    
        indices_canvas = tk.Canvas(self.indices_frame, highlightthickness=0, bg="#f8f9fa")
        indices_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        indices_container = ttk.Frame(indices_canvas)
        indices_window = indices_canvas.create_window((0, 0), window=indices_container, anchor="nw")
    
        # 生成指数标签
        self.indices_labels = []
        for i, index in enumerate(self.indices):
            col = i * 3
            # 指数名称
            name_label = ttk.Label(
                indices_container,
                text=index["name"],
                width=10,
                style="IndexName.TLabel"
            )
            name_label.grid(row=0, column=col, padx=15, pady=5, sticky=tk.W)
    
            # 指数值
            value_label = ttk.Label(
                indices_container,
                text=f"{index['value']:.2f}",
                width=10,
                style="IndexValue.TLabel"
            )
            value_label.grid(row=0, column=col + 1, padx=5, pady=5, sticky=tk.E)
    
            # 涨跌幅（带颜色标识）
            change_label = ttk.Label(
                indices_container,
                text=f"{index['change_rate']:.2f}%",
                width=8,
                style="IndexUp.TLabel" if index["change_rate"] > 0 else
                      "IndexDown.TLabel" if index["change_rate"] < 0 else
                      "IndexFlat.TLabel"
            )
            change_label.grid(row=0, column=col + 2, padx=5, pady=5, sticky=tk.E)
    
            self.indices_labels.append((name_label, value_label, change_label))
    
        # 动态更新Canvas宽度
        def update_canvas_width(event):
            indices_canvas.itemconfig(indices_window, width=indices_canvas.winfo_width())
    
        indices_canvas.bind("<Configure>", update_canvas_width)
        indices_container.bind("<Configure>", lambda e: indices_canvas.configure(scrollregion=indices_canvas.bbox("all")))
    
        # --- 3. 左右分栏容器（60%/40%）---
        container_frame = ttk.Frame(main_frame)
        container_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
        main_frame.rowconfigure(2, weight=1)  # 关键：让中间区域伸展
        main_frame.columnconfigure(0, weight=1)
    
        # 配置左右列权重：60% / 40%
        container_frame.columnconfigure(0, weight=60)
        container_frame.columnconfigure(1, weight=40)
        container_frame.rowconfigure(0, weight=1)
    
        # 左侧基金列表区域
        left_frame = ttk.Frame(container_frame, style="Card.TFrame")  #
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=0)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=0)  # header 固定
        left_frame.rowconfigure(1, weight=0)  # 留空
        left_frame.rowconfigure(2, weight=1)  # fund_list_frame 占满剩余空间
    
        # 右侧内容区域（40%）
        right_frame = ttk.Frame(container_frame, style="Card.TFrame")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 0), pady=0)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
    
        # --- 左侧：基金列表标题和按钮 ---
        left_header = ttk.Frame(left_frame)
        left_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        left_header.columnconfigure(0, weight=1)
    
        ttk.Label(left_header, text="监控基金列表", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
    
        # 操作按钮（右对齐）
        btn_container = ttk.Frame(left_header)
        btn_container.grid(row=0, column=1, sticky="e")
        ttk.Button(btn_container, text="手动刷新", command=self.manual_refresh).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_container, text="查看历史", command=self.open_history_viewer).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_container, text="策略分析", command=self.open_strategy_analyzer_viewer).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_container, text="计算器"  , command=self.open_fund_calculator).pack(side=tk.LEFT, padx=5)
        # --- 基金列表 ---
        self.fund_list_frame = ttk.Frame(left_frame)
        self.fund_list_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        self.fund_list_frame.columnconfigure(0, weight=1)
        self.fund_list_frame.rowconfigure(0, weight=1)
    
        columns = (
            "hold", "code", "name", "unit_net_value", "realtime_estimate",
            "change_rate", "hold_cost", "hold_shares", "realtime_profit",
            "rise_alert", "fall_alert"
        )
        self.fund_tree = ttk.Treeview(
            self.fund_list_frame,
            columns=columns,
            show="headings",
            style="FundTree.Treeview"
        )
    
        # 设置列标题
        self.fund_tree.heading("hold", text="持有")
        self.fund_tree.heading("code", text="基金代码")
        self.fund_tree.heading("name", text="基金名称")
        self.fund_tree.heading("unit_net_value", text="单位净值(昨)")
        self.fund_tree.heading("realtime_estimate", text="实时估值(今)")
        self.fund_tree.heading("change_rate", text="涨跌幅(%)")
        self.fund_tree.heading("hold_cost", text="持有成本")
        self.fund_tree.heading("hold_shares", text="持有份额")
        self.fund_tree.heading("realtime_profit", text="当日盈亏")
        self.fund_tree.heading("rise_alert", text="上涨提醒(%)")
        self.fund_tree.heading("fall_alert", text="下跌提醒(%)")
    
        # 设置列宽
        self.fund_tree.column("hold", width=60, anchor="center")
        self.fund_tree.column("code", width=80)
        self.fund_tree.column("name", width=180)
        self.fund_tree.column("unit_net_value", width=140, anchor="e")
        self.fund_tree.column("realtime_estimate", width=140, anchor="e")
        self.fund_tree.column("change_rate", width=120, anchor="e")
        self.fund_tree.column("hold_cost", width=140, anchor="e")
        self.fund_tree.column("hold_shares", width=140, anchor="e")
        self.fund_tree.column("realtime_profit", width=140, anchor="e")
        self.fund_tree.column("rise_alert", width=140, anchor="center")
        self.fund_tree.column("fall_alert", width=140, anchor="center")
		
        self.fund_tree.heading("change_rate", command=lambda: self.sort_fund_list("change_rate", False))
        self.fund_tree.heading("realtime_profit", command=lambda: self.sort_fund_list("realtime_profit", False))
        self.fund_tree.heading("hold_shares", command=lambda: self.sort_fund_list("hold_shares", False))
    
        # 滚动条
        tree_vscroll = ttk.Scrollbar(self.fund_list_frame, orient="vertical", command=self.fund_tree.yview)
        self.fund_tree.configure(yscrollcommand=tree_vscroll.set)
    
        tree_hscroll = ttk.Scrollbar(self.fund_list_frame, orient="horizontal", command=self.fund_tree.xview)
        self.fund_tree.configure(xscrollcommand=tree_hscroll.set)
    
        # 使用 grid 布局
        self.fund_tree.grid(row=0, column=0, sticky="nsew")
        tree_vscroll.grid(row=0, column=1, sticky="ns")
        tree_hscroll.grid(row=1, column=0, sticky="ew")
    
        # 配置权重
        self.fund_list_frame.columnconfigure(0, weight=1)
        self.fund_list_frame.rowconfigure(0, weight=1)
    
        # 绑定选中事件
        self.fund_tree.bind("<<TreeviewSelect>>", self.on_fund_select)
    
        # --- 右侧内容容器：使用 grid 替代 pack ---
        right_content_frame = ttk.Frame(right_frame)
        right_content_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        right_content_frame.columnconfigure(0, weight=1)
        # 行权重分配
        right_content_frame.rowconfigure(0, weight=0)  # 基金信息标题
        right_content_frame.rowconfigure(1, weight=0)  # info_panel
        right_content_frame.rowconfigure(2, weight=0)  # 估值历史标题
        right_content_frame.rowconfigure(3, weight=0)  # history_frame
        right_content_frame.rowconfigure(4, weight=0)  # 图表标题
        right_content_frame.rowconfigure(5, weight=1)  # chart_frame 占满剩余空间
    
        # 基金信息面板
        ttk.Label(right_content_frame, text="基金信息", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5))
    
        self.info_panel = ttk.Frame(right_content_frame, style="Inner.TFrame")
        self.info_panel.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.info_panel.columnconfigure(0, weight=1)  # 内部可伸展
    
        self.info_text = tk.Text(
            self.info_panel,
            height=3,
            state=tk.DISABLED,
            bg="#ffffff",
            relief=tk.FLAT,
            font=('SimHei', 10)
        )
        self.info_text.pack(fill=tk.X, padx=5, pady=5)
    
        # 历史估值表格
        ttk.Label(right_content_frame, text="估值历史明细", style="SectionTitle.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 5))
    
        self.history_frame = ttk.Frame(right_content_frame, style="Inner.TFrame")
        self.history_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.history_frame.columnconfigure(0, weight=1)  # 允许横向伸展
    
        history_columns = ("trade_date", "trade_time", "estimate_time", "value", "change_rate")
        self.history_tree = ttk.Treeview(
            self.history_frame,
            columns=history_columns,
            show="headings",
            height=6,
            style="HistoryTree.Treeview"
        )
    
        self.history_tree.heading("trade_date", text="交易日期", anchor=tk.CENTER)
        self.history_tree.heading("trade_time", text="交易时间", anchor=tk.CENTER)
        self.history_tree.heading("estimate_time", text="估值时间点", anchor=tk.CENTER)
        self.history_tree.heading("value", text="估值", anchor=tk.CENTER)
        self.history_tree.heading("change_rate", text="涨跌幅(%)", anchor=tk.CENTER)
    
        self.history_tree.column("trade_date", width=80, anchor=tk.CENTER)
        self.history_tree.column("trade_time", width=110, anchor=tk.CENTER)
        self.history_tree.column("estimate_time", width=60, anchor=tk.CENTER)
        self.history_tree.column("value", width=60, anchor="e")
        self.history_tree.column("change_rate", width=30, anchor="e")
    
        # 滚动条
        history_scroll = ttk.Scrollbar(self.history_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scroll.set)
    
        self.history_tree.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
    
        # 图表区域
        ttk.Label(right_content_frame, text="基金估值走势", style="SectionTitle.TLabel").grid(
            row=4, column=0, sticky="w", pady=(0, 5))
    
        self.chart_frame = ttk.Frame(right_content_frame, style="Inner.TFrame")
        self.chart_frame.grid(row=5, column=0, sticky="nsew", padx=10, pady=10)
        self.chart_frame.columnconfigure(0, weight=1)
        self.chart_frame.rowconfigure(0, weight=1)
    
        # 初始化图表
        self.init_chart()
    
        # 更新基金列表
        self.update_fund_list()

    def setup_styles(self):
        """设置界面样式，支持可配置字体大小，历史表格与基金列表样式统一"""
        
        # 读取配置的字体大小，带默认值和最小值限制
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                font_size = config.get('ui', {}).get('font_size', 10)
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
            font_size = 14  # 默认值
        
        # 保证最小字体为 10
        FONT_SIZE = max(10, int(font_size))
        
        # 全局字体
        DEFAULT_FONT = (AVAILABLE_CHINESE_FONT, FONT_SIZE)
        BOLD_FONT = (AVAILABLE_CHINESE_FONT, FONT_SIZE, 'bold')
        HEADER_FONT = (AVAILABLE_CHINESE_FONT, FONT_SIZE, 'bold')
    
        style = ttk.Style()
        
        # 基础样式
        style.configure(".", font=DEFAULT_FONT)

        style.configure("Red.TFrame", background="red")  # 定义红色 Frame 样式
		
        style.configure("Blue.TFrame", background="blue")
        
        # 卡片样式
        style.configure("Card.TFrame", 
                       background="#ffffff",
                       relief=tk.RAISED,
                       borderwidth=1)
        
        # 内部框架样式
        style.configure("Inner.TFrame",
                       background="#ffffff",
                       relief=tk.SUNKEN,
                       borderwidth=1)
        
        # 标题样式
        style.configure("SectionTitle.TLabel",
                       font=BOLD_FONT,
                       foreground="#2c3e50",
                       padding=(0, 5, 0, 5))
        
        # 状态条样式
        style.configure("Status.TLabel",
                       background="#3498db",
                       foreground="#ffffff",
                       padding=(10, 5),
                       relief=tk.SUNKEN,
                       anchor=tk.W)
        
        # 指数样式
        style.configure("IndexName.TLabel", font=BOLD_FONT, foreground="#34495e")
        style.configure("IndexValue.TLabel", font=DEFAULT_FONT, foreground="#2c3e50")
        style.configure("IndexUp.TLabel", font=BOLD_FONT, foreground="#e74c3c")
        style.configure("IndexDown.TLabel", font=BOLD_FONT, foreground="#2ecc71")
        style.configure("IndexFlat.TLabel", font=DEFAULT_FONT, foreground="#7f8c8d")
        
        # 统一树状图基础样式
        base_tree_style = {
            "rowheight": 25,
            "fieldbackground": "#ffffff",
            "background": "#ffffff",
            "foreground": "#333333",
            "font": DEFAULT_FONT
        }
        
        base_header_style = {
            "font": HEADER_FONT,
            "background": "#f1c40f",
            "foreground": "#2c3e50",
            "padding": (5, 3),
            "bordercolor": "#e6b800",
            "borderwidth": 1,
            "relief": tk.RAISED
        }
        
        base_header_map = {
            "background": [('active', '#f8d775'), ('pressed', '#e6b800')],
            "foreground": [('active', '#2c3e50'), ('pressed', '#2c3e50')]
        }
        
        base_row_map = {
            "background": [
                ('selected', '#ffeaa7'),
                ('active', '#fff3cd'),
                ('alternate', '#fcfcfc')
            ],
            "foreground": [
                ('selected', '#2c3e50'),
                ('active', '#2c3e50')
            ],
            "fieldbackground": [
                ('selected', '#ffeaa7'),
                ('active', '#fff3cd'),
                ('alternate', '#fcfcfc')
            ]
        }
        
        # 应用到基金列表和历史表格
        style.configure("FundTree.Treeview", **base_tree_style)
        style.configure("FundTree.Treeview.Heading", **base_header_style)
        style.map("FundTree.Treeview.Heading", **base_header_map)
        style.map("FundTree.Treeview", **base_row_map)
        
        style.configure("HistoryTree.Treeview", **base_tree_style)
        style.configure("HistoryTree.Treeview.Heading", **base_header_style)
        style.map("HistoryTree.Treeview.Heading", **base_header_map)
        style.map("HistoryTree.Treeview", **base_row_map)
        
        # 滚动条样式
        style.configure("Custom.TScrollbar",
                       troughcolor="#f0f0f0",
                       background="#bdc3c7",
                       arrowcolor="#7f8c8d",
                       borderwidth=1)
        
        # 垂直滚动条布局
        style.layout("Custom.TScrollbar", [
            ('Vertical.Scrollbar.trough', {
                'sticky': 'ns',
                'children': [
                    ('Vertical.Scrollbar.thumb', {
                        'expand': '1',
                        'sticky': 'nsew'
                    })
                ]
            })
        ])
		
    def _start_auto_fetch(self):
        """启动自动拉取，但不自动轮播；由播放引擎驱动显示"""
        def fetch_and_enqueue():
            try:
                current_ts = int(time.time())
                start_ts = self.last_end_ts
                end_ts = current_ts
    
                if start_ts >= end_ts:
                    start_ts = end_ts - 300
    
                news_items = get_news_list(start_ts, end_ts)
                if news_items:
                    self._write_log(f"拉取到 {len(news_items)} 条新快讯", 'info')
                    for item in news_items:
                        # 日志：记录加入队列的每条消息
                        self._write_log(f"入队快讯: [{item['time_str']}] {item['title']}", 'debug')
                        self.news_display_queue.append(item)
                    if len(self.news_display_queue) > 10:
                        self.news_display_queue = self.news_display_queue[-10:]
                    # 启动播报（如果尚未运行）
                    if not self.is_playing:
                        self._play_next_in_queue()
                self.last_end_ts = end_ts
            except Exception as e:
                self._write_log(f"拉取快讯失败: {e}", 'error')
            self.news_fetch_job = self.root.after(30000, fetch_and_enqueue)
    
        self.is_playing = False  # 新增标志位
        self.news_fetch_job = self.root.after(1000, fetch_and_enqueue)
    
    
    def _play_next_in_queue(self):
        """顺序播放：播一条 → 显示它 → 等播完 → 播下一条"""
        if not self.news_display_queue or self.is_playing:
            return
    
        self.is_playing = True
        item = self.news_display_queue.pop(0)  # 立即取出
    
        # 立即更新状态栏为当前播放的这条
        display_text = f"【快讯】{item['time_str']} {item['title']}"
        self.status_var.set(display_text)
        
        # 日志：明确记录“正在播放”
        self._write_log(f"▶ 正在播放: [{item['time_str']}] {item['title']}", 'info')
    
        def play_audio():
            try:
                play_audio_from_url(item["audio_url"])
                self._write_log(f"✅ 播放完成: [{item['time_str']}] {item['title']}", 'info')
            except Exception as e:
                self._write_log(f"❌ 播放失败: {e}", 'error')
            finally:
                # 播放结束后，继续下一条
                self.root.after(500, self._finish_play_and_continue)
    
        threading.Thread(target=play_audio, daemon=True).start()
    
    
    def _finish_play_and_continue(self):
        """播放完成后的清理和继续"""
        self.is_playing = False
        # 如果还有消息，继续播放
        if self.news_display_queue:
            self.root.after(1000, self._play_next_in_queue)
        else:
            # 队列空了，清空状态栏或显示提示
            self.status_var.set("暂无快讯")
    def open_history_viewer(self):
        """打开基金历史记录查看器（传递主窗口实例，用于居中定位）"""
        selected_items = self.fund_tree.selection()
        if not selected_items:
            messagebox.showwarning("提示", "请先选择一个基金")
            return
        
        item = selected_items[0]
        fund_code = self.fund_tree.item(item, "values")[1]
        
        # 查找基金名称
        fund = next((f for f in self.funds if f["code"] == fund_code), None)
        if not fund:
            messagebox.showerror("错误", "未找到选中的基金信息")
            return
        
        # 导入并打开历史记录查看器（新增传递主窗口 self.root）
        from module.fund_history_viewer import open_fund_history_viewer
        open_fund_history_viewer(
            parent=self.root,  # 主窗口实例（关键：用于计算居中位置）
            fund_code=fund_code, 
            fund_name=fund["name"]
        )
    def open_strategy_analyzer_viewer(self):
        """策略分析器（传递主窗口实例，用于居中定位）"""
        selected_items = self.fund_tree.selection()
        if not selected_items:
            messagebox.showwarning("提示", "请先选择一个基金")
            return
        
        item = selected_items[0]
        fund_code = self.fund_tree.item(item, "values")[1]
        
        # 查找基金名称
        fund = next((f for f in self.funds if f["code"] == fund_code), None)
        if not fund:
            messagebox.showerror("错误", "未找到选中的基金信息")
            return
        
        # 打开策略分析器（新增传递主窗口 self.root）
        from module.fund_strategy_analyzer import open_fund_strategy_analyzer
        open_fund_strategy_analyzer(
            parent=self.root,  # 主窗口实例（关键：用于计算居中位置）
            fund_code=fund_code, 
            fund_name=fund["name"]
        )
    def open_fund_calculator(self):
        """打开基金成本计算器（传递主窗口实例，用于居中定位）"""
        selected_items = self.fund_tree.selection()
        if not selected_items:
            messagebox.showwarning("提示", "请先选择一个基金")
            return
    
        item = selected_items[0]
        fund_code = self.fund_tree.item(item, "values")[1]  # 假设 code 在第2列
    
        # 查找基金名称
        fund = next((f for f in self.funds if f["code"] == fund_code), None)
        if not fund:
            messagebox.showerror("错误", "未找到选中的基金信息")
            return
    
        # 导入并打开成本计算器
        from module.fund_calculator import open_fund_calculator_view
        open_fund_calculator_view(
            parent=self.root,      # 主窗口，用于居中和模态控制
            fund_code=fund_code,
            fund_name=fund["name"]
        )
    def start_index_refresh_thread(self):
        """启动指数刷新线程"""
        self.is_refreshing_indices = True
        self.index_thread = threading.Thread(target=self.index_refresh_task, daemon=True)
        self.index_thread.start()
    
    def index_refresh_task(self):
        """指数刷新任务，每30秒更新一次指数数据"""
        while self.is_refreshing_indices:
            try:
                self.refresh_indices()
            except Exception as e:
                print(f"指数刷新出错: {str(e)}")
            
            # 每30秒刷新一次
            for _ in range(30):
                if not self.is_refreshing_indices:
                    break
                time.sleep(1)
    def refresh_indices(self):
        """刷新指数数据，通过调用stock_index_fetcher获取并更新"""
        try:
            # 调用独立模块获取所有指数数据
            index_results = self.index_fetcher.get_all_indices()
            
            # 处理获取到的指数数据（使用与初始化一致的键名）
            for index_name, index_data in index_results.items():
                # 找到对应的指数
                for idx, index in enumerate(self.indices):
                    if index["name"] == index_name:
                        if '错误' not in index_data:
                            try:
                                # 使用与初始化一致的键名：value, change, change_rate
                                self.indices[idx]["value"] = float(index_data['当前值'])
                                self.indices[idx]["change"] = float(index_data['涨跌额'].replace('+', ''))
                                self.indices[idx]["change_rate"] = float(index_data['涨跌幅'].replace('%', '').replace('+', ''))
                            except (ValueError, KeyError) as e:
                                print(f"处理 {index_name} 数据时出错: {str(e)}")
                        else:
                            print(f"警告: {index_name} 获取失败 - {index_data['错误']}")
                        break
            
            # 调用界面更新方法
            self.update_indices_display()
            
        except Exception as e:
            print(f"刷新指数过程中发生错误: {str(e)}")
    def update_indices_display(self):
        """更新指数显示界面"""
        # 确保指数数据和标签数量匹配
        if not hasattr(self, 'indices_labels'):
            print("错误: 未初始化indices_labels")
            return
            
        if len(self.indices) != len(self.indices_labels):
            print(f"警告: 指数数据数量({len(self.indices)})与标签数量({len(self.indices_labels)})不匹配")
            return
            
        for i, (name_label, value_label, change_label) in enumerate(self.indices_labels):
            try:
                # 检查索引是否有效
                if i >= len(self.indices):
                    print(f"警告: 索引{i}超出指数数据范围")
                    continue
                    
                index = self.indices[i]
                
                # 使用正确的键名value，与初始化和refresh_indices保持一致
                value_label.config(text=f"{index['value']:.2f}")
                
                # 更新名称标签（确保名称正确显示）
                name_label.config(text=index['name'])
                
                # 处理涨跌幅显示和颜色
                rate = index["change_rate"]
                if rate >= 0:
                    change_label.config(text=f"+{rate:.2f}%", foreground="red")
                else:
                    change_label.config(text=f"{rate:.2f}%", foreground="green")
                    
            except KeyError as e:
                print(f"警告: 指数数据中缺少键{e}")
            except Exception as e:
                print(f"更新指数显示时出错: {str(e)}")

    def init_settings_tab(self):
        """初始化设置标签页"""
        frame = ttk.Frame(self.settings_tab, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 刷新间隔设置
        interval_frame = ttk.Frame(frame)
        interval_frame.pack(fill=tk.X, pady=15)
        
        ttk.Label(interval_frame, text="自动刷新间隔(分钟):").pack(side=tk.LEFT, padx=(0, 10))
        
        self.refresh_interval_var = tk.IntVar(value=self.update_interval // 60)
        self.refresh_interval_combo = ttk.Combobox(interval_frame, textvariable=self.refresh_interval_var, 
                                                  values=[1, 2, 5, 10, 15, 30], width=5, state="readonly")
        self.refresh_interval_combo.pack(side=tk.LEFT)
        
        # 数据库管理
        db_frame = ttk.LabelFrame(frame, text="数据库管理", padding="10")
        db_frame.pack(fill=tk.X, pady=15)
        
        # 修改按钮绑定，直接调用secure_reset_database方法
        ttk.Button(db_frame, text="重置数据库（会备份当前数据）", 
                  command=lambda: self.confirm_reset_database()).pack(side=tk.LEFT, padx=10, pady=5)
        # 保存设置按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text="保存设置", command=self.save_settings).pack(side=tk.LEFT)
        
        # 说明文本
        说明_text = """
设置说明:

1. 自动刷新间隔: 设置基金估值自动刷新的时间间隔(分钟)
   刷新将在交易时间内执行

2. 交易时间: 每个交易日 
   上午 9:00 - 11:30
   下午 13:30 - 15:00

3. 数据存储: 所有基金数据和历史估值保存在SQLite数据库中
   数据库文件: fund_data.db
        """
        text_widget = tk.Text(frame, wrap=tk.WORD, height=10, width=60)
        text_widget.pack(fill=tk.X, pady=10)
        text_widget.insert(tk.END, 说明_text)
        text_widget.config(state=tk.DISABLED)
    def init_chart(self):
        self.fig, self.ax = plt.subplots(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 初始化线条和点
        self.line, = self.ax.plot([], [], 'b-', linewidth=2)
        self.points, = self.ax.plot([], [], 'ro', markersize=8)
        
        self.ax.set_title("基金估值走势")
        self.ax.set_xlabel('时间')
        self.ax.set_ylabel('估值 (元)')
        self.ax.grid(True)
        
        # 设置x轴为时间格式
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        self.fig.autofmt_xdate()
        
        self.canvas.draw()	
	
    def confirm_reset_database(self):
        """确认重置数据库"""
        if messagebox.askyesno("确认", "确定要重置数据库吗？当前数据将被备份并创建新数据库。"):
            if secure_reset_database():
                #提示用户重启
                messagebox.showinfo(
                    "重置完成",
                    "数据库已重置并备份。\n\n"
                    "请现在关闭并重新启动本程序，\n"
                    "以完成数据库脚本升级。"
                )
                
                # 3. 安全关闭程序
                self.root.quit()   # 停止主循环
                self.root.destroy()  # 销毁窗口

            else:
                messagebox.showerror("错误", "数据库重置失败")


    def load_settings(self):
        """加载设置"""
        with db_connection() as conn:
            result = conn.execute(
                "SELECT value FROM settings WHERE key = ?", 
                ("refresh_interval",)
            ).fetchone()
            if result:
                self.update_interval = int(result[0]) * 60  # 转换为秒
            else:
                self.update_interval = 300  # 默认5分钟
    def save_settings(self):
        """保存设置"""
        interval_minutes = self.refresh_interval_var.get()
        self.update_interval = interval_minutes * 60  # 转换为秒
        
        with db_connection() as cursor:
            cursor.execute(
                "UPDATE settings SET value = ? WHERE key = 'refresh_interval'",
                (str(interval_minutes),)
            )
        
        # 保存窗口位置和大小
        #self.save_window_settings()
        
        # 重启监控以应用新的间隔
        self.stop_monitoring()
        self.start_monitoring()
        
        messagebox.showinfo("成功", f"设置已保存，自动刷新间隔为 {interval_minutes} 分钟")

    def on_fund_select(self, event):
        selected_items = self.fund_tree.selection()
        if not selected_items:
            self.selected_fund = None
            self.clear_chart()
            self.clear_history_tree()
            return
        
        item = selected_items[0]
        # 排除汇总行
        if item == self.summary_item_id:
            print("用户点击了汇总行，不加载基金详情")
            self.selected_fund = None
            self.clear_chart()          # 可选：清空图表
            self.clear_history_tree()   # 清空历史列表
            # 可选：在信息面板显示“汇总信息”提示
            self.update_info_panel()    # 如果你希望 info panel 显示“已选中汇总”也可以定制
            return
        
        fund_code = self.fund_tree.item(item, "values")[1]
        self.selected_fund = next((f for f in self.funds if f["code"] == fund_code), None)
        
        # 加载该基金的历史数据
        if self.selected_fund:
            self.load_fund_history(self.selected_fund, datetime.date.today().strftime('%Y-%m-%d'))
            self.update_history_tree()
        
        # 更新信息面板
        self.update_info_panel()
        
        # 更新图表
        self.update_chart()

    def update_history_tree(self):
        """更新历史估值表格（显示明细表数据）"""
        self.clear_history_tree()
        
        if not self.selected_fund or not self.selected_fund["history"]:
            return
        
        # 按时间倒序显示，最新的在最上面
        for item in reversed(self.selected_fund["history"]):
            trade_date, trade_time, estimate_time, value, rate, is_close = item
            
            # 确定初始标签
            tags = []
            if rate >= 0:
                tags.append("up")
            else:
                tags.append("down")
                
            # 如果是收盘数据，添加close标签
            if is_close:
                tags.append("close")
                
            # 插入到表格，创建时就包含所有标签
            tree_item = self.history_tree.insert("", tk.END, 
                                           values=(trade_date, trade_time, estimate_time, 
                                                   f"{value:.4f}", f"{rate:.2f}%"),
                                           tags=tuple(tags))
        
        # 配置标签样式
        self.history_tree.tag_configure("up", foreground="red")
        self.history_tree.tag_configure("down", foreground="green")
        self.history_tree.tag_configure("close", font=('SimHei', 10, 'bold'))

    def clear_history_tree(self):
        """清空历史估值表格"""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

    def update_info_panel(self):
        if not self.selected_fund:
            self.info_text.config(state=tk.NORMAL)
            self.info_text.delete(1.0, tk.END)
            self.info_text.config(state=tk.DISABLED)
            return
        
        fund = self.selected_fund
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        
        info = f"基金名称: {fund['name']}({fund['code']})\n"
        info += f"昨日净值: {fund['latest_net_value']:.4f} 元\n" if fund['latest_net_value'] else ""
        
        if fund["current_value"]:
            info += f"当前估值: {fund['current_value']:.4f} 元 ({fund['change_rate']:.2f}%)\n"
        
        if fund["is_hold"] and fund["cost"] and fund["shares"]:
            # 当天盈亏 = 持有份额 × (当日实时估值 - 昨日单位净值)
            profit = fund["shares"] * (fund["current_value"] - fund["latest_net_value"]) if (fund["current_value"] and fund["latest_net_value"]) else 0
            info += f"持有成本: {fund['cost']:.4f} 元, 持有份额: {fund['shares']:.2f}\n"
            info += f"当日盈亏: {profit:.2f} 元 ({'盈利' if profit >= 0 else '亏损'})"
        
        self.info_text.insert(tk.END, info)
        self.info_text.config(state=tk.DISABLED)

    def update_chart(self):
        """
        更新基金估值走势图：支持连续交易时间 9:30-15:00
        图表X轴每5分钟一个刻度，数据按实际时间点标点连线
        """
        # 1. 基础校验
        if not self.selected_fund or len(self.selected_fund.get("history", [])) < 2:
            self.clear_chart()
            return
    
        fund = self.selected_fund
        self.ax.clear()
    
        # 2. 配置参数
        TRADING_START = (9, 30)
        TRADING_END = (15, 0)
        current_display_date = self.current_display_date
        interval_minutes = 15  # 固定X轴刻度为5分钟
    
        # 3. 数据过滤：只保留当前日期 + 9:30~15:00 的数据
        valid_times = []
        valid_values = []
    
        for item in fund["history"]:
            try:
                trade_date, _, estimate_time, value, _, _ = item
            except ValueError:
                continue
    
            if trade_date != current_display_date:
                continue
    
            full_time_str = f"{trade_date} {estimate_time}"
            try:
                time_obj = datetime.datetime.strptime(full_time_str, "%Y-%m-%d %H:%M:%S")
                hour, minute = time_obj.hour, time_obj.minute
            except ValueError:
                continue
    
            # 判断是否在 9:30 ~ 15:00 内
            current_min = hour * 60 + minute
            start_min = TRADING_START[0] * 60 + TRADING_START[1]  # 570
            end_min = TRADING_END[0] * 60 + TRADING_END[1]        # 900
            if not (start_min <= current_min <= end_min):
                continue
    
            valid_times.append(time_obj)
            valid_values.append(float(value))
    
        if len(valid_times) < 2:
            self.clear_chart()
            self.ax.text(0.5, 0.5, "交易时段数据不足\n无法绘制走势图",
                        ha="center", va="center", transform=self.ax.transAxes, fontsize=12)
            self.canvas.draw()
            return
    
        # 4. 生成X轴刻度（每5分钟一个，从9:30到15:00）
        trading_time_ticks = []
        start_dt = datetime.datetime.strptime(f"{current_display_date} 09:30:00", "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.datetime.strptime(f"{current_display_date} 15:00:00", "%Y-%m-%d %H:%M:%S")
        current = start_dt
        while current <= end_dt:
            trading_time_ticks.append(current)
            current += datetime.timedelta(minutes=interval_minutes)
    
        # 5. 绘制趋势线和点
        self.line, = self.ax.plot(
            valid_times, valid_values,
            color="#1E90FF", linewidth=2.5, label="估值趋势"
        )
        self.points, = self.ax.plot(
            valid_times, valid_values,
            color="#FF4500", marker="o", markersize=6, alpha=0.8, label="估值点"
        )
    
        # 6. 标记收盘点（15:00）
        close_idx = None
        for idx, t in enumerate(valid_times):
            if t.hour == 15 and t.minute == 0:
                close_idx = idx
                break
        if close_idx is not None:
            self.ax.plot(
                valid_times[close_idx], valid_values[close_idx],
                color="#32CD32", marker="o", markersize=10,
                markerfacecolor="white", markeredgewidth=2.5, markeredgecolor="#32CD32",
                label="收盘估值"
            )
    
        # 7. 图表美化
        # 标题
        last_time = valid_times[-1]
        last_value = valid_values[-1]
        last_rate = 0.0
        for item in reversed(fund["history"]):
            try:
                if item[0] == current_display_date:
                    last_rate = float(item[4])
                    break
            except:
                continue
        rate_color = "#DC143C" if last_rate >= 0 else "#008000"
    
        self.ax.set_title(
            f"{fund.get('name', '未知基金')}({fund.get('code', '000000')}) 估值走势\n"
            f"最新：{last_value:.4f}元 | 涨跌幅：{last_rate:.2f}%（截至{last_time.strftime('%H:%M')}）",
            color=rate_color, fontsize=12, pad=15
        )
    
        self.ax.set_xlabel("交易时间", fontsize=10, labelpad=8)
        self.ax.set_ylabel("估值（元）", fontsize=10, labelpad=8)
        self.ax.grid(True, alpha=0.3, linestyle="--")
    
        # X轴设置
        self.ax.set_xticks(trading_time_ticks)
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
        # X轴范围（含边距）
        xlim_start = datetime.datetime.strptime(f"{current_display_date} 09:25:00", "%Y-%m-%d %H:%M:%S")
        xlim_end = datetime.datetime.strptime(f"{current_display_date} 15:05:00", "%Y-%m-%d %H:%M:%S")
        self.ax.set_xlim(xlim_start, xlim_end)
    
        # 图例
        self.ax.legend(fontsize=9, loc="upper right", framealpha=0.9)
    
        # 布局与刷新
        self.canvas.draw()

    def clear_chart(self):
        self.ax.clear()
        self.ax.set_title("基金估值走势")
        self.ax.set_xlabel('时间')
        self.ax.set_ylabel('估值 (元)')
        self.ax.grid(True)
    
        # 使用固定5分钟刻度
        interval_minutes = 10
        all_time_points = self.generate_trading_time_points(self.current_display_date, interval_minutes)
        self.ax.set_xticks(all_time_points)
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
        plt.xticks(rotation=45)
        self.fig.subplots_adjust(
            left=0.12,
            bottom=0.2,
            right=0.95,
            top=0.9
        )
        self.canvas.draw()

    def update_fund_list(self):
        """增量更新基金列表（添加、更新、删除）"""
        today = datetime.date.today().strftime('%Y-%m-%d')
        updated = False
    
        # 当前所有基金代码集合
        current_fund_codes = {fund["code"] for fund in self.funds}
		
		
    
        #更新或插入现有基金 ===
        for fund in self.funds:
            fund_code = fund["code"]
            main_table_data = self.get_main_table_today_latest(fund_code, today)
            
            # 计算各项显示值（与原有逻辑一致）
            hold_mark = "✓" if fund["is_hold"] else ""
            cost = f"{fund['cost']:.4f}" if (fund["is_hold"] and fund["cost"]) else "-"
            shares = f"{fund['shares']:.2f}" if (fund["is_hold"] and fund["shares"]) else "-"
    
            unit_net_value = "-"
            realtime_estimate = "-"
            change_rate = "-"
            realtime_profit = "-"
            tag = ""
    
            latest_detail = self.get_latest_detail_from_db(fund_code, today)
            if latest_detail:
                realtime_estimate = f"{latest_detail['value']:.4f}"
                change_rate = f"{latest_detail['rate']:.2f}%"
                tag = "up" if latest_detail['rate'] >= 0 else "down"
				
            if main_table_data and 'realtime_profit' in main_table_data:
                fund['realtime_profit'] = float(main_table_data['realtime_profit']) if main_table_data['realtime_profit'] is not None else 0.0
            else:
                fund['realtime_profit'] = 0.0
            
            # 后续用于界面显示（字符串格式）
            realtime_profit_display = f"{fund['realtime_profit']:.2f}" if abs(fund['realtime_profit']) >= 0.01 else "0.00"
		
            if main_table_data:
                unit_net_value = f"{main_table_data['unit_net_value']:.4f}" if main_table_data['unit_net_value'] else "-"
            else:
                unit_net_value = f"{fund['latest_net_value']:.4f}" if fund["latest_net_value"] else "-"
    
            # 获取提醒阈值（新增）
            rise_alert = f"{fund['rise_alert']:.2f}%" if fund.get("rise_alert") not in (None, 0) else "-"
            fall_alert = f"{fund['fall_alert']:.2f}%" if fund.get("fall_alert") not in (None, 0) else "-"
    
            # 组装显示数据
            new_values = {
                0: hold_mark,
                1: fund["code"],
                2: fund["name"],
                3: unit_net_value,
                4: realtime_estimate,
                5: change_rate,
                6: cost,
                7: shares,
                8: realtime_profit_display,
                9: rise_alert,
                10: fall_alert,
            }
    
            # 增量更新逻辑
            if fund_code in self.code_to_item_id:
                # 已存在，只更新变化的列
                item_id = self.code_to_item_id[fund_code]
                old_values = self.current_display_data.get(fund_code, {})
    
                for col_idx, new_val in new_values.items():
                    if old_values.get(col_idx) != new_val:
                        self.fund_tree.set(item_id, col_idx, new_val)
                        updated = True
    
                # 更新标签（涨跌幅颜色）
                current_tags = self.fund_tree.item(item_id, "tags")
                if tag not in current_tags:
                    self.fund_tree.item(item_id, tags=(tag,))
    
                # 更新缓存
                self.current_display_data[fund_code] = new_values
            else:
                # 新基金，插入新行
                item_id = self.fund_tree.insert("", tk.END, values=tuple(new_values.values()), tags=(tag,))
                self.code_to_item_id[fund_code] = item_id
                self.current_display_data[fund_code] = new_values
                updated = True
    
        #删除已不存在的基金 ===
        codes_to_remove = []
        for fund_code in self.code_to_item_id:
            if fund_code not in current_fund_codes:
                item_id = self.code_to_item_id[fund_code]
                self.fund_tree.delete(item_id)  # 从 Treeview 删除
                codes_to_remove.append(fund_code)
                updated = True
    
        # 清理缓存
        for fund_code in codes_to_remove:
            self.code_to_item_id.pop(fund_code, None)
            self.current_display_data.pop(fund_code, None)
        # === 在所有行插入完成后，恢复排序状态 ===
        if self.last_sorted_col is not None:
            self.sort_fund_list(self.last_sorted_col, self.last_sorted_reverse)
        # 更新汇总行（确保它在最后一行）
        # 先删除再插入，确保位置正确
        if self.summary_item_id in self.fund_tree.get_children():
            self.fund_tree.delete(self.summary_item_id)
    
        # 重新插入到最后
        self.insert_or_update_summary_row()
    
        # 保持标签样式配置
        self.fund_tree.tag_configure("up", foreground="red")
        self.fund_tree.tag_configure("down", foreground="green")

        return updated

    def sort_fund_list(self, col, reverse):
        """
        对基金列表按指定列排序，排除汇总行，排序后将其置于最后一行。
        """
        # 列标题中文映射
        column_titles = {
            "change_rate": "涨跌幅(%)",
            "realtime_profit": "当日盈亏",
            "hold_shares": "持有份额"
        }
        title = column_titles.get(col, col)
    
        # === 分离普通行和汇总行 ===
        items = []
        summary_item = None
    
        for item in self.fund_tree.get_children():
            if item == self.summary_item_id:
                summary_item = item
            else:
                value_str = self.fund_tree.set(item, col)
                try:
                    if col == "change_rate":
                        sort_value = float(value_str.rstrip('%'))
                    elif col == "realtime_profit":
                        sort_value = float(value_str.replace('¥', '').replace(',', '').strip())
                    elif col == "hold_shares":
                        sort_value = float(value_str.replace(',', '').strip())
                    else:
                        sort_value = 0
                except (ValueError, AttributeError):
                    sort_value = 0
                items.append((sort_value, item))
    
        # 排序（不包含汇总行）
        items.sort(key=lambda x: x[0], reverse=reverse)
    
        # 重新插入排序后的行
        for index, (sort_value, item) in enumerate(items):
            self.fund_tree.move(item, '', index)
    
        # === 重新插入汇总行到最后一行 ===
        if summary_item:
            self.fund_tree.move(summary_item, '', 'end')  # 放到最后
            self.fund_tree.selection_remove(summary_item)  # 确保不能被选中
    
        # === 记录排序状态 ===
        self.last_sorted_col = col
        self.last_sorted_reverse = reverse
    
        # === 更新列标题显示箭头 ===
        next_reverse = not reverse
        for c in column_titles:
            t = column_titles[c]
            if c == col:
                self.fund_tree.heading(c, text=f"{t} {'▲' if not reverse else '▼'}",
                                       command=lambda col=c: self.sort_fund_list(col, next_reverse))
            else:
                self.fund_tree.heading(c, text=t,
                                       command=lambda col=c: self.sort_fund_list(col, False))							   
    def insert_or_update_summary_row(self):
        """插入或更新汇总行"""
        total_profit = 0.0
        hold_count = 0
    
        # 直接遍历funds，避免依赖 UI 字符串
        for fund in self.funds:
            # 兼容多种字段名和类型
            is_hold = fund.get('is_hold') or fund.get('hold')
            shares = fund.get('shares') or fund.get('hold_shares', 0)
            profit = fund.get('realtime_profit', 0.0)
    
            # 转换 is_hold 为布尔值
            is_holding = bool(is_hold) and is_hold not in (0, '0', '', 'False', 'false', None)
    
            # 调试打印
            #print(f"基金: {fund.get('name', '未知')}, 持有: {is_holding}, 份额: {shares}, 盈亏: {profit}")
    
            if is_holding and shares > 0:
                total_profit += profit
                hold_count += 1
    
        #print(f"汇总完成：共 {hold_count} 只基金，总盈亏: ¥{total_profit:,.2f}")
        # 格式化显示
        if total_profit >= 0:
            total_text = f"¥{total_profit:,.2f}"
        else:
            total_text = f"¥{total_profit:,.2f}"
    
    
        # 汇总行显示内容
        summary_values = (
            "",  # 持有
            "盈亏合计",  # 基金代码
            f"共持有 {hold_count} 只基金",  # 基金名称
            "", "", "", "", "",  # 单位净值 到 持有份额
            total_text,  # 当日盈亏合计
            "", ""  # 上涨/下跌提醒
        )
    
        # 检查是否已存在
        if self.summary_item_id in self.fund_tree.get_children():
            self.fund_tree.item(self.summary_item_id, values=summary_values)
        else:
            self.fund_tree.insert(
                "", 
                tk.END, 
                iid=self.summary_item_id,  # 固定 ID
                values=summary_values,
                tags=("summary",)
            )
    
        # 可选：滚动到底部看到汇总（如果列表很长）
        # self.fund_tree.see(self.summary_item_id)
    
        # 可选：禁止选中
        self.fund_tree.selection_remove(self.summary_item_id)

    def get_latest_detail_from_db(self, fund_code, date):
        """从明细表获取最新的估值数据"""
        try:
            with db_connection() as conn:
                row = conn.execute('''
                    SELECT realtime_estimate, change_rate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ?
                    ORDER BY estimate_time DESC 
                    LIMIT 1
                ''', (fund_code, date)).fetchone()
                
                if row:
                    return {
                        "value": row[0],   # 改为索引访问
                        "rate": row[1]
                    }
            return None
        except Exception as e:
            print(f"获取明细表最新数据出错(fund:{fund_code}): {str(e)}")
            return None

    def get_main_table_today_latest(self, fund_code, date):
        """从主表获取当天最新记录（包含昨日单位净值）"""
        try:
            with db_connection() as conn:
                result = conn.execute('''
                    SELECT unit_net_value, realtime_estimate, change_rate, realtime_profit 
                    FROM fund_estimate_main 
                    WHERE fund_code = ? AND trade_date = ?
                    ORDER BY trade_time DESC 
                    LIMIT 1
                ''', (fund_code, date))
                
                row = result.fetchone()  # 或直接: conn.execute(...).fetchone()
                if row:
                    return {
                        "unit_net_value": row[0],
                        "realtime_estimate": row[1],
                        "change_rate": row[2],
                        "realtime_profit": row[3]
                    }
            return None
        except Exception as e:
            print(f"获取主表数据出错(fund:{fund_code}): {str(e)}")
            return None



    def get_realtime_estimate(self, fund_code):
        """获取基金实时估值，包括单位净值(dwjz)"""
        try:
            url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://fund.eastmoney.com/"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            content = response.text.strip().lstrip("jsonpgz(").rstrip(");")
            
            data = json.loads(content)
            
            # 提取关键信息，包括单位净值(dwjz)
            return {
                "dwjz": float(data["dwjz"]),  # 单位净值
                "value": float(data["gsz"]),  # 估算净值
                "rate": float(data["gszzl"]),  # 估算涨跌幅(%)
                "time": data["gztime"]  # 更新时间
            }
            
        except Exception as e:
            print(f"获取实时估值出错: {str(e)}")
            return None


    def generate_trading_time_points(self, date, interval_minutes):
        """生成交易时段内的所有刷新时间点（含收盘15:00）"""
        time_points = []
        
        # 调整为连续时段：9:30-15:00
        start_time = datetime.datetime.strptime(f"{date} 09:30:00", "%Y-%m-%d %H:%M:%S")
        end_time = datetime.datetime.strptime(f"{date} 15:00:00", "%Y-%m-%d %H:%M:%S")
        
        # 生成连续时段的时间点
        current = start_time
        while current < end_time:
            time_points.append(current)
            current += datetime.timedelta(minutes=interval_minutes)
        
        # 确保15:00收盘点被包含
        if end_time not in time_points:
            time_points.append(end_time)
        
        return time_points

    def start_core_threads_async(self):
        """异步启动核心线程，避免阻塞界面初始化"""
        # 启动指数刷新线程
        self.start_index_refresh_thread()
        
        # 再延迟启动监控线程
        self.root.after(1000, self.start_monitoring)
	
    def start_monitoring(self):
        """启动监控"""
        if self.is_monitoring:
            self._write_log("监控尝试启动，但已在运行中")
            return
            
        self.is_monitoring = True
        self._write_log("监控已启动")
        self.root.after(100, self.perform_periodic_refresh)
			
		
    def perform_periodic_refresh(self):
        if not self.is_monitoring:
            return
    
        now = self.get_now()
        current_time = now.time()
    
        # --- 1. 检查是否在交易时段 ---
        if not self.is_trading_time(now):
            if current_time < datetime.time(9, 30):
                # 等待开盘...
                wait_until = now.replace(hour=9, minute=30, second=0, microsecond=0)
                if wait_until < now:
                    wait_until += datetime.timedelta(days=1)
                wait_ms = int((wait_until - now).total_seconds() * 1000)
                self.status_var.set(f"等待开盘... {wait_until.strftime('%H:%M:%S')}")
                self._write_log(f"盘前等待，将在 {wait_until.strftime('%H:%M:%S')} 开始刷新")
                self.root.after(wait_ms, self.perform_periodic_refresh)
            else:
                self.status_var.set("今日监控结束，明天再见")
                self._write_log("今日监控结束")
                self.is_monitoring = False
            return
    
        #启动后台线程执行刷新
        threading.Thread(target=self._refresh_worker, args=(now,), daemon=True).start()
    
    def _refresh_worker(self, trigger_time: datetime.datetime):
        """在后台线程中执行耗时操作"""
        try:
            self._write_log(f"开始刷新数据 @ {trigger_time.strftime('%H:%M:%S')}")
    
            #所有耗时操作放在这里：网络请求、计算等
            success_count, fail_count = self.refresh_all_funds(force=False)
    
            #所有 UI 更新通过 after 回主线程
            self.root.after(0, self.update_fund_list)
            if self.selected_fund:
                self.root.after(0, self.update_history_tree)
                self.root.after(0, self.update_chart)
    
            #在主线程执行“刷新完成”逻辑
            next_refresh_dt = self.calculate_next_refresh_time()
            status_msg = f"刷新完成 | 成功:{success_count} 失败:{fail_count} | 下次: {next_refresh_dt.strftime('%H:%M')}"
            
            def on_main_thread():
                self.status_var.set(status_msg)
                self._write_log(status_msg)
                #重新调度下一次
                now = self.get_now()
                wait_seconds = (next_refresh_dt - now).total_seconds()
                if wait_seconds > 0:
                    self.root.after(int(wait_seconds * 1000), self.perform_periodic_refresh)
                else:
                    self.root.after(1000, self.perform_periodic_refresh)
    
            self.root.after(0, on_main_thread)
    
        except Exception as e:
            error_msg = f"刷新异常: {e}，10秒后重试"
            self._write_log(error_msg, 'error')
            #异常后也回主线程重试
            self.root.after(10000, self.perform_periodic_refresh)
    		
    def is_trading_time(self, check_time: datetime.datetime = None) -> bool:
        now = check_time if check_time else self.get_now()
        if now.weekday() >= 5:  # 周六日
            return False
        current_time = now.time()
        return datetime.time(9, 30) <= current_time < datetime.time(15, 1)
    

    def calculate_next_refresh_time(self):
        """计算下一个刷新时间点（对齐到刷新间隔）"""
        interval_minutes = self.refresh_interval_var.get()  # 如 5, 10, 15
        now = self.get_now()
        
        # 计算从 9:30 开始的第几个间隔
        minutes_since_start = (now.hour - 9) * 60 + now.minute - 30
        next_interval_index = (minutes_since_start // interval_minutes) + 1
        next_minute_offset = next_interval_index * interval_minutes
        
        # 构造下一个时间点
        next_hour, next_minute = divmod(30 + next_minute_offset, 60)
        next_hour = 9 + next_hour
        
        # 限制在 15:00 前
        if next_hour > 15 or (next_hour == 15 and next_minute > 0):
            return datetime.datetime.combine(now.date(), datetime.time(15, 0))
        
        return now.replace(hour=next_hour, minute=next_minute, second=0, microsecond=0)
		
    def _write_log(self, message: str, level: str = 'info'):
        """
        封装 write_log，自动传入目录和前缀
        
        :param message: 日志内容
        :param level: 日志级别，可选，默认为 'info'
        """
        full_message = f"{level.upper():<8} {message}"
        write_log(full_message, log_dir=self.log_dir, prefix=self.log_prefix)
    def manual_refresh(self):
        """手动刷新基金数据"""
        # 检查是否正在刷新中
        if self.refresh_lock.acquire(blocking=False):
            try:
                # 手动刷新不受交易时间限制
                def refresh_task():
                    success_count, fail_count = self.refresh_all_funds(force=True)
                    self.root.after(0, lambda: self.status_var.set(
                        f"手动刷新完成 {datetime.datetime.now().strftime('%H:%M:%S')}，成功:{success_count} 失败:{fail_count}"
                    ))
                    self.root.after(0, self.update_fund_list)
                    if self.selected_fund:
                        self.root.after(0, self.update_history_tree)
                        self.root.after(0, self.update_chart)
                
                threading.Thread(target=refresh_task, daemon=True).start()
                self.status_var.set("正在执行手动刷新...")
            finally:
                self.refresh_lock.release()
        else:
            self.status_var.set("已有刷新操作正在进行中，请稍候...")


    def refresh_all_funds(self, force=False):
        """刷新所有基金的数据并保存到数据库（支持强制刷新）"""
        # 记录成功刷新的基金数量
        success_count = 0
        fail_count = 0
        
        # 非强制刷新且非交易时间则不执行
        if not force and not self.is_trading_time():
            print("当前非交易时间，不执行自动刷新")
            return (0, 0)
        now = self.get_now()
        self._write_log(f"开始刷新所有基金数据: {now.strftime('%H:%M:%S')}")
        interval_minutes = self.update_interval // 60
        current_time = datetime.datetime.now()
        
        # 计算时间点（非交易时段使用当前时间）
        if self.is_trading_time():
            prev_interval_minute = (current_time.minute // interval_minutes) * interval_minutes
            prev_refresh_time = current_time.replace(
                minute=prev_interval_minute, 
                second=0, 
                microsecond=0
            )
        else:
            # 非交易时段使用当前时间作为记录时间
            prev_refresh_time = current_time
        
        # 判断是否为收盘后数据（15:00之后）
        is_after_close = current_time.hour >= 15 and (current_time.hour > 15 or current_time.minute >= 0)
        
        for fund in self.funds:
            fund_code = fund["code"]
            current_fund_estimate = None
            
            try:
                # 获取实时估值数据
                current_fund_estimate = self.get_realtime_estimate(fund_code)
                if not current_fund_estimate:
                    print(f"基金 {fund_code} 获取实时数据失败")
                    fail_count += 1
                    continue
                
                # 计算盈亏
                realtime_profit = 0
                if fund["is_hold"] and fund["shares"] and current_fund_estimate["dwjz"]:
                    realtime_profit = fund["shares"] * (current_fund_estimate["value"] - current_fund_estimate["dwjz"])
                
                # 保存数据（标记是否为收盘后数据）
                self.save_fund_estimate_data(
                    fund, 
                    current_fund_estimate, 
                    prev_refresh_time, 
                    realtime_profit,
                    is_close_data=1 if is_after_close else 0
                )
                #调用邮件涨跌提醒
                # 获取当前估值和成本价
                current_value = float(current_fund_estimate["value"])
                cost_price = fund.get("cost")
                
                # 初始化提醒阈值
                rise_alert = fund.get("rise_alert")   # 如 10 表示 +10%
                fall_alert = fund.get("fall_alert")   # 如 18 表示 -18%
                cost_str = f"{cost_price:.4f}" if cost_price is not None else "None"
                print(f"基金 {fund['code']} | 成本: {cost_str}, 当前: {current_value:.4f}")

                # 只有当成本价存在时，才计算盈亏并提醒
                if cost_price is not None and isinstance(cost_price, (int, float)) and cost_price > 0:
                    # 计算累计盈亏百分比（正为盈利，负为亏损）
                    profit_rate = (current_value - cost_price) / cost_price * 100  # 单位：%
                    # 调试打印：显示盈亏情况
                    #print(f"基金 {fund['code']} | 成本: {cost_price:.4f}, 当前: {current_value:.4f}, 浮动: {profit_rate:.2f}%")
                    # 上涨提醒
                    if rise_alert is not None and profit_rate >= rise_alert:
                        #print(f"触发上涨提醒: {profit_rate:.2f}% >= {rise_alert}%")
                        self.notif_sender.send_alert(
                            fund_code=fund["code"],
                            fund_name=fund["name"],
                            change_rate=profit_rate,       # 传入累计盈亏
                            current_value=current_value,
                            alert_type='rise'
                        )
                    # 下跌提醒
                    elif fall_alert is not None and profit_rate <= -fall_alert:
                        #print(f"触发下跌提醒: {profit_rate:.2f}% <= {-fall_alert}%")
                        self.notif_sender.send_alert(
                            fund_code=fund["code"],
                            fund_name=fund["name"],
                            change_rate=profit_rate,       # 传入累计盈亏（负数）
                            current_value=current_value,
                            alert_type='fall'
                        )			
                self.load_fund_history(fund, self.current_display_date)
                success_count += 1
                
            except Exception as e:
                print(f"处理基金 {fund_code} 错误: {str(e)}")
                fail_count += 1
                continue
        self._write_log("基金数据刷新完成")
        return (success_count, fail_count)

    def save_fund_estimate_data(self, fund, estimate_data, prev_refresh_time, realtime_profit, is_close_data=0):
        """保存基金估值数据到数据库（主表和明细表）"""
        today = datetime.date.today().strftime('%Y-%m-%d')
        current_datetime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        estimate_time_str = prev_refresh_time.strftime('%H:%M:%S')  # 用计算出的间隔时间点作为明细时间
        
        # 特殊处理：如果是收盘后数据，强制使用15:00作为记录时间
        if is_close_data and estimate_time_str != "15:00:00":
            close_time = prev_refresh_time.replace(hour=15, minute=0, second=0)
            estimate_time_str = close_time.strftime('%H:%M:%S')
        try:
            with db_connection() as conn:
                # ---------------------- 处理主表：更新或插入当天最新记录 ----------------------
                result = conn.execute('''
                    SELECT id FROM fund_estimate_main 
                    WHERE fund_code = ? AND trade_date = ?
                ''', (fund["code"], today))
                main_record = result.fetchone()
                
                if main_record:
                    # 更新主表
                    conn.execute('''
                        UPDATE fund_estimate_main 
                        SET trade_time = ?, unit_net_value = ?, realtime_estimate = ?, 
                            change_rate = ?, realtime_profit = ?
                        WHERE fund_code = ? AND trade_date = ?
                    ''', (current_datetime, 
                          estimate_data["dwjz"], 
                          estimate_data["value"],
                          estimate_data["rate"], 
                          realtime_profit, 
                          fund["code"], 
                          today))
                else:
                    # 获取最大ID并插入
                    result = conn.execute('SELECT MAX(id) FROM fund_estimate_main WHERE fund_code = ?', (fund["code"],))
                    max_id = result.fetchone()[0]
                    new_id = 1 if max_id is None else max_id + 1
                    
                    conn.execute('''
                        INSERT INTO fund_estimate_main 
                        (id, fund_code, fund_name, trade_date, trade_time,
                         unit_net_value, realtime_estimate, change_rate,
                         is_hold, hold_cost, hold_shares, realtime_profit)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (new_id, fund["code"], fund["name"], today, current_datetime,
                          estimate_data["dwjz"], estimate_data["value"], estimate_data["rate"],
                          1 if fund["is_hold"] else 0, fund["cost"], fund["shares"], realtime_profit))
                
                # ---------------------- 处理明细表：插入固定间隔的估值记录 ----------------------
                result = conn.execute('''
                    SELECT id FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ? AND estimate_time = ?
                ''', (fund["code"], today, estimate_time_str))
                
                if not result.fetchone():
                    # 获取明细表最大ID
                    result = conn.execute('SELECT MAX(id) FROM fund_estimate_details WHERE fund_code = ?', (fund["code"],))
                    max_detail_id = result.fetchone()[0]
                    new_detail_id = 1 if max_detail_id is None else max_detail_id + 1
                    
                    # 插入明细记录
                    conn.execute('''
                        INSERT INTO fund_estimate_details 
                        (id, fund_code, trade_date, trade_time, estimate_time,
                         realtime_estimate, change_rate, is_close_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (new_detail_id, fund["code"], today, current_datetime,
                          estimate_time_str, estimate_data["value"], estimate_data["rate"], is_close_data))
                
                # ✅ 显式提交（如果 db_connection 不自动提交）
                conn.commit()
            
            # 更新基金对象
            fund["current_value"] = estimate_data["value"]
            fund["change_rate"] = estimate_data["rate"]
            fund["update_time"] = current_datetime
            
        except Exception as e:
            print(f"保存基金估值数据出错(fund:{fund['code']}): {str(e)}")
            # 如果需要，这里可以 re-raise 或记录日志
    def load_fund_history(self, fund, date):
        """从数据库明细表加载基金的历史估值数据（优化：非交易时段不过滤数据）"""
        fund["history"] = []
        try:
            with db_connection() as conn:
                rows = conn.execute('''
                    SELECT trade_date, trade_time, estimate_time, realtime_estimate, change_rate, is_close_data 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ?
                    ORDER BY trade_time, estimate_time
                ''', (fund["code"], date)).fetchall()
                
                # 非交易时段：显示所有数据
                if not self.is_trading_time():
                    fund["history"] = rows
                    return
    
                # 交易时段：只保留 9:00 - 15:00 的数据（含收盘数据）
                filtered = []
                for row in rows:
                    try:
                        # 使用 estimate_time 字段判断是否在交易时段内
                        dt = datetime.datetime.strptime(f"{row[0]} {row[2]}", "%Y-%m-%d %H:%M:%S")
                        minutes = dt.hour * 60 + dt.minute
                        is_trading_time = 540 <= minutes <= 900  # 9:00 - 15:00（含）
                        
                        # 保留交易时段内的数据，或标记为收盘的数据
                        if is_trading_time or row[5]:  # row[5] 是 is_close_data
                            filtered.append(row)
                    except Exception:
                        continue  # 跳过时间格式错误的记录
                fund["history"] = filtered
    
        except Exception as e:
            print(f"加载基金历史数据出错: {str(e)}")

    def on_closing(self):
        """处理窗口关闭事件，确保线程和资源正确释放"""
        # 1. 标记所有线程停止信号（非阻塞）
        self.is_refreshing_indices = False
        self.is_monitoring = False  # 通知监控线程停止
        
        # 2. 定义线程终止处理函数，减少重复代码
        def terminate_thread(thread_name, thread_attr, timeout):
            if hasattr(self, thread_attr) and getattr(self, thread_attr).is_alive():
                self.status_var.set(f"正在关闭{thread_name}...")
                self.root.update()  # 刷新UI显示状态
                getattr(self, thread_attr).join(timeout=timeout)
                if getattr(self, thread_attr).is_alive():
                    print(f"警告：{thread_name}未能正常终止，可能仍在运行")
        
        # 批量处理线程终止
        threads = [
            ("监控线程", "monitor_thread", 2.0),
            ("首次刷新线程", "first_refresh_thread", 1.0),
            ("指数刷新线程", "index_refresh_thread", 1.0)
        ]
        
        for name, attr, timeout in threads:
            terminate_thread(name, attr, timeout)
        
        # 3. 释放Matplotlib图表资源
        if hasattr(self, 'fig'):
            plt.close(self.fig)  # 关闭图表
            del self.fig  # 显式删除引用
        
        if hasattr(self, 'ax'):
            del self.ax  # 清除轴对象引用
        
        # 4. 异步保存窗口设置（避免IO操作阻塞关闭流程）
        def save_settings_async():
            try:
                self.save_window_settings()
            except Exception as e:
                print(f"保存窗口设置失败: {str(e)}")
        
        # 使用线程执行保存操作，不阻塞主窗口关闭
        import threading
        save_thread = threading.Thread(target=save_settings_async, daemon=True)
        save_thread.start()
        
        # 5. 最后销毁窗口
        self.root.destroy()
        
        # 6. 仅在极端情况下使用强制退出，通常不需要
        import sys
        sys.exit(0)
    
if __name__ == "__main__":
    try:
        # 确保中文显示正常
        root = tk.Tk()
        root.withdraw()  # 先隐藏窗口，初始化完成后再显示
        root.update_idletasks()  # 强制刷新窗口
        
        # 初始化应用
        app = FVTracker(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
		
        #app.test_refresh_times()
		
        # 获取SQLite数据库引擎版本
        sqlite_engine_version = sqlite3.sqlite_version
        # 获取Python sqlite3模块版本
        sqlite_module_version = sqlite3.version
        
        print(f"SQLite 引擎版本: {sqlite_engine_version}")
        print(f"Python sqlite3 模块版本: {sqlite_module_version}")
 
        if version.parse(sqlite3.sqlite_version) >= version.parse("3.32.0"):
            print("支持 ALTER COLUMN SET DEFAULT 语法")
        else:
            print("不支持 ALTER COLUMN SET DEFAULT 语法，需要使用兼容方案")
        
        root.deiconify()  # 显示窗口
        root.lift()  # 提升窗口层级
        root.attributes('-topmost', True)  # 临时置顶确保可见
#
        root.after_idle(root.attributes, '-topmost', False)  # 空闲后取消置顶
        root.mainloop()
    except KeyboardInterrupt:
        print("程序被手动中断")
        # 确保资源正确释放
        if 'app' in locals():
            app.on_closing()
