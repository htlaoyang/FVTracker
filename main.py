import sys
import os
import threading 
import sqlite3
import tkinter as tk
from tkinter import messagebox
from packaging import version
import traceback  # ✅ 必须导入
import tkinter.font as tkfont  # 显式导入 font

# ===== 托盘支持 =====
try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


from module.FVTracker import FVTracker
from utils.db.db_upgrade_manager import DBUpgradeManager

def get_resource_path(relative_path):
    """获取 PyInstaller 打包后的资源路径"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def load_tray_icon():
    """尝试加载 FVTracker.ico，失败则返回 None"""
    icon_path = get_resource_path("FVTracker.ico")  # 使用资源路径
    if os.path.exists(icon_path):
        try:
            # .ico 文件可被 PIL 直接读取
            return Image.open(icon_path)
        except Exception as e:
            print(f"⚠️ 无法加载图标 {icon_path}: {e}")
    return None


def create_default_icon():
    """备用：生成简单图标"""
    from PIL import Image, ImageDraw
    width, height = 64, 64
    image = Image.new('RGB', (width, height), (255, 255, 255))
    dc = ImageDraw.Draw(image)
    dc.ellipse((width // 4, height // 4, 3 * width // 4, 3 * height // 4), fill=(0, 100, 200))
    return image


class TrayManager:
    def __init__(self, root):
        self.root = root
        self.icon = None
        self.window_visible = True
        if HAS_TRAY:
            self._create_tray()

    def _create_tray(self):
        image = load_tray_icon() or create_default_icon()
        self.icon = Icon("FVTracker", image, "FVTracker - 基金监控", menu=self._build_menu())
        threading.Thread(target=self.icon.run, daemon=True).start()

    def _build_menu(self):
        if self.window_visible:
            toggle = MenuItem('隐藏主窗口', self.hide_window, default=True)
        else:
            toggle = MenuItem('显示主窗口', self.show_window, default=True)
        return Menu(toggle, Menu.SEPARATOR, MenuItem('退出', self.quit_app))

    def show_window(self, icon=None, item=None):
        self.root.after(0, self._do_show)

    def _do_show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after_idle(self.root.attributes, '-topmost', False)
        self.window_visible = True
        if self.icon:
            self.icon.menu = self._build_menu()

    def hide_window(self, icon=None, item=None):
        self.root.after(0, self._do_hide)

    def _do_hide(self):
        self.root.withdraw()
        self.window_visible = False
        if self.icon:
            self.icon.menu = self._build_menu()

    def quit_app(self, icon=None, item=None):
        self.root.after(0, self._do_quit)

    def _do_quit(self):
        if self.icon:
            self.icon.stop()
        self.root.quit()
        self.root.destroy()

    def on_closing(self):
        if HAS_TRAY and self.icon:
            self.hide_window()
        else:
            self.root.quit()
            self.root.destroy()

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
        # ===== 注入托盘管理器 =====
        tray_mgr = TrayManager(root)
        root.protocol("WM_DELETE_WINDOW", tray_mgr.on_closing)

        # 处理最小化事件（Windows/Linux）
        def on_minimize(event):
            if str(event.type) == 'Iconify' and event.widget is root:
                tray_mgr.hide_window()
        root.bind("<Unmap>", on_minimize)
		

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
