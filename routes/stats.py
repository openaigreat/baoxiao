from flask import Blueprint, render_template, request, redirect, url_for, session, abort, jsonify, g, flash
import sqlite3
import logging
from models import get_db
from datetime import datetime

bp = Blueprint('stats', __name__)

@bp.route('/stats')
def stats():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    # 获取项目统计，包括已提交金额
    project_stats = conn.execute('''
        SELECT p.id, p.name,
               SUM(e.amount) AS total_expense,
               SUM(CASE WHEN re.expense_id IS NOT NULL THEN e.amount ELSE 0 END) AS submitted_amount,
               p.note, p.status
        FROM projects p
        LEFT JOIN expenses e ON p.id = e.project_id
        LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
        GROUP BY p.id
    ''').fetchall()
    
    # 获取无项目支出统计，包括已提交金额
    orphan_stats = conn.execute('''
        SELECT SUM(e.amount) AS total_expense,
               SUM(CASE WHEN re.expense_id IS NOT NULL THEN e.amount ELSE 0 END) AS submitted_amount
        FROM expenses e
        LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
        WHERE e.project_id IS NULL
    ''').fetchone()
    
    orphan_total = orphan_stats['total_expense'] or 0
    orphan_submitted = orphan_stats['submitted_amount'] or 0
    
    # 初始化统计结果列表
    stats = []
    
    # 如果有无项目支出，将其添加到统计结果的最前面
    if orphan_total > 0:
        # 使用字典模拟Row对象来显示无项目支出
        orphan_record = {'id': None, 'name': '无项目支出', 'project_amount': 0, 
                        'total_expense': orphan_total, 'submitted_amount': orphan_submitted, 'note': ''}
        stats.append(orphan_record)
    
    # 添加正常项目统计，并处理None值
    for project in project_stats:
        # 转换Row对象为字典，并处理None值
        project_dict = dict(project)
        # 设置默认的项目预算金额为0
        project_dict['project_amount'] = 0
        project_dict['total_expense'] = project_dict.get('total_expense', 0) or 0
        project_dict['submitted_amount'] = project_dict.get('submitted_amount', 0) or 0
        stats.append(project_dict)
    
    conn.close()
    return render_template('stats.html', stats=stats)

@bp.route('/expenses/<int:project_id>')
def expenses(project_id):
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取排序参数
    sort_by = request.args.get('sort_by', 'category')  # 默认按类别排序
    sort_order = request.args.get('sort_order', 'asc')  # 默认正序
    
    # 验证排序字段
    valid_sort_fields = ['category', 'date', 'description', 'amount', 'payment_method']
    # 保存原始排序字段用于模板显示
    original_sort_by = sort_by
    # 允许使用'purpose'作为排序字段（内部会映射到'description'）
    if sort_by == 'purpose':
        sort_by = 'description'
    # 允许使用'note'作为排序字段（内部会映射到'payment_method'）
    elif sort_by == 'note':
        sort_by = 'payment_method'
    elif sort_by not in valid_sort_fields:
        sort_by = 'category'
        original_sort_by = 'category'
    
    # 验证排序顺序
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
    conn = get_db()
    project = conn.execute('''
        SELECT id, name
        FROM projects
        WHERE id = ?
    ''', (project_id,)).fetchone()
    
    # 构建带排序的SQL查询，只返回未报销的支出记录
    # 根据expenses.py中的实现，description字段存储purpose内容，payment_method字段存储note内容
    query = f'''
        SELECT e.id, e.date, e.category, e.amount, e.description as purpose, e.project_id, 
               e.created_at, e.created_by, CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status,
               e.payment_method as note
        FROM expenses e
        LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
        WHERE e.project_id = ? AND re.reimbursement_id IS NULL
        ORDER BY e.{sort_by} {sort_order}, e.date asc
    '''
    params = (project_id,)
    
    expenses = conn.execute(query, params).fetchall()
    
    # 获取所有进行中的项目列表，用于归属项目选择
    projects = conn.execute('''
        SELECT id, name
        FROM projects
        WHERE status = ?
        ORDER BY name
    ''', ('进行中',)).fetchall()
    
    total_amount = sum(expense['amount'] for expense in expenses)  # 使用字典访问方式
    
    if not project:
        conn.close()
        return redirect(url_for('index'))
    
    # 计算下一次点击的排序顺序
    next_sort_order = 'desc' if sort_order == 'asc' else 'asc'
    
    conn.close()
    return render_template('expenses.html', 
                           expenses=expenses, 
                           project=project, 
                           total_amount=total_amount, 
                           projects=projects,
                           current_sort=original_sort_by,
                           current_order=sort_order,
                           next_sort_order=next_sort_order)

