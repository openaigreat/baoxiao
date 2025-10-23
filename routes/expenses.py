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
                INSERT INTO expenses (date, project_id, purpose, amount, note, user_id, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                date,
                project_id,
                request.form['purpose'],
                float(request.form['amount']),
                request.form['note'],
                1,  # 使用固定值1，避免引用users表
                request.form['category']
            ))
            conn.commit()
            return redirect(url_for('stats.stats'))
        
        projects = conn.execute('SELECT id, name FROM projects').fetchall()
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
                    project_id = None  # 允许项目ID为空，设置为None
                else:
                    try:
                        project_id = int(project_id)
                    except ValueError:
                        flash(f'第 {index+2} 行项目ID格式错误', 'warning')
                        continue  # 跳过插入操作

                # === 用途处理 ===
                purpose = str(row[mapping['purpose_col']]) if not pd.isna(row[mapping['purpose_col']]) else '未填写用途'
                
                # === 金额处理 ===
                # 添加金额格式化功能，处理带有货币符号或分隔符的情况
                amount_value = row[mapping['amount_col']]
                if pd.isna(amount_value):
                    amount = 0.0
                else:
                    # 转换为字符串并进行清理
                    amount_str = str(amount_value)
                    # 移除非数字字符（保留小数点）
                    import re
                    amount_str = re.sub(r'[^0-9.]', '', amount_str)
                    try:
                        amount = float(amount_str)
                    except ValueError:
                        flash(f'第 {index+2} 行金额格式错误，无法转换为数字', 'warning')
                        error_count += 1
                        continue  # 跳过此行
                
                # === 备注处理 ===
                note = ''
                if mapping['note_col'] and mapping['note_col'] in row:
                    note = str(row[mapping['note_col']]) if not pd.isna(row[mapping['note_col']]) else ''
                
                # === 费用分类处理 ===
                category = '其他'  # 默认类别
                if mapping['category_col'] and mapping['category_col'] in row:
                    if not pd.isna(row[mapping['category_col']]):
                        category_value = str(row[mapping['category_col']])
                        # 标准化常见类别
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
                    (date, project_id, purpose, amount, note, user_id, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    date,
                    project_id,
                    purpose,
                    amount,
                    note,
                    session['user_id'],  # 自动关联当前用户
                    category  # 使用映射的类别或默认值
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
        # 改进导入结果提示，更清晰地显示成功和失败的记录数
        total_records = len(df)
        if success_count == total_records:
            flash(f'🎉 成功导入全部 {success_count} 条记录！', 'success')
        elif success_count > 0:
            flash(f'✅ 部分成功：成功导入 {success_count} 条记录，失败 {error_count} 条记录', 'warning')
        else:
            flash(f'❌ 导入失败：全部 {error_count} 条记录处理失败，请检查数据格式', 'danger')
        
    except Exception as e:
        conn.rollback()
        flash(f'导入失败: {str(e)}', 'danger')
    finally:
        conn.close()
        if os.path.exists(temp_path):
            os.remove(temp_path)  # 清理临时文件

    return redirect(url_for('stats.stats'))
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
            WHERE id = ? AND user_id = ?
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
                    purpose = ?,
                    amount = ?,
                    note = ?,
                    category = ?
                WHERE id = ?
            ''', (
                request.form['date'],
                project_id,
                request.form['purpose'],
                float(request.form['amount']),
                request.form['note'],
                request.form['category'],
                expense_id
            ))
            conn.commit()
            return redirect(url_for('stats.stats'))
        
        projects = conn.execute('SELECT id, name FROM projects').fetchall()
        return render_template('edit_expense.html', 
                             expense=expense, 
                             projects=projects)
    finally:
        conn.close()