# fund_notif_send.py

import yagmail
import datetime
import json
import threading
import os
from typing import Optional, Tuple, Dict
from utils.logger import write_log  # ✅ 导入日志工具


# 发件人配置（QQ 邮箱）
EMAIL_CONFIG1 = {
    'smtp_server': 'smtp.qq.com',
    'port': 465,
    'username': 'your_sender@qq.com',      # 替换为你的邮箱
    'password': 'your_auth_token',         # 替换为授权码
    'from': 'your_sender@qq.com'
}
EMAIL_CONFIG = {
    'smtp_server': 'smtp.163.com',
    'port': 465,
    'username': 'pushnessplus@163.com',      # 替换为你的邮箱
    'password': 'TZRhzfK8gQzykGdy',         # 替换为授权码
    'from': 'pushnessplus@163.com'
}

CONFIG_FILE = 'config.json'

def is_valid_email(email: str) -> bool:
    """
    简单但有效的邮箱格式校验（RFC 5322 兼容基本场景）
    """
    if not isinstance(email, str) or not email.strip():
        return False
    email = email.strip()
    # 基本正则（覆盖绝大多数合法邮箱）
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

class NotificationSender:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._last_alert_time: Dict[str, datetime.datetime] = {}
            cls._instance._yag = None
            # 日志配置
            cls._instance.log_dir = os.path.join("logs", "send")
            cls._instance.log_prefix = "send_log"
        return cls._instance

    def _write_log(self, message: str, level: str = 'info'):
        """封装 write_log，统一日志路径和前缀"""
        full_message = f"{level.upper():<8} {message}"
        write_log(
            message=full_message,
            log_dir=self.log_dir,
            prefix=self.log_prefix
        )

    def _load_notification_config(self) -> Tuple[bool, Optional[str]]:
        """
        从 config.json 加载通知配置
        返回: (enabled: bool, email: str or None)
        """
        if not os.path.exists(CONFIG_FILE):
            self._write_log(f"配置文件 {CONFIG_FILE} 不存在", 'warning')
            return False, None

        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)

            notif = config.get("notification", {})
            enabled = bool(notif.get("enabled", False))
            email = notif.get("email")

            if enabled and email and isinstance(email, str) and '@' in email:
                return True, email.strip()
            else:
                if not enabled:
                    self._write_log("邮件通知未启用（notification.enabled=false）", 'info')
                elif not email:
                    self._write_log("邮件通知已启用，但未设置有效邮箱", 'warning')
                return False, None

        except Exception as e:
            self._write_log(f"读取 config.json 失败: {e}", 'error')
            return False, None

    def _init_yagmail(self):
        if self._yag is None:
            try:
                self._yag = yagmail.SMTP(
                    user=EMAIL_CONFIG['username'],
                    password=EMAIL_CONFIG['password'],
                    host=EMAIL_CONFIG['smtp_server'],
                    port=EMAIL_CONFIG['port']
                )
            except Exception as e:
                self._write_log(f"初始化 yagmail 客户端失败: {e}", 'error')

    def should_send_alert(self, fund_code: str, cooldown_hours: int = 24) -> bool:
        now = datetime.datetime.now()
        last_time = self._last_alert_time.get(fund_code)
        if last_time is None:
            return True
        return (now - last_time).total_seconds() >= cooldown_hours * 3600

    def record_alert_time(self, fund_code: str):
        self._last_alert_time[fund_code] = datetime.datetime.now()

    def _send_email_in_background(self, to_email: str, subject: str, body: str):
        try:
            self._init_yagmail()
            if self._yag is None:
                self._write_log("yagmail 客户端未初始化，无法发送邮件", 'error')
                return

            self._yag.send(
                to=to_email,
                subject=subject,
                contents=body
            )
            #self._write_log(f"邮件已成功发送至 {to_email}", 'info')
            masked_email = to_email[:3] + "***" + to_email[to_email.find("@"):]
            self._write_log(f"邮件已成功发送至 {masked_email}", 'info')
        except Exception as e:
            self._write_log(f"邮件发送失败: {e}", 'error')

    def send_alert(
        self,
        fund_code: str,
        fund_name: str,
        change_rate: float,
        current_value: float,
        alert_type: str,
        cooldown_hours: int = 24
    ):
        """
        非阻塞发送邮件（仅当 config.json 中 enabled=true 且邮箱有效时）
        """
        # 1. 检查是否启用通知
        enabled, to_email = self._load_notification_config()
        if not enabled:
            return  # 静默跳过，已在 _load_notification_config 中记录

        if not to_email:
            self._write_log("通知已启用，但未设置有效收件人邮箱，跳过发送", 'warning')
            return

        #严格校验 to_email 格式
        if not to_email or not is_valid_email(to_email):
            self._write_log(f"收件人邮箱格式无效: '{to_email}'，跳过发送", 'warning')
            return
			
        # 2. 检查冷却时间
        if not self.should_send_alert(fund_code, cooldown_hours):
            self._write_log(
                f"基金 {fund_code} 在 {cooldown_hours} 小时内已提醒，跳过",
                'info'
            )
            return

        # 3. 构造邮件
        direction = "上涨" if alert_type == 'rise' else "下跌"
        subject = f"【基金提醒】{fund_name} {direction}超阈值！"
        body = f"""
基金代码：{fund_code}
基金名称：{fund_name}
当前估值：{current_value:.4f}
涨跌幅：{change_rate:.2f}%
提醒类型：{direction}
触发时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()

        # 4. 异步发送（不阻塞 refresh_all_funds 线程）
        thread = threading.Thread(
            target=self._send_email_in_background,
            args=(to_email, subject, body),
            daemon=True
        )
        thread.start()

        # 5. 立即记录时间（防止短时间内重复触发）
        self.record_alert_time(fund_code)

        self._write_log(
            f"触发{direction}提醒，基金 {fund_code} ({change_rate:.2f}%)，已启动后台发送",
            'info'
        )