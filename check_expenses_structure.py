import sqlite3

# 连接数据库
conn = sqlite3.connect('instance/baoxiao.db')
cursor = conn.cursor()

# 检查expenses表结构
print('Expenses table structure:')
cursor.execute('PRAGMA table_info(expenses)')
columns = cursor.fetchall()
for col in columns:
    print(f'- {col[1]} ({col[2]})')

# 关闭连接
conn.close()