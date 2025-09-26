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
        self.software_version = "V1.1.7   by htlaoyang"
        self.version_update_log = """
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
        
        # 数据存储初始化
        init_database()
        self.root = root
        # 初始化主窗口标题（含版本号）
        root.title(f"FVTracker-基金估值监控工具 - {self.software_version}")
        # 从配置文件加载窗口设置
        self.load_window_settings()
        
        # 基金数据存储
        self.funds = []  # 存储所有基金信息
        self.selected_fund = None  # 当前选中的基金
        self.is_monitoring = False  # 是否正在监控
        self.first_refresh_done = False  # 首次刷新是否完成
        self.current_display_date = datetime.date.today().strftime('%Y-%m-%d') # 默认显示当天数据
        
		
        # 新增：缓存当前显示的数据，用于比对差异
        self.current_display_data = {}  # 格式: {fund_code: {column_index: value, ...}}
        self.code_to_item_id = {}  # 基金代码与Treeview行ID的映射
		
        def refresh_funds():
            """主程序刷新基金数据的回调"""
            self.funds = self.fund_manager.load_funds_data()

        def update_main_fund_list():
            """主程序更新监控列表的回调"""
            self.update_fund_list()

        # 实例化FundManager
        self.fund_manager = FundManager(
            root=self.root,
            status_var=self.status_var,
            refresh_funds_cb=refresh_funds,
            update_main_list_cb=update_main_fund_list
        )

        # 加载基金数据（通过FundManager）
        refresh_funds()
        self.load_settings()
        self.initialize_main_table_if_empty()  # 初始化主表空数据
        
        # 创建界面
        self.create_widgets()
        self._now_func = None  # 用于测试时替换时间

        self.root.after(100, self.start_core_threads_async)

    def get_now(self) -> datetime.datetime:
        """获取当前时间，支持测试时 mock"""
        return self._now_func() if self._now_func else datetime.datetime.now()

    def set_now_func(self, func):
        """设置当前时间函数（用于测试）"""
        self._now_func = func


    def initialize_main_table_if_empty(self):
        """初始化主表空数据（确保每日有基础记录）"""
        today = datetime.date.today().strftime('%Y-%m-%d')
        
        with db_connection() as cursor:
            for fund in self.funds:
                fund_code = fund["code"]
                # 检查今日是否已有记录
                cursor.execute('''
                SELECT id FROM fund_estimate_main 
                WHERE fund_code = ? AND trade_date = ?
                ''', (fund_code, today))
                
                if not cursor.fetchone():
                    # 获取最大ID
                    cursor.execute('''
                    SELECT MAX(id) FROM fund_estimate_main WHERE fund_code = ?
                    ''', (fund_code,))
                    max_id = cursor.fetchone()[0]
                    new_id = 1 if max_id is None else max_id + 1
                    # 处理 rise_alert：未设置则默认为 0
                    rise_alert = fund.get("rise_alert")
                    if rise_alert is None or rise_alert == "":
                        rise_alert = 0.0
                    else:
                        rise_alert = float(rise_alert)
                    
                    # 处理 fall_alert：未设置则默认为 0，但写入数据库时存为负数
                    fall_alert = fund.get("fall_alert")
                    if fall_alert is None or fall_alert == "":
                        fall_alert = 0.0
                    else:
                        fall_alert = float(fall_alert)
                    fall_alert = -abs(fall_alert)  # 强制转为负数（即使配置成负的，也确保是负的）
                    # 插入初始记录（空值）
                    cursor.execute('''
                    INSERT INTO fund_estimate_main 
                    (id, fund_code, fund_name, trade_date, trade_time,
                     unit_net_value, realtime_estimate, change_rate,
                     is_hold, hold_cost, hold_shares, realtime_profit,
					 rise_alert, fall_alert)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        new_id, fund_code, fund["name"], today, 
                        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        None, None, None,  # 待刷新字段
                        1 if fund["is_hold"] else 0, fund["cost"], fund["shares"], None,
						rise_alert, fall_alert
                    ))
                    print(f"为基金 {fund_code} 初始化主表数据，上涨提醒={rise_alert}%，下跌提醒={fall_alert}%")

    def load_window_settings(self):
        """从配置文件加载窗口设置"""
        if os.path.exists(CONFIG_FILE):
            config = configparser.ConfigParser()
            try:
                config.read(CONFIG_FILE, encoding='utf-8')
                if 'Settings' in config:
                    x = int(config['Settings'].get('window_x', 100))
                    y = int(config['Settings'].get('window_y', 100))
                    width = int(config['Settings'].get('window_width', 1600))
                    height = int(config['Settings'].get('window_height', 900))
                    self.root.geometry(f"{width}x{height}+{x}+{y}")
                    return
            except Exception as e:
                print(f"加载窗口设置错误: {e}")
        
        # 默认窗口设置
        self.root.geometry("1600x900+100+100")

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
        main_frame = ttk.Frame(self.main_tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 1. 顶部状态条
        status_bar = ttk.Label(
            main_frame, 
            textvariable=self.status_var, 
            style="Status.TLabel"
        )
        status_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        # 2. 常用指数区域
        self.indices_frame = ttk.Frame(main_frame, padding="5 0 5 0")
        self.indices_frame.pack(fill=tk.X, pady=(0, 15))
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
        
        # 3. 左右分栏的框架（放在指数下方）
        container_frame = ttk.Frame(main_frame)
        container_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧基金列表区域（占40%宽度）
        left_frame = ttk.Frame(container_frame, style="Card.TFrame")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 基金列表标题和手动刷新按钮
        left_header = ttk.Frame(left_frame)
        left_header.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        ttk.Label(left_header, text="监控基金列表", style="SectionTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(left_header, text="手动刷新", command=self.manual_refresh).pack(side=tk.RIGHT)
        
        # 新增：查看历史按钮
        btn_container = ttk.Frame(left_header)
        btn_container.pack(side=tk.RIGHT)
        ttk.Button(btn_container, text="查看历史", command=self.open_history_viewer).pack(side=tk.LEFT, padx=5)
  
        # 基金列表（显示主表数据）
        self.fund_list_frame = ttk.Frame(left_frame)
        self.fund_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 基金列表配置
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
        
        # 设置列宽和对齐方式
        self.fund_tree.column("hold", width=50, anchor="center")
        self.fund_tree.column("code", width=60)
        self.fund_tree.column("name", width=150)
        self.fund_tree.column("unit_net_value", width=110, anchor="e")
        self.fund_tree.column("realtime_estimate", width=110, anchor="e")
        self.fund_tree.column("change_rate", width=90, anchor="e")
        self.fund_tree.column("hold_cost", width=80, anchor="e")
        self.fund_tree.column("hold_shares", width=90, anchor="e")
        self.fund_tree.column("realtime_profit", width=80, anchor="e")
        self.fund_tree.column("rise_alert", width=100, anchor="center")
        
        self.fund_tree.column("fall_alert", width=100, anchor="center")       
        # 添加滚动条
        tree_scroll = ttk.Scrollbar(
            self.fund_list_frame, 
            orient="vertical", 
            command=self.fund_tree.yview,
            style="Custom.TScrollbar"
        )
        self.fund_tree.configure(yscrollcommand=tree_scroll.set)
        
        # 布局树状图和滚动条
        self.fund_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定选中事件
        self.fund_tree.bind("<<TreeviewSelect>>", self.on_fund_select)
        
        # 右侧内容区域（占60%宽度）
        right_frame = ttk.Frame(container_frame, style="Card.TFrame")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 右侧内容容器
        right_content_frame = ttk.Frame(right_frame)
        right_content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 基金信息面板
        ttk.Label(right_content_frame, text="基金信息", style="SectionTitle.TLabel").pack(anchor=tk.W, pady=(0, 5))
        self.info_panel = ttk.Frame(right_content_frame, style="Inner.TFrame")
        self.info_panel.pack(fill=tk.X, pady=(0, 10))
        
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
        ttk.Label(right_content_frame, text="估值历史明细", style="SectionTitle.TLabel").pack(anchor=tk.W, pady=(0, 5))
        self.history_frame = ttk.Frame(right_content_frame, style="Inner.TFrame")
        self.history_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 确保列名设置正确且可见
        history_columns = ("trade_date", "trade_time", "estimate_time", "value", "change_rate")
        self.history_tree = ttk.Treeview(
            self.history_frame, 
            columns=history_columns, 
            show="headings",  # 确保显示表头
            height=6,
            style="HistoryTree.Treeview"
        )
        
        # 明确设置列标题，确保文字清晰
        self.history_tree.heading("trade_date", text="交易日期", anchor=tk.CENTER)
        self.history_tree.heading("trade_time", text="交易时间", anchor=tk.CENTER)
        self.history_tree.heading("estimate_time", text="估值时间点", anchor=tk.CENTER)
        self.history_tree.heading("value", text="估值", anchor=tk.CENTER)
        self.history_tree.heading("change_rate", text="涨跌幅(%)", anchor=tk.CENTER)
        
        # 调整列宽，确保内容可见，修复对齐方式参数
        self.history_tree.column("trade_date", width=110, anchor=tk.CENTER)
        self.history_tree.column("trade_time", width=130, anchor=tk.CENTER)
        self.history_tree.column("estimate_time", width=110, anchor=tk.CENTER)
        self.history_tree.column("value", width=100, anchor=tk.E)
        self.history_tree.column("change_rate", width=110, anchor=tk.E)
    
        
        # 历史表格滚动条
        history_scroll = ttk.Scrollbar(
            self.history_frame, 
            orient="vertical", 
            command=self.history_tree.yview,
            style="Custom.TScrollbar"
        )
        self.history_tree.configure(yscrollcommand=history_scroll.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # 图表区域
        ttk.Label(right_content_frame, text="基金估值走势", style="SectionTitle.TLabel").pack(anchor=tk.W, pady=(0, 5))
        self.chart_frame = ttk.Frame(right_content_frame, style="Inner.TFrame")
        self.chart_frame.pack(fill=tk.BOTH, expand=True)
        
        # 初始化图表
        self.init_chart()
        
        # 更新基金列表
        self.update_fund_list()

    def setup_styles(self):
        """设置界面样式，使历史表格表头与基金列表样式统一"""
        style = ttk.Style()
        
        # 基础样式
        style.configure(".", font=('SimHei', 10))
        
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
                       font=('SimHei', 11, 'bold'),
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
        style.configure("IndexName.TLabel",
                       font=('SimHei', 10, 'bold'),
                       foreground="#34495e")
        
        style.configure("IndexValue.TLabel",
                       font=('SimHei', 10),
                       foreground="#2c3e50")
        
        style.configure("IndexUp.TLabel",
                       font=('SimHei', 10, 'bold'),
                       foreground="#e74c3c")  # 红色表示上涨
        
        style.configure("IndexDown.TLabel",
                       font=('SimHei', 10, 'bold'),
                       foreground="#2ecc71")  # 绿色表示下跌
        
        style.configure("IndexFlat.TLabel",
                       font=('SimHei', 10),
                       foreground="#7f8c8d")  # 灰色表示持平
        
        # 基金列表树状图样式 - 基础样式定义
        base_tree_style = {
            "rowheight": 25,
            "fieldbackground": "#ffffff",
            "background": "#ffffff",
            "foreground": "#333333",
            "font": ('SimHei', 10)
        }
        
        # 表头基础样式定义
        base_header_style = {
            "font": ('SimHei', 10, 'bold'),
            "background": "#f1c40f",  # 统一的表头背景色
            "foreground": "#2c3e50",  # 统一的表头文字色
            "padding": (5, 3),
            "bordercolor": "#e6b800",
            "borderwidth": 1,
            "relief": tk.RAISED
        }
        
        # 表头交互样式定义
        base_header_map = {
            "background": [('active', '#f8d775'), ('pressed', '#e6b800')],
            "foreground": [('active', '#2c3e50'), ('pressed', '#2c3e50')]
        }
        
        # 表格行交互样式定义
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
        
        # 基金列表树状图样式 - 应用基础样式
        style.configure("FundTree.Treeview", **base_tree_style)
        style.configure("FundTree.Treeview.Heading",** base_header_style)
        style.map("FundTree.Treeview.Heading", **base_header_map)
        style.map("FundTree.Treeview",** base_row_map)
        
        # 历史表格样式 - 与基金列表保持一致
        style.configure("HistoryTree.Treeview",** base_tree_style)
        style.configure("HistoryTree.Treeview.Heading", **base_header_style)
        style.map("HistoryTree.Treeview.Heading",** base_header_map)
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
        self.fig, self.ax = plt.subplots(figsize=(16, 5), dpi=100)
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
		
    # 实现confirm_reset_database方法
    def confirm_reset_database(self):
        """确认重置数据库"""
        if messagebox.askyesno("确认", "确定要重置数据库吗？当前数据将被备份并创建新数据库。"):
            secure_reset_database()
            # 重新加载数据
            self.load_funds_data()
            self.update_fund_list()
            self.update_existing_funds_list()
            messagebox.showinfo("完成", "数据库已重置并备份")
		

    def load_settings(self):
        """加载设置"""
        with db_connection() as cursor:
            cursor.execute("SELECT value FROM settings WHERE key = 'refresh_interval'")
            result = cursor.fetchone()
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
        self.save_window_settings()
        
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
        interval_minutes = 10  # 固定X轴刻度为5分钟
    
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
        self.fig.tight_layout()
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
        self.fig.tight_layout()
        self.canvas.draw()
    def update_fund_list(self):
        """增量更新基金列表（只更新变化的单元格，保留列表结构）"""
        today = datetime.date.today().strftime('%Y-%m-%d')
        updated = False
        
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
            
            if main_table_data:
                unit_net_value = f"{main_table_data['unit_net_value']:.4f}" if main_table_data['unit_net_value'] else "-"
                realtime_profit = f"{main_table_data['realtime_profit']:.2f}" if main_table_data['realtime_profit'] else "-"
            else:
                unit_net_value = f"{fund['latest_net_value']:.4f}" if fund["latest_net_value"] else "-"
            
			#获取提醒阈值（新增）
            rise_alert = f"{fund['rise_alert']:.2f}%" if fund.get("rise_alert") not in (None, 0) else "-"
            fall_alert = f"{fund['fall_alert']:.2f}%" if fund.get("fall_alert") not in (None, 0) else "-"
            # 组装显示数据（与列索引对应）
            new_values = {
                0: hold_mark,
                1: fund["code"],
                2: fund["name"],
                3: unit_net_value,
                4: realtime_estimate,
                5: change_rate,
                6: cost,
                7: shares,
                8: realtime_profit,
                9: rise_alert,
                10: fall_alert,
            }
            
            # 增量更新逻辑
            if fund_code in self.code_to_item_id:
                # 已有该行，只更新变化的单元格
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
        
        # 保持标签样式配置
        self.fund_tree.tag_configure("up", foreground="red")
        self.fund_tree.tag_configure("down", foreground="green")
        
        return updated
    def get_latest_detail_from_db(self, fund_code, date):
        """从明细表获取最新的估值数据"""
        try:
            with db_connection() as cursor:
                cursor.execute('''
                SELECT realtime_estimate, change_rate 
                FROM fund_estimate_details 
                WHERE fund_code = ? AND trade_date = ?
                ORDER BY estimate_time DESC 
                LIMIT 1
                ''', (fund_code, date))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "value": result[0],
                        "rate": result[1]
                    }
            return None
        except Exception as e:
            print(f"获取明细表最新数据出错(fund:{fund_code}): {str(e)}")
            return None

    def get_main_table_today_latest(self, fund_code, date):
        """从主表获取当天最新记录（包含昨日单位净值）"""
        try:
            with db_connection() as cursor:
                cursor.execute('''
                SELECT unit_net_value, realtime_estimate, change_rate, realtime_profit 
                FROM fund_estimate_main 
                WHERE fund_code = ? AND trade_date = ?
                ORDER BY trade_time DESC 
                LIMIT 1
                ''', (fund_code, date))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "unit_net_value": result[0],
                        "realtime_estimate": result[1],
                        "change_rate": result[2],
                        "realtime_profit": result[3]
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
    
        try:
            now = self.get_now()
            current_time = now.time()
    
            # --- 1. 检查是否在交易时段 ---
            if not self.is_trading_time():
                # 判断是“盘前”还是“盘后”
                if current_time < datetime.time(9, 30):
                    # 🕐 盘前：计算到 9:30 的等待时间
                    wait_until = now.replace(hour=9, minute=30, second=0, microsecond=0)
                    if wait_until < now:  # 防止跨日错误
                        wait_until += datetime.timedelta(days=1)
                    
                    wait_seconds = (wait_until - now).total_seconds()
                    wait_ms = int(wait_seconds * 1000)
                    
                    status_msg = f"⏳ 等待开盘... {wait_until.strftime('%H:%M:%S')} 开始刷新"
                    self.status_var.set(status_msg)
                    self._write_log(f"盘前等待，将在 {wait_until.strftime('%H:%M:%S')} 开始首次刷新")
                    
                    #调度到 9:30 执行
                    self.root.after(wait_ms, self.perform_periodic_refresh)
                    return
    
                else:
                    #盘后：15:00 之后，今日结束
                    self.status_var.set("今日监控结束，明天再见")
                    self._write_log("今日监控结束")
                    self.is_monitoring = False
                    return
    
            # --- 2. 交易时段内：执行刷新 ---
            self._write_log(f"开始刷新数据 @ {now.strftime('%H:%M:%S')}")
            success_count, fail_count = self.refresh_all_funds(force=False)
            
            self.update_fund_list()
            if self.selected_fund:
                self.update_history_tree()
                self.update_chart()
    
            next_refresh_dt = self.calculate_next_refresh_time()
            status_msg = (
                f"刷新完成 | 成功:{success_count} 失败:{fail_count} | "
                f"下次: {next_refresh_dt.strftime('%H:%M')}"
            )
            self.status_var.set(status_msg)
            self._write_log(status_msg)
    
            # --- 3. 调度下一次刷新 ---
            wait_seconds = (next_refresh_dt - self.get_now()).total_seconds()
            if wait_seconds > 0:
                self.root.after(int(wait_seconds * 1000), self.perform_periodic_refresh)
            else:
                self.root.after(1000, self.perform_periodic_refresh)
    
        except Exception as e:
            self._write_log( f"刷新异常: {e}10秒后重试",'error')
            self.root.after(10000, self.perform_periodic_refresh)  # 10秒后重试
			
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
        
        with db_connection() as cursor:
            # ---------------------- 处理主表：更新或插入当天最新记录 ----------------------
            cursor.execute('''
            SELECT id FROM fund_estimate_main 
            WHERE fund_code = ? AND trade_date = ?
            ''', (fund["code"], today))
            main_record = cursor.fetchone()
            
            if main_record:
                # 有记录则更新（主表存储当天最新估值）- 修复：增加对当前估值和涨跌幅的更新
                cursor.execute('''
                UPDATE fund_estimate_main 
                SET trade_time = ?, unit_net_value = ?, realtime_estimate = ?, 
                    change_rate = ?, realtime_profit = ?
                WHERE fund_code = ? AND trade_date = ?
                ''', (current_datetime, estimate_data["dwjz"], estimate_data["value"],
                      estimate_data["rate"], realtime_profit, fund["code"], today))
            else:
                # 无记录则插入新记录
                cursor.execute('''
                SELECT MAX(id) FROM fund_estimate_main WHERE fund_code = ?
                ''', (fund["code"],))
                max_id = cursor.fetchone()[0]
                new_id = 1 if max_id is None else max_id + 1
                
                cursor.execute('''
                INSERT INTO fund_estimate_main 
                (id, fund_code, fund_name, trade_date, trade_time,
                 unit_net_value, realtime_estimate, change_rate,
                 is_hold, hold_cost, hold_shares, realtime_profit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (new_id, fund["code"], fund["name"], today, current_datetime,
                      estimate_data["dwjz"], estimate_data["value"], estimate_data["rate"],
                      1 if fund["is_hold"] else 0, fund["cost"], fund["shares"], realtime_profit))
            
            # ---------------------- 处理明细表：插入固定间隔的估值记录 ----------------------
            # 检查明细表是否已有该基金当天该时间点的记录（避免重复存储）
            cursor.execute('''
            SELECT id FROM fund_estimate_details 
            WHERE fund_code = ? AND trade_date = ? AND estimate_time = ?
            ''', (fund["code"], today, estimate_time_str))
            
            if not cursor.fetchone():
                # 获取明细表最大ID
                cursor.execute('''
                SELECT MAX(id) FROM fund_estimate_details WHERE fund_code = ?
                ''', (fund["code"],))
                max_detail_id = cursor.fetchone()[0]
                new_detail_id = 1 if max_detail_id is None else max_detail_id + 1
                
                # 插入明细记录（包含收盘标记）
                cursor.execute('''
                INSERT INTO fund_estimate_details 
                (id, fund_code, trade_date, trade_time, estimate_time,
                 realtime_estimate, change_rate, is_close_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (new_detail_id, fund["code"], today, current_datetime,
                      estimate_time_str, estimate_data["value"], estimate_data["rate"], is_close_data))
        
        # 更新基金对象的当前估值和涨跌幅
        fund["current_value"] = estimate_data["value"]
        fund["change_rate"] = estimate_data["rate"]
        fund["update_time"] = current_datetime

    def load_fund_history(self, fund, date):
        """从数据库明细表加载基金的历史估值数据（优化：非交易时段不过滤数据）"""
        fund["history"] = []
        try:
            with db_connection() as cursor:
                cursor.execute('''
                SELECT trade_date, trade_time, estimate_time, realtime_estimate, change_rate, is_close_data 
                FROM fund_estimate_details 
                WHERE fund_code = ? AND trade_date = ?
                ORDER BY trade_time, estimate_time
                ''', (fund["code"], date))
                
                history_data = cursor.fetchall()
                
                # 非交易时段不过滤数据，确保能看到所有记录（包括收盘数据）
                if self.is_trading_time():
                    # 交易时段过滤非交易时间数据
                    filtered_data = []
                    for item in history_data:
                        trade_date, trade_time, estimate_time, value, rate, is_close = item
                        time_str = f"{trade_date} {estimate_time}"
                        try:
                            time_obj = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                            hour, minute = time_obj.hour, time_obj.minute
                            time_in_min = hour * 60 + minute
                            
                            # 只保留 9:00-11:30 或 13:30-15:00 的数据
                            is_morning = (9*60) <= time_in_min <= (11*60 + 30)
                            is_afternoon = (13*60 + 30) <= time_in_min <= (15*60)
                            if is_morning or is_afternoon or is_close:  # 保留收盘数据
                                filtered_data.append(item)
                        except:
                            continue  # 跳过格式错误的时间
                    fund["history"] = filtered_data
                else:
                    # 非交易时段显示所有数据
                    fund["history"] = history_data
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
