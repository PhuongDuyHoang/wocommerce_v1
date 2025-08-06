# app/__init__.py

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_required
from config import Config
import json
from datetime import datetime

# REMOVED: The import from .services is moved inside the dashboard function to prevent circular imports.
# from .services import get_dashboard_statistics 

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

    from .models import AppUser, WooCommerceOrder, WooCommerceStore, Setting
    from .commands import register_commands
    register_commands(app)

    # Đăng ký các blueprint
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

    @login_manager.user_loader
    def load_user(user_id):
        return AppUser.query.get(int(user_id))

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('auth.login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        # MODIFIED: Imports are moved here, inside the function scope.
        from .services import get_dashboard_statistics, get_visible_orders_query

        # Lấy các tham số lọc từ URL
        selected_admin_id = request.args.get('admin_id', type=int)
        selected_sub_user_id = request.args.get('sub_user_id', type=int)
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end_date_str else None

        # 1. Xác định người dùng mục tiêu để xem thống kê
        target_user_for_stats = current_user
        if current_user.is_super_admin() and selected_sub_user_id:
            target_user_for_stats = AppUser.query.get(selected_sub_user_id) or current_user
        elif current_user.is_super_admin() and selected_admin_id:
            target_user_for_stats = AppUser.query.get(selected_admin_id) or current_user
        elif current_user.is_admin() and selected_sub_user_id:
            sub_user = AppUser.query.get(selected_sub_user_id)
            if sub_user and sub_user.parent_id == current_user.id:
                target_user_for_stats = sub_user
        
        # 2. Gọi hàm dịch vụ để lấy tất cả thống kê
        stats = get_dashboard_statistics(target_user_for_stats, start_date, end_date)

        # 3. Lấy dữ liệu cho các bộ lọc dropdown
        admin_users = []
        sub_users = []
        if current_user.is_super_admin():
            admin_users = AppUser.query.filter(AppUser.role.in_(['admin', 'super_admin'])).order_by(AppUser.username).all()
            if selected_admin_id:
                admin_owner = AppUser.query.get(selected_admin_id)
                if admin_owner:
                    sub_users = admin_owner.children.order_by(AppUser.username).all()
            else:
                 sub_users = AppUser.query.filter_by(role='user').order_by(AppUser.username).all()
        elif current_user.is_admin():
            sub_users = current_user.children.order_by(AppUser.username).all()

        # Lấy các đơn hàng gần đây một cách riêng biệt vì nó không bị ảnh hưởng bởi bộ lọc ngày
        recent_orders = get_visible_orders_query(target_user_for_stats)\
            .order_by(WooCommerceOrder.order_created_at.desc())\
            .limit(10).all()

        return render_template(
            'dashboard.html',
            title=f'Thống kê cho {target_user_for_stats.username}',
            start_date=start_date_str,
            end_date=end_date_str,
            recent_orders=recent_orders,
            admin_users=admin_users,
            sub_users=sub_users,
            selected_admin_id=selected_admin_id,
            selected_sub_user_id=selected_sub_user_id,
            **stats
        )

    return app