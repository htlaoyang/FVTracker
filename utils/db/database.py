"""
数据库操作模块：负责数据库连接、初始化、重置等
"""
import sqlite3
import shutil
import os
from contextlib import contextmanager
from datetime import datetime
from config import DB_FILE, BACKUP_DIR
from utils.logger import write_log 


def db_log(message: str):
    """数据库专用日志记录，输出到 logs/dblogs/ 目录"""
    write_log(message, log_dir="logs/dblogs", prefix="")

@contextmanager
def db_connection():
    # 确保父目录存在
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 创建连接
    conn = sqlite3.connect(DB_FILE)
    
    # 关键：启用 WAL 模式
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn.cursor()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()  # 确保关闭

def init_database():
    """初始化数据库表结构"""
    with db_connection() as cursor:
        # 基金基本信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS funds (
            code TEXT PRIMARY KEY, --  '基金代码，唯一标识'
            name TEXT, --  '基金名称'
            latest_net_value REAL, --  '最新单位净值'
            is_hold INTEGER, --  '是否持有，1=持有，0=未持有'
            cost REAL, --  '持有成本价'
            shares REAL --  '持有份额'
        )
        ''')

        # 基金估值历史主表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_estimate_main (
            id INTEGER, --  '记录序号',
            fund_code TEXT, --  '基金代码',
            fund_name TEXT, --  '基金名称',
            trade_date DATE, --  '交易日期',
            trade_time DATETIME, --  '交易时间',
            unit_net_value REAL, --  '单位净值(昨日)',
            realtime_estimate REAL, --  '实时估值(今日)',
            change_rate REAL, --  '涨跌幅(%)',
            is_hold INTEGER, --  '是否持有，1=持有，0=未持有',
            hold_cost REAL, --  '持有成本价',
            hold_shares REAL, --  '持有份额',
            realtime_profit REAL, --  '实时盈亏金额',
            FOREIGN KEY (fund_code) REFERENCES funds(code),
            PRIMARY KEY (fund_code, trade_date, id)
        )
        ''')

        # 基金估值历史明细表（含收盘标记）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_estimate_details (
            id INTEGER, --  '记录序号',
            fund_code TEXT, --  '基金代码',
            trade_date DATE, --  '交易日期',
            trade_time DATETIME, --  '交易时间',
            estimate_time TIME, --  '估值时间点',
            realtime_estimate REAL, --  '实时估值',
            change_rate REAL, --  '涨跌幅(%)',
            is_close_data INTEGER DEFAULT 0, --  '是否为收盘数据，1=是，0=否'
            FOREIGN KEY (fund_code) REFERENCES funds(code),
            PRIMARY KEY (fund_code, trade_date, estimate_time, id)
        )
        ''')

        # 刷新配置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, --  '配置项键名'
            value TEXT --  '配置项值' 这里移除了多余的逗号
        )
        ''')

        # 初始化默认刷新间隔
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                       ("refresh_interval", "5"))
					   
def secure_reset_database():
    """安全重置数据库：备份旧数据，创建新空库"""
    try:
        # 确保备份目录存在
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        if DB_FILE.exists():
            backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUP_DIR / f"fund_data_backup_{backup_time}.db"
            
            # 执行备份
            shutil.copy2(DB_FILE, backup_file)
            # 同时打印到控制台和日志文件
            log_msg = f"数据库已备份至: {backup_file}"
            print(log_msg)
            db_log(log_msg)  # 使用专用日志函数

            # 删除原数据库
            DB_FILE.unlink()
            log_msg = f"原数据库已删除: {DB_FILE}"
            print(log_msg)
            db_log(log_msg)  # 使用专用日志函数

        # 重新初始化空数据库
        init_database()  # 此函数内部也会调用 db_log
        log_msg = "新的空数据库已创建"
        print(log_msg)
        db_log(log_msg)  # 使用专用日志函数
        return True

    except Exception as e:
        error_msg = f"数据库重置失败: {e}"
        print(error_msg)
        db_log(error_msg)  # 使用专用日志函数
        return False		

