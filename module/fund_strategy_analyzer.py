import os
import tkinter as tk
import requests
import time
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from tkinter import ttk, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import DateFormatter, DayLocator, MonthLocator
from matplotlib.patches import Rectangle

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict

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
        
        # 设置默认日期范围：结束日期为今天，开始日期为5年前
        self.end_date = datetime.today()
        self.start_date = self.end_date - relativedelta(years=5)
        
        # 1. 预设子窗口尺寸（可根据需求调整）
        window_width = 1600
        window_height = 1000
        self.root.geometry(f"{window_width}x{window_height}")
        
        # 2. 计算主窗口正中心的坐标
        self._set_window_center(window_width, window_height)
        
        # 初始化图表相关变量
        self.current_fig = None
        self.current_canvas = None
        
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
		
		
        self.start_date_var.trace_add("write", self._on_start_date_change)
        self.end_date_var.trace_add("write", self._on_end_date_change)
    
        action_frame = ttk.LabelFrame(control_frame, text="操作", padding="10")
        action_frame.grid(row=0, column=1, sticky="ew")
        
        ttk.Button(action_frame, text="分析加仓策略", command=self.analyze_dca_strategy).grid(
            row=0, column=0, padx=5, pady=5, sticky=tk.W
        )
        
        ttk.Button(action_frame, text="趋势检测", command=self.analyze_daily_channel_strategy).grid(
            row=0, column=1, padx=5, pady=5, sticky=tk.W
        )
        
        ttk.Button(action_frame, text="月度季节性分析", command=self.analyze_monthly_seasonality).grid(
            row=0, column=2, padx=5, pady=5, sticky=tk.W
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
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.result_text.configure(yscrollcommand=scrollbar.set)
    
        # --- 右侧：图表区域（高度固定）---
        chart_container = ttk.LabelFrame(main_content_frame, text="图表显示", padding="10")
        chart_container.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        chart_container.columnconfigure(0, weight=1)
        chart_container.rowconfigure(0, weight=1)
    
        # 创建画布容器
        self.chart_canvas_frame = ttk.Frame(chart_container)
        self.chart_canvas_frame.grid(row=0, column=0, sticky="nsew")
        self.chart_canvas_frame.columnconfigure(0, weight=1)
        self.chart_canvas_frame.rowconfigure(0, weight=1)
        
        # 初始显示一个空白图表
        self.show_blank_chart()
    def _on_start_date_change(self, *args):
        """当开始日期输入框内容变化时，尝试更新 self.start_date"""
        date_str = self.start_date_var.get().strip()
        if not date_str:
            return
        try:
            parsed = datetime.strptime(date_str, "%Y-%m-%d")
            self.start_date = parsed  # 更新内部 datetime 对象
        except ValueError:
            pass
    
    def _on_end_date_change(self, *args):
        """当结束日期输入框内容变化时，尝试更新 self.end_date"""
        date_str = self.end_date_var.get().strip()
        if not date_str:
            return
        try:
            parsed = datetime.strptime(date_str, "%Y-%m-%d")
            self.end_date = parsed
        except ValueError:
            pass 
    def show_blank_chart(self):
        """显示空白图表"""
        if hasattr(self, 'canvas_widget') and self.canvas_widget:
            self.canvas_widget.destroy()
            
        fig = Figure(figsize=(8, 6), dpi=100)
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, "等待分析...", ha='center', va='center', 
                fontsize=16, transform=ax.transAxes)
        ax.axis('off')
        
        self.current_canvas = FigureCanvasTkAgg(fig, self.chart_canvas_frame)
        self.canvas_widget = self.current_canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")
        self.current_canvas.draw()
        
    def clear_chart_area(self):
        """清空图表区域"""
        if hasattr(self, 'canvas_widget') and self.canvas_widget:
            self.canvas_widget.destroy()
            
        # 创建新的画布
        self.current_canvas = FigureCanvasTkAgg(Figure(figsize=(8, 6), dpi=100), 
                                               self.chart_canvas_frame)
        self.canvas_widget = self.current_canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")
        
    def display_chart(self, fig):
        """显示图表"""
        self.clear_chart_area()
        self.current_canvas = FigureCanvasTkAgg(fig, self.chart_canvas_frame)
        self.canvas_widget = self.current_canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")
        self.current_canvas.draw()
        
    def analyze_dca_strategy(self):
        """优化版分析分批加仓策略"""
        try:
            # 清空之前的图表
            self.clear_chart_area()
            
            start_date = self.start_date.strftime("%Y-%m-%d")
            end_date = self.end_date.strftime("%Y-%m-%d")
    
            # 从数据库获取收盘净值数据
            with db_connection() as conn:
                result = conn.execute('''
                    SELECT trade_date, unit_net_value 
                    FROM fund_estimate_main 
                    WHERE fund_code = ? AND trade_date BETWEEN ? AND ?
                      AND unit_net_value IS NOT NULL
                    ORDER BY trade_date
                ''', (self.fund_code, start_date, end_date))
                rows = result.fetchall()
    
            if not rows:
                self.result_text.delete(1.0, tk.END)
                self.result_text.insert(tk.END, f"❌ 基金 {self.fund_code} 在指定区间无收盘净值数据。")
                return
    
            # 准备数据
            dates = []
            values = []
            for row in rows:
                dates.append(datetime.strptime(row[0], "%Y-%m-%d"))
                values.append(row[1])
            
            min_val = min(values)
            max_val = max(values)
            avg_val = sum(values) / len(values)
            
            # 计算加仓点位
            buy_points = {
                '首次建仓区间': (min_val - 0.005, min_val + 0.005),
                '第一次加仓': min_val * 0.95,   # 跌5%
                '第二次加仓': min_val * 0.90,   # 跌10%
                '第三次加仓': min_val * 0.85    # 跌15%
            }
            
            # 获取最新估值
            latest_estimate = None
            intraday_low = None
            today = datetime.now().date().strftime("%Y-%m-%d")
            with db_connection() as conn:
                result = conn.execute('''
                    SELECT realtime_estimate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND DATE(trade_date) = ?
                    ORDER BY estimate_time DESC
                ''', (self.fund_code, today))
                today_vals = [row[0] for row in result.fetchall() if row[0] is not None]
                if today_vals:
                    latest_estimate = today_vals[0]
                    intraday_low = min(today_vals)
            
            # 判断当前触发层级
            triggered_level = None
            check_val = intraday_low if intraday_low is not None else latest_estimate
            
            if check_val is not None:
                # 检查是否在首次建仓区间
                if buy_points['首次建仓区间'][0] <= check_val <= buy_points['首次建仓区间'][1]:
                    triggered_level = '首次建仓区间'
                elif check_val <= buy_points['第三次加仓']:
                    triggered_level = '第三次加仓'
                elif check_val <= buy_points['第二次加仓']:
                    triggered_level = '第二次加仓'
                elif check_val <= buy_points['第一次加仓']:
                    triggered_level = '第一次加仓'
            
            # 观察区段分析
            observation_text = self.get_observation_zone_analysis(
                fund_code=self.fund_code,
                min_val=min_val,
                start_date=self.start_date,
                end_date=self.end_date,
                expand_by=0.0100
            )
            
            # 生成分析结果文本
            result_text = (
                f"基金分批加仓策略分析\n"
                f"────────────────────────────────\n"
                f"基金代码：{self.fund_code}\n"
                f"基金名称：{self.fund_name}\n"
                f"查询区间：{start_date} 至 {end_date}\n"
                f"数据量：{len(values):,} 个收盘净值\n"
                f"统计：最低={min_val:.4f}，最高={max_val:.4f}，平均={avg_val:.4f}\n\n"
    
                f"基准设定\n"
                f"历史最低收盘净值：{min_val:.4f}\n"
                f"首次建仓区间：{buy_points['首次建仓区间'][0]:.4f} ~ {buy_points['首次建仓区间'][1]:.4f}\n"
                f"后续加仓：基于历史最低每下跌一定比例触发\n\n"
    
                f"分批加仓建议（越跌越买）：\n"
                f"○ 首次建仓: {buy_points['首次建仓区间'][0]:.4f} ~ {buy_points['首次建仓区间'][1]:.4f}\n"
                f"○ 第一次加仓: ≤{buy_points['第一次加仓']:.4f} (跌≥5%)\n"
                f"○ 第二次加仓: ≤{buy_points['第二次加仓']:.4f} (跌≥10%)\n"
                f"○ 第三次加仓: ≤{buy_points['第三次加仓']:.4f} (跌≥15%)\n\n"
            )
            
            # 盘中估值监测
            result_text += f"盘中估值监测：\n"
            if latest_estimate is not None and intraday_low is not None:
                result_text += f"  最新估值：{latest_estimate:.4f}\n"
                result_text += f"  当日最低：{intraday_low:.4f}\n"
                if triggered_level:
                    result_text += f"\n⚠️ 强烈建议：盘中已触及【{triggered_level}】区间！\n"
                else:
                    result_text += f"\n建议：尚未进入加仓区间，继续观望。\n"
            else:
                result_text += f"  提示：今日无盘中估值数据。\n"
            
            result_text += f"\n说明：以历史最低**收盘净值** {min_val:.4f} 为锚点，越跌越买。\n"
            result_text += observation_text
            result_text += "提示：本策略基于历史收盘数据，仅供参考，投资需谨慎。"
    
            # 显示结果
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, result_text)
            
            # 绘制策略图表
            fig = self.create_strategy_chart(dates, values, buy_points, latest_estimate, intraday_low)
            self.display_chart(fig)
    
        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"❌ 分析失败：{str(e)}")
            
    def create_strategy_chart(self, dates, values, buy_points, latest_estimate=None, intraday_low=None):
        """创建加仓策略图表"""
        fig = Figure(figsize=(10, 8), dpi=100)
        ax = fig.add_subplot(111)
        
        # 绘制净值走势
        ax.plot(dates, values, 'b-', linewidth=1.5, label='收盘净值', alpha=0.8)
        
        # 绘制加仓区间
        colors = ['#2ECC71', '#F39C12', '#E74C3C', '#9B59B6']
        level_names = ['首次建仓区间', '第一次加仓', '第二次加仓', '第三次加仓']
        
        for i, level in enumerate(level_names):
            if level == '首次建仓区间':
                # 绘制区间
                low, high = buy_points[level]
                ax.axhspan(low, high, alpha=0.2, color=colors[i], label=f'{level}: {low:.4f}~{high:.4f}')
            else:
                # 绘制水平线
                price = buy_points[level]
                ax.axhline(y=price, color=colors[i], linestyle='--', linewidth=1.5, 
                          alpha=0.7, label=f'{level}: ≤{price:.4f}')
        
        # 标记当前估值
        if latest_estimate is not None:
            ax.axhline(y=latest_estimate, color='#000000', linestyle='-', 
                      linewidth=2, alpha=0.8, label=f'最新估值: {latest_estimate:.4f}')
            
            # 在最新日期处标记
            last_date = dates[-1]
            ax.scatter([last_date], [latest_estimate], color='red', s=100, 
                      zorder=5, label='当前点位')
            
            # 添加箭头标注
            if intraday_low is not None and intraday_low != latest_estimate:
                ax.axhline(y=intraday_low, color='#FF5733', linestyle=':', 
                          linewidth=1, alpha=0.6, label=f'当日最低: {intraday_low:.4f}')
        
        # 标记最低点
        min_val = min(values)
        min_idx = values.index(min_val)
        ax.scatter([dates[min_idx]], [min_val], color='green', s=150, 
                  zorder=5, label=f'历史最低: {min_val:.4f}')
        
        # 图表设置
        ax.set_title(f'{self.fund_name} 加仓策略分析', fontsize=16, fontweight='bold')
        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('净值', fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.xaxis.set_major_formatter(DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(MonthLocator(interval=3))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # 添加图例
        ax.legend(loc='upper left', bbox_to_anchor=(1.05, 1), borderaxespad=0.)
        
        fig.tight_layout()
        return fig
        
    def analyze_monthly_seasonality(self):
        """优化版月度季度分析功能 - 修复颜色问题"""
        try:
            # 清空之前的图表
            self.clear_chart_area()
            
            # 获取最近5年数据
            end_date = datetime.today()
            start_date = end_date - relativedelta(years=5)
    
            with db_connection() as conn:
                result = conn.execute('''
                    SELECT trade_date, unit_net_value 
                    FROM fund_estimate_main 
                    WHERE fund_code = ? AND trade_date BETWEEN ? AND ?
                      AND unit_net_value IS NOT NULL
                    ORDER BY trade_date
                ''', (self.fund_code, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
                rows = result.fetchall()
    
            if len(rows) < 30:
                self.result_text.delete(1.0, tk.END)
                self.result_text.insert(tk.END, "❌ 数据不足，无法进行月度分析。")
                return
    
            # 转换为DataFrame
            data = []
            for row in rows:
                date_str = row[0]
                if isinstance(date_str, str):
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    date = date_str
                data.append({
                    '交易日期': date,
                    '净值': row[1]
                })
            
            df = pd.DataFrame(data)
            
            # 创建分析器
            analyzer = self.FundSeasonalityAnalyzer(df, self.fund_code, self.fund_name)
            
            # 执行分析
            monthly_df, month_stats = analyzer.analyze_monthly_seasonality()
            
            # 生成报告文本
            report_text = "📊 基金月度季度分析报告\n"
            report_text += "=" * 50 + "\n"
            report_text += f"基金: {self.fund_name} ({self.fund_code})\n"
            report_text += f"分析期间: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}\n"
            report_text += f"数据点数: {len(df)} 个\n\n"
            
            # 月度分析结果
            report_text += "📈 月度季节性分析\n"
            report_text += "-" * 40 + "\n"
            
            # 识别上涨和下跌月份
            up_months = []
            down_months = []
            neutral_months = []
            
            month_names = ["1月", "2月", "3月", "4月", "5月", "6月",
                          "7月", "8月", "9月", "10月", "11月", "12月"]
            
            for month in range(1, 13):
                stats = month_stats.get(month, {})
                if stats.get('上涨概率', 0) > 60:  # 上涨概率大于60%
                    up_months.append(month)
                elif stats.get('上涨概率', 0) < 40:  # 下跌概率大于60%
                    down_months.append(month)
                else:
                    neutral_months.append(month)
            
            report_text += f"📈 上涨趋势月份 ({len(up_months)}个): "
            report_text += ", ".join([month_names[m-1] for m in up_months]) + "\n"
            
            report_text += f"📉 下跌趋势月份 ({len(down_months)}个): "
            report_text += ", ".join([month_names[m-1] for m in down_months]) + "\n"
            
            report_text += f"⚖️  中性月份 ({len(neutral_months)}个): "
            report_text += ", ".join([month_names[m-1] for m in neutral_months]) + "\n\n"
            
            # 详细月度统计表
            report_text += "📋 详细月度统计\n"
            report_text += "-" * 40 + "\n"
            report_text += f"{'月份':<6}{'平均涨跌幅':<12}{'上涨概率':<10}{'上涨次数':<10}{'下跌次数':<10}{'样本数':<8}\n"
            report_text += "-" * 60 + "\n"
            
            for month in range(1, 13):
                stats = month_stats.get(month, {})
                if stats:
                    # 修改：红色表示上涨，绿色表示下跌
                    avg_return = stats.get('平均涨跌幅', 0)
                    trend = "📈" if avg_return > 0 else "📉"
                    color_code = "🔴" if avg_return > 0 else "🟢"
                    
                    report_text += f"{trend} {month_names[month-1]:<4}"
                    report_text += f"{avg_return:>7.2f}%{'':<5}"
                    report_text += f"{stats.get('上涨概率', 0):>6.1f}%{'':<4}"
                    report_text += f"{stats.get('涨跌次数', 0):>8}{'':<2}"
                    report_text += f"{stats.get('下跌次数', 0):>8}{'':<2}"
                    report_text += f"{stats.get('样本数量', 0):>6}\n"
                else:
                    report_text += f"⚪ {month_names[month-1]:<4}{'0.00%':>12}{'0.0%':>10}{'0':>10}{'0':>10}{'0':>8}\n"
            
            # 当前月份建议
            current_month = datetime.now().month
            current_stats = month_stats.get(current_month, {})
            
            report_text += "\n💡 当前月份建议\n"
            report_text += "-" * 40 + "\n"
            report_text += f"当前月份: {month_names[current_month-1]}\n"
            
            if current_stats:
                report_text += f"历史平均表现: {current_stats.get('平均涨跌幅', 0):.2f}%\n"
                report_text += f"历史上涨概率: {current_stats.get('上涨概率', 0):.1f}%\n"
                
                avg_return = current_stats.get('平均涨跌幅', 0)
                if avg_return > 0:
                    report_text += "🔴 建议: 本月历史表现较好，可考虑逢低布局\n"
                elif avg_return < 0:
                    report_text += "🟢 建议: 本月历史表现较弱，需谨慎操作\n"
                else:
                    report_text += "⚖️  建议: 本月历史表现中性，可持有观望\n"
            else:
                report_text += "📊 历史数据不足，无法提供建议\n"
            
            # 显示结果
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, report_text)
            
            # 绘制图表 - 修复颜色问题
            fig = self.create_seasonality_chart(df, month_stats, month_names)
            self.display_chart(fig)
            
        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"❌ 月度分析失败：{str(e)}\n\n错误详情: {e}")

    def create_seasonality_chart(self, df, month_stats, month_names):
        """创建季节性分析图表 - 统一红涨绿跌语义"""
        from matplotlib.dates import DateFormatter, MonthLocator
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
        # 使用 GridSpec 控制布局比例
        fig = Figure(figsize=(12, 10), dpi=100, constrained_layout=False)
        gs = GridSpec(2, 2, 
                      width_ratios=[1, 1],
                      height_ratios=[1, 2],
                      hspace=0.35, wspace=0.3)
        
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[1, :])
    
        months = list(range(1, 13))
    
        # ===== 1. 月度平均涨跌幅：红涨（正），绿跌（负） =====
        avg_returns = [month_stats.get(month, {}).get('平均涨跌幅', 0) for month in months]
        # 红色：上涨（正收益），绿色：下跌（负收益）
        colors_return = ['#FF4500' if r > 0 else '#2E8B57' for r in avg_returns]  # 更鲜明的红/绿
    
        bars1 = ax1.bar(month_names, avg_returns, color=colors_return, alpha=0.85, edgecolor='black')
        ax1.axhline(y=0, color='gray', linestyle='-', linewidth=0.8)
        ax1.set_title('月度平均涨跌幅 (%)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('月份')
        ax1.set_ylabel('涨跌幅 (%)')
        ax1.grid(axis='y', linestyle='--', alpha=0.6)
    
        for bar, ret in zip(bars1, avg_returns):
            height = bar.get_height()
            text_color = 'white' if abs(ret) < 0.5 else 'black'  # 小值用白字更清晰
            va = 'bottom' if height >= 0 else 'top'
            ax1.text(bar.get_x() + bar.get_width()/2, height,
                    f'{ret:.2f}%', ha='center', va=va,
                    fontsize=9, fontweight='bold', color=text_color)
    
        # ===== 2. 月度上涨概率：红=高概率（>50%），绿=低概率（<50%）=====
        up_probs = [month_stats.get(month, {}).get('上涨概率', 0) for month in months]
        # 关键修正：上涨概率高 → 红色（积极信号），低 → 绿色（谨慎信号）
        colors_prob = ['#FF4500' if p >= 50 else '#2E8B57' for p in up_probs]
    
        bars2 = ax2.bar(month_names, up_probs, color=colors_prob, alpha=0.85, edgecolor='black')
        ax2.axhline(y=50, color='gray', linestyle='-', linewidth=0.8)
        ax2.set_title('月度上涨概率 (%)', fontsize=14, fontweight='bold')
        ax2.set_xlabel('月份')
        ax2.set_ylabel('上涨概率 (%)')
        ax2.set_ylim(0, 100)
        ax2.grid(axis='y', linestyle='--', alpha=0.6)
    
        for bar, prob in zip(bars2, up_probs):
            height = bar.get_height()
            text_color = 'white' if prob < 20 or prob > 80 else 'black'
            ax2.text(bar.get_x() + bar.get_width()/2, height + 1,
                    f'{prob:.1f}%', ha='center', va='bottom',
                    fontsize=9, fontweight='bold', color=text_color)
    
        # ===== 3. 净值走势图：最高点=红，最低点=绿 =====
        dates = df['交易日期'].tolist()
        values = df['净值'].tolist()
    
        ax3.plot(dates, values, color='#1E90FF', linewidth=2, label='基金净值')
    
        # 20日均线
        if len(values) > 20:
            ma20 = pd.Series(values).rolling(window=20).mean()
            ax3.plot(dates, ma20, color='#FFA500', linewidth=1.5, alpha=0.8, label='20日均线')
    
        min_val = min(values)
        max_val = max(values)
        min_idx = values.index(min_val)
        max_idx = values.index(max_val)
    
        # 最低点：绿色（下跌到位），最高点：红色（上涨见顶）
        ax3.scatter([dates[min_idx]], [min_val], color='#2E8B57', s=120, zorder=5, label='历史最低点')
        ax3.scatter([dates[max_idx]], [max_val], color='#FF4500', s=120, zorder=5, label='历史最高点')
    
        # 标注文字颜色同步
        ax3.annotate(f'最低: {min_val:.4f}', 
                    xy=(dates[min_idx], min_val),
                    xytext=(10, 10), textcoords='offset points',
                    ha='left', va='bottom',
                    color='white',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='#2E8B57', alpha=0.8))
    
        ax3.annotate(f'最高: {max_val:.4f}', 
                    xy=(dates[max_idx], max_val),
                    xytext=(10, -10), textcoords='offset points',
                    ha='left', va='top',
                    color='white',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='#FF4500', alpha=0.8))
    
        ax3.set_title('基金净值走势（近5年）', fontsize=14, fontweight='bold')
        ax3.set_xlabel('日期')
        ax3.set_ylabel('单位净值')
        ax3.grid(True, linestyle='--', alpha=0.4)
        ax3.legend(loc='best')
    
        # 日期格式
        ax3.xaxis.set_major_formatter(DateFormatter('%Y-%m'))
        ax3.xaxis.set_major_locator(MonthLocator(interval=6))
        for label in ax3.get_xticklabels():
            label.set_rotation(45)
            label.set_ha('right')
    
        fig.suptitle(f'{self.fund_name} ({self.fund_code}) 季节性分析报告', 
                    fontsize=16, fontweight='bold')
        #fig.tight_layout(rect=[0, 0, 1, 0.97])					
        return fig
          

    def analyze_daily_channel_strategy(self):
        """分析日线趋势通道策略"""
        try:
            # 清空之前的图表
            self.clear_chart_area()
            
            lookback_days = 90
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
                self.result_text.insert(tk.END, "❌ 详细的估值明细记录的日线数据少于10天，无法分析。")
                return

            highs = [daily_data[d]['high'] for d in sorted_dates]
            lows = [daily_data[d]['low'] for d in sorted_dates]
            finals = [daily_data[d]['final'] for d in sorted_dates]
            date_objs = [datetime.strptime(d, "%Y-%m-%d") for d in sorted_dates]
            date_nums = np.array([d.toordinal() for d in date_objs])

            # 拟合趋势线
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
                
            # 生成文本结果
            if current_val is not None:
                pos_info = f"{current_val:.4f}（{pos_desc}）"
            else:
                pos_info = "N/A"
                
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
            
            # 绘制图表
            fig = self.create_channel_chart(date_objs, highs, lows, finals, 
                                          trend_upper, trend_lower, trend_final, 
                                          current_val)
            self.display_chart(fig)

        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"❌ 趋势分析失败：{str(e)}")
            
    def create_channel_chart(self, dates, highs, lows, finals, 
                           trend_upper, trend_lower, trend_final, current_val):
        """创建趋势通道图表"""
        fig = Figure(figsize=(10, 8), dpi=100)
        ax = fig.add_subplot(111)
        
        # 填充通道区域
        ax.fill_between(dates, trend_lower, trend_upper, color='lightblue', alpha=0.3, label='趋势通道')
        
        # 绘制实际数据
        ax.plot(dates, highs, 'r-', alpha=0.6, linewidth=1, label='每日最高')
        ax.plot(dates, lows, 'b-', alpha=0.6, linewidth=1, label='每日最低')
        ax.plot(dates, finals, 'k-', linewidth=1.5, label='每日收盘')
        
        # 绘制趋势线
        ax.plot(dates, trend_upper, 'r--', alpha=0.8, linewidth=2, label='阻力趋势线')
        ax.plot(dates, trend_lower, 'b--', alpha=0.8, linewidth=2, label='支撑趋势线')
        ax.plot(dates, trend_final, 'g--', alpha=0.8, linewidth=2, label='收盘趋势线')
        
        # 标记当前估值
        if current_val is not None:
            ax.scatter([dates[-1]], [current_val], color='red', s=100, zorder=5, label='当前估值')
            ax.axhline(y=current_val, color='purple', linestyle=':', alpha=0.5, linewidth=1)
            
            # 计算位置百分比
            if trend_upper[-1] > trend_lower[-1]:
                pos_percent = (current_val - trend_lower[-1]) / (trend_upper[-1] - trend_lower[-1]) * 100
                ax.text(dates[-1], current_val, f'{pos_percent:.1f}%', 
                       ha='left', va='bottom', fontsize=10, fontweight='bold')
        
        ax.set_title(f"{self.fund_name}({self.fund_code}) 日线趋势通道分析", fontsize=16, fontweight='bold')
        ax.set_xlabel("日期", fontsize=12)
        ax.set_ylabel("估值", fontsize=12)
        ax.legend(loc='upper left', bbox_to_anchor=(1.05, 1), borderaxespad=0.)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(DateFormatter("%m-%d"))
        ax.xaxis.set_major_locator(DayLocator(interval=7))
        fig.autofmt_xdate()
        fig.tight_layout()
        
        return fig
        
    class FundSeasonalityAnalyzer:
        """内部季节性分析器类"""
        def __init__(self, df, fund_code=None, fund_name=None):
            self.df = df
            self.fund_code = fund_code
            self.fund_name = fund_name
            self.monthly_stats = None
            self.weekly_stats = None
            
        def analyze_monthly_seasonality(self):
            """分析月度季节性"""
            monthly_results = []
            
            # 提取年月信息
            self.df['年份'] = self.df['交易日期'].dt.year
            self.df['月份'] = self.df['交易日期'].dt.month
            
            # 按月分组
            grouped = self.df.groupby(['年份', '月份'])
            
            for (year, month), group in grouped:
                if len(group) < 2:
                    continue
                    
                # 按日期排序
                group_sorted = group.sort_values('交易日期')
                
                # 获取第一个和最后一个交易日的净值
                first_val = group_sorted.iloc[0]['净值']
                last_val = group_sorted.iloc[-1]['净值']
                
                # 计算月度涨跌幅
                if pd.notna(first_val) and pd.notna(last_val) and first_val != 0:
                    monthly_return = (last_val - first_val) / first_val * 100
                else:
                    monthly_return = 0
                    
                monthly_results.append({
                    '年份': year,
                    '月份': month,
                    '起始净值': first_val,
                    '结束净值': last_val,
                    '涨跌幅%': monthly_return
                })
            
            # 转换为DataFrame
            monthly_df = pd.DataFrame(monthly_results)
            
            # 按月份计算统计信息
            month_stats = {}
            month_names = ["1月", "2月", "3月", "4月", "5月", "6月",
                          "7月", "8月", "9月", "10月", "11月", "12月"]
            
            for month in range(1, 13):
                month_data = monthly_df[monthly_df['月份'] == month]
                if len(month_data) > 0:
                    returns = month_data['涨跌幅%']
                    month_stats[month] = {
                        '月份名称': month_names[month-1],
                        '平均涨跌幅': returns.mean(),
                        '涨跌次数': len(returns[returns > 0]),
                        '下跌次数': len(returns[returns < 0]),
                        '最大涨幅': returns.max(),
                        '最大跌幅': returns.min(),
                        '上涨概率': len(returns[returns > 0]) / len(returns) * 100 if len(returns) > 0 else 0,
                        '样本数量': len(returns)
                    }
                else:
                    month_stats[month] = {
                        '月份名称': month_names[month-1],
                        '平均涨跌幅': 0,
                        '涨跌次数': 0,
                        '下跌次数': 0,
                        '最大涨幅': 0,
                        '最大跌幅': 0,
                        '上涨概率': 0,
                        '样本数量': 0
                    }
            
            self.monthly_stats = month_stats
            return monthly_df, month_stats
            
    def get_observation_zone_analysis(self, fund_code, min_val, start_date, end_date, expand_by=0.0100):
        """
        根据历史最低估值生成观察区段分析文本
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