import sqlite3
import os
from datetime import datetime, timezone, timedelta

# 创建东八区时区对象
CST = timezone(timedelta(hours=8))

def get_current_cst_time():
    """获取当前东八区（CST）时间"""
    return datetime.now(CST)

def get_db():
    db_path = os.path.join('instance', 'baoxiao.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # 注册一个函数，用于获取当前东八区时间
    def current_cst_time():
        return get_current_cst_time().strftime('%Y-%m-%d %H:%M:%S')
    
    # 注册一个函数，用于在查询时将存储的时间转换为本地时间（现在直接返回，因为已存储为东八区时间）
    def convert_to_local_time(timestamp_str):
        if not timestamp_str:
            return None
        return timestamp_str
    
    # 注册函数到SQLite连接
    conn.create_function('CURRENT_CST_TIME', 0, current_cst_time)
    conn.create_function('LOCAL_TIME', 1, convert_to_local_time)
    
    return conn