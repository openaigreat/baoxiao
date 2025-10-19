from flask import Blueprint, render_template, request, redirect, url_for, session, abort, jsonify, g
import sqlite3
import logging
from models import get_db

bp = Blueprint('stats', __name__)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('database.db')
        g.db.row_factory = sqlite3.Row
    return g.db

@bp.teardown_request
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@bp.route('/stats')
def stats():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    stats = conn.execute('''
        SELECT p.id, p.name, p.amount AS project_amount, p.year,
               SUM(e.amount) AS total_expense, p.note
        FROM projects p
        LEFT JOIN expenses e ON p.id = e.project_id
        GROUP BY p.id
    ''').fetchall()
    conn.close()
    return render_template('stats.html', stats=stats)

@bp.route('/expenses/<int:project_id>')
def expenses(project_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    project = conn.execute('''
        SELECT id, name, year
        FROM projects
        WHERE id = ?
    ''', (project_id,)).fetchone()
    
    user_id = request.args.get('user')
    query = '''
        SELECT e.*, u.username 
        FROM expenses e
        JOIN users u ON e.user_id = u.id
        WHERE e.project_id = ?
    '''
    params = (project_id,)
    
    if user_id:
        query += ' AND e.user_id = ?'
        params += (user_id,)
    
    query += ' ORDER BY e.date ASC, u.username'
    
    expenses = conn.execute(query, params).fetchall()
    
    total_amount = sum(expense['amount'] for expense in expenses)  # 使用字典访问方式
    
    conn.close()
    
    return render_template('expenses.html', expenses=expenses, project=project, total_amount=total_amount)

@bp.route('/orphan_expenses')
def orphan_expenses():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    try:
        orphan_expenses = conn.execute('''
            SELECT e.id, e.date, e.purpose, e.amount, e.note, e.user_id, u.username, p.name AS project_name, p.year AS project_year
            FROM expenses e
            LEFT JOIN users u ON e.user_id = u.id
            LEFT JOIN projects p ON e.project_id = p.id
            WHERE e.project_id NOT IN (SELECT id FROM projects)
        ''').fetchall()
        total_amount = sum(expense['amount'] for expense in orphan_expenses)  # 使用字典访问方式
    except Exception as e:
        logging.error(f"Error fetching orphan expenses details: {e}")
        orphan_expenses = []
        total_amount = 0
    finally:
        conn.close()
    
    return render_template('orphan_expenses.html', expenses=orphan_expenses, total_amount=total_amount)

@bp.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    
    if request.method == 'POST':
        date = request.form['date']
        project_id = request.form['project_id']
        purpose = request.form['purpose']
        amount = request.form['amount']
        note = request.form['note']
        
        conn.execute('''
            UPDATE expenses
            SET date = ?, project_id = ?, purpose = ?, amount = ?, note = ?
            WHERE id = ?
        ''', (date, project_id, purpose, amount, note, expense_id))
        conn.commit()
        conn.close()
        return redirect(url_for('stats.expenses', project_id=project_id))
    
    expense = conn.execute('''
        SELECT e.*, p.name AS project_name, p.year
        FROM expenses e
        JOIN projects p ON e.project_id = p.id
        WHERE e.id = ?
    ''', (expense_id,)).fetchone()
    
    projects = conn.execute('''
        SELECT id, name, year
        FROM projects
    ''').fetchall()
    
    conn.close()
    
    return render_template('edit_expense.html', expense=expense, projects=projects)

@bp.route('/delete_expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    
    # 获取项目的ID以便重定向
    expense = conn.execute('''
        SELECT project_id
        FROM expenses
        WHERE id = ?
    ''', (expense_id,)).fetchone()
    
    if not expense:
        abort(404, description="Expense not found")
    
    project_id = expense['project_id']
    
    # 删除记录
    conn.execute('''
        DELETE FROM expenses
        WHERE id = ?
    ''', (expense_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('stats.expenses', project_id=project_id))

@bp.route('/get_orphan_expenses_total')
def get_orphan_expenses_total():
    conn = get_db()
    try:
        orphan_expenses = conn.execute('''
            SELECT u.username, SUM(e.amount) AS total_amount
            FROM expenses e
            JOIN users u ON e.user_id = u.id
            WHERE e.project_id NOT IN (SELECT id FROM projects)
            GROUP BY u.username
        ''').fetchall()
        logging.info(f"Orphan expenses by user: {orphan_expenses}")
    except Exception as e:
        logging.error(f"Error fetching orphan expenses total: {e}")
        orphan_expenses = []
    finally:
        conn.close()
    return jsonify([dict(row) for row in orphan_expenses])

