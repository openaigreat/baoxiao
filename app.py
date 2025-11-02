from flask import Flask, redirect, url_for, request, session
from routes.auth import bp as auth_bp
from routes.projects import bp as projects_bp
from routes.expenses import bp as expenses_bp
from routes.stats import bp as stats_bp
from routes.reimbursements import bp as reimbursements_bp
from routes.todos import bp as todos_bp
from config import Config
import os

def create_app():
    app = Flask(__name__)
    # 加载配置
    app.config.from_object(Config)
    # 确保上传文件夹存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # 从auth模块导入登录验证装饰器
    from routes.auth import login_required
    
    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(reimbursements_bp)
    app.register_blueprint(todos_bp)
    
    # 使用before_request来保护所有路由（除了登录相关路由和todos模块）
    @app.before_request
    def require_login():
        # 检查是否是需要登录的路径
        needs_login = True
        
        # 静态文件不需要登录
        if request.path.startswith('/static/'):
            needs_login = False
        # 登录页面不需要登录
        elif request.path == '/auth/login' or request.path == '/login':
            needs_login = False
        # 根路径重定向到todos
        elif request.path == '/':
            needs_login = False
        # todos相关路径不需要登录
        elif request.path.startswith('/todos') or request.path.startswith('/toggle_todo') or request.path.startswith('/update_todo_order') or request.path.startswith('/project_todos'):
            needs_login = False
        
        # 其他所有路径都需要登录验证
        if needs_login and 'user_id' not in session:
            return redirect(url_for('auth.login'))
    
    @app.route('/')
    def index():
        return redirect(url_for('todos.todos'))
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)