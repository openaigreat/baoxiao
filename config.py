import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_very_secret_key_123!'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 允许16MB文件上传
    UPLOAD_FOLDER = 'temp_uploads'