@bp.route('/category_stats')
def category_stats():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取排序参数
    sort_by = request.args.get('sort_by', 'total_amount')  # 默认按总金额排序
    sort_order = request.args.get('sort_order', 'desc')  # 默认降序
    
    # 验证排序字段
    valid_sort_fields = ['category', 'count', 'total_amount']
    if sort_by not in valid_sort_fields:
        sort_by = 'total_amount'
    
    # 验证排序顺序
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    
    conn = get_db()
    
    # 构建带排序的SQL查询
    query = f'''
        SELECT 
            category,
            COUNT(*) as count,
            SUM(amount) as total_amount
        FROM expenses
        WHERE created_by = ?
        GROUP BY category
        ORDER BY {sort_by} {sort_order}
    '''
    
    categories = conn.execute(query, (session['user_id'],)).fetchall()
    
    # 获取总费用
    total_expenses = conn.execute('''
        SELECT SUM(amount) as total
        FROM expenses
        WHERE created_by = ?
    ''', (session['user_id'],)).fetchone()['total'] or 0
    
    # 计算下一次点击的排序顺序
    next_sort_order = 'desc' if sort_order == 'asc' else 'asc'
    
    conn.close()
    
    return render_template('category_stats.html', 
                         categories=categories, 
                         total_expenses=total_expenses,
                         current_sort=sort_by,
                         current_order=sort_order,
                         next_sort_order=next_sort_order)

@bp.route('/category/<category_name>')
def category_expenses(category_name):
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取排序参数
    sort_by = request.args.get('sort_by', 'project_name')
    sort_order = request.args.get('sort_order', 'asc')
    
    # 验证排序参数
    valid_sort_fields = ['project_name', 'date', 'category', 'purpose', 'amount', 'note', 'payment_method']
    if sort_by not in valid_sort_fields:
        sort_by = 'project_name'
    
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
    conn = get_db()
    
    # 获取该类别的所有费用记录，支持动态排序，并左连接报销表以获取报销状态
    # 根据expenses.py中的实现，description字段存储purpose内容，payment_method字段存储note内容
    query = f'''
        SELECT e.id, e.date, e.category, e.amount, e.description as purpose, e.project_id, 
               e.created_at, e.created_by, p.name as project_name, 
               CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status,
               e.payment_method as note
        FROM expenses e
        LEFT JOIN projects p ON e.project_id = p.id
        LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
        WHERE e.created_by = ? AND e.category = ?
        ORDER BY {sort_by} {sort_order}
    '''
    params = (session['user_id'], category_name)
    
    expenses = conn.execute(query, params).fetchall()
    
    # 获取总金额
    total_amount = conn.execute('''
        SELECT SUM(amount) as total
        FROM expenses
        WHERE created_by = ? AND category = ?
    ''', (session['user_id'], category_name)).fetchone()['total'] or 0
    
    # 获取所有进行中的项目列表，用于批量修改
    projects = conn.execute('''
        SELECT id, name
        FROM projects
        WHERE status = ?
        ORDER BY name
    ''', ('进行中',)).fetchall()
    
    conn.close()
    
    # 计算下一次点击的排序顺序
    next_sort_order = 'desc' if sort_order == 'asc' else 'asc'
    
    return render_template('category_expenses.html', 
                         expenses=expenses, 
                         category_name=category_name,
                         total_amount=total_amount,
                         projects=projects,
                         current_sort=sort_by,
                         current_order=sort_order,
                         next_sort_order=next_sort_order)

