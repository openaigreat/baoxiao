from flask import Blueprint, render_template, redirect, url_for, request, session, jsonify, flash
import sqlite3
from datetime import datetime
import logging
from models import get_db  # 从models.py导入统一的数据库连接函数

bp = Blueprint('reimbursements', __name__)

def get_db_connection():
    # 使用models.py中的get_db函数，确保使用同一个数据库文件
    return get_db()

@bp.route('/fetch_reimbursements', methods=['GET'])
def fetch_reimbursements():
    # 获取报销单列表，用于批量添加到报销单功能
    conn = get_db_connection()
    try:
        # 获取所有草稿或已拒绝状态的报销单
        reimbursements = conn.execute('''
            SELECT r.*,
                   COUNT(re.id) as expense_count,
                   COALESCE(SUM(re.reimbursement_amount), 0) as calculated_total
            FROM reimbursements r
            LEFT JOIN reimbursement_expenses re ON r.id = re.reimbursement_id
            WHERE r.status IN ('草稿', '已拒绝')
            GROUP BY r.id
            ORDER BY r.created_at DESC
        ''').fetchall()
        
        # 转换为字典列表
        result = []
        for r in reimbursements:
            result.append({
                'id': r['id'],
                'submission_date': r['submit_date'],
                'total_amount': r['calculated_total'] or 0,
                'status': r['status']
            })
        
        conn.close()
        return jsonify({'reimbursements': result})
    except Exception as e:
        conn.close()
        return jsonify({'reimbursements': []})

