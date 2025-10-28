import sqlite3
import os

# 连接到数据库
db_path = os.path.join('instance', 'baoxiao.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"数据库: {db_path}")
print("\nProjects表结构:")
cursor.execute('PRAGMA table_info(projects)')
columns = cursor.fetchall()
for column in columns:
    print(f"ID: {column[0]}, 名称: {column[1]}, 类型: {column[2]}, 是否可以为NULL: {column[3]}, 默认值: {column[4]}, 主键: {column[5]}")

conn.close()