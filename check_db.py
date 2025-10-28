import sqlite3

# 连接到数据库
conn = sqlite3.connect('instance/baoxiao.db')
cursor = conn.cursor()

# 查询projects表结构
print("Projects表结构:")
cursor.execute("PRAGMA table_info(projects);")
columns = cursor.fetchall()
for column in columns:
    print(column)

# 查看所有表
print("\n所有表:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for table in tables:
    print(table[0])

# 查询sqlite_sequence表内容
print("\nsqlite_sequence表内容:")
cursor.execute("SELECT * FROM sqlite_sequence;")
sequence_data = cursor.fetchall()
print(f"数据量: {len(sequence_data)} 条")
if sequence_data:
    print("表名\t| 下一个ID")
    print("-" * 30)
    for row in sequence_data:
        print(f"{row[0]}\t| {row[1]}")

conn.close()