@bp.route('/reimbursements')
def reimbursements():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    try:
        # 获取筛选参数
        status_filter = request.args.get('status', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        # 构建SQL查询和参数
        query = '''
            SELECT r.*, 
                   COUNT(re.id) as expense_count,
                   COALESCE(SUM(re.reimbursement_amount), 0) as calculated_total,
                   COALESCE(SUM(rp.amount), 0) as total_paid,
                   MAX(rp.payment_date) as latest_payment_date
            FROM reimbursements r
            LEFT JOIN reimbursement_expenses re ON r.id = re.reimbursement_id
            LEFT JOIN reimbursement_payments rp ON r.id = rp.reimbursement_id
        '''
        params = []
        
        # 添加WHERE子句
        if status_filter or date_from or date_to:
            query += ' WHERE'
            
            if status_filter:
                query += ' r.status = ?'
                params.append(status_filter)
            
            if date_from:
                if params:
                    query += ' AND'
                query += ' r.submit_date >= ?'
                params.append(date_from)
            
            if date_to:
                if params:
                    query += ' AND'
                query += ' r.submit_date <= ?'
                params.append(date_to)
        
        # 添加GROUP BY和ORDER BY
        query += '''
            GROUP BY r.id
            ORDER BY r.created_at DESC
        '''
        
        # 执行查询
        reimbursements = conn.execute(query, params).fetchall()
        
        # 获取报销状态统计（带筛选条件）
        stats_query = 'SELECT status, COUNT(*) as count, SUM(total_amount) as total FROM reimbursements'
        stats_params = []
        
        if status_filter or date_from or date_to:
            stats_query += ' WHERE'
            
            if status_filter:
                stats_query += ' status = ?'
                stats_params.append(status_filter)
            
            if date_from:
                if stats_params:
                    stats_query += ' AND'
                stats_query += ' submit_date >= ?'
                stats_params.append(date_from)
            
            if date_to:
                if stats_params:
                    stats_query += ' AND'
                stats_query += ' submit_date <= ?'
                stats_params.append(date_to)
        
        stats_query += ' GROUP BY status'
        status_stats = conn.execute(stats_query, stats_params).fetchall()
        
    except Exception as e:
        logging.error(f"Error fetching reimbursements: {e}")
        reimbursements = []
        status_stats = []
    finally:
        conn.close()
    
    return render_template('reimbursements.html', 
                          reimbursements=reimbursements, 
                          status_stats=status_stats)

@bp.route('/add_reimbursement', methods=['GET', 'POST'])
def add_reimbursement():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    
    if request.method == 'POST':
        submit_date = request.form['submit_date']
        note = request.form['note'] or ''
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            # 创建新的报销单（草稿状态）
            conn.execute('''
                INSERT INTO reimbursements (submit_date, total_amount, status, note, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (submit_date, 0.0, '草稿', note, session['user_id'], current_time, current_time))
            conn.commit()
            
            # 获取新创建的报销单ID
            reimbursement_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            
            return redirect(url_for('reimbursements.edit_reimbursement', reimbursement_id=reimbursement_id))
            
        except Exception as e:
            logging.error(f"Error adding reimbursement: {e}")
            conn.rollback()
    
    conn.close()
    return render_template('add_reimbursement.html')

@bp.route('/edit_reimbursement/<int:reimbursement_id>', methods=['GET', 'POST'])
def edit_reimbursement(reimbursement_id):
    # 获取回款记录的函数
    def get_reimbursement_payments(reimbursement_id):
        conn = get_db_connection()
        payments = conn.execute('''
            SELECT * FROM reimbursement_payments 
            WHERE reimbursement_id = ? 
            ORDER BY payment_date DESC
        ''', (reimbursement_id,)).fetchall()
        conn.close()
        return payments
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取报销单信息
    conn = get_db_connection()
    reimbursement = conn.execute('''
        SELECT r.*, COALESCE(SUM(rp.amount), 0) as total_paid
        FROM reimbursements r
        LEFT JOIN reimbursement_payments rp ON r.id = rp.reimbursement_id
        WHERE r.id = ?
        GROUP BY r.id
    ''', (reimbursement_id,)).fetchone()
    
    if not reimbursement:
        conn.close()
        return redirect(url_for('reimbursements.reimbursements'))
    
    # 处理表单提交
    if request.method == 'POST':
        action = request.form.get('action')
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if action == 'update':
            # 更新报销单基本信息
            submit_date = request.form['submit_date']
            note = request.form['note'] or ''
            
            try:
                conn.execute('''
                    UPDATE reimbursements
                    SET submit_date = ?, note = ?, updated_at = ?
                    WHERE id = ?
                ''', (submit_date, note, current_time, reimbursement_id))
                conn.commit()
                
                # 更新成功后重新获取报销单信息，以显示最新数据
                reimbursement = conn.execute('''
                    SELECT * FROM reimbursements WHERE id = ?
                ''', (reimbursement_id,)).fetchone()
                
            except Exception as e:
                logging.error(f"Error updating reimbursement: {e}")
                conn.rollback()
        
        elif action == 'submit':
            # 提交报销单
            try:
                # 检查是否有关联的支出记录
                has_expenses = conn.execute('''
                    SELECT COUNT(*) as count
                    FROM reimbursement_expenses
                    WHERE reimbursement_id = ?
                ''', (reimbursement_id,)).fetchone()
                
                if has_expenses['count'] == 0:
                    flash('报销单必须至少关联一条支出记录才能提交', 'error')
                    return redirect(url_for('reimbursements.edit_reimbursement', reimbursement_id=reimbursement_id))
                
                # 计算总金额
                total_result = conn.execute('''
                    SELECT SUM(reimbursement_amount) as total
                    FROM reimbursement_expenses
                    WHERE reimbursement_id = ?
                ''', (reimbursement_id,)).fetchone()
                
                total_amount = total_result['total'] or 0.0
                
                conn.execute('''
                    UPDATE reimbursements
                    SET status = ?, total_amount = ?, updated_at = ?
                    WHERE id = ?
                ''', ('已提交', total_amount, current_time, reimbursement_id))
                conn.commit()
                
                # 添加成功消息
                flash('报销单已成功提交！', 'success')
                return redirect(url_for('reimbursements.reimbursements'))
                
            except Exception as e:
                logging.error(f"Error submitting reimbursement: {e}")
                conn.rollback()
                flash(f'提交报销单失败: {str(e)}', 'error')
                return redirect(url_for('reimbursements.edit_reimbursement', reimbursement_id=reimbursement_id))
    
    # 获取已关联的支出记录
    attached_expenses = conn.execute('''
        SELECT e.*, re.reimbursement_amount, p.name as project_name
        FROM reimbursement_expenses re
        JOIN expenses e ON re.expense_id = e.id
        LEFT JOIN projects p ON e.project_id = p.id
        WHERE re.reimbursement_id = ?
    ''', (reimbursement_id,)).fetchall()
    
    # 获取回款记录
    payments = get_reimbursement_payments(reimbursement_id)
    
    # 计算总回款金额
    total_paid = sum(payment['amount'] for payment in payments) if payments else 0
    
    # 获取可添加的支出记录（未被任何报销单关联的）
    available_expenses = conn.execute('''
        SELECT e.*, p.name as project_name
        FROM expenses e
        LEFT JOIN projects p ON e.project_id = p.id
        WHERE e.id NOT IN (
            SELECT expense_id FROM reimbursement_expenses
        )
        ORDER BY e.date DESC
    ''').fetchall()
    
    conn.close()
    
    # 计算当前日期，格式为YYYY-MM-DD
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('edit_reimbursement.html',
                          reimbursement=reimbursement,
                          attached_expenses=attached_expenses,
                          available_expenses=available_expenses,
                          payments=payments,
                          total_paid=total_paid,
                          today_date=today_date)

@bp.route('/add_expense_to_reimbursement', methods=['POST'])
def add_expense_to_reimbursement():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db_connection()
    
    try:
        reimbursement_id = request.form.get('reimbursement_id', type=int)
        expense_id = request.form.get('expense_id', type=int)
        reimbursement_amount = request.form.get('reimbursement_amount', type=float)
        
        # 验证报销单是否存在且状态允许编辑
        reimbursement = conn.execute('''
            SELECT * FROM reimbursements WHERE id = ?
        ''', (reimbursement_id,)).fetchone()
        
        if not reimbursement:
            conn.close()
            return jsonify({'success': False, 'error': '报销单不存在'})
        
        if reimbursement['status'] not in ['草稿', '已拒绝']:
            conn.close()
            return jsonify({'success': False, 'error': '只有草稿或已拒绝状态的报销单可以添加支出记录'})
        
        # 验证支出记录是否存在
        expense = conn.execute('''
            SELECT * FROM expenses WHERE id = ?
        ''', (expense_id,)).fetchone()
        
        if not expense:
            conn.close()
            return jsonify({'success': False, 'error': '支出记录不存在'})
        
        # 检查支出记录是否已关联到其他报销单
        existing = conn.execute('''
            SELECT 1 FROM reimbursement_expenses WHERE expense_id = ?
        ''', (expense_id,)).fetchone()
        
        if existing:
            conn.close()
            return jsonify({'success': False, 'error': '该支出记录已关联到其他报销单'})
        
        # 添加关联
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
            INSERT INTO reimbursement_expenses (reimbursement_id, expense_id, reimbursement_amount, added_date)
            VALUES (?, ?, ?, ?)
        ''', (reimbursement_id, expense_id, reimbursement_amount, current_time))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/add_reimbursement_payment/<int:reimbursement_id>', methods=['POST'])
def add_reimbursement_payment(reimbursement_id):
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db_connection()
    
    try:
        # 验证报销单是否存在
        reimbursement = conn.execute('''
            SELECT * FROM reimbursements WHERE id = ?
        ''', (reimbursement_id,)).fetchone()
        
        if not reimbursement:
            conn.close()
            return jsonify({'success': False, 'error': '报销单不存在'})
        
        # 非草稿状态的报销单都可以添加回款
        if reimbursement['status'] == '草稿':
            conn.close()
            return jsonify({'success': False, 'error': '草稿状态的报销单不能添加回款'})
        
        # 获取回款信息
        payment_date = request.form.get('payment_date')
        amount = request.form.get('amount', type=float)
        note = request.form.get('note', '')
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 验证必填字段
        if not payment_date or amount is None or amount <= 0:
            conn.close()
            return jsonify({'success': False, 'error': '回款日期和金额为必填项，金额必须大于0'})
        
        # 添加回款记录
        conn.execute('''
            INSERT INTO reimbursement_payments 
            (reimbursement_id, payment_date, amount, note, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (reimbursement_id, payment_date, amount, note, current_time))
        
        # 计算总回款金额
        total_paid = conn.execute('''
            SELECT SUM(amount) as total FROM reimbursement_payments 
            WHERE reimbursement_id = ?
        ''', (reimbursement_id,)).fetchone()['total'] or 0
        
        # 更新报销单的总回款金额
        conn.execute('''
            UPDATE reimbursements SET total_paid = ? 
            WHERE id = ?
        ''', (total_paid, reimbursement_id))
        
        # 如果回款金额等于或超过报销总额，更新状态为'已回款'
        if total_paid >= reimbursement['total_amount']:
            conn.execute('''
                UPDATE reimbursements SET status = '已回款' 
                WHERE id = ?
            ''', (reimbursement_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        logging.error(f"添加回款记录时出错: {e}")
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/add_expenses_to_reimbursement', methods=['POST'])
def add_expenses_to_reimbursement():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db_connection()
    
    try:
        reimbursement_id = request.form.get('reimbursement_id', type=int)
        expense_ids_str = request.form.get('expense_ids', '')
        expense_ids = [int(id.strip()) for id in expense_ids_str.split(',') if id.strip()]
        
        # 验证报销单是否存在且状态允许编辑
        reimbursement = conn.execute('''
            SELECT * FROM reimbursements WHERE id = ?
        ''', (reimbursement_id,)).fetchone()
        
        if not reimbursement:
            conn.close()
            return jsonify({'success': False, 'error': '报销单不存在'})
        
        if reimbursement['status'] not in ['草稿', '已拒绝']:
            conn.close()
            return jsonify({'success': False, 'error': '只有草稿或已拒绝状态的报销单可以添加支出记录'})
        
        # 开始事务
        conn.execute('BEGIN TRANSACTION')
        
        added_count = 0
        for expense_id in expense_ids:
            # 验证支出记录是否存在
            expense = conn.execute('''
                SELECT * FROM expenses WHERE id = ?
            ''', (expense_id,)).fetchone()
            
            if not expense:
                continue
            
            # 检查支出记录是否已关联到其他报销单
            existing = conn.execute('''
                SELECT 1 FROM reimbursement_expenses WHERE expense_id = ?
            ''', (expense_id,)).fetchone()
            
            if existing:
                continue
            
            # 添加关联（使用原始金额）
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute('''
                INSERT INTO reimbursement_expenses (reimbursement_id, expense_id, reimbursement_amount, added_date)
                VALUES (?, ?, ?, ?)
            ''', (reimbursement_id, expense_id, expense['amount'], current_time))
            
            added_count += 1
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'count': added_count})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/remove_expense_from_reimbursement', methods=['POST'])
def remove_expense_from_reimbursement():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db_connection()
    
    try:
        reimbursement_id = request.form.get('reimbursement_id', type=int)
        expense_id = request.form.get('expense_id', type=int)
        
        # 验证报销单是否存在且状态允许编辑
        reimbursement = conn.execute('''
            SELECT * FROM reimbursements WHERE id = ?
        ''', (reimbursement_id,)).fetchone()
        
        if not reimbursement:
            conn.close()
            return jsonify({'success': False, 'error': '报销单不存在'})
        
        if reimbursement['status'] not in ['草稿', '已拒绝']:
            conn.close()
            return jsonify({'success': False, 'error': '只有草稿或已拒绝状态的报销单可以移除支出记录'})
        
        # 验证关联是否存在
        conn.execute('''
            DELETE FROM reimbursement_expenses 
            WHERE reimbursement_id = ? AND expense_id = ?
        ''', (reimbursement_id, expense_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/delete_reimbursement/<int:reimbursement_id>', methods=['POST'])
def delete_reimbursement(reimbursement_id):
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db_connection()
    
    # 开始事务
    conn.execute('BEGIN TRANSACTION')
    
    try:
        # 验证报销单是否存在
        reimbursement = conn.execute('''
            SELECT * FROM reimbursements WHERE id = ?
        ''', (reimbursement_id,)).fetchone()
        
        if not reimbursement:
            conn.rollback()
            conn.close()
            return jsonify({'success': False, 'error': '报销单不存在'})
        
        # 只有草稿状态可以删除
        if reimbursement['status'] != '草稿':
            conn.rollback()
            conn.close()
            return jsonify({'success': False, 'error': '只有草稿状态的报销单可以删除'})
        
        # 删除关联的支出记录关联
        conn.execute('''
            DELETE FROM reimbursement_expenses 
            WHERE reimbursement_id = ?
        ''', (reimbursement_id,))
        
        # 删除报销单
        conn.execute('''
            DELETE FROM reimbursements 
            WHERE id = ?
        ''', (reimbursement_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/get_reimbursements', methods=['GET'])
def get_reimbursements():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, submit_date as submission_date, total_amount FROM reimbursements', ())
            reimbursements = cursor.fetchall()
            
            result = []
            for row in reimbursements:
                result.append({
                    'id': row[0],
                    'submission_date': row[1],
                    'total_amount': row[2]
                })
            
            return jsonify({'reimbursements': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/get_draft_reimbursements', methods=['GET'])
def get_draft_reimbursements():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 只获取草稿状态的报销单
            cursor.execute('''
                SELECT id, submit_date as submission_date, total_amount, note 
                FROM reimbursements 
                WHERE status = '草稿' 
                ORDER BY submit_date DESC
            ''', ())
            reimbursements = cursor.fetchall()
            
            result = []
            for row in reimbursements:
                result.append({
                    'id': row[0],
                    'submission_date': row[1],
                    'total_amount': row[2],
                    'note': row[3] or ''
                })
            
            return jsonify({'reimbursements': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/create_reimbursement_and_add_expenses', methods=['POST'])
def create_reimbursement_and_add_expenses():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db_connection()
    
    try:
        # 获取表单数据
        submit_date = request.form.get('submit_date')
        note = request.form.get('note', '')
        expense_ids_str = request.form.get('expense_ids', '')
        expense_ids = [int(id.strip()) for id in expense_ids_str.split(',') if id.strip()]
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 创建新的报销单（草稿状态）
        conn.execute('''
            INSERT INTO reimbursements (submit_date, total_amount, status, note, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (submit_date, 0.0, '草稿', note, session['user_id'], current_time, current_time))
        conn.commit()
        
        # 获取新创建的报销单ID
        reimbursement_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        # 开始事务，批量添加支出记录
        conn.execute('BEGIN TRANSACTION')
        added_count = 0
        skipped_count = 0
        
        total_amount = 0.0
        
        for expense_id in expense_ids:
            # 验证支出记录是否存在
            expense = conn.execute('''
                SELECT * FROM expenses WHERE id = ?
            ''', (expense_id,)).fetchone()
            
            if not expense:
                skipped_count += 1
                continue
            
            # 检查支出记录是否已被关联到其他报销单
            existing = conn.execute('''
                SELECT * FROM reimbursement_expenses WHERE expense_id = ?
            ''', (expense_id,)).fetchone()
            
            if existing:
                skipped_count += 1
                continue
            
            # 添加支出记录到报销单
            conn.execute('''
                INSERT INTO reimbursement_expenses (reimbursement_id, expense_id, reimbursement_amount, added_date)
                VALUES (?, ?, ?, ?)
            ''', (reimbursement_id, expense_id, expense['amount'], current_time))
            
            added_count += 1
            total_amount += expense['amount']
        
        # 更新报销单总金额
        if added_count > 0:
            conn.execute('''
                UPDATE reimbursements
                SET total_amount = ?, updated_at = ?
                WHERE id = ?
            ''', (total_amount, current_time, reimbursement_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'count': added_count,
            'skipped': skipped_count
        })
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logging.error(f"Error creating reimbursement and adding expenses: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@bp.route('/batch_add_to_reimbursement', methods=['POST'])
def batch_add_to_reimbursement():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db_connection()
    
    try:
        reimbursement_id = request.form.get('reimbursement_id', type=int)
        expense_ids_str = request.form.get('expense_ids', '')
        expense_ids = [int(id.strip()) for id in expense_ids_str.split(',') if id.strip()]
        
        # 验证报销单是否存在且状态允许编辑
        reimbursement = conn.execute('''
            SELECT * FROM reimbursements WHERE id = ?
        ''', (reimbursement_id,)).fetchone()
        
        if not reimbursement:
            conn.close()
            return jsonify({'success': False, 'error': '报销单不存在'})
        
        if reimbursement['status'] != '草稿':
            conn.close()
            return jsonify({'success': False, 'error': '只有草稿状态的报销单可以添加支出记录'})
        
        # 开始事务
        conn.execute('BEGIN TRANSACTION')
        
        added_count = 0
        skipped_count = 0
        
        for expense_id in expense_ids:
            # 验证支出记录是否存在
            expense = conn.execute('''
                SELECT * FROM expenses WHERE id = ?
            ''', (expense_id,)).fetchone()
            
            if not expense:
                skipped_count += 1
                continue
            
            # 检查支出记录是否已关联到其他报销单
            existing = conn.execute('''
                SELECT 1 FROM reimbursement_expenses WHERE expense_id = ?
            ''', (expense_id,)).fetchone()
            
            if existing:
                skipped_count += 1
                continue
            
            # 添加关联（使用原始金额）
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute('''
                INSERT INTO reimbursement_expenses (reimbursement_id, expense_id, reimbursement_amount, added_date)
                VALUES (?, ?, ?, ?)
            ''', (reimbursement_id, expense_id, expense['amount'], current_time))
            
            added_count += 1
        
        conn.commit()
        conn.close()
        
        message = f'成功添加 {added_count} 条支出记录到报销单'
        if skipped_count > 0:
            message += f'，跳过 {skipped_count} 条已关联的支出记录'
        
        return jsonify({'success': True, 'count': added_count, 'message': message})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)})



@bp.route('/create_reimbursement_ajax', methods=['POST'])
def create_reimbursement_ajax():
    # 无需登录验证
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    try:
        submission_date = request.form.get('submission_date') or datetime.now().strftime('%Y-%m-%d')
        note = request.form.get('note', '')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO reimbursements (submission_date, total_amount, status, note, user_id) VALUES (?, ?, ?, ?, ?)',
                (submission_date, 0, '草稿', note, session['user_id'])
            )
            reimbursement_id = cursor.lastrowid
            conn.commit()
            
            return jsonify({'success': True, 'reimbursement_id': reimbursement_id, 'submission_date': submission_date})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