@bp.route('/batch_update_categories', methods=['POST'])
def batch_update_categories():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 支持多种方式获取费用ID
    expense_ids_str = request.form.get('expense_ids_hidden')  # 从前端表单的隐藏字段获取
    if expense_ids_str:
        expense_ids = expense_ids_str.split(',')
    else:
        # 兼容原有的获取方式
        expense_ids_str = request.form.get('expense_ids')
        if expense_ids_str:
            expense_ids = expense_ids_str.split(',')
        else:
            expense_ids = request.form.getlist('expense_ids')
    
    # 过滤空字符串ID
    expense_ids = [exp_id for exp_id in expense_ids if exp_id.strip()]
    
    # 支持多种方式获取类别名称
    new_category = request.form.get('category')  # 从前端新表单获取
    if not new_category:
        new_category = request.form.get('new_category')
    if not new_category:
        new_category = request.form.get('category_name')
    
    if not expense_ids:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': '请选择要修改的记录'})
        flash('请选择要修改的记录', 'warning')
        return redirect(url_for('stats.category_stats'))
    
    if not new_category:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': '请选择费用类别'})
        flash('请选择费用类别', 'warning')
        return redirect(url_for('stats.category_stats'))
    
    conn = get_db()
    try:
        # 批量更新费用类别
        placeholders = ','.join(['?' for _ in expense_ids])
        conn.execute(f'''
            UPDATE expenses
            SET category = ?
            WHERE id IN ({placeholders}) AND created_by = ?
        ''', [new_category] + expense_ids + [session['user_id']])
        conn.commit()
        
        updated_count = conn.execute('''
            SELECT COUNT(*)
            FROM expenses
            WHERE id IN ({placeholders}) AND category = ? AND created_by = ?
        '''.format(placeholders=placeholders), expense_ids + [new_category] + [session['user_id']]).fetchone()[0]
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # 对于AJAX请求，返回JSON响应，增加成功消息
            return jsonify({
                'success': True, 
                'count': updated_count,
                'message': f'🎉 成功更新 {updated_count} 条记录的费用类别！'
            })
        else:
            # 对于普通请求，使用flash消息，增加emoji和详细信息
            flash(f'🎉 成功更新 {updated_count} 条记录的费用类别！', 'success')
            # 添加多层回退机制
            return redirect(url_for('stats.category_stats'))
    except Exception as e:
        conn.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # 对于AJAX请求，返回JSON错误响应，使用更友好的错误消息
            return jsonify({
                'success': False, 
                'error': f'❌ 更新失败: {str(e)}',
                'message': '请稍后重试或联系管理员'
            })
        else:
            # 对于普通请求，使用flash消息，使用更友好的错误消息
            flash(f'❌ 更新失败: {str(e)}', 'danger')
            return redirect(url_for('stats.category_stats'))
    finally:
        conn.close()

@bp.route('/orphan_expenses')
def orphan_expenses():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取排序参数
    sort_by = request.args.get('sort_by', 'date')  # 默认按日期排序
    sort_order = request.args.get('sort_order', 'asc')  # 默认正序
    
    # 验证排序字段
    valid_sort_fields = ['date', 'description', 'category', 'amount', 'payment_method']
    # 保存原始排序字段用于模板显示
    original_sort_by = sort_by
    # 允许使用'purpose'作为排序字段（内部会映射到'description'）
    if sort_by == 'purpose':
        sort_by = 'description'
    # 允许使用'note'作为排序字段（内部会映射到'payment_method'）
    elif sort_by == 'note':
        sort_by = 'payment_method'
    elif sort_by not in valid_sort_fields:
        sort_by = 'date'
        original_sort_by = 'date'
    
    # 验证排序顺序
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
    conn = get_db()
    try:
        # 构建带排序的SQL查询，并左连接报销表以获取报销状态
        query = f'''
            SELECT e.id, e.date, e.description as purpose, e.amount, e.payment_method as note, e.created_by, e.category, 
                   CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status
            FROM expenses e
            LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
            WHERE e.project_id IS NULL OR e.project_id NOT IN (SELECT id FROM projects)
            ORDER BY e.{sort_by} {sort_order}
        '''
        orphan_expenses = conn.execute(query).fetchall()
        total_amount = sum(expense['amount'] for expense in orphan_expenses)  # 使用字典访问方式
        
        # 获取进行中的项目列表，用于归属项目选择
        projects = conn.execute('''
            SELECT id, name
            FROM projects
            WHERE status = ?
            ORDER BY name
        ''', ('进行中',)).fetchall()
    except Exception as e:
        logging.error(f"Error fetching orphan expenses details: {e}")
        orphan_expenses = []
        total_amount = 0
        projects = []
    finally:
        conn.close()
    
    # 计算下一次点击的排序顺序
    next_sort_order = 'desc' if sort_order == 'asc' else 'asc'
    
    # 获取记录数量
    expense_count = len(orphan_expenses)
    
    return render_template('orphan_expenses.html', 
                           expenses=orphan_expenses, 
                           total_amount=total_amount, 
                           projects=projects,
                           current_sort=original_sort_by,
                           current_order=sort_order,
                           next_sort_order=next_sort_order,
                           expense_count=expense_count)

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
            return jsonify({'success': True, 'count': updated_count, 'message': f'🎉 成功分配 {updated_count} 条支出到项目'})
        
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
            return jsonify({'success': False, 'error': '❌ 操作失败，请重试'})
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
            SET date = ?, project_id = ?, description = ?, amount = ?, payment_method = ?, category = ?
            WHERE id = ? AND created_by = ?
        ''', (date, project_id, request.form.get('description', purpose), amount, request.form.get('note', ''), request.form['category'], expense_id, session['user_id']))
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
        WHERE status = ?
    ''', ('进行中',)).fetchall()
    
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

