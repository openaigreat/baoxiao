from flask import Flask, redirect, url_for, request, session
from routes.auth import bp as auth_bp
from routes.projects import bp as projects_bp
from routes.expenses import bp as expenses_bp
from routes.stats import bp as stats_bp
from routes.reimbursements import bp as reimbursements_bp
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
    
    # 使用before_request来保护所有路由（除了登录相关路由）
    @app.before_request
    def require_login():
        # 允许访问的路径
        allowed_paths = ['/login', '/static/']
        
        # 检查是否需要登录
        if not any(request.path.startswith(path) for path in allowed_paths):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
    
    @app.route('/')
    def index():
        return redirect(url_for('stats.stats'))
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)