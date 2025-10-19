from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from models import get_db

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if not user or user['password'] != password:
            return redirect(url_for('auth.login'))
        
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect(url_for('index'))
    
    conn = get_db()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('login.html', users=users)

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        if user['password'] != old_password:
            conn.close()
            return "原密码错误！"
        
        conn.execute('UPDATE users SET password = ? WHERE id = ?', (new_password, session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    return render_template('change_password.html')