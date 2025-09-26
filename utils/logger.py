# utils/logger.py
import os
from datetime import datetime
from typing import Optional

# 全局默认配置
_DEFAULT_LOG_DIR = "logs"
_DEFAULT_PREFIX = "app"

def write_log(
    message: str,
    log_dir: Optional[str] = None,
    prefix: Optional[str] = None
):
    """
    写入日志到按日期命名的日志文件

    :param message: 日志内容
    :param log_dir: 日志目录（可选），默认为 'logs'
    :param prefix: 日志文件前缀（可选），默认为 'app'
    """
    # 使用传入参数或默认值
    use_log_dir = log_dir or _DEFAULT_LOG_DIR
    use_prefix = prefix or _DEFAULT_PREFIX

    # 确保日志目录存在
    if not os.path.exists(use_log_dir):
        os.makedirs(use_log_dir)

    # 生成日志文件路径：{prefix}_YYYYMMDD.log
    log_file = os.path.join(use_log_dir, f"{use_prefix}_{datetime.now().strftime('%Y%m%d')}.log")

    # 写入日志
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        # 防止日志失败导致程序崩溃（尽量记录，但不抛出）
        print(f"[Logger Error] 无法写入日志: {str(e)}")