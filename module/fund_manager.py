# fund_manager.py
# 标准库
import json
import math
import requests
import re  # 需要导入 re 模块用于 _fetch_fund_info
from bs4 import BeautifulSoup
from datetime import datetime

# GUI 相关
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 本地模块（需确保路径正确）
from utils.db.database import db_connection


class FundManager:
    def __init__(self, root, status_var, refresh_funds_cb, update_main_list_cb):
        """
        基金管理核心类：封装基金添加、编辑、删除、导入导出等功能
        :param root: 主窗口实例（用于GUI操作）
        :param status_var: 主程序状态显示变量（更新状态条）
        :param refresh_funds_cb: 主程序刷新基金数据的回调函数
        :param update_main_list_cb: 主程序更新监控列表的回调函数
        """
        self.root = root
        self.status_var = status_var
        self.refresh_funds_cb = refresh_funds_cb  # 主程序刷新funds的回调
        self.update_main_list_cb = update_main_list_cb  # 主程序更新监控列表的回调

        # 表单控件变量（用于添加/编辑基金）
        self.add_code_var = None
        self.add_name_var = None
        self.add_net_value_var = None
        self.add_hold_var = None
        self.add_cost_var = None
        self.add_shares_var = None
        # 新增：提醒阈值变量
        self.add_rise_alert_var = None
        self.add_fall_alert_var = None

        # 已添加基金列表（Treeview控件）
        self.existing_funds_tree = None

        # 表单输入控件（缓存用于状态切换）
        self.add_cost_entry = None
        self.add_shares_entry = None
        # 新增：提醒阈值输入控件
        self.add_rise_alert_entry = None
        self.add_fall_alert_entry = None

    def load_funds_data(self):
        """从数据库加载基金数据，返回基金列表（供主程序使用）"""
        funds = []
        try:
            with db_connection() as cursor:
                # 假设数据库表 funds 已更新，包含 rise_alert 和 fall_alert 字段
                cursor.execute("SELECT code, name, latest_net_value, is_hold, cost, shares, rise_alert, fall_alert FROM funds")
                for record in cursor.fetchall():
                    funds.append({
                        "code": record[0],
                        "name": record[1],
                        "latest_net_value": record[2],
                        "is_hold": bool(record[3]),
                        "cost": record[4],
                        "shares": record[5],
                        # 新增字段
                        "rise_alert": record[6],
                        "fall_alert": record[7],
                        "current_value": None,
                        "change_rate": None,
                        "update_time": None,
                        "history": []
                    })
        except Exception as e:
            print(f"[FundManager] 加载基金数据失败: {str(e)}")
            self.status_var.set(f"加载基金数据失败: {str(e)}")
        return funds

    def init_add_fund_tab(self, add_fund_tab):
        """初始化「基金管理」标签页（创建表单、列表、按钮等GUI组件）"""
        main_frame = ttk.Frame(add_fund_tab, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---------------------- 1. 添加基金表单 ----------------------
        # 基金代码
        ttk.Label(main_frame, text="基金代码:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.add_code_var = tk.StringVar()
        ttk.Entry(
            main_frame, 
            textvariable=self.add_code_var, 
            width=10
        ).grid(row=0, column=1, sticky=tk.W, pady=5)
        # 获取基金信息按钮
        ttk.Button(
            main_frame, 
            text="获取基金信息", 
            command=self._fetch_fund_info
        ).grid(row=0, column=2, padx=5, pady=5)

        # 基金名称（只读，自动获取）
        ttk.Label(main_frame, text="基金名称:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.add_name_var = tk.StringVar()
        ttk.Entry(
            main_frame, 
            textvariable=self.add_name_var, 
            width=30, 
            state="readonly"
        ).grid(row=1, column=1, sticky=tk.W, pady=5)

        # 最新净值（只读，自动获取）
        ttk.Label(main_frame, text="最新净值:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.add_net_value_var = tk.StringVar()
        ttk.Entry(
            main_frame, 
            textvariable=self.add_net_value_var, 
            width=15, 
            state="readonly"
        ).grid(row=2, column=1, sticky=tk.W, pady=5)

        # 是否持有（勾选后显示成本/份额/提醒阈值输入框）
        self.add_hold_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            main_frame, 
            text="是否持有", 
            variable=self.add_hold_var, 
            command=self._toggle_hold_fields
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=5)

        # 成本价（默认禁用）
        ttk.Label(main_frame, text="成本价:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.add_cost_var = tk.DoubleVar()
        self.add_cost_entry = ttk.Entry(
            main_frame, 
            textvariable=self.add_cost_var, 
            width=15, 
            state="disabled"
        )
        self.add_cost_entry.grid(row=4, column=1, sticky=tk.W, pady=5)

        # 持有份额（默认禁用）
        ttk.Label(main_frame, text="持有份额:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.add_shares_var = tk.DoubleVar()
        self.add_shares_entry = ttk.Entry(
            main_frame, 
            textvariable=self.add_shares_var, 
            width=15, 
            state="disabled"
        )
        self.add_shares_entry.grid(row=5, column=1, sticky=tk.W, pady=5)

        # 新增：上涨提醒阈值（默认禁用）
        ttk.Label(main_frame, text="上涨提醒阈值 (%):").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.add_rise_alert_var = tk.DoubleVar()
        self.add_rise_alert_entry = ttk.Entry(
            main_frame,
            textvariable=self.add_rise_alert_var,
            width=15,
            state="disabled"
        )
        self.add_rise_alert_entry.grid(row=6, column=1, sticky=tk.W, pady=5)

        # 新增：下跌提醒阈值（默认禁用）
        ttk.Label(main_frame, text="下跌提醒阈值 (%):").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.add_fall_alert_var = tk.DoubleVar()
        self.add_fall_alert_entry = ttk.Entry(
            main_frame,
            textvariable=self.add_fall_alert_var,
            width=15,
            state="disabled"
        )
        self.add_fall_alert_entry.grid(row=7, column=1, sticky=tk.W, pady=5)

        # 保存/清空按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=8, column=0, columnspan=3, pady=15)
        ttk.Button(btn_frame, text="保存基金", command=self._save_fund).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空", command=self._clear_form).pack(side=tk.LEFT, padx=5)

        # ---------------------- 2. 分隔线 ----------------------
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(
            row=9, column=0, columnspan=3, sticky=tk.EW, pady=10
        )

        # ---------------------- 3. 导入导出 ----------------------
        import_export_frame = ttk.LabelFrame(main_frame, text="数据导入导出", padding="10")
        import_export_frame.grid(row=10, column=0, columnspan=3, sticky=tk.EW, pady=10)
        ttk.Button(
            import_export_frame, 
            text="导出基金数据", 
            command=self._export_funds
        ).pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Button(
            import_export_frame, 
            text="导入基金数据", 
            command=self._import_funds
        ).pack(side=tk.LEFT, padx=10, pady=5)

        # ---------------------- 4. 已添加基金列表 ----------------------
        ttk.Label(main_frame, text="已添加基金:").grid(row=11, column=0, sticky=tk.W, pady=5)
        # 创建Treeview
        self.existing_funds_tree = ttk.Treeview(
            main_frame, 
            columns=("code", "name", "hold"), 
            show="headings", 
            height=8
        )
        # 配置列
        self.existing_funds_tree.heading("code", text="基金代码")
        self.existing_funds_tree.heading("name", text="基金名称")
        self.existing_funds_tree.heading("hold", text="是否持有")
        self.existing_funds_tree.column("code", width=100)
        self.existing_funds_tree.column("name", width=200)
        self.existing_funds_tree.column("hold", width=80, anchor="center")
        # 布局
        self.existing_funds_tree.grid(row=12, column=0, columnspan=2, sticky=tk.EW, pady=5)

        # 编辑/删除按钮
        ops_frame = ttk.Frame(main_frame)
        ops_frame.grid(row=12, column=2, padx=10)
        ttk.Button(ops_frame, text="编辑", command=self._edit_fund).pack(fill=tk.X, pady=2)
        ttk.Button(ops_frame, text="删除", command=self._delete_fund).pack(fill=tk.X, pady=2)

        # 初始化已添加基金列表
        self._refresh_existing_funds_list()

    # ---------------------- 内部工具方法 ----------------------
    def _toggle_hold_fields(self):
        """根据「是否持有」勾选状态，切换成本/份额/提醒阈值输入框的启用状态"""
        state = "normal" if self.add_hold_var.get() else "disabled"
        self.add_cost_entry.config(state=state)
        self.add_shares_entry.config(state=state)
        # 新增：切换提醒阈值输入框状态
        self.add_rise_alert_entry.config(state=state)
        self.add_fall_alert_entry.config(state=state)

    def _fetch_fund_info(self):
        """从东方财富网获取基金名称和最新净值（供添加表单使用）"""
        fund_code = self.add_code_var.get().strip()
        # 校验基金代码格式
        if not (fund_code.isdigit() and len(fund_code) == 6):
            messagebox.showerror("错误", "请输入有效的6位基金代码")
            return

        self.status_var.set(f"正在获取基金信息: {fund_code}")
        self.root.update()  # 强制刷新UI，显示状态

        try:
            # 爬取东方财富网基金详情页
            url = f"https://fund.eastmoney.com/{fund_code}.html"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")

            # 提取基金名称
            name_tag = soup.find("div", class_="fundDetail-tit")
            if not name_tag:
                raise ValueError("未找到基金名称")
            fund_name = name_tag.get_text(strip=True).split("(")[0]

            # 提取最新净值
            net_value = None
            for item in soup.find_all("div", class_="dataItem"):
                if "单位净值" in item.text:
                    match = re.search(r"(\d+\.\d+)", item.get_text(strip=True))
                    if match:
                        net_value = float(match.group(1))
                        break

            # 更新表单
            self.add_name_var.set(fund_name)
            self.add_net_value_var.set(f"{net_value:.4f}" if net_value else "")
            self.status_var.set("就绪")

        except Exception as e:
            messagebox.showerror("错误", f"获取基金信息失败: {str(e)}")
            self.status_var.set("就绪")


    def _save_fund(self):
        """保存基金（新增或更新）"""
        # 表单数据校验
        fund_code = self.add_code_var.get().strip()
        fund_name = self.add_name_var.get().strip()
    
        if not fund_code or not fund_name:
            messagebox.showerror("错误", "请先获取基金信息")
            return
    
        #最新净值处理：非法或空值 → 0.0
        net_value_str = self.add_net_value_var.get().strip()
        try:
            latest_net_value = float(net_value_str) if net_value_str else 0.0
            if math.isinf(latest_net_value) or math.isnan(latest_net_value):
                latest_net_value = 0.0
        except (ValueError, TypeError):
            latest_net_value = 0.0
    
        # 处理持有状态
        is_hold = self.add_hold_var.get()
        cost = shares = rise_alert = fall_alert = None
    
        if is_hold:
            # 获取输入值
            cost_str = self.add_cost_entry.get().strip()
            shares_str = self.add_shares_entry.get().strip()
            rise_alert_str = self.add_rise_alert_entry.get().strip()
            fall_alert_str = self.add_fall_alert_entry.get().strip()
    
            # 必填项校验
            if not cost_str:
                messagebox.showerror("错误", "持有状态下，成本价不能为空")
                return
            if not shares_str:
                messagebox.showerror("错误", "持有状态下，份额不能为空")
                return
    
            # 成本与份额转换与校验
            try:
                cost = float(cost_str)
                shares = float(shares_str)
                if cost <= 0:
                    raise ValueError("成本价必须大于 0")
                if shares <= 0:
                    raise ValueError("份额必须大于 0")
            except ValueError as e:
                messagebox.showerror("错误", f"成本价或份额输入无效: {e}")
                return
    
            # 提醒阈值校验（可选字段）
            try:
                if rise_alert_str:
                    rise_alert = float(rise_alert_str)
                    if not (0 <= rise_alert <= 1000):
                        raise ValueError("上涨提醒阈值必须在 0 到 1000 之间")
                if fall_alert_str:
                    fall_alert = float(fall_alert_str)
                    if not (0 <= fall_alert <= 1000):
                        raise ValueError("下跌提醒阈值必须在 0 到 1000 之间")
            except ValueError as e:
                messagebox.showerror("错误", f"提醒阈值输入无效: {e}")
                return
    
        # 数据库操作：新增或更新
        try:
            with db_connection() as cursor:
                cursor.execute("SELECT code FROM funds WHERE code = ?", (fund_code,))
                exists = cursor.fetchone()
        
                # 所有字段（包含提醒阈值）
                base_fields = (
                    fund_name,
                    latest_net_value,
                    1 if is_hold else 0,
                    cost,
                    shares,
                    rise_alert,
                    fall_alert
                )
        
                if exists:
                    cursor.execute('''
                        UPDATE funds 
                        SET name = ?, 
                            latest_net_value = ?, 
                            is_hold = ?, 
                            cost = ?, 
                            shares = ?, 
                            rise_alert = ?, 
                            fall_alert = ?
                        WHERE code = ?
                    ''', base_fields + (fund_code,))
                    msg = f"已更新基金: {fund_name}({fund_code})"
                else:
                    cursor.execute('''
                        INSERT INTO funds (
                            code, name, latest_net_value, is_hold, 
                            cost, shares, rise_alert, fall_alert
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (fund_code,) + base_fields)
                    msg = f"已添加基金: {fund_name}({fund_code})"
        
            # 成功提示与界面刷新
            messagebox.showinfo("成功", msg)
            self.refresh_funds_cb()                  # 刷新下拉列表
            self.update_main_list_cb()               # 更新主监控列表
            self._refresh_existing_funds_list()      # 刷新已添加基金列表
            self._clear_form()                       # 清空表单
        
        except Exception as e:
            messagebox.showerror("错误", f"保存基金失败: {str(e)}")
    def _clear_form(self):
        """清空添加基金表单"""
        self.add_code_var.set("")
        self.add_name_var.set("")
        self.add_net_value_var.set("")
        self.add_hold_var.set(False)
        self.add_cost_var.set(0)
        self.add_shares_var.set(0)
        # 新增：清空提醒阈值
        self.add_rise_alert_var.set(0)
        self.add_fall_alert_var.set(0)
        self._toggle_hold_fields()  # 重置输入框状态

    def _refresh_existing_funds_list(self):
        """刷新「已添加基金」列表"""
        # 清空现有数据
        for item in self.existing_funds_tree.get_children():
            self.existing_funds_tree.delete(item)
        # 加载并添加新数据
        funds = self.load_funds_data()
        for fund in funds:
            hold_mark = "✓" if fund["is_hold"] else ""
            self.existing_funds_tree.insert(
                "", tk.END, values=(fund["code"], fund["name"], hold_mark)
            )

    def _edit_fund(self):
        """编辑选中的基金"""
        selected = self.existing_funds_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一个基金")
            return

        # 获取选中基金的代码和数据
        fund_code = self.existing_funds_tree.item(selected[0], "values")[0]
        funds = self.load_funds_data()
        fund = next((f for f in funds if f["code"] == fund_code), None)
        if not fund:
            messagebox.showerror("错误", "未找到选中基金的数据")
            return

        # 填充表单
        self.add_code_var.set(fund["code"])
        self.add_name_var.set(fund["name"])
        self.add_net_value_var.set(f"{fund['latest_net_value']:.4f}" if fund["latest_net_value"] else "")
        self.add_hold_var.set(fund["is_hold"])
        self.add_cost_var.set(fund["cost"] if fund["cost"] else 0)
        self.add_shares_var.set(fund["shares"] if fund["shares"] else 0)
        # 新增：填充提醒阈值
        self.add_rise_alert_var.set(fund["rise_alert"] if fund["rise_alert"] else 0)
        self.add_fall_alert_var.set(fund["fall_alert"] if fund["fall_alert"] else 0)
        self._toggle_hold_fields()  # 同步输入框状态

    def _delete_fund(self):
        """删除选中的基金（含关联估值数据）"""
        selected = self.existing_funds_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一个基金")
            return

        # 确认删除
        fund_code = self.existing_funds_tree.item(selected[0], "values")[0]
        fund_name = self.existing_funds_tree.item(selected[0], "values")[1]
        if not messagebox.askyesno("确认", f"确定删除基金 {fund_name}({fund_code}) 吗？\n（关联估值数据也会删除）"):
            return

        # 数据库操作（删除基金+关联估值数据）
        try:
            with db_connection() as cursor:
                # 删除关联估值数据
                cursor.execute("DELETE FROM fund_estimate_main WHERE fund_code = ?", (fund_code,))
                cursor.execute("DELETE FROM fund_estimate_details WHERE fund_code = ?", (fund_code,))
                # 删除基金本身
                cursor.execute("DELETE FROM funds WHERE code = ?", (fund_code,))

            # 同步更新界面
            self.refresh_funds_cb()
            self.update_main_list_cb()
            self._refresh_existing_funds_list()
            messagebox.showinfo("成功", "基金已删除")

        except Exception as e:
            messagebox.showerror("错误", f"删除基金失败: {str(e)}")

    def _export_funds(self):
        """导出基金数据到JSON文件"""
        funds = self.load_funds_data()
        if not funds:
            messagebox.showinfo("提示", "没有可导出的基金数据")
            return

        # 选择保存路径
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            title="导出基金数据"
        )
        if not file_path:
            return

        # 导出数据（格式化JSON）
        try:
            export_data = [
                {
                    "code": f["code"],
                    "name": f["name"],
                    "latest_net_value": f["latest_net_value"],
                    "is_hold": f["is_hold"],
                    "cost": f["cost"],
                    "shares": f["shares"],
                    # 新增：导出提醒阈值
                    "rise_alert": f["rise_alert"],
                    "fall_alert": f["fall_alert"]
                } for f in funds
            ]
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"基金数据已导出到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {str(e)}")

    def _import_funds(self):
        """从JSON文件导入基金数据"""
        # 选择导入文件
        file_path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            title="导入基金数据"
        )
        if not file_path:
            return

        # 解析并导入数据
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                import_data = json.load(f)
            if not isinstance(import_data, list):
                raise ValueError("导入数据必须是列表格式")

            imported = 0
            updated = 0
            with db_connection() as cursor:
                for fund in import_data:
                    # 校验必要字段
                    if not all(k in fund for k in ["code", "name"]):
                        continue

                    fund_code = fund["code"]
                    # 检查基金是否已存在
                    cursor.execute("SELECT code FROM funds WHERE code = ?", (fund_code,))
                    if cursor.fetchone():
                        # 更新现有基金
                        cursor.execute('''
                            UPDATE funds 
                            SET name = ?, latest_net_value = ?, is_hold = ?, cost = ?, shares = ?, rise_alert = ?, fall_alert = ?
                            WHERE code = ?
                        ''', (fund["name"], fund.get("latest_net_value"),
                              1 if fund.get("is_hold", False) else 0,
                              fund.get("cost"), fund.get("shares"),
                              fund.get("rise_alert"), fund.get("fall_alert"), # 新增：更新提醒阈值
                              fund_code))
                        updated += 1
                    else:
                        # 新增基金
                        cursor.execute('''
                            INSERT INTO funds 
                            (code, name, latest_net_value, is_hold, cost, shares, rise_alert, fall_alert) # 新增：字段
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?) # 新增：占位符
                        ''', (fund_code, fund["name"], fund.get("latest_net_value"),
                              1 if fund.get("is_hold", False) else 0,
                              fund.get("cost"), fund.get("shares"),
                              fund.get("rise_alert"), fund.get("fall_alert"))) # 新增：值
                        imported += 1

            # 同步更新界面
            self.refresh_funds_cb()
            self.update_main_list_cb()
            self._refresh_existing_funds_list()
            messagebox.showinfo("成功", f"导入完成\n新增: {imported} 个 | 更新: {updated} 个")

        except Exception as e:
            messagebox.showerror("错误", f"导入失败: {str(e)}")