# app/main/routes.py

from flask import render_template, request, redirect, url_for
from flask_login import current_user, login_required
from datetime import datetime

from . import main_bp
from app.models import AppUser, WooCommerceOrder

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    from app.services import get_dashboard_statistics, get_visible_orders_query

    selected_admin_id = request.args.get('admin_id', type=int)
    selected_sub_user_id = request.args.get('sub_user_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end_date_str else None

    target_user_for_stats = current_user
    if current_user.is_super_admin() and selected_sub_user_id:
        target_user_for_stats = AppUser.query.get(selected_sub_user_id) or current_user
    elif current_user.is_super_admin() and selected_admin_id:
        target_user_for_stats = AppUser.query.get(selected_admin_id) or current_user
    elif current_user.is_admin() and selected_sub_user_id:
        sub_user = AppUser.query.get(selected_sub_user_id)
        if sub_user and sub_user.parent_id == current_user.id:
            target_user_for_stats = sub_user
    
    stats = get_dashboard_statistics(target_user_for_stats, start_date, end_date)

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