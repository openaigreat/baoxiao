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
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    # 获取项目统计
    project_stats = conn.execute('''
        SELECT p.id, p.name, p.amount AS project_amount,
               SUM(e.amount) AS total_expense, p.note
        FROM projects p
        LEFT JOIN expenses e ON p.id = e.project_id
        GROUP BY p.id
    ''').fetchall()
    
    # 获取无项目支出统计
    orphan_total = conn.execute('''
        SELECT SUM(amount) AS total_expense
        FROM expenses
        WHERE project_id IS NULL
    ''').fetchone()['total_expense'] or 0
    
    # 初始化统计结果列表
    stats = []
    
    # 如果有无项目支出，将其添加到统计结果的最前面
    if orphan_total > 0:
        # 使用字典模拟Row对象来显示无项目支出
        orphan_record = {'id': None, 'name': '无项目支出', 'project_amount': 0, 'total_expense': orphan_total, 'note': ''}
        stats.append(orphan_record)
    
    # 添加正常项目统计
    stats.extend(project_stats)
    
    conn.close()
    return render_template('stats.html', stats=stats)

@bp.route('/expenses/<int:project_id>')
def expenses(project_id):
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    project = conn.execute('''
        SELECT id, name
        FROM projects
        WHERE id = ?
    ''', (project_id,)).fetchone()
    
    query = '''
        SELECT e.* 
        FROM expenses e
        WHERE e.project_id = ?
        ORDER BY e.date ASC
    '''
    params = (project_id,)
    
    expenses = conn.execute(query, params).fetchall()
    
    # 获取所有项目列表，用于归属项目选择
    projects = conn.execute('''
        SELECT id, name
        FROM projects
        ORDER BY name
    ''').fetchall()
    
    total_amount = sum(expense['amount'] for expense in expenses)  # 使用字典访问方式
    
    conn.close()
    
    if not project:
        return redirect(url_for('index'))
    
    return render_template('expenses.html', expenses=expenses, project=project, total_amount=total_amount, projects=projects)

@bp.route('/orphan_expenses')
def orphan_expenses():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    try:
        orphan_expenses = conn.execute('''
            SELECT e.id, e.date, e.purpose, e.amount, e.note, e.user_id
            FROM expenses e
            WHERE e.project_id IS NULL OR e.project_id NOT IN (SELECT id FROM projects)
        ''').fetchall()
        total_amount = sum(expense['amount'] for expense in orphan_expenses)  # 使用字典访问方式
        
        # 获取项目列表，用于归属项目选择
        projects = conn.execute('''
            SELECT id, name
            FROM projects
            ORDER BY name
        ''').fetchall()
    except Exception as e:
        logging.error(f"Error fetching orphan expenses details: {e}")
        orphan_expenses = []
        total_amount = 0
        projects = []
    finally:
        conn.close()
    
    return render_template('orphan_expenses.html', expenses=orphan_expenses, total_amount=total_amount, projects=projects)

@bp.route('/batch_assign_project', methods=['POST'])
def batch_assign_project():
    # 添加调试日志
    print("收到batch_assign_project请求")
    print("Form数据:", dict(request.form))
    
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    try:
        # 获取选择的支出ID和目标项目ID
        expense_ids = request.form.get('expense_ids', '').split(',')
        project_id = request.form.get('project_id')
        
        # 验证输入
        if not expense_ids or expense_ids[0] == '' or not project_id:
            return jsonify({'success': False, 'error': '请选择支出记录和目标项目'})
        
        # 将项目ID转换为整数
        try:
            project_id = int(project_id)
        except ValueError:
            return jsonify({'success': False, 'error': '无效的项目ID'})
        
        # 更新数据库
        conn = get_db()
        updated_count = 0
        try:
            # 开始事务
            for expense_id in expense_ids:
                if expense_id.strip():
                    conn.execute('''
                        UPDATE expenses
                        SET project_id = ?
                        WHERE id = ?
                    ''', (project_id, int(expense_id.strip())))
                    updated_count += 1
            conn.commit()
        except Exception as e:
            conn.rollback()
            logging.error(f"Error batch assigning projects: {e}")
            return jsonify({'success': False, 'error': '数据库更新失败'})
        finally:
            conn.close()
        
        # 处理AJAX响应（只检查X-Requested-With头，因为request.is_xhr在新版Flask中已被移除）
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'count': updated_count, 'message': f'成功分配 {updated_count} 条支出到项目'})
        
        # 获取来源URL，判断重定向目标
        referrer = request.headers.get('Referer')
        if referrer:
            # 支持从支出明细页面跳转回来
            if 'expenses/' in referrer:
                # 尝试从URL中提取project_id
                import re
                match = re.search(r'expenses/(\d+)', referrer)
                if match:
                    return redirect(url_for('stats.expenses', project_id=match.group(1)))
            # 支持从孤立支出页面跳转回来
            elif 'orphan_expenses' in referrer:
                return redirect(url_for('stats.orphan_expenses'))
        
        # 默认跳转到统计页面
        return redirect(url_for('stats.stats'))
    except Exception as e:
        logging.error(f"Error in batch_assign_project: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': '操作失败'})
        # 如果是普通请求，直接返回错误页面
        return render_template('error.html', message='操作失败')

@bp.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
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
        return redirect(url_for('stats.stats'))
    
    expense = conn.execute('''
        SELECT e.*, p.name AS project_name
        FROM expenses e
        LEFT JOIN projects p ON e.project_id = p.id
        WHERE e.id = ?
    ''', (expense_id,)).fetchone()
    
    projects = conn.execute('''
        SELECT id, name
        FROM projects
    ''').fetchall()
    
    conn.close()
    
    return render_template('edit_expense.html', expense=expense, projects=projects)

@bp.route('/delete_expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
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
    
    return redirect(url_for('stats.stats'))

@bp.route('/get_orphan_expenses_total')
def get_orphan_expenses_total():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    conn = get_db()
    try:
        orphan_expenses = conn.execute('''
            SELECT SUM(e.amount) AS total_amount
            FROM expenses e
            WHERE e.project_id IS NULL OR e.project_id NOT IN (SELECT id FROM projects)
        ''').fetchone()
        if orphan_expenses and orphan_expenses['total_amount']:
            orphan_expenses = [orphan_expenses]
        else:
            orphan_expenses = []
        logging.info(f"Orphan expenses by user: {orphan_expenses}")
    except Exception as e:
        logging.error(f"Error fetching orphan expenses total: {e}")
        orphan_expenses = []
    finally:
        conn.close()
    return jsonify([dict(row) for row in orphan_expenses])

