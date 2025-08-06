# app/__init__.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Vui lòng đăng nhập để truy cập trang này.'
login_manager.login_message_category = 'info'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from .models import AppUser
    
    @login_manager.user_loader
    def load_user(user_id):
        return AppUser.query.get(int(user_id))

    # Đăng ký các blueprint
    from .main import main_bp
    app.register_blueprint(main_bp)
    
    from .auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .stores import stores_bp
    app.register_blueprint(stores_bp, url_prefix='/stores')
    
    from .orders import orders_bp
    app.register_blueprint(orders_bp, url_prefix='/orders')

    from .users import users_bp
    app.register_blueprint(users_bp, url_prefix='/users')
    
    from .settings import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/settings')

    from .jobs import jobs_bp
    app.register_blueprint(jobs_bp, url_prefix='/jobs')

    # Đăng ký các lệnh CLI
    from . import commands
    commands.register_commands(app)

    return app