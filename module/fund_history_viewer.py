import os
import csv
import tkinter as tk
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import time
from dateutil.relativedelta import relativedelta


from tkinter import ttk, messagebox, simpledialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
from tkinter.filedialog import asksaveasfilename
from utils.logger import write_log
from tqdm import tqdm

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
        
        # 设置默认日期范围：结束日期为今天，开始日期为5年前
        self.end_date = datetime.today()
        self.start_date = self.end_date - relativedelta(years=5)
        
        # 创建界面
        self.create_widgets()
        
        # 加载数据
        self.load_history_main_records()

    def create_widgets(self):
        """创建主界面控件，统一使用 grid 布局"""
		
        self.status_var = tk.StringVar(value="就绪")
        self.status_bar = tk.Label(
            self.root,  # ← 父容器是 root，不是 main_frame！
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            bg="lightgray",
            fg="black",
            padx=5,
            pady=2
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
		
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
        ttk.Button(export_frame, text="历史数据下载", command=self.download_historical_estimates).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
		
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

    def _fetch_lsjz_from_api(self, start_date: str, end_date: str, progress_callback=None):
        """
        API 获取历史净值列表（LSJZ），支持动态分页。
        :param start_date: 起始日期，格式 'YYYY-MM-DD'
        :param end_date: 结束日期，格式 'YYYY-MM-DD'
        :param progress_callback: 可选回调函数，用于更新 GUI 状态，如 lambda msg: ...
        :return: list[dict] 原始数据列表
        """
        all_data = []
        page_size = 20
        max_retries = 3
        retry_delay = 1
    
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": f"http://fundf10.eastmoney.com/jjjz_{self.fund_code}.html",
            "Accept": "application/json, text/plain, */*",
            "Host": "api.fund.eastmoney.com",
            "Connection": "keep-alive"
        }
    
        url = "http://api.fund.eastmoney.com/f10/lsjz"
        params = {
            "fundCode": self.fund_code,
            "pageIndex": 1,
            "pageSize": page_size,
            "startDate": start_date,
            "endDate": end_date,
            "callback": ""
        }
    
        # === 第一页请求 ===
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.encoding = "utf-8"
    
            if '"ErrCode":-999' in resp.text:
                msg = f"[{self.fund_code}] 被反爬（ErrCode: -999），停止抓取"
                write_log(msg)
                if progress_callback:
                    progress_callback(f"❌ {msg}")
                return all_data
    
            data = resp.json()
            err_code = data.get("ErrCode", 0)
            if err_code != 0:
                errmsg = data.get("ErrMsg", "未知错误")
                msg = f"[{self.fund_code}] API 返回错误：ErrCode={err_code}, ErrMsg={errmsg}"
                write_log(msg)
                if progress_callback:
                    progress_callback(f"❌ {msg}")
                return all_data
    
            total_count = data.get("TotalCount", 0)
            first_page_data = data.get("Data", {}).get("LSJZList", [])
            all_data.extend(first_page_data)
    
            if total_count == 0:
                if progress_callback:
                    progress_callback("⚠️ 无历史净值数据")
                write_log(f"[{self.fund_code}] 无历史净值数据")
                return all_data
    
            expected_pages = (total_count + page_size - 1) // page_size
            if progress_callback:
                progress_callback(f"共 {expected_pages} 页，正在下载第 1 页（{int(1/expected_pages*100)}%）")
    
            write_log(f"[{self.fund_code}] 总记录数: {total_count}，预计需请求 {expected_pages} 页")
    
        except Exception as e:
            msg = f"[{self.fund_code}] 获取第一页失败: {e}"
            write_log(msg)
            if progress_callback:
                progress_callback(f"❌ {msg}")
            return all_data
    
        # === 后续页请求 ===
        for page in range(2, expected_pages + 1):
            params["pageIndex"] = page
            retries = 0
            success = False
    
            while retries < max_retries and not success:
                try:
                    resp = requests.get(url, headers=headers, params=params, timeout=10)
                    resp.encoding = "utf-8"
    
                    if '"ErrCode":-999' in resp.text:
                        msg = f"[{self.fund_code}] 第 {page} 页被反爬（ErrCode: -999），停止抓取"
                        write_log(msg)
                        if progress_callback:
                            progress_callback(f"❌ {msg}")
                        return all_data
    
                    data = resp.json()
                    err_code = data.get("ErrCode", 0)
                    if err_code != 0:
                        raise Exception(data.get("ErrMsg", "API 错误"))
    
                    page_data = data.get("Data", {}).get("LSJZList", [])
                    if not page_data:
                        write_log(f"[{self.fund_code}] 第 {page} 页无数据，提前结束")
                        break
    
                    all_data.extend(page_data)
                    success = True
    
                    # 实时更新进度
                    percent = int(page / expected_pages * 100)
                    if progress_callback:
                        progress_callback(f"共 {expected_pages} 页，正在下载第 {page} 页（{percent}%）")
    
                    time.sleep(0.3)  # 避免触发限流
    
                except Exception as e:
                    retries += 1
                    if retries > max_retries:
                        msg = f"[{self.fund_code}] 第 {page} 页达到最大重试次数，跳过"
                        write_log(msg)
                        if progress_callback:
                            progress_callback(f"⚠️ {msg}")
                        break
                    time.sleep(retry_delay)
    
        if progress_callback:
            progress_callback(f" 下载完成！共获取 {len(all_data)} 条原始记录")
        write_log(f"[{self.fund_code}] 历史净值数据拉取完成，共获取 {len(all_data)} 条原始记录")
        return all_data
    
    
    def download_historical_estimates(self):
        """
        下载历史净值数据并保存到数据库，支持实时进度反馈。
        """
        fund_id = f"{self.fund_code} - {self.fund_name}"
        write_log(f"[{fund_id}] 开始下载历史净值数据，日期范围：{self.start_date} 至 {self.end_date}")
    
        # 状态栏更新辅助函数（强制刷新 UI）
        def update_status(message):
            self.status_var.set(message)
            self.root.update_idletasks()
    
        try:
            start_str = self.start_date.strftime("%Y-%m-%d")
            end_str = self.end_date.strftime("%Y-%m-%d")
    
            # 从 API 下载原始数据（带进度回调）
            all_data = self._fetch_lsjz_from_api(start_str, end_str, progress_callback=update_status)
    
            if not all_data:
                update_status("⚠️ 未获取到任何原始数据")
                messagebox.showwarning("警告", "API 返回空数据，请检查基金代码或日期范围。")
                return
    
            # 过滤有效记录 —— 关键修改：trade_date 存为字符串！
            valid_records = []
            for item in all_data:
                fsrq = item.get("FSRQ")
                dwjz = item.get("DWJZ")
                jzzzl = item.get("JZZZL")
                if not fsrq or dwjz == "" or jzzzl == "":
                    continue
                try:
                    # 验证日期格式，但最终存储为字符串 "YYYY-MM-DD"
                    datetime.strptime(fsrq, "%Y-%m-%d")  # 仅用于验证
                    unit_net_value = float(dwjz)
                    change_rate = float(jzzzl)
                    valid_records.append({
                        "trade_date": fsrq,  # 直接使用原始字符串，确保格式一致
                        "unit_net_value": unit_net_value,
                        "change_rate": change_rate
                    })
                except (ValueError, TypeError):
                    continue  # 跳过格式错误的记录
    
            if not valid_records:
                update_status("⚠️ 没有有效净值数据可保存")
                messagebox.showwarning("警告", "所有返回数据格式无效，无法入库。")
                return
    
            total_valid = len(valid_records)
    
            # 数据库操作（查询 + 插入）—— 现在都是字符串比较！
            inserted_count = 0
            with db_connection() as conn:
                cursor = conn.cursor()
    
                # 查询已存在的交易日期（返回的是字符串列表）
                cursor.execute('''
                    SELECT trade_date FROM fund_estimate_main 
                    WHERE fund_code = ? AND trade_date BETWEEN ? AND ?
                ''', (self.fund_code, start_str, end_str))
                existing_dates = {row[0] for row in cursor.fetchall()}  # set of str
    
                # 过滤出新记录：字符串 vs 字符串
                new_records = [rec for rec in valid_records if rec["trade_date"] not in existing_dates]
                inserted_count = len(new_records)
    
                # 插入新记录
                if new_records:
                    cursor.executemany('''
                        INSERT INTO fund_estimate_main (
                            fund_code, trade_date, unit_net_value, 
                            realtime_estimate, change_rate, realtime_profit
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    ''', [
                        (
                            self.fund_code,
                            rec["trade_date"],  # 已是 "YYYY-MM-DD" 字符串
                            rec["unit_net_value"],
                            rec["unit_net_value"],
                            rec["change_rate"],
                            0.0
                        )
                        for rec in new_records
                    ])
                    conn.commit()
    
            # 更新 UI 和日志
            final_msg = f"✅ 成功新增 {inserted_count} 条记录（共 {total_valid} 条有效数据）"
            self.status_var.set(final_msg)
            write_log(f"[{fund_id}] {final_msg}")
    
            # 弹窗提示
            messagebox.showinfo(
                "下载完成",
                f"历史净值数据处理完毕！\n"
                f"• 原始数据：{len(all_data)} 条\n"
                f"• 有效数据：{total_valid} 条\n"
                f"• 新增入库：{inserted_count} 条"
            )
    
            # 刷新表格显示
            self.load_history_main_records()
    
        except Exception as e:
            error_msg = f"❌ 下载异常: {str(e)}"
            self.status_var.set(error_msg)
            write_log(f"[{fund_id}] {error_msg}")
            messagebox.showerror("错误", f"下载过程中发生异常：\n{str(e)}")
    		
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
            with db_connection() as conn:
                cursor = conn.cursor()
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
