import os
import csv
import logging
from datetime import datetime
from io import StringIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response, jsonify
from services.reimbursement_service import ReimbursementService
from services.expense_service import ExpenseService
from models import get_db

bp = Blueprint('reimbursements', __name__, url_prefix='/reimbursements')
reimbursement_service = ReimbursementService()
expense_service = ExpenseService()

def get_db_connection():
    # 使用models.py中的get_db函数，确保使用同一个数据库文件
    return get_db()

@bp.route('/fetch_reimbursements', methods=['GET'])
def fetch_reimbursements():
    # 获取报销单列表，用于批量添加到报销单功能
    try:
        result = reimbursement_service.get_draft_and_rejected_reimbursements()
        return jsonify({'reimbursements': result})
    except Exception as e:
        logging.error(f"Error in fetch_reimbursements: {e}")
        return jsonify({'reimbursements': []})

@bp.route('/')
def reimbursements():
    conn = get_db()
    try:
        # 获取筛选参数
        status_filter = request.args.get('status', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
            
        # 构建SQL查询和参数 - 使用子查询避免笛卡尔积问题
        query = '''
            SELECT r.*, 
                   (SELECT COUNT(*) FROM reimbursement_expenses WHERE reimbursement_id = r.id) as expense_count,
                   COALESCE((SELECT SUM(reimbursement_amount) FROM reimbursement_expenses WHERE reimbursement_id = r.id), 0) as calculated_total,
                   COALESCE((SELECT SUM(amount) FROM reimbursement_payments WHERE reimbursement_id = r.id), 0) as total_paid,
                   (SELECT MAX(payment_date) FROM reimbursement_payments WHERE reimbursement_id = r.id) as latest_payment_date
            FROM reimbursements r
        '''
        params = []
        
        # 添加WHERE子句
        if status_filter or date_from or date_to:
            query += " WHERE 1=1"
            
            if status_filter:
                query += " AND r.status = ?"
                params.append(status_filter)
            
            if date_from:
                query += " AND r.submit_date >= ?"
                params.append(date_from)
            
            if date_to:
                query += " AND r.submit_date <= ?"
                params.append(date_to)
        
        # 添加ORDER BY（不再需要GROUP BY，因为不再有多表JOIN）
        query += '''
            ORDER BY r.submit_date DESC, r.created_at DESC
        '''
        
        reimbursements = conn.execute(query, params).fetchall()
        conn.close()
        
        return render_template('reimbursements.html', 
                             reimbursements=reimbursements,
                             status_filter=status_filter,
                             date_from=date_from,
                             date_to=date_to)
                             
    except Exception as e:
        logging.error(f"Error fetching reimbursements: {e}")
        conn.close()
        return render_template('reimbursements.html', 
                             reimbursements=[],
                             status_filter=status_filter,
                             date_from=date_from,
                             date_to=date_to)

@bp.route('/add_reimbursement', methods=['GET', 'POST'])
def add_reimbursement():
    
    if request.method == 'POST':
        conn = get_db()
        try:
            submit_date = request.form['submit_date']
            note = request.form['note'] or ''
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 创建新的报销单（草稿状态）
            conn.execute('''
                INSERT INTO reimbursements (submit_date, total_amount, status, note, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (submit_date, 0.0, '草稿', note, session['user_id'], current_time, current_time))
            conn.commit()
            
            # 获取新创建的报销单ID
            reimbursement_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            
            conn.close()
            return redirect(url_for('reimbursements.edit_reimbursement', reimbursement_id=reimbursement_id))
            
        except Exception as e:
            logging.error(f"Error creating reimbursement: {e}")
            conn.rollback()
            conn.close()
    
    return render_template('add_reimbursement.html')

@bp.route('/edit_reimbursement/<int:reimbursement_id>', methods=['GET', 'POST'])
def edit_reimbursement(reimbursement_id):
    # 获取回款记录的函数
    def get_reimbursement_payments(reimbursement_id):
        return reimbursement_service.get_reimbursement_payments(reimbursement_id)
    
    
    # 获取报销单信息
    conn = get_db()
    try:
        reimbursement = conn.execute('''
            SELECT r.*, COALESCE(SUM(rp.amount), 0) as total_paid
            FROM reimbursements r
            LEFT JOIN reimbursement_payments rp ON r.id = rp.reimbursement_id
            WHERE r.id = ?
            GROUP BY r.id
        ''', (reimbursement_id,)).fetchone()
    except Exception as e:
        logging.error(f"Error fetching reimbursement: {e}")
        conn.close()
        return redirect(url_for('reimbursements.reimbursements'))
    finally:
        pass  # conn在函数末尾关闭
    
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
        SELECT e.*, e.description as purpose, re.reimbursement_amount, p.name as project_name
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
        SELECT e.*, e.description as purpose, p.name as project_name
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
    
    try:
        reimbursement_id = request.form.get('reimbursement_id', type=int)
        expense_id = request.form.get('expense_id', type=int)
        reimbursement_amount = request.form.get('reimbursement_amount', type=float)
        
        result = reimbursement_service.add_expense_to_reimbursement(
            reimbursement_id, expense_id, reimbursement_amount, session)
        
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error in add_expense_to_reimbursement route: {e}")
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/add_reimbursement_payment/<int:reimbursement_id>', methods=['POST'])
def add_reimbursement_payment(reimbursement_id):
    
    try:
        # 获取回款信息
        payment_date = request.form.get('payment_date')
        amount = request.form.get('amount', type=float)
        note = request.form.get('note', '')
        
        result = reimbursement_service.add_reimbursement_payment(
            reimbursement_id, payment_date, amount, note)
        
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error in add_reimbursement_payment route: {e}")
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/add_expenses_to_reimbursement', methods=['POST'])
def add_expenses_to_reimbursement():
    
    try:
        reimbursement_id = request.form.get('reimbursement_id', type=int)
        expense_ids_str = request.form.get('expense_ids', '')
        expense_ids = [int(id.strip()) for id in expense_ids_str.split(',') if id.strip()]
        
        result = reimbursement_service.add_multiple_expenses_to_reimbursement(
            reimbursement_id, expense_ids, session)
        
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error in add_expenses_to_reimbursement route: {e}")
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/remove_expense_from_reimbursement', methods=['POST'])
def remove_expense_from_reimbursement():
    
    conn = get_db()
    
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
    
    conn = get_db()
    
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
    
    try:
        conn = get_db()
        # 只获取草稿状态的报销单
        reimbursements = conn.execute('''
            SELECT id, submit_date as submission_date, total_amount, note 
            FROM reimbursements 
            WHERE status = '草稿' 
            ORDER BY submit_date DESC
        ''').fetchall()
        
        result = []
        for row in reimbursements:
            result.append({
                'id': row['id'],
                'submission_date': row['submission_date'],
                'total_amount': float(row['total_amount']) if row['total_amount'] is not None else 0.0,
                'note': row['note'] or ''
            })
        
        conn.close()
        return jsonify({'reimbursements': result})
    except Exception as e:
        logging.error(f"Error getting draft reimbursements: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@bp.route('/create_reimbursement_and_add_expenses', methods=['POST'])
def create_reimbursement_and_add_expenses():
    
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

@bp.route('/export_reimbursement/<int:reimbursement_id>')
def export_reimbursement(reimbursement_id):
    
    try:
        # 获取导出数据
        export_data = reimbursement_service.export_reimbursement_details(reimbursement_id)
        
        # 生成CSV内容
        output = StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow(['费用日期', '项目分类', '费用金额'])
        
        # 写入数据行
        for row in export_data:
            # 拼接项目和分类字段并加上"费用"
            project_category = f"{row['project_name']}-{row['category']}费用"
            
            writer.writerow([
                row['date'],
                project_category,
                f"{row['total_amount']:.2f}"
            ])
        
        # 准备响应
        csv_data = output.getvalue()
        output.close()
        
        # 转换为GBK编码
        csv_data_gbk = csv_data.encode('utf-8').decode('utf-8').encode('gbk', errors='ignore')
        
        # 创建响应
        response = make_response(csv_data_gbk)
        response.headers['Content-Type'] = 'text/csv; charset=gbk'
        response.headers['Content-Disposition'] = f'attachment; filename=reimbursement_{reimbursement_id}_summary.csv'
        
        return response
    except UnicodeEncodeError:
        # 如果GBK编码失败，使用UTF-8编码
        try:
            export_data = reimbursement_service.export_reimbursement_details(reimbursement_id)
            
            # 生成CSV内容
            output = StringIO()
            writer = csv.writer(output)
            
            # 写入表头
            writer.writerow(['费用日期', '项目分类', '费用金额'])
            
            # 写入数据行
            for row in export_data:
                # 拼接项目和分类字段并加上"费用"
                project_category = f"{row['project_name']}-{row['category']}费用"
                
                writer.writerow([
                    row['date'],
                    project_category,
                    f"{row['total_amount']:.2f}"
                ])
            
            # 准备响应
            csv_data = output.getvalue()
            output.close()
            
            # 创建响应
            response = make_response(csv_data)
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename=reimbursement_{reimbursement_id}_summary.csv'
            
            return response
        except Exception as e:
            logging.error(f"Error exporting reimbursement: {e}")
            flash('导出失败: ' + str(e), 'error')
            return redirect(url_for('reimbursements.edit_reimbursement', reimbursement_id=reimbursement_id))
    except Exception as e:
        logging.error(f"Error exporting reimbursement: {e}")
        flash('导出失败: ' + str(e), 'error')
        return redirect(url_for('reimbursements.edit_reimbursement', reimbursement_id=reimbursement_id))

@bp.route('/create_reimbursement_ajax', methods=['POST'])
def create_reimbursement_ajax():
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