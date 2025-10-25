import sqlite3

def add_reimbursement_payments_table():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # 创建reimbursement_payments表用于存储回款记录
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reimbursement_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reimbursement_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (reimbursement_id) REFERENCES reimbursements (id) ON DELETE CASCADE
        )
    ''')
    
    # 创建索引以提高查询性能
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reimbursement_payments_reimbursement ON reimbursement_payments(reimbursement_id)")
    except Exception as e:
        print(f"创建索引时出错: {e}")
    
    # 更新reimbursements表，添加累计回款金额字段
    try:
        cursor.execute("ALTER TABLE reimbursements ADD COLUMN total_paid REAL DEFAULT 0")
    except sqlite3.OperationalError:
        print("total_paid字段已存在")
    
    # 添加一个新的状态选项（已回款）
    # 注意：SQLite没有直接修改CHECK约束的方法，这里我们不修改约束，而是在应用层面处理
    
    conn.commit()
    conn.close()
    print("回款相关表和字段创建成功")

if __name__ == "__main__":
    add_reimbursement_payments_table()
