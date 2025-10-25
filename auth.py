from flask import Blueprint, render_template, redirect, request, session, flash
import sqlite3
import hashlib

bp = Blueprint('auth', __name__)

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def check_password(input_password, stored_hash):
    """验证密码哈希"""
    input_hash = hashlib.sha256(input_password.encode()).hexdigest()
    return input_hash == stored_hash

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect('/')
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password(password, user['password']):
            session['username'] = username
            return redirect('/')
        else:
            flash('用户名或密码错误')
    
    return render_template('login.html')

@bp.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/login')

@bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'username' not in session:
        return redirect('/login')
    
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # 验证新密码一致性
        if new_password != confirm_password:
            flash('两次输入的新密码不一致')
            return render_template('change_password.html')
        
        # 获取当前用户信息
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (session['username'],))
        user = cursor.fetchone()
        
        # 验证旧密码
        if not check_password(old_password, user['password']):
            flash('原密码错误')
            conn.close()
            return render_template('change_password.html')
        
        # 更新密码
        new_password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        cursor.execute(
            'UPDATE users SET password = ? WHERE username = ?',
            (new_password_hash, session['username'])
        )
        conn.commit()
        conn.close()
        
        flash('密码修改成功')
        return redirect('/')
    
    return render_template('change_password.html')

# 登录验证装饰器
def login_required(f):
    """装饰器：确保用户已登录"""
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# 将装饰器注册为模板全局函数
bp.app_template_global()(login_required)