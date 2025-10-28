import sqlite3
import os
import datetime

# Get database path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'baoxiao.db')

# Ensure instance directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

print(f"Using database path: {DB_PATH}")

try:
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    conn.execute('PRAGMA foreign_keys = ON')  # Enable foreign keys
    
    # Check all tables in the database
    print("\n--- Database Tables Check ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    print(f"Tables in database: {[table[0] for table in tables]}")
    
    # Ensure expenses table exists (as it's referenced by reimbursement_expenses)
    print("\n--- Checking expenses table ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
    if not cursor.fetchone():
        print("Creating expenses table...")
        cursor.execute('''
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                category TEXT,
                amount REAL,
                description TEXT,
                payment_method TEXT,
                project_id INTEGER,
                created_at TEXT,
                created_by INTEGER,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
        ''')
        print("Expenses table created.")
    else:
        print("Expenses table already exists.")
    
    # Ensure projects table exists
    print("\n--- Checking projects table ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
    if not cursor.fetchone():
        print("Creating projects table...")
        cursor.execute('''
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                note TEXT,
                created_at TEXT,
                status TEXT DEFAULT '进行中'
            )
        ''')
        print("Projects table created.")
    else:
        print("Projects table already exists.")
    
    # Ensure reimbursements table exists
    print("\n--- Checking reimbursements table ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reimbursements'")
    if not cursor.fetchone():
        print("Creating reimbursements table...")
        cursor.execute('''
            CREATE TABLE reimbursements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submit_date TEXT,
                total_amount REAL DEFAULT 0.0,
                status TEXT DEFAULT '草稿',
                note TEXT,
                created_by INTEGER,
                created_at TEXT,
                updated_at TEXT,
                total_paid REAL DEFAULT 0.0,
                submission_date TEXT,
                user_id INTEGER
            )
        ''')
        print("Reimbursements table created.")
    else:
        print("Reimbursements table already exists.")
    
    # Ensure reimbursement_expenses table exists with correct structure
    print("\n--- Checking reimbursement_expenses table ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reimbursement_expenses'")
    if not cursor.fetchone():
        print("Creating reimbursement_expenses table with correct structure...")
        cursor.execute('''
            CREATE TABLE reimbursement_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reimbursement_id INTEGER,
                expense_id INTEGER,
                reimbursement_amount REAL DEFAULT 0.0,
                added_date TEXT,
                FOREIGN KEY (reimbursement_id) REFERENCES reimbursements(id) ON DELETE CASCADE,
                FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE
            )
        ''')
        print("Reimbursement_expenses table created with reimbursement_amount column.")
    else:
        # Check if reimbursement_amount column exists
        cursor.execute("PRAGMA table_info(reimbursement_expenses)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        print(f"Current columns in reimbursement_expenses: {column_names}")
        
        if 'reimbursement_amount' not in column_names:
            print("Adding reimbursement_amount column to reimbursement_expenses table...")
            try:
                cursor.execute("ALTER TABLE reimbursement_expenses ADD COLUMN reimbursement_amount REAL DEFAULT 0.0")
                print("Column added successfully!")
            except sqlite3.Error as e:
                print(f"Error adding column: {e}")
                print("Attempting to recreate the table with correct structure...")
                # Backup the current table if it has data
                cursor.execute("SELECT COUNT(*) FROM reimbursement_expenses")
                count = cursor.fetchone()[0]
                if count > 0:
                    print(f"Found {count} records in current table, creating backup...")
                    backup_table = f"reimbursement_expenses_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    cursor.execute(f"ALTER TABLE reimbursement_expenses RENAME TO {backup_table}")
                    print(f"Data backed up to {backup_table}")
                # Create new table with correct structure
                cursor.execute('''
                    CREATE TABLE reimbursement_expenses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reimbursement_id INTEGER,
                        expense_id INTEGER,
                        reimbursement_amount REAL DEFAULT 0.0,
                        added_date TEXT,
                        FOREIGN KEY (reimbursement_id) REFERENCES reimbursements(id) ON DELETE CASCADE,
                        FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE
                    )
                ''')
                print("Recreated reimbursement_expenses table with correct structure.")
        else:
            print("reimbursement_amount column already exists.")
    
    # Ensure reimbursement_payments table exists
    print("\n--- Checking reimbursement_payments table ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reimbursement_payments'")
    if not cursor.fetchone():
        print("Creating reimbursement_payments table...")
        cursor.execute('''
            CREATE TABLE reimbursement_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reimbursement_id INTEGER,
                payment_date TEXT,
                amount REAL,
                note TEXT,
                created_at TEXT,
                FOREIGN KEY (reimbursement_id) REFERENCES reimbursements(id) ON DELETE CASCADE
            )
        ''')
        print("Reimbursement_payments table created.")
    else:
        print("Reimbursement_payments table already exists.")
    
    # Verify the final structure
    print("\n--- Final Table Structure Verification ---")
    cursor.execute("PRAGMA table_info(reimbursement_expenses)")
    print("Reimbursement_expenses table structure:")
    for column in cursor.fetchall():
        print(f"  {column[1]} ({column[2]})")
    
    # Commit all changes
    conn.commit()
    print("\nDatabase structure has been successfully fixed and verified!")
    
except sqlite3.Error as e:
    print(f"Database error: {e}")
    if 'conn' in locals():
        conn.rollback()
finally:
    if 'conn' in locals():
        conn.close()
