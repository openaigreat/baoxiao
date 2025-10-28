import sqlite3
import hashlib
import os

def create_users_table():
    db_path = os.path.join('instance', 'baoxiao.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            # 创建新的用户表
            cursor.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("创建了新的用户表")
            # 获取新创建表的列信息
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            print(f"新用户表的列：{columns}")
        else:
            # 检查表结构
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            print(f"现有用户表的列：{columns}")
        
        # 检查是否已有默认管理员用户
        cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
        if not cursor.fetchone():
            # 根据表结构插入管理员用户
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            if 'password_hash' in columns:
                cursor.execute(
                    'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                    ('admin', password_hash)
                )
            elif 'password' in columns:
                cursor.execute(
                    'INSERT INTO users (username, password) VALUES (?, ?)',
                    ('admin', password_hash)
                )
            else:
                # 如果都没有，使用通用插入
                cursor.execute(
                    'INSERT INTO users (username) VALUES (?)',
                    ('admin',)
                )
            print("默认管理员用户已创建：用户名admin，密码admin123")
        
        conn.commit()
        print("用户表初始化成功")
    except Exception as e:
        print(f"初始化过程中出错：{e}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_users_table()