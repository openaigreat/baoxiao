from flask import Blueprint, render_template, request, redirect, url_for, session, abort, jsonify, flash
import sqlite3  # 导入 sqlite3 模块
from models import get_db

bp = Blueprint('projects', __name__)

@bp.route('/manage_projects')
def manage_projects():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    conn = get_db()
    projects = conn.execute('SELECT id, name, status, note FROM projects ORDER BY name').fetchall()
    conn.close()
    
    return render_template('projects.html', projects=projects)

@bp.route('/view_all_projects')
def view_all_projects():
    """查看所有项目（包括进行中和已完成）"""
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # 验证分页大小
    if per_page not in [10, 30, 50, 100]:
        per_page = 10
    
    # 计算偏移量
    offset = (page - 1) * per_page
    
    conn = get_db()
    try:
        # 获取项目总数
        total_result = conn.execute('SELECT COUNT(*) as count FROM projects').fetchone()
        total_projects = total_result['count']
        
        # 获取分页项目数据，包括项目预算金额和已提交报销金额
        projects = conn.execute('''
            SELECT 
                p.id,
                p.name,
                p.status,
                p.note,
                COALESCE(SUM(CASE WHEN e.id IS NOT NULL THEN e.amount ELSE 0 END), 0) AS total_expense,
                COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL THEN e.amount ELSE 0 END), 0) AS submitted_amount,
                COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status = '已回款' THEN e.amount ELSE 0 END), 0) AS paid_amount,
                COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status != '已回款' THEN e.amount ELSE 0 END), 0) AS unpaid_amount
            FROM projects p
            LEFT JOIN expenses e ON p.id = e.project_id
            LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
            LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
            GROUP BY p.id, p.name, p.status, p.note
            ORDER BY p.id
            LIMIT ? OFFSET ?
        ''', (per_page, offset)).fetchall()
        
        # 计算总页数
        total_pages = (total_projects + per_page - 1) // per_page
        
    except Exception as e:
        flash(f'获取项目数据失败: {str(e)}')
        projects = []
        total_projects = 0
        total_pages = 1
    finally:
        conn.close()
    
    return render_template('view_all_projects.html', 
                          projects=projects,
                          page=page,
                          per_page=per_page,
                          total_projects=total_projects,
                          total_pages=total_pages)

@bp.route('/add_project', methods=['GET', 'POST'])
def add_project():
    # 无需登录验证
    # 为了兼容性，设置一个默认用户信息
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    
    # 检查是否为AJAX请求
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        name = request.form['name']
        amount = float(request.form.get('amount', 0.0))
        note = request.form.get('note', '')
        
        try:
            db = get_db()
            db.execute(
            'INSERT INTO projects (name, note, status) VALUES (?, ?, ?)',
            (name, note, '进行中')
        )
            db.commit()
            
            if is_ajax:
                # AJAX请求返回JSON
                return jsonify({"success": True})
            else:
                # 重定向到stats页面
                flash('项目添加成功')
                return redirect(url_for('stats.stats'))
        except Exception as e:
            if is_ajax:
                # AJAX请求返回错误
                return jsonify({"success": False, "message": str(e)})
            else:
                # 常规请求显示错误
                flash('添加项目失败: ' + str(e))
                return redirect(url_for('projects.add_project'))
    
    # GET请求
    if is_ajax:
        # 如果是AJAX请求，返回模态框内容
        # GET请求返回所有项目列表
        try:
            db = get_db()
            projects = db.execute(
                'SELECT id, name, status FROM projects ORDER BY name'
            ).fetchall()
            return render_template('projects.html', projects=projects)
        except Exception as e:
            flash('获取项目列表失败: ' + str(e))
            return render_template('stats.html')
    else:
        # 否则返回完整页面
        return render_template('add_project.html')

@bp.route('/get_all_projects')
def get_all_projects():
    """获取所有项目的API端点"""
    try:
        db = get_db()
        projects = db.execute(
            "SELECT id, name FROM projects WHERE status = '进行中' ORDER BY name"
        ).fetchall()
        
        # 转换为字典列表，并在项目名称前加上项目ID
        projects_list = [
            {'id': project['id'], 'name': f"({project['id']}) {project['name']}"}
            for project in projects
        ]
        
        return jsonify({'projects': projects_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/edit_project/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    # 无需登录验证
    
    conn = get_db()
    conn.row_factory = sqlite3.Row  # 设置行工厂为 sqlite3.Row
    
    if request.method == 'POST':
        name = request.form['name']
        note = request.form.get('note', '')
        
        status = request.form['status']
        
        conn.execute('''
            UPDATE projects
            SET name = ?, note = ?, status = ?
            WHERE id = ?
        ''', (name, note, status, project_id))
        conn.commit()
        conn.close()
        return redirect(url_for('stats.expenses', project_id=project_id))
    
    project = conn.execute(''' 
        SELECT id, name, note, status FROM projects
        WHERE id = ? 
    ''', (project_id,)).fetchone()
    
    conn.close()
    
    if not project:
        abort(404, description="Project not found")
    
    return render_template('edit_project.html', project=project)
