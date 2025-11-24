import os
import csv
import tkinter as tk
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from tkinter import ttk, messagebox, simpledialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
from tkinter.filedialog import asksaveasfilename


# 导入中文字体设置
from utils.sys_chinese_font import get_best_chinese_font
# 从数据库工具类导入连接管理器
from utils.db.database import db_connection

# 配置中文字体
AVAILABLE_CHINESE_FONT = get_best_chinese_font()
plt.rcParams["font.family"] = [AVAILABLE_CHINESE_FONT]
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题
UI_FONT_SIZE = 14  # 所有控件的统一字体大小
# 数据库文件路径（与主程序保持一致）
DB_FILE = "fund_data.db"

class FundHistoryViewer:
    def __init__(self, root, parent, fund_code, fund_name):
        self.root = root
        self.parent = parent  # 保存主窗口实例，用于计算位置
        self.root.title(f"基金历史估值记录 - {fund_name}({fund_code})")
        
        # 1. 预设子窗口尺寸（可根据需求调整）
        window_width = 1200
        window_height = 800
        self.root.geometry(f"{window_width}x{window_height}")
        
        # 2. 计算主窗口正中心的坐标
        self._set_window_center(window_width, window_height)
        
        self.fund_code = fund_code
        self.fund_name = fund_name
        self.selected_main_record = None
        
        # 设置默认日期范围（结束日期为今天，开始日期为一个月前）
        self.end_date = datetime.today()
        self.start_date = self.end_date - timedelta(days=30)
        
        # 创建界面
        self.create_widgets()
        
        # 加载数据
        self.load_history_main_records()

    def create_widgets(self):
        """创建主界面控件，统一使用 grid 布局"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
    
        # 控制区域：日期选择 + 操作按钮
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
    
        # 设置列权重：控制两个区域的宽度比例
        control_frame.columnconfigure(0, weight=4)  # 日期区域 占 40%
        control_frame.columnconfigure(1, weight=6)  # 操作区域 占 60%
    
        # 日期选择区域
        date_frame = ttk.LabelFrame(control_frame, text="查询日期范围", padding="10")
        date_frame.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    
        # 使用 grid 在 date_frame 内布局
        ttk.Label(date_frame, text="开始日期:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.start_date_var = tk.StringVar(value=self.start_date.strftime("%Y-%m-%d"))
        self.start_date_entry = ttk.Entry(date_frame, textvariable=self.start_date_var, width=12)
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # 结束日期
        ttk.Label(date_frame, text="结束日期:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.end_date_var = tk.StringVar(value=self.end_date.strftime("%Y-%m-%d"))
        self.end_date_entry = ttk.Entry(date_frame, textvariable=self.end_date_var, width=12)
        self.end_date_entry.grid(row=0, column=3, padx=5, pady=5)
        
        # 查询按钮
        ttk.Button(date_frame, text="查询", command=self.on_query).grid(row=0, column=4, padx=10, pady=5)
        
        # 操作按钮区域
        export_frame = ttk.LabelFrame(control_frame, text="操作", padding="10")
        export_frame.grid(row=0, column=1, sticky="ew")
    
        # 在 export_frame 内使用 grid 布局按钮（横向排列）
        export_frame.columnconfigure(0, weight=1)
        export_frame.columnconfigure(1, weight=1)
        export_frame.columnconfigure(2, weight=1)
    
        ttk.Button(export_frame, text="导出数据", command=self.export_data).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(export_frame, text="分析加仓策略", command=self.analyze_dca_strategy).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
		
        # 2. 历史主记录表格
        main_record_frame = ttk.LabelFrame(main_frame, text="历史估值主记录", padding="10")
        main_record_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 表格配置
        columns = ("trade_date", "unit_net_value", "realtime_estimate", "change_rate", "realtime_profit")
        self.main_record_tree = ttk.Treeview(
            main_record_frame, 
            columns=columns, 
            show="headings",
            height=8
        )
        
        # 设置列标题和宽度
        self.main_record_tree.heading("trade_date", text="交易日期")
        self.main_record_tree.heading("unit_net_value", text="单位净值(昨)")
        self.main_record_tree.heading("realtime_estimate", text="实时估值(今)")
        self.main_record_tree.heading("change_rate", text="涨跌幅(%)")
        self.main_record_tree.heading("realtime_profit", text="当日盈亏")
        
        self.main_record_tree.column("trade_date", width=120, anchor="center")
        self.main_record_tree.column("unit_net_value", width=100, anchor="e")
        self.main_record_tree.column("realtime_estimate", width=100, anchor="e")
        self.main_record_tree.column("change_rate", width=100, anchor="e")
        self.main_record_tree.column("realtime_profit", width=100, anchor="e")
        
        # 添加滚动条
        main_tree_scroll = ttk.Scrollbar(
            main_record_frame, 
            orient="vertical", 
            command=self.main_record_tree.yview
        )
        self.main_record_tree.configure(yscrollcommand=main_tree_scroll.set)
        
        # 布局
        self.main_record_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        main_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定选中事件
        self.main_record_tree.bind("<<TreeviewSelect>>", self.on_main_record_select)
        
        # 3. 历史明细和图表区域
        detail_frame = ttk.Frame(main_frame)
        detail_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧明细表格
        detail_table_frame = ttk.LabelFrame(detail_frame, text="当日估值明细记录", padding="10")
        detail_table_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 明细表格配置
        detail_columns = ("estimate_time", "realtime_estimate", "change_rate", "is_close_data")
        self.detail_tree = ttk.Treeview(
            detail_table_frame, 
            columns=detail_columns, 
            show="headings",
            height=10
        )
        
        # 设置明细列标题和宽度
        self.detail_tree.heading("estimate_time", text="估值时间")
        self.detail_tree.heading("realtime_estimate", text="估值")
        self.detail_tree.heading("change_rate", text="涨跌幅(%)")
        self.detail_tree.heading("is_close_data", text="是否收盘")
        
        self.detail_tree.column("estimate_time", width=120, anchor="center")
        self.detail_tree.column("realtime_estimate", width=100, anchor="e")
        self.detail_tree.column("change_rate", width=100, anchor="e")
        self.detail_tree.column("is_close_data", width=80, anchor="center")
        
        # 添加明细滚动条
        detail_tree_scroll = ttk.Scrollbar(
            detail_table_frame, 
            orient="vertical", 
            command=self.detail_tree.yview
        )
        self.detail_tree.configure(yscrollcommand=detail_tree_scroll.set)
        
        # 布局明细表格
        self.detail_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 右侧图表
        chart_frame = ttk.LabelFrame(detail_frame, text="当日估值走势图", padding="10")
        chart_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 初始化图表
        self.fig, self.ax = plt.subplots(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 设置表格样式
        self.setup_styles()
    
    def setup_styles1(self):
        """设置表格样式"""
        style = ttk.Style()
        style.configure(".", font=(AVAILABLE_CHINESE_FONT, 10))
        
        # 主记录表格样式
        style.configure("MainRecord.Treeview", rowheight=25)
        style.configure("MainRecord.Treeview.Heading", 
                       font=(AVAILABLE_CHINESE_FONT, 10, 'bold'),
                       background="#f0f0f0")
        
        # 明细表格样式
        style.configure("Detail.Treeview", rowheight=25)
        style.configure("Detail.Treeview.Heading", 
                       font=(AVAILABLE_CHINESE_FONT, 10, 'bold'),
                       background="#f0f0f0")
        
        # 涨跌颜色标签
        self.main_record_tree.tag_configure("up", foreground="red")
        self.main_record_tree.tag_configure("down", foreground="green")
        self.detail_tree.tag_configure("up", foreground="red")
        self.detail_tree.tag_configure("down", foreground="green")
        self.detail_tree.tag_configure("close", font=(AVAILABLE_CHINESE_FONT, 10, 'bold'))
    def setup_styles(self):
        """设置表格样式（使用全局字体大小）"""
        style = ttk.Style()
        
        # 全局默认字体
        style.configure(".", font=(AVAILABLE_CHINESE_FONT, UI_FONT_SIZE))
        
        # 主记录表格样式
        row_height = UI_FONT_SIZE + 16  # 经验公式：行高 = 字号 + 10~16
        style.configure(
            "MainRecord.Treeview", 
            font=(AVAILABLE_CHINESE_FONT, UI_FONT_SIZE),
            rowheight=row_height
        )
        style.configure(
            "MainRecord.Treeview.Heading", 
            font=(AVAILABLE_CHINESE_FONT, UI_FONT_SIZE, 'bold'),
            background="#f0f0f0"
        )
        
        # 明细表格样式
        style.configure(
            "Detail.Treeview", 
            font=(AVAILABLE_CHINESE_FONT, UI_FONT_SIZE),
            rowheight=row_height
        )
        style.configure(
            "Detail.Treeview.Heading", 
            font=(AVAILABLE_CHINESE_FONT, UI_FONT_SIZE, 'bold'),
            background="#f0f0f0"
        )
        
        # 涨跌标签
        self.main_record_tree.tag_configure("up", foreground="red")
        self.main_record_tree.tag_configure("down", foreground="green")
        self.detail_tree.tag_configure("up", foreground="red")
        self.detail_tree.tag_configure("down", foreground="green")
        self.detail_tree.tag_configure("close", font=(AVAILABLE_CHINESE_FONT, UI_FONT_SIZE, 'bold'))
    def on_query(self):
        """根据日期范围查询历史记录"""
        try:
            # 解析日期
            start_date = datetime.strptime(self.start_date_var.get(), "%Y-%m-%d")
            end_date = datetime.strptime(self.end_date_var.get(), "%Y-%m-%d")
            
            if start_date > end_date:
                messagebox.showerror("错误", "开始日期不能晚于结束日期")
                return
                
            self.start_date = start_date
            self.end_date = end_date
            
            # 加载数据
            self.load_history_main_records()
            
        except ValueError:
            messagebox.showerror("错误", "日期格式不正确，请使用YYYY-MM-DD格式")
    
    def load_history_main_records(self):
        """加载指定日期范围内的历史主记录，并默认选中第一行"""
        # 清空表格
        for item in self.main_record_tree.get_children():
            self.main_record_tree.delete(item)
        
        try:
            with db_connection() as conn:
                result = conn.execute('''
                    SELECT trade_date, unit_net_value, realtime_estimate, change_rate, realtime_profit 
                    FROM fund_estimate_main 
                    WHERE fund_code = ? AND trade_date BETWEEN ? AND ?
                    ORDER BY trade_date DESC
                ''', (
                    self.fund_code,
                    self.start_date.strftime("%Y-%m-%d"),
                    self.end_date.strftime("%Y-%m-%d")
                ))
                
                records = result.fetchall()
                
                for record in records:
                    trade_date, unit_net_value, realtime_estimate, change_rate, realtime_profit = record
                    
                    # 格式化显示
                    unit_net_value_str = f"{unit_net_value:.4f}" if unit_net_value else "-"
                    realtime_estimate_str = f"{realtime_estimate:.4f}" if realtime_estimate else "-"
                    change_rate_str = f"{change_rate:.2f}%" if change_rate else "-"
                    realtime_profit_str = f"{realtime_profit:.2f}" if realtime_profit else "-"
                    
                    # 设置涨跌标签
                    tag = ""
                    if change_rate is not None:
                        tag = "up" if change_rate >= 0 else "down"
                    
                    self.main_record_tree.insert("", tk.END, 
                                               values=(trade_date, unit_net_value_str, 
                                                       realtime_estimate_str, change_rate_str, 
                                                       realtime_profit_str),
                                               tags=(tag,))
                       
            # 新增：如果有记录，默认选中第一行并加载详情
            items = self.main_record_tree.get_children()
            if items:  # 检查是否有记录
                # 选中第一行
                self.main_record_tree.selection_set(items[0])
                # 触发选中事件，加载详情和图表
                self.on_main_record_select(None)
                
        except Exception as e:
            messagebox.showerror("错误", f"加载历史记录失败: {str(e)}")
    
    def on_main_record_select(self, event):
        """选中主记录后加载对应的明细和图表"""
        selected_items = self.main_record_tree.selection()
        if not selected_items:
            self.selected_main_record = None
            return
        
        item = selected_items[0]
        self.selected_main_record = self.main_record_tree.item(item, "values")
        trade_date = self.selected_main_record[0]
        
        # 加载明细数据
        self.load_detail_records(trade_date)
        
        # 绘制图表
        self.plot_detail_chart(trade_date)
    
    def load_detail_records(self, trade_date):
        """加载指定日期的明细记录"""
        # 清空表格
        for item in self.detail_tree.get_children():
            self.detail_tree.delete(item)
        
        try:
            with db_connection() as conn:
                result = conn.execute('''
                    SELECT estimate_time, realtime_estimate, change_rate, is_close_data 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ?
                    ORDER BY estimate_time
                ''', (self.fund_code, trade_date))
                
                records = result.fetchall()
                
                for record in records:
                    estimate_time, realtime_estimate, change_rate, is_close_data = record
                    
                    # 格式化显示
                    realtime_estimate_str = f"{realtime_estimate:.4f}" if realtime_estimate else "-"
                    change_rate_str = f"{change_rate:.2f}%" if change_rate else "-"
                    is_close_str = "是" if is_close_data else "否"
                    
                    # 设置标签
                    tags = []
                    if change_rate is not None:  # ✅ 修复：使用 is not None 避免 0.0 被误判
                        tags.append("up" if change_rate >= 0 else "down")
                    if is_close_data:
                        tags.append("close")
                    
                    self.detail_tree.insert("", tk.END, 
                                          values=(estimate_time, realtime_estimate_str, 
                                                  change_rate_str, is_close_str),
                                          tags=tuple(tags))
            
        except Exception as e:
            messagebox.showerror("错误", f"加载明细记录失败: {str(e)}")
    
    def plot_detail_chart(self, trade_date):
        """绘制指定日期的估值走势图"""
        self.ax.clear()
        
        try:
            with db_connection() as conn:
                # 获取主数据
                result = conn.execute('''
                    SELECT estimate_time, realtime_estimate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ?
                    ORDER BY estimate_time
                ''', (self.fund_code, trade_date))
                
                records = result.fetchall()
                
                if not records or len(records) < 2:
                    self.ax.text(0.5, 0.5, "没有足够的数据绘制图表", 
                                ha="center", va="center", transform=self.ax.transAxes)
                    self.fig.tight_layout()
                    self.canvas.draw()
                    return
                
                # 准备数据
                times = []
                values = []
                for record in records:
                    estimate_time, realtime_estimate = record
                    # 转换为datetime对象
                    time_str = f"{trade_date} {estimate_time}"
                    try:
                        time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                        times.append(time_obj)
                        values.append(realtime_estimate)
                    except ValueError:
                        continue  # 跳过格式错误的时间
                
                # 绘制主趋势
                self.ax.plot(times, values, 'b-', linewidth=2, label='估值走势')
                self.ax.scatter(times, values, color='red', s=30, alpha=0.7)
                
                # 查询并标记收盘点
                close_result = conn.execute('''
                    SELECT estimate_time, realtime_estimate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ? AND is_close_data = 1
                ''', (self.fund_code, trade_date))
                
                close_data = close_result.fetchone()
                if close_data:
                    close_time_str = f"{trade_date} {close_data[0]}"
                    try:
                        close_time = datetime.strptime(close_time_str, "%Y-%m-%d %H:%M:%S")
                        self.ax.scatter(close_time, close_data[1], 
                                       color='green', s=80, alpha=0.8, 
                                       marker='*', label='收盘估值')
                    except ValueError:
                        pass  # 时间解析失败则跳过
                
                # 设置图表属性
                self.ax.set_title(f"{self.fund_name} {trade_date} 估值走势", fontsize=12)
                self.ax.set_xlabel('时间', fontsize=10)
                self.ax.set_ylabel('估值 (元)', fontsize=10)
                self.ax.grid(True, linestyle='--', alpha=0.7)
                
                # 设置x轴时间格式
                self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
                
                # 添加图例
                self.ax.legend()
                
                self.fig.tight_layout()
                self.canvas.draw()
                
        except Exception as e:
            self.ax.text(0.5, 0.5, f"绘制图表失败: {str(e)}", 
                        ha="center", va="center", transform=self.ax.transAxes)
            self.fig.tight_layout()
            self.canvas.draw()

    def _set_window_center(self, window_width, window_height):
        """私有方法：计算并设置子窗口在主窗口正上方居中位置"""
        # 获取主窗口的位置和尺寸（主窗口必须已显示，否则坐标为 (0,0)）
        parent_x = self.parent.winfo_x()  # 主窗口左上角 x 坐标
        parent_y = self.parent.winfo_y()  # 主窗口左上角 y 坐标
        parent_width = self.parent.winfo_width()  # 主窗口宽度
        parent_height = self.parent.winfo_height()  # 主窗口高度

        # 计算子窗口的左上角坐标（让子窗口中心与主窗口中心对齐）
        x = parent_x + (parent_width - window_width) // 2
        y = parent_y + (parent_height - window_height) // 2

        # 特殊情况处理：如果主窗口未正常获取尺寸（如首次打开），则显示在屏幕中心
        if parent_width == 1 or parent_height == 1:
            # 获取屏幕尺寸
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2

        # 固定子窗口位置
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # 设置子窗口为模态
        self.root.transient(self.parent)
        self.root.grab_set()
    def analyze_dca_strategy(self):
        """分析分批加仓策略：基于历史最低估值设定基点，按百分比下跌生成加仓档位"""
        try:
            start_date = self.start_date.strftime("%Y-%m-%d")
            end_date = self.end_date.strftime("%Y-%m-%d")
    
            # 获取历史估值数据（用于计算历史最低）
            with db_connection() as conn:
                result  = conn.execute('''
                    SELECT realtime_estimate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date BETWEEN ? AND ?
                ''', (self.fund_code, start_date, end_date))
                values = [row[0] for row in result.fetchall() if row[0] is not None]
    
            if not values:
                messagebox.showinfo("分析结果", "当前查询范围内无估值数据，无法分析。")
                return
    
            min_val = min(values)
            max_val = max(values)
            avg_val = sum(values) / len(values)
    
            # 加仓策略配置：回撤比例与资金分配
            DCA_CONFIG = [
                {"label": "首次建仓", "desc": "0.00%", "drop": 0.00, "funds_ratio": 0.10, "color": ""},
                {"label": "第一次加仓", "desc": "跌≥5%", "drop": 0.05, "funds_ratio": 0.20, "color": ""},
                {"label": "第二次加仓", "desc": "跌≥10%", "drop": 0.10, "funds_ratio": 0.30, "color": ""},
                {"label": "第三次加仓", "desc": "跌≥15%", "drop": 0.15, "funds_ratio": 0.40, "color": ""},
            ]
    
            TOTAL_CAPITAL = 20000  # 总资金（可配置）
    
            # 生成加仓档位
            levels = []
            for config in DCA_CONFIG:
                if config["drop"] == 0:
                    lower_bound = min_val - 0.0050
                    upper_bound = min_val + 0.0050
                    threshold = lower_bound
                    level_str = f"{lower_bound:.4f} ~ {upper_bound:.4f}"
                else:
                    threshold = min_val * (1 - config["drop"])
                    level_str = f"≤ {threshold:.4f} ({config['desc']})"
                levels.append({
                    "label": config["label"],
                    "desc": config["desc"],
                    "threshold": threshold,
                    "funds_ratio": config["funds_ratio"],
                    "level_str": level_str,
                    "color": config["color"]
                })
    
            # ==================== 获取当日估值：最新 + 最低 ====================
            latest_estimate = None
            intraday_low = None
    
            # 从数据库获取当日所有估值
            with db_connection() as conn:
                result = conn.execute('''
                    SELECT realtime_estimate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND DATE(trade_date) = DATE('now')
                    ORDER BY estimate_time DESC
                ''', (self.fund_code,))
                today_values = [row[0] for row in result.fetchall() if row[0] is not None]
    
                if today_values:
                    latest_estimate = today_values[0]  # 最新一条
                    intraday_low = min(today_values)
    
            # 备用：从界面表格获取当日数据
            if not today_values and self.main_record_tree.get_children():
                values_from_ui = []
                for item in self.main_record_tree.get_children():
                    values = self.main_record_tree.item(item)["values"]
                    if len(values) > 2:
                        try:
                            val = float(values[2])
                            values_from_ui.append(val)
                        except (ValueError, TypeError):
                            continue
                if values_from_ui:
                    latest_estimate = values_from_ui[0]
                    intraday_low = min(values_from_ui)
    
            # ==================== 判断触发层级（使用当日最低估值） ====================
            triggered_level = None
            check_val = intraday_low if intraday_low is not None else latest_estimate
    
            if check_val is not None:
                for level in reversed(levels):
                    if level["desc"] == "0.00%":
                        lower_bound = min_val - 0.0050
                        upper_bound = min_val + 0.0050
                        if lower_bound <= check_val <= upper_bound:
                            triggered_level = level
                            break
                    else:
                        if check_val <= level["threshold"]:
                            triggered_level = level
                            break
    
            # ==================== 构建分析文本 ====================
            result_text = (
                f"基金分批加仓策略分析\n"
                f"────────────────────────────────\n"
                f"基金代码：{self.fund_code}\n"
                f"基金名称：{self.fund_name}\n"
                f"查询区间：{start_date} 至 {end_date}\n"
                f"数据量：{len(values):,} 个估值点\n"
                f"统计：最低={min_val:.4f}，最高={max_val:.4f}，平均={avg_val:.4f}\n\n"
    
                f"基准设定\n"
                f"历史最低估值：{min_val:.4f}\n"
                f"首次建仓区间：{min_val - 0.0050:.4f} ~ {min_val + 0.0050:.4f}\n"
                f"后续加仓：基于历史最低估值每下跌一定比例触发\n\n"
    
                f"分批加仓建议（越跌越买）：\n"
            )
    
            # 输出每一档
            for level in levels:
                mark = "✅" if (check_val and (
                    (level["desc"] == "0.00%" and (min_val - 0.0050) <= check_val <= (min_val + 0.0050)) or
                    (level["desc"] != "0.00%" and check_val <= level["threshold"])
                )) else "○"
                result_text += f"{mark} {level['color']} {level['label']}: {level['level_str']}\n"
    
            # 显示盘中估值
            result_text += f"\n盘中估值监测：\n"
            if latest_estimate is not None and intraday_low is not None:
                result_text += f"  最新估值（Last）：{latest_estimate:.4f}\n"
                result_text += f"  当日最低（Low）：{intraday_low:.4f}\n"
                if triggered_level:
                    result_text += f"\n强烈建议：盘中已触及【{triggered_level['label']}】区间！\n"
                    result_text += f"   可考虑执行对应加仓操作。\n"
                else:
                    result_text += f"\n建议：尚未进入加仓区间，继续观望。\n"
            elif latest_estimate is not None:
                result_text += f"  当前估值：{latest_estimate:.4f}\n"
                result_text += f"  提示：暂无完整盘中数据，建议参考实时行情。\n"
            else:
                result_text += f"  当前估值：获取失败\n"
    
            # 资金分配表示例（对齐优化版）
            result_text += f"\n总资金分配示例（假设总资金为 {TOTAL_CAPITAL:,} 元）\n"
            result_text += "─────────────────────────────────────────────────────\n"
    
            # 定义每列宽度（字符数）
            COL_STAGE = 14      # 阶段
            COL_CONDITION = 24  # 触发条件
            COL_INVEST = 18     # 投入资金
            COL_CUMULATIVE = 14 # 累计投入
    
            result_text += (
                f"{'阶段':<{COL_STAGE}}"
                f"{'触发条件（估值）':<{COL_CONDITION}}"
                f"{'投入资金':<{COL_INVEST}}"
                f"{'累计投入':<{COL_CUMULATIVE}}\n"
            )
            result_text += "─────────────────────────────────────────────────────\n"
    
            # 数据行
            cumulative = 0
            for level in levels:
                invest = TOTAL_CAPITAL * level["funds_ratio"]
                cumulative += invest
                condition = level["level_str"]
                amount_str = f"{int(invest):,}元 ({int(level['funds_ratio']*100)}%)"
                cumul_str = f"{int(cumulative):,}元"
    
                result_text += (
                    f"{level['label']:<{COL_STAGE}}"
                    f"{condition:<{COL_CONDITION}}"
                    f"{amount_str:<{COL_INVEST}}"
                    f"{cumul_str:<{COL_CUMULATIVE}}\n"
                )
    
            result_text += f"\n说明：以历史最低估值 {min_val:.4f} 为锚点，越跌越买，逐步重仓。\n"
            result_text += "提示：本策略基于历史估值分析，仅供参考，投资需谨慎。"
    
            # 显示结果
            self._show_analysis_result("加仓策略分析结果", result_text)
    
        except Exception as e:
            messagebox.showerror("分析失败", f"执行分析时发生错误：\n{str(e)}")

    def _show_analysis_result(self, title, text):
        """
        显示可复制的分析结果弹窗
        支持文本展示、滚动条、复制按钮和关闭功能
        """
        # 创建顶级弹窗
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("700x550")  # 适配宽文本内容
        dialog.configure(bg="#f0f0f0")
        
        # 设置为模态窗口（阻塞父窗口操作）
        dialog.transient(self.root)
        dialog.grab_set()  # 捕获输入焦点
        self._center_window(dialog, 700, 550, parent=self.root)
        dialog.focus_force()  # 强制焦点到当前窗口
    
        # 主内容框架（带内边距）
        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
    
        # 文本框（支持换行、高亮、只读）
        #text_widget = tk.Text(
        #    frame,
        #    wrap=tk.WORD,
        #    font=("Consolas", 10),  # 等宽字体，适合数据对齐
        #    bg="white",
        #    fg="black",
        #    relief="flat",
        #    spacing1=6,   # 段前间距
        #    spacing2=2,   # 行间距
        #    spacing3=6    # 段后间距
        #)
        text_widget = tk.Text(
            frame,
            wrap=tk.WORD,
            font=("Consolas", 10),  # 必须使用等宽字体
            bg="white",
            fg="black",
            relief="flat"
        )
		
        # 滚动条
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
    
        # 布局文本框和滚动条
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
        # 插入分析结果文本
        text_widget.insert(tk.END, text)
        text_widget.config(state=tk.DISABLED)  # 设置为只读
    
        # 按钮框架（避免拥挤）
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=5)
    
        # 复制按钮
        ttk.Button(
            button_frame,
            text="复制全部",
            command=lambda: self._copy_to_clipboard(text)
        ).pack(side=tk.LEFT, padx=5)
    
        # 关闭按钮
        ttk.Button(
            button_frame,
            text=" 关闭",
            command=dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)
    
        # 可选：按 Esc 键关闭
        dialog.bind("<Escape>", lambda e: dialog.destroy())
    
        # 可选：支持 Ctrl+C 复制（虽然只读，但默认仍可选中复制）
        # 如果需要强制支持复制快捷键，可添加：
        dialog.bind("<Control-c>", lambda e: self._copy_to_clipboard(text_widget.get("1.0", tk.END)))
    
    
    def _copy_to_clipboard(self, text):
        """将指定文本复制到系统剪贴板"""
        try:
            self.root.clipboard_clear()  # 清空剪贴板
            self.root.clipboard_append(text)
            self.root.update()  # 保持剪贴板内容
            messagebox.showinfo("复制成功", "分析结果已复制到剪贴板。")
        except Exception as e:
            messagebox.showerror("复制失败", f"无法复制到剪贴板：\n{str(e)}")
    
    def _center_window(self, window, width, height, parent=None):
        """
        将窗口居中显示
        :param window: 要居中的 Toplevel 窗口
        :param width: 窗口宽度
        :param height: 窗口高度
        :param parent: 父窗口（默认为 self.root）
        """
        window.update_idletasks()
        
        # 如果指定了父窗口，就相对于父窗口居中；否则相对于 self.root；最后 fallback 到屏幕居中
        if parent is None:
            parent = self.root
    
        if hasattr(parent, 'winfo_rootx'):
            # 计算父窗口的中心点
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()
    
            x = parent_x + (parent_width - width) // 2
            y = parent_y + (parent_height - height) // 2
        else:
            # fallback：屏幕居中
            x = (window.winfo_screenwidth() // 2) - (width // 2)
            y = (window.winfo_screenheight() // 2) - (height // 2)
    
        # 防止出现在屏幕外（可选增强）
        x = max(x, 0)
        y = max(y, 0)
    
        window.geometry(f"{width}x{height}+{x}+{y}")
    def export_data(self):
        """导出当前查询范围内的所有主记录及明细数据，格式适合基金加仓点分析"""
        try:
            # 获取当前查询的日期范围
            start_date = self.start_date.strftime("%Y-%m-%d")
            end_date = self.end_date.strftime("%Y-%m-%d")
    
            # 使用单次 JOIN 查询获取主表 + 明细表的所有数据
            with db_connection() as cursor:
                cursor.execute('''
                    SELECT 
                        m.trade_date,
                        m.unit_net_value,
                        m.realtime_profit,
                        d.estimate_time,
                        d.realtime_estimate AS detail_realtime_estimate,
                        d.change_rate AS detail_change_rate,
                        d.is_close_data
                    FROM fund_estimate_main m
                    LEFT JOIN fund_estimate_details d ON m.fund_code = d.fund_code AND m.trade_date = d.trade_date
                    WHERE m.fund_code = ? AND m.trade_date BETWEEN ? AND ?
                    ORDER BY m.trade_date DESC, d.estimate_time
                ''', (self.fund_code, start_date, end_date))
    
                all_records = cursor.fetchall()
    
            if not all_records:
                messagebox.showinfo("提示", "当前查询范围内没有数据可导出")
                return
    
            # 询问保存路径
            default_filename = f"{self.fund_code}_{self.fund_name}_{start_date}_to_{end_date}_加仓点分析数据.csv"
            file_path = asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
                initialfile=default_filename
            )
    
            if not file_path:  # 用户取消保存
                return
    
            # 写入 CSV 文件
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                # 写入标题行
                writer.writerow([
                    "基金代码", "基金名称", "交易日期", "估值时间",
                    "单位净值(昨)", "实时估值(今)", "涨跌幅(%)",
                    "当日盈亏", "是否收盘数据", "分析备注"
                ])
    
                # 遍历 JOIN 查询结果，直接写入每一行
                for row in all_records:
                    trade_date, unit_net_value, realtime_profit, \
                    estimate_time, detail_realtime_estimate, detail_change_rate, is_close_data = row
    
                    # 分析备注：判断是否为潜在加仓点
                    analysis_note = ""
                    if detail_change_rate is not None:
                        if detail_change_rate <= -1.5:
                            analysis_note = "潜在加仓点：跌幅较大"
                        elif detail_change_rate <= -1.0:
                            analysis_note = "关注：跌幅中等"
    
                    # 写入一行数据
                    writer.writerow([
                        self.fund_code,
                        self.fund_name,
                        trade_date,
                        estimate_time or "",  # 处理 NULL 时间
                        f"{unit_net_value:.4f}" if unit_net_value is not None else "",
                        f"{detail_realtime_estimate:.4f}" if detail_realtime_estimate is not None else "",
                        f"{detail_change_rate:.2f}%" if detail_change_rate is not None else "",
                        f"{realtime_profit:.2f}" if realtime_profit is not None else "",
                        "是" if is_close_data else "否",
                        analysis_note
                    ])
    
            messagebox.showinfo("成功", f"数据已成功导出至:\n{file_path}")
    
        except Exception as e:
            messagebox.showerror("导出失败", f"导出数据时发生错误:\n{str(e)}")
def open_fund_history_viewer(parent, fund_code, fund_name):
    """打开基金历史记录查看器"""
    # 检查数据库文件是否存在
    if not os.path.exists(DB_FILE):
        messagebox.showerror("错误", f"数据库文件不存在: {DB_FILE}")
        return
        
    # 创建顶级窗口
    top = tk.Toplevel(parent)
    app = FundHistoryViewer(top, parent, fund_code, fund_name)
    top.mainloop()
