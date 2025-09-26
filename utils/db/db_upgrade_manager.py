"""
数据库升级管理器（tkinter 版）
功能：检查并执行数据库增量升级，带图形化进度条
支持模态阻塞调用（主窗口等待升级完成）
"""

import sqlite3
import os
import threading
import traceback
import tkinter as tk
from tkinter import ttk
from utils.db.database import db_connection  # 导入现有数据库连接
from datetime import datetime
from queue import Queue
from pathlib import Path

class TkUpgradeDialog:
    """tkinter 升级进度对话框（模态）"""
    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.queue = Queue()  # 用于线程安全通信

        # 创建模态对话框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("数据库升级")
        self.dialog.transient(parent)           # 置于主窗口之上
        self.dialog.grab_set()                  # 模态：阻止操作主窗口
        self.dialog.resizable(False, False)
        self.dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁止关闭

        # 居中显示
        self.dialog.withdraw()
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 160
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 80
        self.dialog.geometry(f"320x120+{x}+{y}")
        self.dialog.deiconify()

        # UI 布局
        frame = ttk.Frame(self.dialog, padding=20)
        frame.pack(fill="both", expand=True)

        self.title_label = ttk.Label(
            frame,
            text="正在升级数据库...",
            font=("微软雅黑", 10, "bold"),
            anchor="center"
        )
        self.title_label.pack(pady=(0, 10))

        self.progress_bar = ttk.Progressbar(
            frame, orient="horizontal", length=280, mode="determinate"
        )
        self.progress_bar.pack(pady=5)

        self.status_label = ttk.Label(
            frame,
            text="准备中...",
            font=("微软雅黑", 9),
            wraplength=280,
            anchor="center",
            foreground="#666666"
        )
        self.status_label.pack(pady=5)

        # 启动轮询机制（从队列中读取更新）
        self.check_queue()

    def check_queue(self):
        """定期检查队列中的更新（主线程安全）"""
        while not self.queue.empty():
            try:
                percent, status = self.queue.get_nowait()
                self.progress_bar["value"] = percent
                self.status_label.config(text=status)
            except:
                pass
        if self.dialog.winfo_exists():
            self.parent.after(50, self.check_queue)  # 每 50ms 检查一次

    def update(self, percent: int, status: str):
        """供子线程调用的更新方法（线程安全）"""
        self.queue.put((percent, status))

    def close(self):
        """关闭对话框"""
        if self.dialog.winfo_exists():
            self.dialog.destroy()


