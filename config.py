"""
项目常量配置
"""
import sys
from pathlib import Path

def get_project_dir():
    """获取程序运行的根目录（支持 PyInstaller 打包）"""
    if getattr(sys, 'frozen', False):
        # 程序是打包运行的（PyInstaller）
        # sys.executable 是 .exe 文件的路径
        return Path(sys.executable).parent
    else:
        # 正常 Python 解释器运行
        return Path(__file__).parent.absolute()

# 获取正确的项目根目录
PROJECT_DIR = get_project_dir()


# 配置文件路径
CONFIG_FILE = PROJECT_DIR / "config.ini"

# 数据库文件路径
DB_FILE = PROJECT_DIR / "fund_data.db"

# 备份目录
BACKUP_DIR = PROJECT_DIR / "backups"

# 确保目录存在
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE.parent.mkdir(parents=True, exist_ok=True)  # 确保 data/ 等父目录存在（如果需要）