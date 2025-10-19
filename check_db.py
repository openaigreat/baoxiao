import sqlite3

# 连接到数据库
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# 查询projects表结构
print("Projects表结构:")
cursor.execute("PRAGMA table_info(projects);")
columns = cursor.fetchall()
for column in columns:
    print(column)

# 也查看一下是否有其他相关表
print("\n所有表:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for table in tables:
    print(table[0])

conn.close()