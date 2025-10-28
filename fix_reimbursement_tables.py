import sqlite3
import os

# 获取数据库文件路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'baoxiao.db')

# 确保instance目录存在
instance_dir = os.path.dirname(DB_PATH)
os.makedirs(instance_dir, exist_ok=True)

print(f"使用数据库路径: {DB_PATH}")

try:
    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查reimbursement_expenses表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reimbursement_expenses'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        print("reimbursement_expenses表已存在，检查其结构...")
        # 检查表结构
        cursor.execute("PRAGMA table_info(reimbursement_expenses)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        print(f"当前列: {column_names}")
        
        # 如果缺少reimbursement_amount列，添加它
        if 'reimbursement_amount' not in column_names:
            print("添加reimbursement_amount列...")
            cursor.execute("ALTER TABLE reimbursement_expenses ADD COLUMN reimbursement_amount REAL DEFAULT 0.0")
            print("列添加成功！")
        else:
            print("reimbursement_amount列已存在。")
    else:
        print("reimbursement_expenses表不存在，创建表...")
        # 创建reimbursement_expenses表
        cursor.execute('''
            CREATE TABLE reimbursement_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reimbursement_id INTEGER,
                expense_id INTEGER,
                reimbursement_amount REAL DEFAULT 0.0,
                added_date TEXT,
                FOREIGN KEY (reimbursement_id) REFERENCES reimbursements (id),
                FOREIGN KEY (expense_id) REFERENCES expenses (id)
            )
        ''')
        print("表创建成功！")
    
    # 提交更改并关闭连接
    conn.commit()
    print("数据库操作成功完成！")
    
except sqlite3.Error as e:
    print(f"数据库错误: {e}")
    if 'conn' in locals():
        conn.rollback()
finally:
    if 'conn' in locals():
        conn.close()
