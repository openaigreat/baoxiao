from flask import Blueprint, render_template, request, redirect, url_for, session, abort, jsonify, g, flash
import sqlite3
import logging
from models import get_db
from datetime import datetime
from services.stats_service import StatsService

bp = Blueprint('stats', __name__)
stats_service = StatsService()

@bp.route('/stats')
def stats():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    stats_data = stats_service.get_project_stats()
    return render_template('stats.html', stats=stats_data)

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
    
    expenses_data = stats_service.get_expenses_by_project(project_id, sort_by, sort_order)
    
    project = {'id': project_id, 'name': f'项目 {project_id}'}
    if project_id is not None:
        conn = get_db()
        project = conn.execute('''
            SELECT id, name
            FROM projects
            WHERE id = ?
        ''', (project_id,)).fetchone()
        conn.close()
    
    return render_template('expenses.html', 
                         project=project,
                         expenses=expenses_data['expenses'],
                         total_amount=expenses_data['total_amount'],
                         projects=expenses_data['projects'],
                         current_sort=expenses_data['current_sort'],
                         current_order=expenses_data['current_order'],
                         next_sort_order=expenses_data['next_sort_order'])

@bp.route('/category_stats')
def category_stats():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    stats_data = stats_service.get_category_stats(session)
    
    # 提取总费用用于模板
    total_stats = stats_data.get('total_stats')
    if total_stats:
        # sqlite3.Row 对象需要通过索引或键访问字段
        total_expenses = total_stats['total_amount'] if total_stats['total_amount'] else 0
    else:
        total_expenses = 0
    
    return render_template('category_stats.html',
                         categories=stats_data.get('categories', []),
                         total_stats=total_stats,
                         total_expenses=total_expenses)

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
    
    expenses_data = stats_service.get_expenses_by_category(category_name, session, sort_by, sort_order)
    
    return render_template('category_expenses.html', 
                         expenses=expenses_data['expenses'], 
                         category_name=category_name,
                         total_amount=expenses_data['total_amount'],
                         projects=expenses_data['projects'],
                         current_sort=expenses_data['current_sort'],
                         current_order=expenses_data['current_order'],
                         next_sort_order=expenses_data['next_sort_order'])

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
        return redirect(request.referrer or url_for('stats.category_stats'))
    
    if not new_category:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': '请提供新的分类名称'})
        flash('请提供新的分类名称', 'warning')
        return redirect(request.referrer or url_for('stats.category_stats'))
    
    # 更新数据库
    conn = get_db()
    try:
        # 使用IN子句和参数化查询来更新记录
        placeholders = ','.join('?' * len(expense_ids))
        conn.execute(f'''
            UPDATE expenses 
            SET category = ? 
            WHERE id IN ({placeholders}) AND created_by = ?
        ''', [new_category] + expense_ids + [session['user_id']])
        conn.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': f'成功更新{len(expense_ids)}条记录的分类为"{new_category}"'})
        flash(f'成功更新{len(expense_ids)}条记录的分类为"{new_category}"', 'success')
    except Exception as e:
        conn.rollback()
        logging.error(f"Error updating categories: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': '更新失败，请重试'})
        flash('更新失败，请重试', 'danger')
    finally:
        conn.close()
    
    # 尝试返回到原来的分类页面
    referer = request.referrer
    if referer and '/category/' in referer:
        return redirect(referer)
    return redirect(url_for('stats.category_stats'))

@bp.route('/orphan_expenses')
def orphan_expenses():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取排序参数
    sort_by = request.args.get('sort_by', 'category')  # 默认按类别排序
    sort_order = request.args.get('sort_order', 'asc')  # 默认正序
    
    expenses_data = stats_service.get_expenses_by_project(None, sort_by, sort_order)
    
    return render_template('orphan_expenses.html', 
                         expenses=expenses_data['expenses'],
                         total_amount=expenses_data['total_amount'],
                         projects=expenses_data['projects'],
                         current_sort=expenses_data['current_sort'],
                         current_order=expenses_data['current_order'],
                         next_sort_order=expenses_data['next_sort_order'])

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

@bp.route('/date_expenses')
def date_expenses():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取筛选参数
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')
    
    # 验证排序参数
    valid_sort_fields = ['date', 'category', 'project_name', 'purpose', 'amount', 'note']
    if sort_by not in valid_sort_fields:
        sort_by = 'date'
    
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
    conn = get_db()
    try:
        # 构建查询语句
        query = f'''
            SELECT e.id, e.date, e.category, e.amount, e.description as purpose, e.project_id, 
                   e.created_at, e.created_by, p.name as project_name, 
                   CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status,
                   e.payment_method as note
            FROM expenses e
            LEFT JOIN projects p ON e.project_id = p.id
            LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
            WHERE e.created_by = ?
        '''
        params = [session['user_id']]
        
        # 添加日期筛选条件
        if date_from:
            query += ' AND e.date >= ?'
            params.append(date_from)
        
        if date_to:
            query += ' AND e.date <= ?'
            params.append(date_to)
        
        # 添加排序
        query += f' ORDER BY {sort_by} {sort_order}'
        
        expenses = conn.execute(query, params).fetchall()
        
        # 计算总金额
        total_query = '''
            SELECT SUM(amount) as total
            FROM expenses
            WHERE created_by = ?
        '''
        total_params = [session['user_id']]
        
        if date_from:
            total_query += ' AND date >= ?'
            total_params.append(date_from)
        
        if date_to:
            total_query += ' AND date <= ?'
            total_params.append(date_to)
            
        total_amount = conn.execute(total_query, total_params).fetchone()['total'] or 0
        
        # 获取所有进行中的项目列表，用于批量修改
        projects = conn.execute('''
            SELECT id, name
            FROM projects
            WHERE status = ?
            ORDER BY name
        ''', ('进行中',)).fetchall()
        
        # 计算下一次点击的排序顺序
        next_sort_order = 'desc' if sort_order == 'asc' else 'asc'
        
    except Exception as e:
        logging.error(f"Error in date_expenses: {e}")
        expenses = []
        total_amount = 0
        projects = []
        next_sort_order = 'asc'
    finally:
        conn.close()
    
    return render_template('date_expenses.html',
                         expenses=expenses,
                         total_amount=total_amount,
                         projects=projects,
                         date_from=date_from,
                         date_to=date_to,
                         current_sort=sort_by,
                         current_order=sort_order,
                         next_sort_order=next_sort_order)

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

@bp.route('/expense_payment_status')
def expense_payment_status():
    """支出回款状态详情"""
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    try:
        expenses = stats_service.get_expense_payment_status()
        return render_template('expense_payment_status.html', expenses=expenses)
    except Exception as e:
        logging.error(f"Error in expense_payment_status route: {e}")
        flash('获取支出回款状态失败: ' + str(e))
        return redirect(url_for('stats.stats'))

@bp.route('/project_payment_stats')
def project_payment_stats():
    """项目回款统计（支持分页）"""
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    try:
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 验证分页参数
        if per_page not in [10, 30, 50, 100]:
            per_page = 10
        
        if page < 1:
            page = 1
        
        result = stats_service.get_project_payment_stats(page, per_page)
        stats = result['stats']
        total_count = result['total_count']
        total_pages = result['total_pages']
        
        return render_template('project_payment_stats.html', 
                             stats=stats,
                             total_count=total_count,
                             total_pages=total_pages,
                             current_page=page,
                             per_page=per_page)
    except Exception as e:
        logging.error(f"Error in project_payment_stats route: {e}")
        flash('获取项目回款统计失败: ' + str(e))
        return redirect(url_for('stats.stats'))

@bp.route('/project_all_expenses')
def project_all_expenses():
    """显示项目所有支出记录（支持分页）"""
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    try:
        project_id = request.args.get('project_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 验证分页参数
        if per_page not in [10, 30, 50, 100]:
            per_page = 10
        
        if page < 1:
            page = 1
        
        if project_id is None:
            flash('项目ID参数缺失')
            return redirect(url_for('stats.project_payment_stats'))
        
        # 获取项目所有支出记录（分页）
        result = stats_service.get_all_expenses_by_project(project_id, page, per_page)
        expenses = result['expenses']
        total_count = result['total_count']
        total_pages = result['total_pages']
        
        # 获取项目名称
        project_name = '所有项目'
        if project_id == 0:
            project_name = '无项目'
        elif project_id > 0:
            conn = get_db()
            project = conn.execute('SELECT name FROM projects WHERE id = ?', (project_id,)).fetchone()
            conn.close()
            project_name = project['name'] if project else '未知项目'
        
        title = f"{project_name} - 所有支出记录"
        
        return render_template('project_all_expenses.html', 
                             expenses=expenses, 
                             title=title,
                             project_id=project_id,
                             project_name=project_name,
                             total_count=total_count,
                             total_pages=total_pages,
                             current_page=page,
                             per_page=per_page)
    except Exception as e:
        logging.error(f"Error in project_all_expenses route: {e}")
        flash('获取项目支出记录失败: ' + str(e))
        return redirect(url_for('stats.project_payment_stats'))

@bp.route('/expense_payment_details')
def expense_payment_details():
    """支出回款详情页面"""
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    try:
        project_id = request.args.get('project_id', type=int)
        status = request.args.get('status')
        
        # 获取符合条件的支出记录
        expenses = stats_service.get_expenses_by_payment_status(project_id, status)
        
        # 设置页面标题
        status_names = {
            'unreimbursed': '未报销',
            'reimbursed_unpaid': '已报销未回款',
            'reimbursed_paid': '已回款'
        }
        
        project_name = '所有项目'
        if project_id is not None:
            if project_id > 0:
                # 获取项目名称
                conn = get_db()
                project = conn.execute('SELECT name FROM projects WHERE id = ?', (project_id,)).fetchone()
                conn.close()
                project_name = project['name'] if project else '未知项目'
            else:
                project_name = '无项目'
        
        title = f"{project_name} - {status_names.get(status, '未知状态')}支出详情"
        
        return render_template('expense_payment_details.html', 
                             expenses=expenses, 
                             title=title,
                             status=status)
    except Exception as e:
        logging.error(f"Error in expense_payment_details route: {e}")
        flash('获取支出详情失败: ' + str(e))
        return redirect(url_for('stats.project_payment_stats'))
