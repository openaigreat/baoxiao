import sqlite3
import os

# 连接到数据库
db_path = 'database.db'

if os.path.exists(db_path):
    print(f"连接到数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 先查看表结构
        print("查看表结构...")
        cursor.execute("PRAGMA table_info(projects)")
        columns = cursor.fetchall()
        print("当前表结构:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        
        # 创建一个新的表结构，不包含year字段
        print("创建临时表...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT
            )
        ''')
        
        # 复制数据到新表，只复制存在的字段
        print("复制数据到新表...")
        cursor.execute('''
            INSERT INTO projects_new (id, name, amount, note)
            SELECT id, name, amount, note FROM projects
        ''')
        
        # 删除旧表
        print("删除旧表...")
        cursor.execute('DROP TABLE IF EXISTS projects')
        
        # 重命名新表
        print("重命名新表...")
        cursor.execute('ALTER TABLE projects_new RENAME TO projects')
        
        # 创建必要的索引
        print("重建索引...")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_id ON projects (id)')
        
        # 提交更改
        conn.commit()
        print("数据库修改成功！已移除projects表中的year字段。")
        
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        conn.rollback()
    finally:
        conn.close()
else:
    print(f"数据库文件不存在: {db_path}")