class DBUpgradeManager:
    """数据库升级管理器：使用版本号(YYYYMMDDHHMMSS)作为主键的升级系统"""
    _system_tables_initialized = False

    def __init__(self):
        if not DBUpgradeManager._system_tables_initialized:
            self.init_system_tables()
            DBUpgradeManager._system_tables_initialized = True
        self.register_upgrades()

    def _write_log(self, message: str):
        """写入日志到按日期命名的日志文件，目录为 logs/uplogs"""
        log_dir = Path("logs") / "uplogs"
        log_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        log_file = log_dir / f"up_{now.strftime('%Y%m%d')}.log"
        timestamp = now.strftime("%H:%M:%S")

        try:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            # 可选：记录错误或打印到控制台
            print(f"Failed to write log: {e}")
    def init_system_tables(self):
        """初始化升级表和系统变量表（如果不存在）"""
        try:
            with db_connection() as cursor:
                # 先启用 WAL
                cursor.execute("PRAGMA journal_mode=WAL")
                # 1. 创建升级记录表（使用版本号作为主键）
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS db_upgrades (
                    version TEXT PRIMARY KEY NOT NULL, -- 版本号，格式YYYYMMDDHHMMSS
                    upgrade_type TEXT NOT NULL, -- 类型: table, column, procedure
                    target_name TEXT NOT NULL, -- 目标名称: 表名、字段名或存储过程名
                    sql_script TEXT NOT NULL, -- 升级SQL脚本
                    description TEXT, -- 升级描述
                    executed INTEGER DEFAULT 0, -- 执行状态: 0-未执行, 1-已执行
                    execution_time DATETIME -- 实际执行时间
                )
                ''')
                
                # 2. 创建系统变量表（存储最后升级版本等系统信息）
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_vars (
                    var_name TEXT PRIMARY KEY NOT NULL, -- 变量名
                    var_value TEXT, -- 变量值
                    description TEXT, -- 变量描述
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 最后更新时间
                )
                ''')

                # 3. 初始化最后升级版本变量
                cursor.execute('''
                INSERT OR IGNORE INTO system_vars 
                (var_name, var_value, description)
                VALUES (?, ?, ?)
                ''', ("last_upgrade_version", "20000101000000", "最后一次数据库升级的版本号"))

                self._write_log("系统表初始化完成")
        except Exception as e:
            self._write_log(f"初始化系统表失败: {str(e)}")

    @staticmethod
    def generate_version(dt=None):
        """
        根据日期时间生成版本号
        :param dt: datetime对象，默认为当前时间
        :return: 格式为YYYYMMDDHHMMSS的版本号字符串
        """
        if dt is None:
            dt = datetime.now()
        return dt.strftime("%Y%m%d%H%M%S")

    @staticmethod
    def parse_version(version_str):
        """
        将版本号字符串解析为datetime对象
        :param version_str: 格式为YYYYMMDDHHMMSS的版本号
        :return: datetime对象或None
        """
        try:
            return datetime.strptime(version_str, "%Y%m%d%H%M%S")
        except ValueError:
            return None

    def register_upgrades(self):
        """注册所有需要的数据库升级脚本（包含版本号）"""
        # 示例升级
        self.register_upgrade(
            version=self.generate_version(datetime(2023, 10, 1, 9, 30, 0)),
            upgrade_type="column",
            target_name="funds.rise_alert",
            sql_script="ALTER TABLE funds ADD COLUMN rise_alert REAL",
            description="为基金表添加上涨提醒阈值字段"
        )

        self.register_upgrade(
            version=self.generate_version(datetime(2023, 10, 5, 14, 15, 0)),
            upgrade_type="column",
            target_name="funds.fall_alert",
            sql_script="ALTER TABLE funds ADD COLUMN fall_alert REAL",
            description="为基金表添加下跌提醒阈值字段"
        )

        self.register_upgrade(
            version=self.generate_version(datetime(2023, 11, 15, 10, 0, 0)),
            upgrade_type="table",
            target_name="fund_reminders",
            sql_script='''
            CREATE TABLE fund_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_code TEXT NOT NULL,
                reminder_type TEXT NOT NULL,
                threshold REAL NOT NULL,
                triggered INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fund_code) REFERENCES funds(code)
            )
            ''',
            description="创建基金提醒历史记录表"
        )

        # 新增：为 fund_estimate_main 表添加 rise_alert 和 fall_alert 字段
        self.register_upgrade(
            version="20250917163500",
            upgrade_type="column",
            target_name="fund_estimate_main.rise_alert",
            sql_script="ALTER TABLE fund_estimate_main ADD COLUMN rise_alert REAL",
            description="为 fund_estimate_main 表添加上涨提醒阈值字段"
        )

        self.register_upgrade(
            version="20250917163501",
            upgrade_type="column",
            target_name="fund_estimate_main.fall_alert",
            sql_script="ALTER TABLE fund_estimate_main ADD COLUMN fall_alert REAL",
            description="为 fund_estimate_main 表添加下跌提醒阈值字段"
        )

    def register_upgrade(self, version, upgrade_type, target_name, sql_script, description):
        """
        注册升级脚本（如果尚未注册）
        
        :param version: 版本号，格式YYYYMMDDHHMMSS
        :param upgrade_type: 升级类型 table/column/procedure
        :param target_name: 目标名称，格式如 table_name 或 table_name.column_name
        :param sql_script: 要执行的SQL脚本
        :param description: 升级描述
        """
        try:
            with db_connection() as cursor:
                cursor.execute('SELECT version FROM db_upgrades WHERE version = ?', (version,))
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO db_upgrades 
                        (version, upgrade_type, target_name, sql_script, description)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (version, upgrade_type, target_name, sql_script, description))
                    self._write_log(f"已注册升级: 版本 {version} - {target_name}")
                else:
                    self._write_log(f"升级已存在: 版本 {version} - {target_name}")
        except Exception as e:
            self._write_log(f"注册升级失败 版本 {version}: {str(e)}")
            self._write_log(traceback.format_exc())

    def check_and_upgrade(self, parent: tk.Tk, callback=None):
        """
        【异步】检查并执行升级（推荐用于非阻塞场景）
        :param parent: 主窗口 tk.Tk 实例
        :param callback: 升级完成后回调函数，接收 success: bool
        """
        dialog = TkUpgradeDialog(parent)
        dialog.update(0, "正在检查升级...")

        result_queue = Queue()

        def run_upgrade():
            try:
                self._execute_upgrade_sync(progress_callback=dialog.update)
                result_queue.put(True)
            except Exception as e:
                self._write_log(f"升级失败: {str(e)}")
                result_queue.put(False)
            finally:
                result_queue.put(None)  # 结束标记

        def check_result():
            try:
                result = result_queue.get_nowait()
                if result is True:
                    dialog.update(100, "升级完成！")
                    if callback:
                        callback(True)
                elif result is False:
                    dialog.update(100, "升级失败")
                    if callback:
                        callback(False)
                elif result is None:
                    parent.after(500, dialog.close)
                    return
            except:
                parent.after(100, check_result)

        thread = threading.Thread(target=run_upgrade, daemon=True)
        thread.start()
        parent.after(100, check_result)

    def run_modal(self, parent: tk.Tk) -> bool:
        """
        【同步】运行模态升级窗口，阻塞直到完成，返回是否成功
        使用 wait_window 实现模态阻塞。
        """
        self.success = None  # 存储结果
        dialog = TkUpgradeDialog(parent)
        dialog.update(0, "正在检查升级...")
    
        result_queue = Queue()  # 用于从子线程传递结果
    
        def run_upgrade():
            """在子线程中执行升级"""
            try:
                self._execute_upgrade_sync(progress_callback=dialog.update)
                result_queue.put(True)
            except Exception as e:
                self._write_log(f"升级失败: {str(e)}")
                result_queue.put(False)
    
        def check_result():
            """在主线程中检查队列，安全更新 GUI"""
            try:
                # 非阻塞获取结果
                success = result_queue.get_nowait()
                self.success = success
    
                # 更新 UI
                if success:
                    dialog.update(100, "升级完成！")
                else:
                    dialog.update(100, "升级失败")
    
                # 延迟关闭对话框（确保 GUI 更新完成）
                parent.after(300, dialog.close)
    
            except Exception:
                # 队列为空，继续轮询
                parent.after(100, check_result)
    
        # 启动子线程执行升级
        thread = threading.Thread(target=run_upgrade, daemon=True)
        thread.start()
    
        # 启动主线程轮询机制（检查结果）
        parent.after(100, check_result)
    
        # 阻塞，直到对话框关闭
        parent.wait_window(dialog.dialog)
    
        return self.success
    def _execute_upgrade_sync(self, progress_callback=None):
        """同步执行升级逻辑（在子线程中调用）"""
        upgraded_count = 0
        latest_executed_version = "20000101000000"  # 默认初始版本
    
        try:
            with db_connection() as cursor:

                #获取上次升级版本 ===
                cursor.execute("SELECT var_value FROM system_vars WHERE var_name = ?", ("last_upgrade_version",))
                row = cursor.fetchone()
                last_version = row[0] if row else "20000101000000"
                self._write_log(f"读取最后成功升级版本: {last_version}")
    
                #查询待执行的升级项 ===
                cursor.execute('''
                    SELECT version, upgrade_type, target_name, sql_script, description 
                    FROM db_upgrades 
                    WHERE executed = 0 AND version > ?
                    ORDER BY version ASC
                ''', (last_version,))
                pending_upgrades = cursor.fetchall()
    
                if not pending_upgrades:
                    self._write_log("数据库已是最新版本，无需升级。")
                    if progress_callback:
                        progress_callback(100, "数据库已是最新版本")
                    return 0
    
                total = len(pending_upgrades)
                self._write_log(f"发现 {total} 个待升级任务，开始执行...")
    
                #逐个执行升级 ===
                for i, (version, up_type, target, sql_script, desc) in enumerate(pending_upgrades):
                    status_msg = desc or f"[{up_type}] {target}"
                    percent = int((i + 1) / total * 100)  # 使用 i+1 避免最后一步不更新到 100%
    
                    try:
                        # 更新状态（即使检查也可能耗时）
                        if progress_callback:
                            progress_callback(percent, f"检查: {status_msg}")
    
                        # 检查是否已存在（防重复）
                        if self._check_if_already_exists(cursor, up_type, target):
                            self._write_log(f"跳过已存在对象: {target} (版本 {version})")
                            self._mark_as_executed(cursor, version)
                            latest_executed_version = version
                            upgraded_count += 1
                            continue
    
                        # 执行 SQL 升级脚本
                        if progress_callback:
                            progress_callback(percent, f"执行: {status_msg}")
                        self._write_log(f"正在执行升级 [{version}]: {desc or sql_script[:60]}...")
    
                        cursor.execute(sql_script)
    
                        # 标记为已执行
                        self._mark_as_executed(cursor, version)
                        self._write_log(f"✅ 升级成功: 版本 {version} | {desc}")
    
                        latest_executed_version = version
                        upgraded_count += 1
    
                    except Exception as e:
                        error_msg = f"升级失败 [版本 {version}]: {desc} | 错误: {str(e)}"
                        self._write_log(error_msg)
                        self._write_log(f"SQL 脚本: {sql_script}")
                        self._write_log(traceback.format_exc())
    
                        # 可选：决定是否继续后续升级
                        # 当前策略：中断并抛出异常（保证数据一致性）
                        raise RuntimeError(error_msg) from e
    
                #全部成功后更新最后版本号 ===
                if upgraded_count > 0:
                    self._update_last_upgrade_version(latest_executed_version, cursor=cursor)
                    self._write_log(f"数据库升级完成！共执行 {upgraded_count} 项，最新版本: {latest_executed_version}")
                else:
                    self._write_log("无有效升级项被执行。")
    
                #完成 UI 回调 ===
                if progress_callback:
                    progress_callback(100, "升级完成！")
    
                return upgraded_count
    
        except Exception as e:
            self._write_log(f"数据库升级过程发生严重错误: {str(e)}")
            if progress_callback:
                # 给用户可见提示
                progress_callback(100, "升级失败，请查看日志")
            raise  # 向上传播异常，由调用方处理
    # ==================== 辅助方法 ====================

    def _check_if_already_exists(self, cursor, upgrade_type, target_name):
        """检查目标是否已存在，避免重复执行升级"""
        try:
            if upgrade_type == "table":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (target_name,))
                return cursor.fetchone() is not None
            elif upgrade_type == "column":
                if '.' not in target_name:
                    return False
                table, column = target_name.split('.', 1)
                cursor.execute(f"PRAGMA table_info({table})")
                cols = [row[1] for row in cursor.fetchall()]
                return column in cols
            return False
        except Exception as e:
            self._write_log(f"检查目标 {target_name} 存在性失败: {str(e)}")
            return False

    def _mark_as_executed(self, cursor, version):
        cursor.execute('''
            UPDATE db_upgrades 
            SET executed = 1, execution_time = ? 
            WHERE version = ?
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), version))
    def _update_last_upgrade_version(self, version, cursor=None):
        """
        更新最后升级版本号
        :param version: 版本号字符串，如 "20250925120000"
        :param cursor: 可选的数据库游标（用于复用事务）
        """
        query = '''
            INSERT OR REPLACE INTO system_vars (var_name, var_value, updated_at)
            VALUES ('last_upgrade_version', ?, ?)
        '''
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
        if cursor is not None:
            # 使用传入的 cursor（同一个事务）
            try:
                cursor.execute(query, (version, updated_at))
                self._write_log(f"已更新最后升级版本: {version}")
            except Exception as e:
                error_msg = f"更新最后升级版本失败: {str(e)}"
                self._write_log(error_msg)
                raise  # 向上传播异常，避免静默失败
        else:
            # 独立调用：自己管理连接
            try:
                with db_connection() as conn_cursor:
                    conn_cursor.execute(query, (version, updated_at))
                    self._write_log(f"已更新最后升级版本: {version}")
            except Exception as e:
                error_msg = f"更新最后升级版本失败: {str(e)}"
                self._write_log(error_msg)
                raise
    
# -----------------------------
# 使用示例（在 main.py 中）
# -----------------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.title("测试主窗口")
    root.geometry("600x400")

    upgrade_manager = DBUpgradeManager()

    # === 方式一：同步阻塞调用（推荐用于启动时升级）===
    print("开始同步升级...")
    success = upgrade_manager.run_modal(root)
    print("升级完成，结果:", success)
    if success:
        # 此处可安全加载新结构的数据
        print("现在可以安全刷新主界面了。")

    # === 方式二：异步回调（适合菜单触发）===
    # def on_complete(success):
    #     if success:
    #         print("异步升级成功")
    #     else:
    #         print("异步升级失败")
    #
    # upgrade_manager.check_and_upgrade(root, callback=on_complete)

    root.mainloop()
