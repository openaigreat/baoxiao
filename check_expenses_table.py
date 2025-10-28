import sqlite3
import os

# 获取数据库路径
db_path = os.path.join('instance', 'baoxiao.db')
print(f'Checking database: {os.path.abspath(db_path)}')

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查expenses表结构
print('\nExpenses table columns:')
cursor.execute('PRAGMA table_info(expenses)')
columns = cursor.fetchall()
for col in columns:
    print(f'- {col[1]} ({col[2]})')

# 检查是否存在created_by列（可能是用户ID相关的列）
has_created_by = any(col[1] == 'created_by' for col in columns)
print(f'\nHas created_by column: {has_created_by}')

# 关闭连接
conn.close()