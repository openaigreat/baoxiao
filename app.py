from flask import Flask, redirect, url_for, session, render_template
from config import Config
from routes import auth, projects, expenses, stats
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 确保上传文件夹存在
    upload_folder = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    # 注册蓝图
    app.register_blueprint(auth.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(expenses.bp)
    app.register_blueprint(stats.bp)

    @app.route('/')
    def index():
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return render_template('index.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)