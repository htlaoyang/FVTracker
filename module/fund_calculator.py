from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional
from decimal import Decimal, InvalidOperation
from datetime import datetime

# 自定义工具导入
from utils.sys_chinese_font import get_best_chinese_font
from utils.db.database import db_connection

# 配置中文字体
AVAILABLE_CHINESE_FONT = get_best_chinese_font() or "SimHei"  # fallback


class FundCostCalculator:
    def __init__(self, root, parent, fund_code, fund_name):
        self.root = root
        self.parent = parent
        self.fund_code = fund_code
        self.fund_name = fund_name

        # 持有数据（初始为 None，表示未加载或未持有）
        self.hold_cost = None
        self.hold_shares = None

        # 结果变量
        self.result_cost = tk.StringVar(value="--")
        self.result_new_shares = tk.StringVar(value="--")
        self.result_total_shares = tk.StringVar(value="--")
        self.result_add_amount = tk.StringVar(value="--")
        self.input_var = tk.StringVar()

        # 手动输入的持有数据（用于未持有场景）
        self.manual_cost = tk.DoubleVar(value=0.0)
        self.manual_shares = tk.DoubleVar(value=0.0)

        # 操作模式
        self.operation_mode = tk.StringVar(value="amount")

        # 设置窗口
        self.root.title(f"成本计算器 - {fund_name}")
        self.root.geometry("640x480")
        self.root.resizable(False, False)
        self._set_window_center(640, 480)

        # 加载数据
        self.load_holding_data()

        # 创建控件
        self.create_widgets()

        # 绑定模式切换事件
        self.operation_mode.trace("w", self.on_mode_change)

        # 预加载估值
        self.after_id = self.root.after(100, self.preload_and_update_on_start)

    def _set_window_center(self, width, height):
        """居中显示窗口"""
        try:
            parent_x = self.parent.winfo_x()
            parent_y = self.parent.winfo_y()
            parent_w = self.parent.winfo_width()
            parent_h = self.parent.winfo_height()

            x = parent_x + (parent_w - width) // 2
            y = parent_y + (parent_h - height) // 2

            if parent_w <= 1 or parent_h <= 1:
                x = (self.root.winfo_screenwidth() - width) // 2
                y = (self.root.winfo_screenheight() - height) // 2

            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.root.transient(self.parent)
            self.root.grab_set()
        except Exception as e:
            print(f"居中失败：{e}")

    def load_holding_data(self):
        """从数据库加载持有成本和份额，若未持有则留空"""
        self.hold_cost = None
        self.hold_shares = None
        try:
            with db_connection() as conn:
                result = conn.execute("""
                    SELECT cost, shares FROM funds 
                    WHERE code = ? AND is_hold = 1
                """, (self.fund_code,))
                row = result.fetchone()
                if row and row[0] is not None and row[1] is not None:
                    self.hold_cost = float(row[0])
                    self.hold_shares = float(row[1])
        except Exception as e:
            messagebox.showwarning("数据库错误", f"读取基金数据失败：{str(e)}")

    def create_widgets(self):
        """创建控件"""
        frame = ttk.Frame(self.root, padding="12")
        frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        # === 基金信息区 ===
        tk.Label(frame, text="基金代码：", font=(AVAILABLE_CHINESE_FONT, 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=2)
        tk.Label(frame, text=self.fund_code, fg="blue", font=(AVAILABLE_CHINESE_FONT, 10)).grid(
            row=0, column=1, sticky="w", padx=(10, 0))

        tk.Label(frame, text="基金名称：", font=(AVAILABLE_CHINESE_FONT, 10, "bold")).grid(
            row=1, column=0, sticky="w", pady=2)
        tk.Label(frame, text=self.fund_name, font=(AVAILABLE_CHINESE_FONT, 10)).grid(
            row=1, column=1, sticky="w", padx=(10, 0))

        # --- 持有信息输入区 ---
        tk.Label(frame, text="持有成本（元）：", font=(AVAILABLE_CHINESE_FONT, 10, "bold")).grid(
            row=2, column=0, sticky="w", pady=6)

        self.cost_entry = ttk.Entry(frame, width=18)
        self.cost_entry.grid(row=2, column=1, sticky="w", padx=(10, 0))
        # 初始值由后续逻辑设置

        tk.Label(frame, text="持有份额：", font=(AVAILABLE_CHINESE_FONT, 10, "bold")).grid(
            row=3, column=0, sticky="w", pady=6)

        self.shares_entry = ttk.Entry(frame, width=18)
        self.shares_entry.grid(row=3, column=1, sticky="w", padx=(10, 0))
        # 初始值由后续逻辑设置

        # 提示标签
        self.hold_info_label = tk.Label(frame, text="", font=(AVAILABLE_CHINESE_FONT, 9), fg="gray")
        self.hold_info_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))

        # 分隔线
        ttk.Separator(frame, orient='horizontal').grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)

        # === 操作模式选择 ===
        tk.Label(frame, text="操作模式：", font=(AVAILABLE_CHINESE_FONT, 10, "bold")).grid(
            row=6, column=0, sticky="w", pady=2)

        mode_frame = ttk.Frame(frame)
        mode_frame.grid(row=6, column=1, sticky="w", padx=(10, 0))
        ttk.Radiobutton(mode_frame, text="输入加仓金额", variable=self.operation_mode, value="amount").pack(side="left")
        ttk.Radiobutton(mode_frame, text="输入目标成本", variable=self.operation_mode, value="target_cost").pack(side="left", padx=(10, 0))

        # === 输入框 + 刷新按钮行 ===
        input_row_frame = ttk.Frame(frame)
        input_row_frame.grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=2)

        self.input_label = tk.Label(input_row_frame, text="加仓金额（元）：", font=(AVAILABLE_CHINESE_FONT, 10))
        self.input_label.pack(side="left")

        ttk.Entry(input_row_frame, textvariable=self.input_var, width=18).pack(side="left", padx=(5, 0))

        # 刷新按钮
        refresh_btn = ttk.Button(input_row_frame, text="刷新估值", width=12, command=self.refresh_current_estimate)
        refresh_btn.pack(side="right", padx=(10, 0))

        # === 自动填充提示标签 ===
        self.auto_fill_label = tk.Label(frame, text="", font=(AVAILABLE_CHINESE_FONT, 9), fg="gray")
        self.auto_fill_label.grid(row=8, column=0, columnspan=2, sticky="w", padx=30, pady=(0, 5))

        # === 计算按钮 ===
        calc_btn = ttk.Button(frame, text="▶ 开始计算", command=self.calculate)
        calc_btn.grid(row=9, column=0, columnspan=2, pady=15)

        # === 结果区 ===
        result_container = tk.LabelFrame(frame, text="计算结果", font=(AVAILABLE_CHINESE_FONT, 10, "bold"), bd=2)
        result_container.grid(row=10, column=0, columnspan=2, sticky="ew", pady=5, padx=5)

        tk.Label(result_container, text="新的成本价：", font=(AVAILABLE_CHINESE_FONT, 10)).grid(row=0, column=0, sticky="w", pady=2)
        tk.Label(result_container, textvariable=self.result_cost, fg="green", font=(AVAILABLE_CHINESE_FONT, 10)).grid(
            row=0, column=1, sticky="w", padx=(10, 0))

        tk.Label(result_container, text="新增持有份额：", font=(AVAILABLE_CHINESE_FONT, 10)).grid(row=1, column=0, sticky="w", pady=2)
        tk.Label(result_container, textvariable=self.result_new_shares, font=(AVAILABLE_CHINESE_FONT, 10)).grid(
            row=1, column=1, sticky="w", padx=(10, 0))

        tk.Label(result_container, text="总计持有份额：", font=(AVAILABLE_CHINESE_FONT, 10)).grid(row=2, column=0, sticky="w", pady=2)
        tk.Label(result_container, textvariable=self.result_total_shares, font=(AVAILABLE_CHINESE_FONT, 10)).grid(
            row=2, column=1, sticky="w", padx=(10, 0))

        tk.Label(result_container, text="需加仓金额：", font=(AVAILABLE_CHINESE_FONT, 10)).grid(row=3, column=0, sticky="w", pady=2)
        tk.Label(result_container, textvariable=self.result_add_amount, font=(AVAILABLE_CHINESE_FONT, 10)).grid(
            row=3, column=1, sticky="w", padx=(10, 0))

        # 初始化界面状态
        self.init_holding_inputs()

    def init_holding_inputs(self):
        """初始化持有成本和份额输入框"""
        # 判断是否持有
        if self.hold_cost is not None and self.hold_shares is not None:
            # 已持有，显示真实数据
            self.cost_entry.insert(0, f"{self.hold_cost:.4f}")
            self.shares_entry.insert(0, f"{self.hold_shares:.4f}")
            self.hold_info_label.config(text="✅ 当前为已持有基金，使用数据库中的成本与份额。")
        else:
            # 未持有，允许手动输入，初始值为0和最新估值
            self.shares_entry.insert(0, "0")
            # 成本稍后由估值填充
            self.hold_info_label.config(
                text="⚠️ 当前未持有该基金，可手动输入模拟成本与份额进行摊薄测算。")

    def get_current_estimate_from_cache(self) -> Optional[float]:
        """尝试从数据库获取最新实时估值（缓存版）"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            with db_connection() as conn:
                row = conn.execute("""
                    SELECT realtime_estimate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ?
                    ORDER BY estimate_time DESC 
                    LIMIT 1
                """, (self.fund_code, today)).fetchone()
                return float(row[0]) if row and row[0] is not None else None
        except Exception as e:
            print(f"获取估值失败：{e}")
            return None

    def get_current_estimate(self) -> Optional[float]:
        """从数据库获取最新实时估值（带弹窗提示）"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            with db_connection() as conn:
                row = conn.execute("""
                    SELECT realtime_estimate 
                    FROM fund_estimate_details 
                    WHERE fund_code = ? AND trade_date = ?
                    ORDER BY estimate_time DESC 
                    LIMIT 1
                """, (self.fund_code, today)).fetchone()
                if row and row[0] is not None:
                    return float(row[0])
                else:
                    messagebox.showwarning(
                        "数据缺失",
                        f"未找到基金 {self.fund_code} 今日的实时估值。\n请确认数据已更新。"
                    )
                    return None
        except Exception as e:
            messagebox.showerror("数据库错误", f"获取实时估值失败：{str(e)}")
            return None

    def refresh_current_estimate(self):
        """刷新当前估值"""
        current = self.get_current_estimate()
        if current is not None:
            self.update_auto_fill_label(current)
            # 如果是未持有状态，且成本输入为空，则自动填充
            cost_input = self.cost_entry.get().strip()
            if not cost_input or self.is_cost_input_invalid():
                self.cost_entry.delete(0, tk.END)
                self.cost_entry.insert(0, f"{current:.4f}")

            # 如果是 target_cost 模式，也尝试填充目标
            if self.operation_mode.get() == "target_cost":
                if not self.input_var.get().strip() or self.is_input_invalid_for_target_mode():
                    self.input_var.set(f"{current:.4f}")

            self.clear_results()

    def is_cost_input_invalid(self):
        """判断成本输入是否无效"""
        try:
            val = float(self.cost_entry.get())
            return val <= 0
        except Exception:
            return True

    def is_input_invalid_for_target_mode(self):
        """判断目标成本输入是否无效"""
        try:
            val = float(self.input_var.get())
            return val <= 0
        except Exception:
            return True

    def update_auto_fill_label(self, current_value: float):
        """更新自动填充提示文字"""
        self.auto_fill_label.config(
            text=f"系统已自动填充可实现的最低摊薄成本：{current_value:.4f} 元"
        )

    def clear_results(self):
        """清空计算结果"""
        self.result_cost.set("--")
        self.result_new_shares.set("--")
        self.result_total_shares.set("--")
        self.result_add_amount.set("--")

    def preload_and_update_on_start(self):
        """启动时尝试预加载估值并填充成本"""
        try:
            current = self.get_current_estimate_from_cache()
            if current is not None:
                # 只有在未持有且成本为空时才自动填充
                if self.hold_cost is None:
                    cost_input = self.cost_entry.get().strip()
                    if not cost_input:
                        self.cost_entry.delete(0, tk.END)
                        self.cost_entry.insert(0, f"{current:.4f}")
                # 同时更新提示
                self.update_auto_fill_label(current)
        except Exception as e:
            print(f"预加载估值失败：{e}")
        finally:
            if hasattr(self, 'after_id'):
                self.root.after_cancel(self.after_id)
                delattr(self, 'after_id')

    def on_mode_change(self, *args):
        """切换模式时更新标签文本"""
        mode = self.operation_mode.get()

        if mode == "amount":
            self.input_label.config(text="加仓金额（元）：")
            self.auto_fill_label.config(text="")
            self.result_add_amount.set("--")
            self.clear_results()
        else:
            self.input_label.config(text="目标成本价（元）：")
            self.result_cost.set("--")
            self.result_add_amount.set("--")
            self.result_new_shares.set("--")
            self.result_total_shares.set("--")

            # 尝试获取当前估值以更新提示
            current = self.get_current_estimate_from_cache()
            if current is not None:
                self.update_auto_fill_label(current)
                if not self.input_var.get().strip():
                    self.input_var.set(f"{current:.4f}")
            else:
                self.auto_fill_label.config(text="⚠️ 未获取到实时估值，请点击【刷新估值】")

    def get_user_input(self):
        """获取用户输入并转为 Decimal"""
        try:
            val_str = self.input_var.get().strip()
            if not val_str:
                raise ValueError("输入为空")
            value = Decimal(val_str)
            if value <= 0:
                raise ValueError("必须大于0")
            return value
        except (InvalidOperation, ValueError) as e:
            messagebox.showerror("输入错误", f"请输入有效的大于0的数字。\n({str(e)})")
            return None

    def get_holding_data_from_inputs(self) -> tuple[Optional[float], Optional[float]]:
        """从输入框获取持有成本和份额"""
        try:
            cost_str = self.cost_entry.get().strip()
            if not cost_str:
                messagebox.showwarning("输入提示", "请输入持有成本价。")
                return None, None
            cost = float(cost_str)
            if cost <= 0:
                raise ValueError("成本必须 > 0")

            shares_str = self.shares_entry.get().strip()
            shares = float(shares_str or 0)
            if shares < 0:
                raise ValueError("份额不能为负")

            return cost, shares

        except Exception as e:
            messagebox.showerror("输入错误", f"持有成本或份额输入无效：{str(e)}")
            return None, None

    def calculate(self):
        """执行摊薄成本计算"""
        # 获取当前估值
        current_estimate = self.get_current_estimate()
        if current_estimate is None:
            return

        # 获取用户操作输入
        input_val = self.get_user_input()
        if input_val is None:
            return

        # 获取持有信息（从数据库或用户输入）
        cost, shares = self.get_holding_data_from_inputs()
        if cost is None or shares is None:
            return

        # 转换为 Decimal
        try:
            cost_d = Decimal(str(cost))
            shares_d = Decimal(str(shares))
            current_d = Decimal(str(current_estimate))
            input_val_d = Decimal(str(input_val))
        except Exception:
            messagebox.showerror("数据错误", "数值转换失败，请检查输入是否为有效数字。")
            return

        mode = self.operation_mode.get()

        if mode == "amount":
            self._calculate_by_amount(input_val_d, cost_d, shares_d, current_d)
        elif mode == "target_cost":
            self._calculate_by_target_cost(input_val_d, cost_d, shares_d, current_d)

    def _calculate_by_amount(self, add_amount, cost, shares, current):
        """按加仓金额计算新成本"""
        if add_amount <= 0:
            messagebox.showerror("输入错误", "加仓金额必须大于0。")
            return

        new_shares = add_amount / current
        total_shares = shares + new_shares
        total_cost = cost * shares + add_amount
        new_cost = total_cost / total_shares if total_shares != 0 else cost

        self.result_cost.set(f"{new_cost:.4f}")
        self.result_new_shares.set(f"{new_shares:.4f}")
        self.result_total_shares.set(f"{total_shares:.4f}")
        self.result_add_amount.set("--")

    def _calculate_by_target_cost(self, target, cost, shares, current):
        """按目标成本计算所需金额"""
        if target <= 0:
            messagebox.showerror("输入错误", "目标成本价必须大于0。")
            return

        if target >= cost:
            messagebox.showinfo("无需摊薄",
                              f"目标成本 {target:.4f} 不低于当前持有成本 {cost:.4f}，无需加仓摊薄。")
            return

        if target < current:
            messagebox.showwarning("无法实现",
                                 f"目标成本 {target:.4f} 低于当前估值 {current:.4f}，\n"
                                 "无法以低于市价的成本买入，该目标不可达。")
            return

        # 公式推导：
        # (cost * shares + x) / (shares + x/current) = target
        # 解得：
        # x = (cost - target) * shares * current / (target - current)
        numerator = (cost - target) * shares * current
        denominator = target - current

        if denominator == 0:
            messagebox.showerror("计算错误", "目标成本等于当前价，无需加仓即可达成。")
            return

        required_amount = numerator / denominator

        if required_amount < 0:
            messagebox.showerror("异常", "计算出的加仓金额为负，请联系开发者。")
            return

        new_shares = required_amount / current
        total_shares = shares + new_shares

        self.result_add_amount.set(f"{required_amount:.2f}")
        self.result_new_shares.set(f"{new_shares:.4f}")
        self.result_total_shares.set(f"{total_shares:.4f}")
        self.result_cost.set(f"{target:.4f}")


def open_fund_calculator_view(parent, fund_code, fund_name):
    """打开成本计算器窗口"""
    top = tk.Toplevel(parent)
    app = FundCostCalculator(top, parent, fund_code, fund_name)

    def on_close():
        top.destroy()

    top.protocol("WM_DELETE_WINDOW", on_close)