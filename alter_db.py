import sqlite3
import os

# 连接到数据库
db_path = 'database.db'

if os.path.exists(db_path):
    print(f"连接到数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查expenses表是否缺少category列
        print("检查expenses表结构...")
        cursor.execute("PRAGMA table_info(expenses)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        print("当前expenses表列名:")
        for col in column_names:
            print(f"  - {col}")
        
        # 如果缺少category列，则添加它
        if 'category' not in column_names:
            print("添加category列到expenses表...")
            cursor.execute('ALTER TABLE expenses ADD COLUMN category TEXT')
            print("category列添加成功！")
        else:
            print("category列已存在，无需添加。")
        
        # 提交更改
        conn.commit()
        print("数据库修改完成！")
        
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        conn.rollback()
    finally:
        conn.close()
else:
    print(f"数据库文件不存在: {db_path}")