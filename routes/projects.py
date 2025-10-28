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
            'SELECT id, name FROM projects ORDER BY name'
        ).fetchall()
        
        # 转换为字典列表
        projects_list = [
            {'id': project['id'], 'name': project['name']}
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