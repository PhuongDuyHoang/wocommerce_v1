# app/users/routes.py

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required
from . import users_bp
from .forms import UserManagementForm
from app import db
from app.models import AppUser, WooCommerceStore
from app.decorators import admin_or_super_admin_required, super_admin_required

@users_bp.route('/')
@login_required
@admin_or_super_admin_required
def manage():
    """Hiển thị trang quản lý người dùng."""
    if current_user.is_super_admin():
        # Super Admin thấy tất cả người dùng
        users = AppUser.query.order_by(AppUser.username).all()
    else: # Admin chỉ thấy các user con do mình tạo
        users = current_user.children.order_by(AppUser.username).all()
        
    return render_template('users/manage_users.html', title='Quản lý Người dùng', users=users)


@users_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_or_super_admin_required
def add():
    """Xử lý việc thêm người dùng mới."""
    form = UserManagementForm(current_user_logged_in=current_user)
    
    if form.validate_on_submit():
        new_user = AppUser(username=form.username.data)
        new_user.set_password(form.password.data)

        # Gán vai trò và người quản lý
        if current_user.is_super_admin():
            new_user.role = form.role.data
            new_user.parent_id = form.parent.data if form.parent.data != 0 else None
            # Cấp quyền tùy chỉnh nâng cao
            new_user.can_customize_telegram_delay = form.can_customize_telegram_delay.data
            new_user.can_customize_telegram_templates = form.can_customize_telegram_templates.data
        else: # Admin chỉ có thể tạo user con của chính mình
            new_user.role = 'user'
            new_user.parent_id = current_user.id

        new_user.is_active = form.is_active.data
        # Cấp các quyền cơ bản
        new_user.can_add_store = form.can_add_store.data
        new_user.can_delete_store = form.can_delete_store.data
        new_user.can_view_orders = form.can_view_orders.data

        db.session.add(new_user)
        db.session.commit()
        flash(f'Đã tạo người dùng "{new_user.username}" thành công!', 'success')
        return redirect(url_for('users.manage'))

    return render_template('users/add_edit_user.html', title='Thêm Người dùng mới', form=form)


@users_bp.route('/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_or_super_admin_required
def edit(user_id):
    """Xử lý việc chỉnh sửa thông tin người dùng."""
    user_to_edit = AppUser.query.get_or_404(user_id)
    
    # Kiểm tra quyền: Admin chỉ được sửa user con của mình
    if current_user.is_admin() and user_to_edit.parent_id != current_user.id:
        flash('Bạn không có quyền chỉnh sửa người dùng này.', 'danger')
        return redirect(url_for('users.manage'))

    form = UserManagementForm(
        obj=user_to_edit, 
        original_username=user_to_edit.username, 
        user_being_edited=user_to_edit, 
        current_user_logged_in=current_user
    )

    if form.validate_on_submit():
        user_to_edit.username = form.username.data
        
        # Đặt lại mật khẩu nếu có nhập
        if form.password.data:
            user_to_edit.set_password(form.password.data)

        user_to_edit.is_active = form.is_active.data
        
        # Chỉ Super Admin mới được đổi Role và Parent
        if current_user.is_super_admin():
            user_to_edit.role = form.role.data
            user_to_edit.parent_id = form.parent.data if form.parent.data != 0 else None
            user_to_edit.can_customize_telegram_delay = form.can_customize_telegram_delay.data
            user_to_edit.can_customize_telegram_templates = form.can_customize_telegram_templates.data

        user_to_edit.can_add_store = form.can_add_store.data
        user_to_edit.can_delete_store = form.can_delete_store.data
        user_to_edit.can_view_orders = form.can_view_orders.data

        db.session.commit()
        flash(f'Đã cập nhật thông tin cho người dùng "{user_to_edit.username}".', 'success')
        return redirect(url_for('users.manage'))
    
    return render_template('users/add_edit_user.html', title=f'Sửa: {user_to_edit.username}', form=form)


@users_bp.route('/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_or_super_admin_required
def delete(user_id):
    """Xử lý việc xóa một người dùng."""
    user_to_delete = AppUser.query.get_or_404(user_id)
    
    # Các quy tắc an toàn
    if user_to_delete.id == current_user.id:
        flash('Bạn không thể tự xóa chính mình.', 'danger')
        return redirect(url_for('users.manage'))
    
    if user_to_delete.is_super_admin() and AppUser.query.filter_by(role='super_admin').count() <= 1:
        flash('Không thể xóa Super Admin cuối cùng của hệ thống.', 'danger')
        return redirect(url_for('users.manage'))

    if current_user.is_admin() and user_to_delete.parent_id != current_user.id:
        flash('Bạn không có quyền xóa người dùng này.', 'danger')
        return redirect(url_for('users.manage'))

    username = user_to_delete.username
    # Gán lại các cửa hàng của người dùng này thành "chưa gán" (user_id = None)
    WooCommerceStore.query.filter_by(user_id=user_id).update({"user_id": None})
    
    # Gán lại các user con của người dùng này thành "không có người quản lý"
    for child in user_to_delete.children:
        child.parent_id = None
        
    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f'Đã xóa người dùng "{username}" và các liên kết.', 'success')
    return redirect(url_for('users.manage'))


@users_bp.route('/delete_selected', methods=['POST'])
@login_required
@super_admin_required # Chỉ Super Admin được xóa hàng loạt
def delete_selected():
    """Xử lý xóa hàng loạt người dùng được chọn."""
    data = request.get_json()
    if not data or 'ids' not in data:
        return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}), 400

    ids_to_delete = [int(id_str) for id_str in data['ids']]
    deleted_count = 0
    
    for user_id in ids_to_delete:
        # Áp dụng lại các quy tắc an toàn
        if user_id == current_user.id:
            continue
        
        user_to_delete = AppUser.query.get(user_id)
        if not user_to_delete:
            continue

        if user_to_delete.is_super_admin() and AppUser.query.filter_by(role='super_admin').count() <= 1:
            continue

        # Gán lại cửa hàng và user con
        WooCommerceStore.query.filter_by(user_id=user_id).update({"user_id": None})
        for child in user_to_delete.children:
            child.parent_id = None

        db.session.delete(user_to_delete)
        deleted_count += 1
        
    db.session.commit()
    flash(f'Đã xóa thành công {deleted_count} người dùng.', 'success')
    return jsonify({'status': 'success'})