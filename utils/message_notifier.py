# utils/message_notifier.py
"""
美化版消息通知器：右下角弹出，支持圆角、阴影、淡入淡出动画
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import os


class MessageNotifier:
    """
    美化版消息通知器，支持：
    - 右下角弹出
    - 圆角窗口（伪实现）
    - 阴影效果
    - 淡入淡出动画
    - 图标支持
    """

    _root_instances = []

    def __init__(
        self,
        title="消息",
        message="",
        duration=3000,
        width=320,
        height=100,
        icon=None,  # 图标路径（可选）
        bg_color="#2d3748",  # 背景色
        fg_color="#e2e8f0",  # 文字色
        accent_color="#63b3ed"  # 强调色（标题）
    ):
        self.title = title
        self.message = message
        self.duration = duration
        self.width = width
        self.height = height
        self.icon = icon
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color

        self.root = None
        self.window = None
        self.alpha = 0  # 当前透明度

        self._create_ui()

    def _create_ui(self):
        self.root = tk.Tk()
        self.root.withdraw()

        # 创建主窗口（带外边距用于阴影）
        self.window = tk.Toplevel()
        self.window.overrideredirect(True)
        self.window.config(bg="black")  # 外层黑色用于阴影感

        # 内容框架（圆角矩形模拟）
        inner_frame = tk.Frame(
            self.window,
            bg=self.bg_color,
            highlightthickness=0,
            bd=0,
            padx=1,
            pady=1
        )
        inner_frame.pack(padx=2, pady=2)  # 黑边模拟阴影

        # 内容区域
        content_frame = tk.Frame(inner_frame, bg=self.bg_color, padx=14, pady=12)
        content_frame.pack()

        # 图标（可选）
        if self.icon and os.path.exists(self.icon):
            try:
                img = tk.PhotoImage(file=self.icon)
                # 缩放图标（仅限 .png）
                img = img.subsample(max(img.width() // 32, 1), max(img.height() // 32, 1))
                icon_label = tk.Label(content_frame, image=img, bg=self.bg_color)
                icon_label.image = img  # 防止被回收
                icon_label.pack(side="left", padx=(0, 12), anchor="n")
            except Exception as e:
                print(f"图标加载失败: {e}")

        # 文本区域
        text_frame = tk.Frame(content_frame, bg=self.bg_color)
        text_frame.pack(side="left", fill="both", expand=True)

        # 标题
        title_font = tkfont.Font(family="Microsoft YaHei", size=10, weight="bold")
        title_label = tk.Label(
            text_frame,
            text=self.title,
            font=title_font,
            bg=self.bg_color,
            fg=self.accent_color,
            anchor="w"
        )
        title_label.pack(fill="x")

        # 消息
        msg_font = tkfont.Font(family="Microsoft YaHei", size=9)
        message_label = tk.Label(
            text_frame,
            text=self.message,
            font=msg_font,
            bg=self.bg_color,
            fg=self.fg_color,
            anchor="w",
            justify="left",
            wraplength=self.width - 80  # 留出图标和边距
        )
        message_label.pack(fill="x", pady=(4, 0))

        # 定位到右下角
        self._position_window()

        # 绑定事件
        click_handler = lambda e: self.close()
        self.window.bind("<Button-1>", click_handler)
        content_frame.bind("<Button-1>", click_handler)
        text_frame.bind("<Button-1>", click_handler)
        title_label.bind("<Button-1>", click_handler)
        message_label.bind("<Button-1>", click_handler)

        # 添加到全局实例
        MessageNotifier._root_instances.append(self.root)

        # 先隐藏，准备淡入
        self.window.attributes("-alpha", 0)
        self.root.update()

        # 启动淡入动画
        self.fade_in()

        # 设置自动关闭（淡出后销毁）
        self.root.after(self.duration, self.fade_out)

    def _position_window(self):
        """定位到屏幕右下角"""
        self.window.update_idletasks()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        x = screen_width - self.width - 20
        y = screen_height - self.height - 30

        self.window.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def fade_in(self):
        """淡入动画"""
        self.alpha += 0.08
        if self.alpha > 1.0:
            self.alpha = 1.0
        self.window.attributes("-alpha", self.alpha)

        if self.alpha < 1.0:
            self.root.after(30, self.fade_in)  # 每30ms增加透明度

    def fade_out(self):
        """淡出动画"""
        self.alpha -= 0.08
        if self.alpha <= 0:
            self.close()
            return
        self.window.attributes("-alpha", self.alpha)
        self.root.after(30, self.fade_out)

    def close(self):
        """安全关闭"""
        try:
            if self.root and self.root.winfo_exists():
                self.root.destroy()
            if self.root in MessageNotifier._root_instances:
                MessageNotifier._root_instances.remove(self.root)
        except Exception:
            pass


# ✅ 全局通知函数（供导入）
def notify(title="消息", message="", duration=3000, icon=None, level="info"):
    """
    快捷通知函数
    :param level: "info", "warn", "error", "success"
    """
    colors = {
        "info": {"bg": "#2d3748", "accent": "#63b3ed"},
        "warn": {"bg": "#7c2d12", "accent": "#fbbf24"},
        "error": {"bg": "#7f1d1d", "accent": "#f87171"},
        "success": {"bg": "#166534", "accent": "#4ade80"},
    }
    style = colors.get(level, colors["info"])

    def _show():
        try:
            MessageNotifier(
                title=title,
                message=message,
                duration=duration,
                icon=icon,
                bg_color=style["bg"],
                accent_color=style["accent"]
            )
        except Exception as e:
            print(f"通知失败: {e}")

    thread = threading.Thread(target=_show, daemon=True)
    thread.start()