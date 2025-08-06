# app/decorators.py

from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_or_super_admin_required(f):
    """
    Decorator yêu cầu người dùng phải có vai trò 'admin' hoặc 'super_admin'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (not current_user.is_admin() and not current_user.is_super_admin()):
            flash('Bạn không có quyền truy cập trang này.', 'danger')
            return redirect(url_for('main.dashboard')) # MODIFIED
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """
    Decorator yêu cầu người dùng phải có vai trò 'super_admin'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_super_admin():
            flash('Bạn không có quyền truy cập trang này.', 'danger')
            return redirect(url_for('main.dashboard')) # MODIFIED
        return f(*args, **kwargs)
    return decorated_function

# --- Decorator kiểm tra quyền cụ thể (dựa trên các cột boolean trong model AppUser) ---

def can_add_store_required(f):
    """
    Decorator kiểm tra người dùng có quyền 'can_add_store'.
    Super Admin và Admin mặc định có quyền này.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Super admin và admin luôn có quyền này
        if current_user.is_authenticated and (current_user.is_super_admin() or current_user.is_admin()):
            return f(*args, **kwargs)
        # User thường cần được cấp quyền cụ thể
        if not current_user.is_authenticated or not current_user.can_add_store:
            flash('Bạn không có quyền thêm cửa hàng mới.', 'danger')
            return redirect(url_for('main.dashboard')) # MODIFIED
        return f(*args, **kwargs)
    return decorated_function

def can_view_orders_required(f):
    """
    Decorator kiểm tra người dùng có quyền 'can_view_orders'.
    Super Admin và Admin mặc định có quyền này.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and (current_user.is_super_admin() or current_user.is_admin()):
            return f(*args, **kwargs)
        if not current_user.is_authenticated or not current_user.can_view_orders:
            flash('Bạn không có quyền xem danh sách đơn hàng.', 'danger')
            return redirect(url_for('main.dashboard')) # MODIFIED
        return f(*args, **kwargs)
    return decorated_function