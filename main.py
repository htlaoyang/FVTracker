import sys
import sqlite3
import tkinter as tk
from tkinter import messagebox
from packaging import version
import traceback  # ✅ 必须导入
import tkinter.font as tkfont  # 显式导入 font

from module.FVTracker import FVTracker
from utils.db.db_upgrade_manager import DBUpgradeManager


if __name__ == "__main__":
    try:
        # ======== 在这里设置 DPI 感知（创建 Tk() 之前！）========
        #import ctypes
        #try:
        #    # 2: PROCESS_PER_MONITOR_DPI_AWARE_V2 (最佳支持高分屏)
        #    ctypes.windll.shcore.SetProcessDpiAwareness(2)
        #    print("已启用高 DPI 支持 (Per-Monitor DPI Aware V2)")
        #except Exception as e:
        #    print(f"SetProcessDpiAwareness(2) 失败，尝试级别 1: {e}")
        #    try:
        #        # 1: PROCESS_PER_MONITOR_DPI_AWARE
        #        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        #        print("已启用中等 DPI 支持 (Per-Monitor DPI Aware)")
        #    except Exception as e:
        #        print(f"无法设置 DPI 感知: {e}")
        ##  ======== DPI 设置结束 ========
        ## 创建 Tk 实例
        root = tk.Tk()
        root.withdraw()  # 先隐藏主窗口
        root.update_idletasks()

        # ======== 数据库升级：模态阻塞执行 ========
        print("开始数据库升级检查...")
        upgrade_manager = DBUpgradeManager()

        success = upgrade_manager.run_modal(root)  # 模态阻塞，显示进度条

        if not success:
            messagebox.showerror("数据库升级失败", "数据库升级过程中发生错误，请查看日志文件 logs/uplogs/ 下的日志。")
            root.destroy()
            raise SystemExit("数据库升级失败，程序退出。")

        print("数据库升级完成，继续启动应用...")

        # ======== 初始化主应用 ========
        app = FVTracker(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)

        # ======== SQLite 版本信息输出（可选） ========
        sqlite_engine_version = sqlite3.sqlite_version
        sqlite_module_version = sqlite3.version
        print(f"SQLite 引擎版本: {sqlite_engine_version}")
        print(f"Python sqlite3 模块版本: {sqlite_module_version}")

        if version.parse(sqlite_engine_version) >= version.parse("3.32.0"):
            print("支持 ALTER COLUMN SET DEFAULT 语法")
        else:
            print("不支持 ALTER COLUMN SET DEFAULT 语法，使用兼容方案")

        # ======== 显示主窗口 ========
        root.deiconify()  # 显示主窗口
        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(root.attributes, '-topmost', False)
        root.mainloop()

    except KeyboardInterrupt:
        print("程序被手动中断")
        if 'app' in locals():
            app.on_closing()

    except Exception as e:
        print(f"程序启动异常: {e}")
        messagebox.showerror("错误", f"程序启动失败：\n{str(e)}")
        raise
