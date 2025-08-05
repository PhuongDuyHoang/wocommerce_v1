# app/auth/routes.py

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user, login_user, logout_user, login_required
from . import auth_bp
from .forms import LoginForm, RegistrationForm, ChangePasswordForm
from app import db
from app.models import AppUser, Setting

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Xử lý việc đăng nhập của người dùng."""
    # Nếu người dùng đã đăng nhập, chuyển hướng đến trang dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = AppUser.query.filter_by(username=form.username.data).first()
        # Kiểm tra xem người dùng có tồn tại không và mật khẩu có đúng không
        if user is None or not user.check_password(form.password.data):
            flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Kiểm tra xem tài khoản đã được kích hoạt chưa
        if not user.is_active:
            flash('Tài khoản của bạn chưa được kích hoạt. Vui lòng liên hệ quản trị viên.', 'warning')
            return redirect(url_for('auth.login'))
        
        login_user(user)
        # Chuyển hướng đến trang mà người dùng định truy cập trước đó, hoặc về dashboard
        next_page = request.args.get('next')
        return redirect(next_page or url_for('dashboard'))
    
    return render_template('auth/login.html', title='Đăng nhập', form=form)


@auth_bp.route('/logout')
def logout():
    """Xử lý việc đăng xuất."""
    logout_user()
    flash('Bạn đã đăng xuất.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Xử lý việc đăng ký tài khoản mới."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    # Lấy cài đặt cho phép đăng ký từ DB
    enable_registration_setting = Setting.query.filter_by(key='ENABLE_REGISTRATION').first()
    enable_registration = (enable_registration_setting.value.lower() == 'true') if enable_registration_setting else False

    # Nếu chức năng đăng ký bị tắt, thông báo cho người dùng
    if not enable_registration and AppUser.query.filter_by(role='super_admin').first():
        flash('Chức năng đăng ký tài khoản mới hiện đang bị tắt.', 'warning')
        return redirect(url_for('auth.login'))

    form = RegistrationForm()
    if form.validate_on_submit():
        new_user = AppUser(username=form.username.data)
        new_user.set_password(form.password.data)

        # Người dùng đầu tiên đăng ký sẽ là super_admin
        if AppUser.query.count() == 0:
            new_user.role = 'super_admin'
            new_user.is_active = True
            # Super admin mặc định có toàn bộ quyền
            new_user.can_add_store = True
            new_user.can_delete_store = True
            new_user.can_edit_store = True
            new_user.can_view_orders = True
            db.session.add(new_user)
            db.session.commit()
            flash('Đăng ký tài khoản Super Admin thành công! Bạn đã được tự động đăng nhập.', 'success')
            login_user(new_user)
            return redirect(url_for('dashboard'))
        else:
            # Các người dùng sau sẽ là 'user' và cần admin duyệt
            new_user.role = 'user'
            new_user.is_active = False # Mặc định là chưa kích hoạt
            db.session.add(new_user)
            db.session.commit()
            flash('Đăng ký tài khoản thành công! Tài khoản của bạn đang chờ quản trị viên phê duyệt.', 'info')
            return redirect(url_for('auth.login'))

    return render_template('auth/register.html', title='Đăng ký', form=form)


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Xử lý việc đổi mật khẩu cho người dùng hiện tại."""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Mật khẩu hiện tại không đúng.', 'danger')
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash('Mật khẩu của bạn đã được thay đổi thành công.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('auth/change_password.html', title='Đổi mật khẩu', form=form)