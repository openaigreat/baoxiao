from flask import Blueprint, render_template, request, redirect, url_for, session, abort, flash, current_app
from models import get_db
import pandas as pd
from io import BytesIO
import os
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime  # 导入 datetime 模块

bp = Blueprint('expenses', __name__)

@bp.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    try:
        if request.method == 'POST':
                        
            # 处理手动输入
            if 'date' not in request.form:
                return "日期字段不能为空", 400
            date = request.form['date']
            project_id = int(request.form['project_id'])
            session['last_date'] = date
            session['last_project'] = project_id
            
            conn.execute('''
                INSERT INTO expenses (date, project_id, purpose, amount, note, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                date,
                project_id,
                request.form['purpose'],
                float(request.form['amount']),
                request.form['note'],
                session['user_id']
            ))
            conn.commit()
            return redirect(url_for('expenses.add_expense'))
        
        projects = conn.execute('SELECT * FROM projects').fetchall()
        current_date = datetime.now().strftime('%Y-%m-%d')  # 使用 datetime 模块
        return render_template('add_expense.html', 
                            projects=projects,
                            current_date=current_date)
    finally:
        conn.close()

@bp.route('/import_expense', methods=['GET', 'POST'])
def import_expense():
    if request.method == 'POST':
        # 保存上传文件
        file = request.files['excel_file']
        if file.filename == '':
            return "未选择文件", 400
        if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
            return "不支持的文件格式", 400
        
        filename = str(uuid.uuid4()) + '_' + secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']
        temp_path = os.path.join(upload_folder, filename)
        file.save(temp_path)
        
        # 读取文件列名
        if file.filename.endswith('.csv'):
            df = pd.read_csv(temp_path)
        else:
            engine = 'openpyxl' if file.filename.endswith('.xlsx') else 'xlrd'
            df = pd.read_excel(temp_path, engine=engine)
        
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
        'note_col': request.form.get('note_col')
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
   
    # 读取数据文件
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(temp_path)
        else:
            engine = 'openpyxl' if file_path.endswith('.xlsx') else 'xlrd'
            df = pd.read_excel(temp_path, engine=engine)
    except Exception as e:
        flash(f'文件读取失败: {str(e)}', 'danger')
        return redirect(url_for('expenses.import_expense'))
    
    # 数据转换
    conn = get_db()
    success_count = 0
    error_count = 0
    try:
        for index, row in df.iterrows():
            try:
                # === 日期处理 ===
                if pd.isna(row[mapping['date_col']]):
                    flash(f'第 {index+2} 行日期为空', 'warning')
                    continue  # 跳过插入操作
                else:
                    try:
                        date = pd.to_datetime(row[mapping['date_col']]).strftime('%Y-%m-%d')
                    except pd.errors.ParserError:
                        flash(f'第 {index+2} 行日期格式错误', 'warning')
                        continue  # 跳过插入操作
                
                # === 项目ID处理 ===
                project_id = row[mapping['project_col']]
                if pd.isna(project_id):
                    flash(f'第 {index+2} 行项目ID为空', 'warning')
                    continue  # 跳过插入操作
                else:
                    try:
                        project_id = int(project_id)
                    except ValueError:
                        flash(f'第 {index+2} 行项目ID格式错误', 'warning')
                        continue  # 跳过插入操作

                # === 用途处理 ===
                purpose = str(row[mapping['purpose_col']]) if not pd.isna(row[mapping['purpose_col']]) else '未填写用途'
                
                # === 金额处理 ===
                amount = float(row[mapping['amount_col']]) if not pd.isna(row[mapping['amount_col']]) else 0.0
                
                # === 备注处理 ===
                note = ''
                if mapping['note_col'] and mapping['note_col'] in row:
                    note = str(row[mapping['note_col']]) if not pd.isna(row[mapping['note_col']]) else ''

                # === 插入数据库 ===
                conn.execute('''
                    INSERT INTO expenses 
                    (date, project_id, purpose, amount, note, user_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    date,
                    project_id,
                    purpose,
                    amount,
                    note,
                    session['user_id']  # 自动关联当前用户
                ))
                success_count += 1
                
            except ValueError as e:
                flash(f'第 {index+2} 行数据格式错误: {str(e)}', 'warning')
                error_count += 1
            except KeyError as e:
                flash(f'第 {index+2} 行列名 {e} 不存在', 'danger')
                error_count += 1
            except Exception as e:
                flash(f'第 {index+2} 行插入失败: {str(e)}', 'danger')
                error_count += 1

        conn.commit()
        flash(f'成功导入 {success_count}/{len(df)} 条记录, 跳过 {error_count} 条记录', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'导入失败: {str(e)}', 'danger')
    finally:
        conn.close()
        if os.path.exists(temp_path):
            os.remove(temp_path)  # 清理临时文件

    return redirect(url_for('expenses.add_expense'))
@bp.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    try:
        expense = conn.execute('''
            SELECT * FROM expenses 
            WHERE id = ? AND user_id = ?
        ''', (expense_id, session['user_id'])).fetchone()
        
        if not expense:
            abort(403)
        
        if request.method == 'POST':
            conn.execute('''
                UPDATE expenses SET
                    date = ?,
                    project_id = ?,
                    purpose = ?,
                    amount = ?,
                    note = ?
                WHERE id = ?
            ''', (
                request.form['date'],
                int(request.form['project_id']),
                request.form['purpose'],
                float(request.form['amount']),
                request.form['note'],
                expense_id
            ))
            conn.commit()
            return redirect(url_for('stats.expenses', project_id=expense['project_id']))  # 修改这里的端点名称
        
        projects = conn.execute('SELECT * FROM projects').fetchall()
        return render_template('edit_expense.html', 
                             expense=expense, 
                             projects=projects)
    finally:
        conn.close()