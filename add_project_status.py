import sqlite3
import os

# 连接到数据库
def add_status_column():
    print("开始为projects表添加status字段...")
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(projects)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'status' not in columns:
            # 添加status字段，默认为'进行中'
            cursor.execute("ALTER TABLE projects ADD COLUMN status TEXT DEFAULT '进行中'")
            print("✓ 已成功添加status字段，默认值为'进行中'")
        else:
            print("✓ status字段已存在")
        
        # 更新数据库表结构总结信息
        print("\n数据库表结构更新完成！")
        print("- projects: 项目管理表（增加了status字段）")
        print("- status字段默认值: 进行中")
        print("- 可用状态: 进行中、已完成")
        
        conn.commit()
        print("\n✅ 数据库更新完成！")
    except Exception as e:
        print(f"❌ 更新数据库时出错: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_status_column()
