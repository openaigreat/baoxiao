import sqlite3
import os

def create_todo_table():
    db_path = os.path.join('instance', 'baoxiao.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='todos'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            # 创建todo表
            cursor.execute('''
                CREATE TABLE todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    completed INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    completed_at TIMESTAMP NULL,
                    sort_order INTEGER DEFAULT 0,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            ''')
            print("创建了todo表")
        else:
            # 检查是否已有sort_order字段，如果没有则添加
            cursor.execute("PRAGMA table_info(todos)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'sort_order' not in columns:
                cursor.execute("ALTER TABLE todos ADD COLUMN sort_order INTEGER DEFAULT 0")
                print("为todo表添加了sort_order字段")
            
            # 检查是否已有completed_at字段，如果没有则添加
            if 'completed_at' not in columns:
                cursor.execute("ALTER TABLE todos ADD COLUMN completed_at TIMESTAMP NULL")
                print("为todo表添加了completed_at字段")
            
            if 'sort_order' in columns and 'completed_at' in columns:
                print("todo表已存在且包含所需字段")
        
        conn.commit()
        print("todo表初始化成功")
    except Exception as e:
        print(f"初始化过程中出错：{e}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_todo_table()