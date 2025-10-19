import sqlite3

def allow_null_project_id():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # 先检查表结构
    cursor.execute("PRAGMA table_info(expenses)")
    columns = cursor.fetchall()
    print("当前expenses表结构:")
    for col in columns:
        print(f"列名: {col[1]}, 类型: {col[2]}, 是否允许NULL: {'是' if col[3] == 0 else '否'}")
    
    # 修改project_id字段允许NULL
    try:
        cursor.execute("ALTER TABLE expenses ALTER COLUMN project_id DROP NOT NULL")
        print("\n成功修改project_id字段允许NULL值")
    except sqlite3.OperationalError as e:
        # SQLite不支持直接修改列属性，需要重建表
        print(f"\nSQLite不支持直接修改列属性，需要重建表: {e}")
        
        # 创建临时表
        cursor.execute('''
            CREATE TABLE expenses_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                project_id INTEGER,
                purpose TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT,
                user_id INTEGER DEFAULT 1
            )
        ''')
        
        # 复制数据
        cursor.execute('''
            INSERT INTO expenses_new (id, date, project_id, purpose, amount, note, user_id)
            SELECT id, date, project_id, purpose, amount, note, user_id
            FROM expenses
        ''')
        
        # 删除旧表并重新命名
        cursor.execute("DROP TABLE expenses")
        cursor.execute("ALTER TABLE expenses_new RENAME TO expenses")
        
        # 重建索引（如果有的话）
        try:
            cursor.execute("CREATE INDEX idx_expenses_user_id ON expenses(user_id)")
        except:
            pass
        
        print("成功重建表并允许project_id为NULL")
    
    # 再次检查表结构确认修改
    cursor.execute("PRAGMA table_info(expenses)")
    columns = cursor.fetchall()
    print("\n修改后的expenses表结构:")
    for col in columns:
        print(f"列名: {col[1]}, 类型: {col[2]}, 是否允许NULL: {'是' if col[3] == 0 else '否'}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    allow_null_project_id()