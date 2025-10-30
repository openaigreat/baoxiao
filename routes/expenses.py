"""
费用相关的业务逻辑服务层
"""

import pandas as pd
import os
import uuid
from werkzeug.utils import secure_filename
import re

class ExpenseService:
    """处理与费用导入相关的业务逻辑"""

    def save_uploaded_file(self, file, upload_folder):
        """
        保存上传的文件并返回安全的文件名
        """
        if file.filename == '':
            raise ValueError("未选择文件")
            
        # 检查文件格式
        filename = file.filename.lower()
        if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
            raise ValueError("不支持的文件格式")

        # 生成唯一文件名并保存
        unique_filename = str(uuid.uuid4()) + '_' + secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, unique_filename)
        file.save(temp_path)
        return unique_filename

    def read_excel_file(self, temp_path, file_ext):
        """
        根据文件扩展名读取Excel或CSV文件
        """
        if file_ext.endswith('.csv'):
            # 尝试不同的编码格式来读取CSV文件
            for encoding in ['utf-8', 'gbk', 'gb2312']:
                try:
                    return pd.read_csv(temp_path, encoding=encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError('CSV文件编码不支持，请尝试UTF-8或GBK编码格式')
        
        elif file_ext.endswith('.xlsx'):
            # 对于xlsx文件，强制使用openpyxl引擎
            return pd.read_excel(temp_path, engine='openpyxl')
        elif file_ext.endswith('.xls'):
            # 对于xls文件，使用xlrd引擎
            return pd.read_excel(temp_path, engine='xlrd')
        else:
            raise ValueError('不支持的文件格式')

    def process_imported_expenses(self, df, mapping, session):
        """
        处理导入的数据框，并将其插入数据库
        返回成功和失败的数量
        """
        from models import get_db
        conn = get_db()
        success_count = 0
        error_count = 0

        try:
            for index, row in df.iterrows():
                try:
                    # === 日期处理 ===
                    if pd.isna(row[mapping['date_col']]):
                        continue  # 跳过插入操作
                    try:
                        date = pd.to_datetime(row[mapping['date_col']]).strftime('%Y-%m-%d')
                    except pd.errors.ParserError:
                        error_count += 1
                        continue  # 跳过插入操作

                    # === 项目ID处理 ===
                    project_id = row[mapping['project_col']]
                    if pd.isna(project_id):
                        project_id = None
                    else:
                        try:
                            project_id = int(project_id)
                        except ValueError:
                            error_count += 1
                            continue

                    # === 用途处理 ===
                    purpose = str(row[mapping['purpose_col']]) if not pd.isna(row[mapping['purpose_col']]) else '未填写用途'

                    # === 金额处理 ===
                    amount_value = row[mapping['amount_col']]
                    if pd.isna(amount_value):
                        amount = 0.0
                    else:
                        amount_str = str(amount_value)
                        amount_str = re.sub(r'[^0-9.]', '', amount_str)  # 移除非数字字符
                        try:
                            amount = float(amount_str)
                        except ValueError:
                            error_count += 1
                            continue

                    # === 备注处理 ===
                    note = ''
                    if mapping['note_col'] and mapping['note_col'] in row:
                        note = str(row[mapping['note_col']]) if not pd.isna(row[mapping['note_col']]) else ''

                    # === 费用分类处理 ===
                    category = '其他'
                    if mapping['category_col'] and mapping['category_col'] in row:
                        if not pd.isna(row[mapping['category_col']]):
                            category_value = str(row[mapping['category_col']])
                            if any(keyword in category_value for keyword in ['餐', '食', '饭']):
                                category = '餐费'
                            elif any(keyword in category_value for keyword in ['交通', '车', '油', '票']):
                                category = '交通'
                            elif any(keyword in category_value for keyword in ['材料', '物', '品']):
                                category = '材料'
                            else:
                                category = category_value

                    # === 插入数据库 ===
                    conn.execute('''
                        INSERT INTO expenses 
                        (date, project_id, description, amount, payment_method, created_by, category)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        date,
                        project_id,
                        purpose,
                        amount,
                        note,
                        session.get('user_id', 1),
                        category
                    ))
                    success_count += 1

                except Exception:
                    error_count += 1

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

        return success_count, error_count
from flask import Blueprint, render_template, request, redirect, url_for, session, abort, flash, current_app
from models import get_db
import os
from datetime import datetime
from services.expense_service import ExpenseService

bp = Blueprint('expenses', __name__)
# 创建服务实例
expense_service = ExpenseService()

@bp.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    try:
        if request.method == 'POST':
            # 处理手动输入
            if 'date' not in request.form:
                return "日期字段不能为空", 400
            date = request.form['date']
            project_id = request.form['project_id']
            if project_id == '':
                project_id = None
            else:
                project_id = int(project_id)
                session['last_project'] = project_id
            
            session['last_date'] = date
            
            conn.execute('''
                INSERT INTO expenses (date, project_id, description, amount, payment_method, category, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                date,
                project_id,
                request.form['purpose'],
                float(request.form['amount']),
                request.form.get('note', ''),  # 使用payment_method列存储note内容
                request.form['category'],
                1  # 使用固定值1作为created_by
            ))
            conn.commit()
            return redirect(url_for('stats.stats'))
        
        projects = conn.execute('SELECT id, name FROM projects WHERE status = ?', ('进行中',)).fetchall()
        current_date = datetime.now().strftime('%Y-%m-%d')
        return render_template('add_expense.html', 
                            projects=projects,
                            current_date=current_date)
    finally:
        conn.close()

@bp.route('/import_expense', methods=['GET', 'POST'])
def import_expense():
    if request.method == 'POST':
        try:
            # 保存上传文件
            file = request.files['excel_file']
            upload_folder = current_app.config['UPLOAD_FOLDER']
            filename = expense_service.save_uploaded_file(file, upload_folder)
            
            # 读取文件列名
            file_ext = file.filename.lower()
            temp_path = os.path.join(upload_folder, filename)
            df = expense_service.read_excel_file(temp_path, file_ext)
            
        except Exception as e:
            flash(f'文件读取失败: {str(e)}', 'danger')
            return redirect(url_for('expenses.import_expense'))
        
        return render_template('import_expense_mapping.html',
                             excel_columns=df.columns.tolist(),
                             temp_file=filename)
    return render_template('add_expense.html')

@bp.route('/import_expense_mapping', methods=['POST'])  # 仅允许POST
def import_expense_mapping():
    # 获取映射参数
    temp_file = request.form['temp_file']
    mapping = {
        'date_col': request.form.get('date_col'),
        'project_col': request.form.get('project_col'),
        'purpose_col': request.form.get('purpose_col'),
        'amount_col': request.form.get('amount_col'),
        'note_col': request.form.get('note_col'),
        'category_col': request.form.get('category_col')
    }
    
    # 将参数存入session
    session['import_params'] = {
        'file_path': temp_file,
        'mapping': mapping
    }
    
    # 直接跳转到最终处理（无需URL参数）
    return redirect(url_for('expenses.import_expense_final'))

@bp.route('/import_expense_final', methods=['GET', 'POST'])
def import_expense_final():
    # 从session获取参数
    if 'import_params' not in session:
        flash('导入参数已失效，请重新操作', 'danger')
        return redirect(url_for('expenses.import_expense'))
    
    params = session.pop('import_params')  # 取出后立即清除
    file_path = params['file_path']
    mapping = params['mapping']
    
    # 文件路径验证
    upload_folder = current_app.config['UPLOAD_FOLDER']
    temp_path = os.path.join(upload_folder, file_path)
    if not os.path.exists(temp_path):
        flash('临时文件已丢失', 'danger')
        return redirect(url_for('expenses.import_expense'))
   
    try:
        # 读取数据文件
        file_ext = file_path.lower()
        df = expense_service.read_excel_file(temp_path, file_ext)
        
        # 处理导入的数据
        success_count, error_count = expense_service.process_imported_expenses(df, mapping, session)
        
        # 显示结果
        if success_count == len(df):
            flash(f'🎉 成功导入全部 {success_count} 条记录！', 'success')
        elif success_count > 0:
            flash(f'✅ 部分成功：成功导入 {success_count} 条记录，失败 {error_count} 条记录', 'warning')
        else:
            flash(f'❌ 导入失败：全部 {error_count} 条记录处理失败，请检查数据格式', 'danger')
        
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return redirect(url_for('stats.stats'))
        
    except Exception as e:
        flash(f'导入过程中出现错误: {str(e)}', 'danger')
        return redirect(url_for('expenses.import_expense'))

@bp.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    try:
        expense = conn.execute('''
            SELECT * FROM expenses 
            WHERE id = ? AND created_by = ?
        ''', (expense_id, session['user_id'])).fetchone()
        
        if not expense:
            abort(403)
        
        if request.method == 'POST':
            project_id = request.form['project_id']
            if project_id == '':
                project_id = None
            else:
                project_id = int(project_id)
                
            conn.execute('''
                UPDATE expenses SET
                    date = ?,
                    project_id = ?,
                    description = ?,
                    amount = ?,
                    payment_method = ?,
                    category = ?
                WHERE id = ?
            ''', (
                request.form['date'],
                project_id,
                request.form['description'],  # 使用description字段
                float(request.form['amount']),
                request.form.get('note', ''),  # 使用note字段的值存储到payment_method列
                request.form['category'],
                expense_id
            ))
            conn.commit()
            return redirect(url_for('stats.stats'))
        
        projects = conn.execute('SELECT id, name FROM projects WHERE status = ?', ('进行中',)).fetchall()
        return render_template('edit_expense.html', 
                             expense=expense, 
                             projects=projects)
    finally:
        conn.close()