import os
import tkinter as tk
import requests
import time
import matplotlib.pyplot as plt
import numpy as np

from tkinter import ttk, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import DateFormatter, DayLocator


from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# 导入自定义工具
from utils.sys_chinese_font import get_best_chinese_font
from utils.db.database import db_connection

# 配置中文字体和字号
AVAILABLE_CHINESE_FONT = get_best_chinese_font()
plt.rcParams["font.family"] = [AVAILABLE_CHINESE_FONT]
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题
plt.rcParams["font.size"] = 14  # 全局字体大小设为14号
plt.rcParams["axes.labelsize"] = 14      # 坐标轴标签大小
plt.rcParams["xtick.labelsize"] = 14     # x轴刻度标签大小
plt.rcParams["ytick.labelsize"] = 14     # y轴刻度标签大小
plt.rcParams["legend.fontsize"] = 14     # 图例字体大小
plt.rcParams["figure.titlesize"] = 16    # 图表标题大小（可稍大）
plt.rcParams["axes.titlesize"] = 16      # 子图标题大小
# 数据库路径
DB_FILE = "fund_data.db"


class FundStrategyAnalyzer:
    def __init__(self, root, parent, fund_code, fund_name):
        self.root = root
        self.parent = parent
        self.fund_code = fund_code
        self.fund_name = fund_name
        self.root.title(f"基金策略分析 - {fund_name}({fund_code})")
        self.root.geometry("1200x800")

        # 设置默认日期范围：结束日期为今天，开始日期为5年前
        self.end_date = datetime.today()
        self.start_date = self.end_date - relativedelta(years=5)
		
        # 1. 预设子窗口尺寸（可根据需求调整）
        window_width  = 1600
        window_height = 1000
        self.root.geometry(f"{window_width}x{window_height}")
        
        # 2. 计算主窗口正中心的坐标
        self._set_window_center(window_width, window_height)

        # 创建界面
        self.create_widgets()

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
    def create_widgets(self):
        """创建主界面控件：结果在左，图表在右，图表高度固定，结果区域自动拉伸"""

    
        # === 配置 root 窗口的 grid 权重 ===
        self.root.columnconfigure(0, weight=0)  # 控制区列（不需要伸展）
        self.root.columnconfigure(1, weight=1)  # 主内容区（可伸展）
        self.root.rowconfigure(0, weight=0)     # 控制区
        self.root.rowconfigure(1, weight=0)     # 信息区
        self.root.rowconfigure(2, weight=1)     # 主内容区（结果+图表），结果区域自动拉伸
    
        # ===================================================================
        # === 2. 控制区域：日期 + 操作按钮（完全保留）===
        # ===================================================================
        control_frame = ttk.Frame(self.root)
        control_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 5))
        control_frame.columnconfigure(0, weight=4)
        control_frame.columnconfigure(1, weight=6)
    
        date_frame = ttk.LabelFrame(control_frame, text="查询日期范围", padding="10")
        date_frame.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        date_frame.columnconfigure(1, weight=1)
        date_frame.columnconfigure(3, weight=1)
    
        ttk.Label(date_frame, text="开始日期:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.start_date_var = tk.StringVar(value=self.start_date.strftime("%Y-%m-%d"))
        self.start_date_entry = ttk.Entry(date_frame, textvariable=self.start_date_var, width=12)
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
    
        ttk.Label(date_frame, text="结束日期:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.end_date_var = tk.StringVar(value=self.end_date.strftime("%Y-%m-%d"))
        self.end_date_entry = ttk.Entry(date_frame, textvariable=self.end_date_var, width=12)
        self.end_date_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")
    

		
        action_frame = ttk.LabelFrame(control_frame, text="操作", padding="10")
        action_frame.grid(row=0, column=1, sticky="ew")
        # 不设置 columnconfigure，让列宽自动适应内容
        
        ttk.Button(action_frame, text="分析加仓策略", command=self.analyze_dca_strategy).grid(
            row=0, column=0, padx=5, pady=5, sticky=tk.W  # 左对齐，不拉伸
        )
        
        ttk.Button(action_frame, text="趋势检测", command=self.analyze_daily_channel_strategy).grid(
            row=0, column=1, padx=5, pady=5, sticky=tk.W  # 左对齐，不拉伸
        )
    
        # ===================================================================
        # === 3. 基金信息显示（居中）===
        # ===================================================================
        info_frame = ttk.Frame(self.root)
        info_frame.grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 5))
        info_frame.columnconfigure(0, weight=1)
    
        info_label = ttk.Label(
            info_frame,
            text=f"基金代码: {self.fund_code} | 基金名称: {self.fund_name}",
            font=("Arial", 14, "bold"),
            anchor="center"
        )
        info_label.grid(row=0, column=0, sticky="ew")
    
        # ===================================================================
        # === 4. 主内容区域：结果（左） + 图表（右）===
        # ===================================================================
        main_content_frame = ttk.Frame(self.root)
        main_content_frame.grid(row=2, column=1, sticky="nsew", padx=10, pady=(0, 10))
        main_content_frame.columnconfigure(0, weight=4)  # 结果区 40%
        main_content_frame.columnconfigure(1, weight=6)  # 图表区 60%
        main_content_frame.rowconfigure(0, weight=1)     # 结果行可拉伸
    
        # --- 左侧：分析结果区域（可拉伸高度）---
        result_frame = ttk.LabelFrame(main_content_frame, text="分析结果", padding="10")
        result_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)  # 关键：让文本区域自动拉伸
    
        self.result_text = tk.Text(result_frame, wrap=tk.WORD, font=("Consolas", 12))
        self.result_text.grid(row=0, column=0, sticky="nsew")
    
        # --- 右侧：图表区域（高度固定）---
        chart_container = ttk.LabelFrame(main_content_frame, text="图表显示", padding="10")
        chart_container.grid(row=0, column=1, sticky="ns", padx=(0, 0))  # 注意：sticky="ns" 仅垂直对齐，不拉伸
        chart_container.columnconfigure(0, weight=1)
        # 不设置 rowconfigure，保持高度固定
    
        # 固定图表大小（例如：高度 600px）
        self.fig = Figure(figsize=(8, 6), dpi=100)  # 8*100=800宽, 6*100=600高
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, chart_container)
        self.canvas_widget = self.canvas.get_tk_widget()
    
        # 设置 canvas 的固定高度
        self.canvas_widget.config(height=800)  # 固定高度为 600 像素
        self.canvas_widget.grid(row=0, column=0, sticky="ew", padx=0, pady=0)  # 仅水平拉伸，不垂直拉伸
    
        self.canvas.draw()

    def setup_chart_area(self, figsize=(10, 6)):
        """统一设置图表区域大小并返回 fig, ax"""
        # 清除旧 canvas 内容
        for widget in self.canvas.get_tk_widget().winfo_children():
            widget.destroy()
    
        # 创建新 figure
        self.fig = Figure(figsize=figsize, dpi=100)
        self.ax = self.fig.add_subplot(111)
    
        # 更新 canvas
        self.canvas = FigureCanvasTkAgg(self.fig, self.canvas.get_tk_widget())
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.grid(row=0, column=0, sticky="nsew")
		
        #设置固定高度
        canvas_widget.config(height=800)  # 固定高度为 800 像素
        canvas_widget.grid(row=0, column=0, sticky="ew", padx=0, pady=0)  # 仅水平拉伸
        self.canvas.draw()
    
        return self.fig, self.ax

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
                self.result_text.delete(1.0, tk.END)
                self.result_text.insert(tk.END, f"❌ 基金 {self.fund_code} 在过去90天内无估值数据。")
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
            #if not today_values and self.main_record_tree.get_children():
            #    values_from_ui = []
            #    for item in self.main_record_tree.get_children():
            #        values = self.main_record_tree.item(item)["values"]
            #        if len(values) > 2:
            #            try:
            #                val = float(values[2])
            #                values_from_ui.append(val)
            #            except (ValueError, TypeError):
            #                continue
            #    if values_from_ui:
            #        latest_estimate = values_from_ui[0]
            #        intraday_low = min(values_from_ui)
            #if not today_values:
            #    print(f"日期 {date} 没有数据，跳过。")
            #    continue  # 跳过当天，继续处理其他天
            ## ==================== 判断触发层级（使用当日最低估值） ====================
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
    
            observation_text = self.get_observation_zone_analysis(
                fund_code=self.fund_code,
                min_val=min_val,
                start_date=self.start_date,
                end_date=self.end_date,
                expand_by=0.0100  # 可动态调整
            )
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
            # 插入观察区段分析
            result_text += observation_text
            result_text += "提示：本策略基于历史估值分析，仅供参考，投资需谨慎。"
    
            # 显示到文本框
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, result_text)
    
            # 清空图表
            self.ax.clear()
            try:
                self.plot_strategy_chart(
                    start_date=self.start_date,
                    end_date=self.end_date
                )
            except Exception as e:
                # 防止绘图失败导致崩溃
                self.ax.text(0.5, 0.5, f"绘图失败: {str(e)}", 
                            ha="center", va="center", transform=self.ax.transAxes)
                self.fig.tight_layout()
                self.canvas.draw()
    
        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"❌ 分析失败：{str(e)}")

    def plot_strategy_chart(self, start_date, end_date, first_buy_date=None):
        """
        根据加仓策略绘制多日估值趋势图，每日取一个代表点（优先收盘，其次末次，最新日取实时）
        
        :param start_date: datetime.date 起始日期
        :param end_date: datetime.date 结束日期
        :param first_buy_date: datetime.date 首次建仓日（可选），用于标记
        """
        self.ax.clear()
        
        try:
            with db_connection() as conn:
                current = start_date
                all_dates = []
                plot_times = []      # 用于绘图的 x 轴时间点
                plot_values = []     # 对应的 y 轴估值
        
                today = datetime.now().date()
        
                while current <= end_date:
                    all_dates.append(current)
                    current += timedelta(days=1)
        
                for trade_date in all_dates:
                    date_str = trade_date.strftime("%Y-%m-%d")
                    is_latest_day = (trade_date == today)
        
                    if is_latest_day:
                        # 最新日：取最新一条记录（无论是否是收盘）
                        result = conn.execute('''
                            SELECT estimate_time, realtime_estimate 
                            FROM fund_estimate_details 
                            WHERE fund_code = ? AND trade_date = ?
                            ORDER BY estimate_time DESC 
                            LIMIT 1
                        ''', (self.fund_code, date_str))
                    else:
                        # 非最新日：从 master 表获取收盘数据
                        result = conn.execute('''
                            SELECT realtime_estimate 
                            FROM fund_estimate_main 
                            WHERE fund_code = ? AND trade_date = ?
                        ''', (self.fund_code, date_str))
        
                    row = result.fetchone()
                    if row:
                        value = row[0] if not is_latest_day else row[1]
                        time_str = f"{date_str} {row[0]}" if not is_latest_day else f"{date_str} {row[0]}"
                        try:
                            dt = datetime.strptime(time_str.split()[0], "%Y-%m-%d")  # 只保留日期部分作为x轴
                            plot_times.append(dt)
                            plot_values.append(value)
                        except ValueError:
                            continue
        
                if len(plot_times) < 2:
                    self.ax.text(0.5, 0.5, "没有足够的数据绘制策略图", 
                                ha="center", va="center", transform=self.ax.transAxes)
                else:
                    # 绘制主趋势线
                    self.ax.plot(plot_times, plot_values, 'b-', linewidth=2, label='每日估值趋势')
                    self.ax.scatter(plot_times, plot_values, color='red', s=30, alpha=0.7, label='每日数据点')
    
                    # 计算最低估值及其区间
                    min_value = min(plot_values)
                    low_band = min_value - 0.0050
                    high_band = min_value + 0.0050
                    
                    # 绘制最低估值的水平线和区间
                    self.ax.axhline(y=min_value, color='green', linestyle='-', linewidth=1.5, alpha=0.8,
                                    label=f'最低估值: {min_value:.4f}')
                    self.ax.axhspan(low_band, high_band, color='green', alpha=0.1, label='低估区间')
                    
                    # 标记首次建仓日（可选）
                    if first_buy_date:
                        start_dt = datetime.combine(first_buy_date, datetime.min.time())
                        end_dt = start_dt + timedelta(days=1)
                        self.ax.axvline(start_dt, color='purple', linestyle='--', linewidth=1.5, label='首次建仓日')
                        self.ax.axvline(end_dt, color='purple', linestyle='--', linewidth=1.5)
    
                    # 图表设置
                    self.ax.set_title(f"{self.fund_name} {start_date} 至 {end_date} 策略估值走势", fontsize=12)
                    self.ax.set_xlabel('时间', fontsize=10)
                    self.ax.set_ylabel('估值 (元)', fontsize=10)
                    self.ax.grid(True, linestyle='--', alpha=0.7)
                    self.ax.xaxis.set_major_formatter(DateFormatter('%m-%d'))
                    plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
                    self.ax.legend()
    
                self.fig.tight_layout()
                self.canvas.draw()
    
        except Exception as e:
            self.ax.text(0.5, 0.5, f"绘制策略图失败: {str(e)}", 
                        ha="center", va="center", transform=self.ax.transAxes)
            self.fig.tight_layout()
            self.canvas.draw()

    def get_observation_zone_analysis(self,fund_code, min_val, start_date, end_date, expand_by=0.0100):
        """
        根据历史最低估值生成观察区段分析文本
        观察区段：[min_val - 0.0100, min_val + 0.0100]
        
        :param fund_code: 基金代码
        :param min_val: 历史最低估值（作为锚点）
        :param start_date: datetime.date 起始日期
        :param end_date: datetime.date 结束日期
        :return: str，格式化的分析文本
        """
        # 计算观察区段
        observe_low = min_val - expand_by
        observe_high = min_val + expand_by
        in_range_days = []  # 存储 (date_str, daily_value)
    
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
    
        try:
            with db_connection() as conn:
                # 获取该基金在区间内的所有交易日
                date_result = conn.execute('''
                    SELECT DISTINCT trade_date 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date BETWEEN ? AND ?
                    ORDER BY trade_date
                ''', (fund_code, start_date_str, end_date_str))
    
                for row in date_result.fetchall():
                    trade_date = row[0]
                    # 优先取 master 表的收盘价
                    close_result = conn.execute('''
                        SELECT realtime_estimate 
                        FROM fund_estimate_main 
                        WHERE fund_code = ? AND trade_date = ?
                    ''', (fund_code, trade_date))
                    close_row = close_result.fetchone()
                    if close_row and close_row[0] is not None:
                        daily_val = close_row[0]
                    else:
                        # 否则取 details 表当天最后一条估值
                        detail_result = conn.execute('''
                            SELECT realtime_estimate 
                            FROM fund_estimate_details 
                            WHERE fund_code = ? AND trade_date = ?
                            ORDER BY estimate_time DESC 
                            LIMIT 1
                        ''', (fund_code, trade_date))
                        detail_row = detail_result.fetchone()
                        if detail_row and detail_row[0] is not None:
                            daily_val = detail_row[0]
                        else:
                            continue  # 无有效数据
    
                    # 判断是否在观察区段内
                    if observe_low <= daily_val <= observe_high:
                        in_range_days.append((trade_date, daily_val))
    
            # 排序
            in_range_days.sort(key=lambda x: x[0])
    
            # 统计
            if in_range_days:
                in_range_vals = [v for _, v in in_range_days]
                in_range_min = min(in_range_vals)
                in_range_max = max(in_range_vals)
                in_range_count = len(in_range_days)
            else:
                in_range_min = in_range_max = None
                in_range_count = 0
    
            # 构建返回文本
            text = (
                f"【首次建仓】观察区段分析\n"
                f"─────────────────────────────────────────────────────\n"
                f"观察区段：{observe_low:.4f} ~ {observe_high:.4f}\n"
                f"区间跨度：±0.0100（基于历史最低 {min_val:.4f} 扩展）\n"
                f"落入天数：{in_range_count} 天\n"
            )
    
            if in_range_count > 0:
                text += f"区间估值：最低 {in_range_min:.4f}，最高 {in_range_max:.4f}\n"
                text += "\n具体日期与估值：\n"
                for date_str, val in in_range_days:
                    text += f"  {date_str}: {val:.4f}\n"
            else:
                text += f"提示：查询期间内无任何一天估值落入该观察区段。\n"
    
            text += "─────────────────────────────────────────────────────\n"
            return text
    
        except Exception as e:
            return (
                f"【首次建仓】观察区段分析失败\n"
                f"─────────────────────────────────────────────────────\n"
                f"错误：{str(e)}\n"
                f"─────────────────────────────────────────────────────\n"
            )
    def analyze_daily_channel_strategy(self):
        """分析日线趋势通道策略（带可视化图表）"""
        try:
            lookback_days = 60
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)

            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT realtime_estimate, trade_date 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date BETWEEN ? AND ?
                    ORDER BY trade_date
                ''', (self.fund_code, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
                raw_data = cursor.fetchall()

            if not raw_data:
                self.result_text.delete(1.0, tk.END)
                self.result_text.insert(tk.END, f"❌ 基金 {self.fund_code} 无历史估值数据。")
                return

            # 聚合日线数据
            daily_data = {}
            for value, date_str in raw_data:
                if value is None:
                    continue
                date_key = date_str.split()[0]  # 只取日期部分
                if date_key not in daily_data:
                    daily_data[date_key] = {'high': value, 'low': value, 'final': value}
                else:
                    daily_data[date_key]['high'] = max(daily_data[date_key]['high'], value)
                    daily_data[date_key]['low'] = min(daily_data[date_key]['low'], value)
                    daily_data[date_key]['final'] = value

            sorted_dates = sorted(daily_data.keys())
            if len(sorted_dates) < 10:
                self.result_text.delete(1.0, tk.END)
                self.result_text.insert(tk.END, "❌ 有效日线数据少于10天，无法分析。")
                return

            highs = [daily_data[d]['high'] for d in sorted_dates]
            lows = [daily_data[d]['low'] for d in sorted_dates]
            finals = [daily_data[d]['final'] for d in sorted_dates]
            date_objs = [datetime.strptime(d, "%Y-%m-%d") for d in sorted_dates]
            date_nums = np.array([d.toordinal() for d in date_objs])

            # 拟合趋势线（一次多项式）
            z_upper = np.polyfit(date_nums, highs, 1)
            z_lower = np.polyfit(date_nums, lows, 1)
            z_final = np.polyfit(date_nums, finals, 1)

            trend_upper = np.polyval(z_upper, date_nums)
            trend_lower = np.polyval(z_lower, date_nums)
            trend_final = np.polyval(z_final, date_nums)

            current_upper = trend_upper[-1]
            current_lower = trend_lower[-1]

            # 当前估值
            today_vals = [v for v, d in raw_data if d.startswith(datetime.now().strftime("%Y-%m-%d"))]
            current_val = today_vals[-1] if today_vals else None

            # 通道位置判断
            if current_val and current_upper > current_lower:
                pos = (current_val - current_lower) / (current_upper - current_lower)
                if pos < 0.3:
                    pos_desc = "低位"
                    action = "可考虑加仓"
                elif pos < 0.7:
                    pos_desc = "中位"
                    action = "持有观望"
                else:
                    pos_desc = "高位"
                    action = "避免追高"
            else:
                pos_desc = "N/A"
                action = "数据不足"

            # 趋势判断
            slope_low = z_lower[0]
            slope_high = z_upper[0]
            if slope_low > 1e-5 and slope_high > 1e-5:
                trend = "📈 上升通道"
            elif slope_low < -1e-5 and slope_high < -1e-5:
                trend = "📉 下降通道"
            else:
                trend = "🔄 震荡通道"
            # 生成文本结果（安全处理 current_val 为 None 的情况）
            if current_val is not None:
                pos_info = f"{current_val:.4f}（{pos_desc}）"
            else:
                pos_info = "N/A"
            # 生成文本结果
            result = (
                f"📈 趋势通道分析\n"
                f"────────────────────────────────\n"
                f"基金：{self.fund_name}({self.fund_code})\n"
                f"趋势：{trend}\n"
                f"支撑线斜率：{slope_low:.6f}\n"
                f"阻力线斜率：{slope_high:.6f}\n"
                f"当前支撑：{current_lower:.4f}\n"
                f"当前阻力：{current_upper:.4f}\n"
                f"当前估值：{pos_info}\n"
                f"操作建议：{action}\n\n"
                f"📌 说明：基于日线高低点构建趋势通道，辅助决策。"
            )

            # 更新文本
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, result)
            
            self.fig, self.ax = self.setup_chart_area(figsize=(10, 6))

            # 绘制图表
            self.ax.clear()
            self.ax.plot(date_objs, highs, 'r-', alpha=0.6, label='每日最高')
            self.ax.plot(date_objs, lows, 'b-', alpha=0.6, label='每日最低')
            self.ax.plot(date_objs, finals, 'k-', linewidth=1, label='每日收盘')
            self.ax.plot(date_objs, trend_upper, 'r--', alpha=0.8, label='阻力趋势线')
            self.ax.plot(date_objs, trend_lower, 'b--', alpha=0.8, label='支撑趋势线')
            self.ax.plot(date_objs, trend_final, 'g--', alpha=0.8, label='收盘趋势线')

            if current_val is not None:
                self.ax.scatter([date_objs[-1]], [current_val], color='red', s=50, zorder=5, label='当前估值')

            self.ax.set_title(f"{self.fund_name}({self.fund_code}) 日线趋势通道分析", fontsize=16)
            self.ax.set_xlabel("日期")
            self.ax.set_ylabel("估值")
            self.ax.legend(fontsize=12)
            self.ax.grid(True, alpha=0.3)
            self.ax.xaxis.set_major_formatter(DateFormatter("%m-%d"))
            self.ax.xaxis.set_major_locator(DayLocator(interval=5))
            self.fig.autofmt_xdate()

            # 绘制图表后，显示图表
            self.canvas_widget.grid(row=0, column=0, sticky="nsew")  # 确保显示
            self.canvas.draw()

        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f" 趋势分析失败：{str(e)}")


def open_fund_strategy_analyzer(parent, fund_code, fund_name):
    """
    打开基金策略分析器（供 FVTracker.py 等外部模块调用）

    :param parent: 父级 Tk 或 Toplevel 窗口
    :param fund_code: 基金代码
    :param fund_name: 基金名称
    """
    # 检查数据库文件是否存在
    if not os.path.exists(DB_FILE):
        messagebox.showerror("错误", f"数据库文件不存在: {DB_FILE}")
        return

    # 创建顶级窗口
    top = tk.Toplevel(parent)
    app = FundStrategyAnalyzer(top, parent, fund_code, fund_name)

    # 设置关闭行为
    def on_close():
        top.destroy()

    top.protocol("WM_DELETE_WINDOW", on_close)