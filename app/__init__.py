# app/__init__.py

from flask import Flask, redirect, url_for, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_required
from sqlalchemy import func
import json
from config import Config
from datetime import datetime, timedelta, timezone

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Vui lòng đăng nhập để truy cập trang này."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    from .models import AppUser
    return AppUser.query.get(int(user_id))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # --- Đăng ký các Blueprints ---
    from .auth.routes import auth_bp
    app.register_blueprint(auth_bp)
    from .stores.routes import stores_bp
    app.register_blueprint(stores_bp, url_prefix='/stores')
    from .orders.routes import orders_bp
    app.register_blueprint(orders_bp, url_prefix='/orders')
    from .users.routes import users_bp
    app.register_blueprint(users_bp, url_prefix='/users')
    from .settings.routes import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/settings')
    
    # ### THÊM DÒNG ĐĂNG KÝ BLUEPRINT CHO JOBS ###
    from .jobs.routes import jobs_bp
    app.register_blueprint(jobs_bp, url_prefix='/jobs')
    # ###########################################

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('auth.login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        from .models import WooCommerceOrder, WooCommerceStore, AppUser
        
        stores_query = WooCommerceStore.query
        if current_user.is_admin():
            managed_user_ids = [user.id for user in current_user.children]
            managed_user_ids.append(current_user.id)
            stores_query = stores_query.filter(WooCommerceStore.user_id.in_(managed_user_ids))
        elif not current_user.is_super_admin():
            stores_query = stores_query.filter_by(user_id=current_user.id)
        
        accessible_stores = stores_query.all()
        accessible_store_ids = [store.id for store in accessible_stores]
        total_stores = len(accessible_store_ids)

        if not accessible_store_ids:
            return render_template('dashboard.html', title='Thống kê', total_revenue='$0.00', total_orders=0, total_stores=0, new_orders_24h=0, recent_orders=[], top_stores=[], chart_labels=json.dumps([]), chart_data=json.dumps([]), admin_users=[], sub_users=[], selected_admin_id=None, selected_sub_user_id=None)

        orders_query = WooCommerceOrder.query.filter(WooCommerceOrder.store_id.in_(accessible_store_ids))

        selected_admin_id = request.args.get('admin_id', type=int)
        selected_sub_user_id = request.args.get('sub_user_id', type=int)
        
        admin_users_for_filter = []
        sub_users_for_filter = []

        if current_user.is_super_admin():
            admin_users_for_filter = AppUser.query.filter_by(role='admin').order_by(AppUser.username).all()
            if selected_admin_id:
                selected_admin = AppUser.query.get(selected_admin_id)
                if selected_admin:
                    sub_users_for_filter = selected_admin.children.order_by(AppUser.username).all()
                
                if selected_sub_user_id:
                    stores_query = stores_query.filter_by(user_id=selected_sub_user_id)
                else:
                    user_ids_to_filter = [selected_admin_id] + [u.id for u in sub_users_for_filter]
                    stores_query = stores_query.filter(WooCommerceStore.user_id.in_(user_ids_to_filter))
        elif current_user.is_admin():
            sub_users_for_filter = current_user.children.order_by(AppUser.username).all()
            if selected_sub_user_id:
                if selected_sub_user_id in [u.id for u in sub_users_for_filter]:
                    stores_query = stores_query.filter_by(user_id=selected_sub_user_id)
                else:
                    stores_query = stores_query.filter_by(user_id=-1) 
            else:
                managed_user_ids = [u.id for u in sub_users_for_filter]
                managed_user_ids.append(current_user.id)
                stores_query = stores_query.filter(WooCommerceStore.user_id.in_(managed_user_ids))
        
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                orders_query = orders_query.filter(WooCommerceOrder.order_created_at >= start_date)
            except ValueError:
                start_date_str = None
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                orders_query = orders_query.filter(WooCommerceOrder.order_created_at <= end_date)
            except ValueError:
                end_date_str = None

        valid_statuses = ['completed', 'processing']
        
        total_revenue = orders_query.filter(
            WooCommerceOrder.status.in_(valid_statuses)
        ).with_entities(db.func.sum(WooCommerceOrder.total)).scalar() or 0
        
        total_orders = orders_query.count()

        time_24h_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        new_orders_24h = WooCommerceOrder.query.filter(
            WooCommerceOrder.store_id.in_(accessible_store_ids),
            WooCommerceOrder.order_created_at >= time_24h_ago
        ).count()

        recent_orders = orders_query.order_by(WooCommerceOrder.order_created_at.desc()).limit(10).all()

        top_stores = db.session.query(
            WooCommerceStore.name,
            db.func.sum(WooCommerceOrder.total).label('total_revenue')
        ).join(WooCommerceOrder).filter(
            WooCommerceOrder.store_id.in_(accessible_store_ids),
            WooCommerceOrder.status.in_(valid_statuses)
        ).group_by(WooCommerceStore.name).order_by(db.desc('total_revenue')).limit(5).all()

        today = datetime.now(timezone.utc).date()
        seven_days_ago = today - timedelta(days=6)
        
        daily_revenue_results = db.session.query(
            func.date(WooCommerceOrder.order_created_at).label('order_date'),
            func.sum(WooCommerceOrder.total).label('daily_revenue')
        ).filter(
            WooCommerceOrder.store_id.in_(accessible_store_ids),
            WooCommerceOrder.status.in_(valid_statuses),
            func.date(WooCommerceOrder.order_created_at) >= seven_days_ago
        ).group_by('order_date').order_by('order_date').all()
        
        revenue_by_date = {result.order_date.strftime('%d-%m'): result.daily_revenue for result in daily_revenue_results}
        chart_labels = []
        chart_data = []
        for i in range(7):
            day = seven_days_ago + timedelta(days=i)
            day_str = day.strftime('%d-%m')
            chart_data.append(revenue_by_date.get(day_str, 0))
            chart_labels.append(day_str)

        context = {
            'title': 'Thống kê',
            'total_revenue': f"${total_revenue:,.2f}",
            'total_orders': total_orders,
            'total_stores': total_stores,
            'new_orders_24h': new_orders_24h,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'recent_orders': recent_orders,
            'top_stores': top_stores,
            'chart_labels': json.dumps(chart_labels),
            'chart_data': json.dumps(chart_data),
            'admin_users': admin_users_for_filter,
            'sub_users': sub_users_for_filter,
            'selected_admin_id': selected_admin_id,
            'selected_sub_user_id': selected_sub_user_id
        }
        
        return render_template('dashboard.html', **context)

    return app

from . import models