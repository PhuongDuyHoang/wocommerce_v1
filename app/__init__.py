# app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
import logging
from logging.handlers import RotatingFileHandler

# Khởi tạo các extension
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'Vui lòng đăng nhập để truy cập trang này.'
login.login_message_category = 'info'

def create_app(config_class=None):
    """App Factory Pattern"""
    app = Flask(__name__)
    
    # Load config
    if config_class is None:
        from config import Config
        app.config.from_object(Config)
    else:
        app.config.from_object(config_class)

    # Khởi tạo extension với app
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)

    # === START: SỬA LỖI - THÊM LẠI USER LOADER BỊ THIẾU ===
    # Hàm này phải được định nghĩa sau khi các extension đã được khởi tạo
    from app.models import AppUser
    
    @login.user_loader
    def load_user(user_id):
        """Hàm được Flask-Login sử dụng để tải người dùng từ session."""
        return db.session.get(AppUser, int(user_id))
    # === END: SỬA LỖI - THÊM LẠI USER LOADER BỊ THIẾU ===

    # Đăng ký Blueprints
    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.main import main_bp
    app.register_blueprint(main_bp)

    from app.stores import stores_bp
    app.register_blueprint(stores_bp, url_prefix='/stores')

    from app.orders import orders_bp
    app.register_blueprint(orders_bp, url_prefix='/orders')

    from app.jobs import jobs_bp
    app.register_blueprint(jobs_bp, url_prefix='/jobs')
    
    from app.settings import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/settings')

    from app.users import users_bp
    app.register_blueprint(users_bp, url_prefix='/users')

    from app.designs import designs_bp
    app.register_blueprint(designs_bp, url_prefix='/designs')

    # Đăng ký các lệnh CLI
    from . import commands
    commands.register_commands(app)

    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('App startup')

    return app

from app import models