@bp.route('/date_expenses/<date>')
@bp.route('/date_expenses/')
def date_expenses(date=None):
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取排序参数
    # 获取排序参数并保存原始字段名
    original_sort_by = request.args.get('sort_by', 'project_name')
    sort_order = request.args.get('sort_order', 'asc')
    
    # 验证排序参数并进行字段映射
    valid_sort_fields = ['project_name', 'date', 'category', 'purpose', 'amount', 'note']
    
    # 字段映射：将前端显示的字段名映射到数据库实际列名
    field_mapping = {
        'purpose': 'description',
        'note': 'payment_method'
    }
    
    # 设置排序字段，应用映射
    if original_sort_by in valid_sort_fields:
        sort_by = field_mapping.get(original_sort_by, original_sort_by)
    else:
        sort_by = 'project_name'
        original_sort_by = 'project_name'
    
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
    conn = get_db()
    
    # 根据是否提供日期参数构建不同的查询
    if date:
        # 获取特定日期的所有费用记录
        query = f'''
            SELECT e.*, p.name as project_name, e.description as purpose, e.payment_method as note, 
                   CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status
            FROM expenses e
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
            WHERE e.created_by = ? AND e.date = ?
            ORDER BY {sort_by} {sort_order}
        '''
        params = (session['user_id'], date)
        
        expenses = conn.execute(query, params).fetchall()
        
        # 获取总金额
        total_amount = conn.execute('''
            SELECT SUM(amount) as total
            FROM expenses
            WHERE created_by = ? AND date = ?
        ''', (session['user_id'], date)).fetchone()['total'] or 0
    else:
        # 获取所有日期的费用记录
        query = f'''
            SELECT e.*, p.name as project_name, e.description as purpose, e.payment_method as note, 
                   CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status
            FROM expenses e
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
            WHERE e.created_by = ?
            ORDER BY {sort_by} {sort_order}
        '''
        params = (session['user_id'],)
        
        expenses = conn.execute(query, params).fetchall()
        
        # 获取总金额
        total_amount = conn.execute('''
            SELECT SUM(amount) as total
            FROM expenses
            WHERE created_by = ?
        ''', (session['user_id'],)).fetchone()['total'] or 0
    
    # 获取所有进行中的项目列表，用于批量分配功能
    projects = conn.execute('SELECT id, name FROM projects WHERE status = ? ORDER BY name', ('进行中',)).fetchall()
    
    conn.close()
    
    # 计算下一次点击的排序顺序
    next_sort_order = 'desc' if sort_order == 'asc' else 'asc'
    
    return render_template('date_expenses.html', 
                         expenses=expenses, 
                         target_date=date,
                         total_amount=total_amount,
                         current_sort=original_sort_by,
                         current_order=sort_order,
                         next_sort_order=next_sort_order,
                         projects=projects)

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

