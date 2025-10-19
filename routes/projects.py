from flask import Blueprint, render_template, request, redirect, url_for, session, abort
import sqlite3  # 导入 sqlite3 模块
from models import get_db

bp = Blueprint('projects', __name__)

@bp.route('/add_project', methods=['GET', 'POST'])
def add_project():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        conn = get_db()
        conn.execute('''
            INSERT INTO projects (name, amount, year, note)
            VALUES (?, ?, ?, ?)
        ''', (
            request.form['name'],
            float(request.form['amount']),
            int(request.form['year']),
            request.form['note']
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    return render_template('add_project.html')

@bp.route('/edit_project/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    conn.row_factory = sqlite3.Row  # 设置行工厂为 sqlite3.Row
    
    if request.method == 'POST':
        name = request.form['name']
        amount = float(request.form['amount'])
        year = int(request.form['year'])
        note = request.form['note']
        
        conn.execute('''
            UPDATE projects
            SET name = ?, amount = ?, year = ?, note = ?
            WHERE id = ?
        ''', (name, amount, year, note, project_id))
        conn.commit()
        conn.close()
        return redirect(url_for('stats.expenses', project_id=project_id))
    
    project = conn.execute('''
        SELECT * FROM projects
        WHERE id = ?
    ''', (project_id,)).fetchone()
    
    conn.close()
    
    if not project:
        abort(404, description="Project not found")
    
    return render_template('edit_project.html', project=project)