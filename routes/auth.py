from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from models import get_db

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    # 移除登录验证，直接设置默认用户并重定向到主页
    if 'user_id' not in session:
        session['user_id'] = 1
        session['username'] = '默认用户'
    return redirect(url_for('index'))

@bp.route('/logout')
def logout():
    # 保持会话，仅更新用户名为默认值
    session['username'] = '默认用户'
    return redirect(url_for('index'))

@bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    # 直接重定向到主页，不再支持密码修改功能
    return redirect(url_for('index'))