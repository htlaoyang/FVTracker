"""
项目常量配置
"""

from pathlib import Path

# 使用 Path 获取项目根目录（__file__ 是当前 config.py 的路径）
PROJECT_DIR = Path(__file__).parent.absolute()

# 配置文件路径
CONFIG_FILE = PROJECT_DIR / "config.ini"

# 数据库文件路径
DB_FILE = PROJECT_DIR / "fund_data.db"

# 备份目录
BACKUP_DIR = PROJECT_DIR / "backups"

# 确保目录存在
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE.parent.mkdir(parents=True, exist_ok=True)  # 确保 data/ 等父目录存在（如果需要）