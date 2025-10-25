import sqlite3

def create_reimbursement_tables():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # 创建expenses表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            project_id INTEGER,
            purpose TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            user_id INTEGER,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建projects表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            user_id INTEGER
        )
    ''')
    
    # 创建reimbursements表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reimbursements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submit_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT '草稿',
            note TEXT,
            created_by INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    # 创建reimbursement_expenses表（关联报销单和支出记录）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reimbursement_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reimbursement_id INTEGER NOT NULL,
            expense_id INTEGER NOT NULL,
            reimbursement_amount REAL NOT NULL,
            added_date TEXT NOT NULL,
            FOREIGN KEY (reimbursement_id) REFERENCES reimbursements (id) ON DELETE CASCADE,
            FOREIGN KEY (expense_id) REFERENCES expenses (id) ON DELETE CASCADE,
            UNIQUE(reimbursement_id, expense_id)
        )
    ''')
    
    # 创建索引以提高查询性能
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reimbursements_status ON reimbursements(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reimbursement_expenses_reimbursement ON reimbursement_expenses(reimbursement_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reimbursement_expenses_expense ON reimbursement_expenses(expense_id)")
    except Exception as e:
        print(f"创建索引时出错: {e}")
    
    conn.commit()
    conn.close()
    print("报销相关表创建成功")

if __name__ == "__main__":
    create_reimbursement_tables()