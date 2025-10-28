import sqlite3
import os

# 获取数据库路径
db_path = os.path.join('instance', 'baoxiao.db')
print(f'Checking database: {os.path.abspath(db_path)}')

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查所有表
print('\nAll tables in database:')
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for table in tables:
    print(f'- {table[0]}')

# 检查reimbursement_expenses表结构
print('\nReimbursement_expenses table columns:')
cursor.execute('PRAGMA table_info(reimbursement_expenses)')
columns = cursor.fetchall()
for col in columns:
    print(f'- {col[1]} ({col[2]})')

# 关闭连接
conn.close()