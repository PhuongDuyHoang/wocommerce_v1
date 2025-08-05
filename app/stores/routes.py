# app/stores/routes.py

from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import current_user, login_required
import uuid

from . import stores_bp
from .forms import StoreForm
from app import db
from app.models import WooCommerceStore, AppUser, BackgroundTask
from app.decorators import can_add_store_required
from app.worker import check_single_store, executor, sync_history_for_store

@stores_bp.route('/')
@login_required
def manage():
    """
    Quản lý cửa hàng với chức năng phân trang.
    Mỗi trang hiển thị 30 cửa hàng.
    """
    # Lấy số trang từ query parameter, mặc định là trang 1
    page = request.args.get('page', 1, type=int)
    
    # Số lượng mục trên mỗi trang
    per_page = 30

    # Xây dựng truy vấn cơ bản, sắp xếp theo tên
    stores_query = WooCommerceStore.query.order_by(WooCommerceStore.name.asc())

    # Lọc cửa hàng dựa trên vai trò của người dùng
    if current_user.is_super_admin():
        # Super admin thấy tất cả cửa hàng
        pagination = stores_query.paginate(page=page, per_page=per_page, error_out=False)
    elif current_user.is_admin():
        # Admin thấy cửa hàng của mình và của các user con do mình quản lý
        managed_user_ids = [user.id for user in current_user.children]
        managed_user_ids.append(current_user.id)
        pagination = stores_query.filter(WooCommerceStore.user_id.in_(managed_user_ids)).paginate(page=page, per_page=per_page, error_out=False)
    else:
        # User thường chỉ thấy cửa hàng của mình
        pagination = stores_query.filter_by(user_id=current_user.id).paginate(page=page, per_page=per_page, error_out=False)
    
    # Lấy danh sách các cửa hàng cho trang hiện tại từ đối tượng pagination
    stores = pagination.items
    
    return render_template('stores/manage_stores.html', 
                           title='Quản lý Cửa hàng', 
                           stores=stores, 
                           pagination=pagination)

@stores_bp.route('/add', methods=['GET', 'POST'])
@login_required
@can_add_store_required
def add():
    """Thêm cửa hàng mới."""
    form = StoreForm()
    # Logic gán người dùng cho cửa hàng
    if current_user.is_super_admin() or current_user.is_admin():
        if current_user.is_super_admin():
            assignable_users = AppUser.query.filter(AppUser.role.in_(['user', 'admin'])).order_by(AppUser.username).all()
        else: # is_admin
            assignable_users = [current_user] + current_user.children.order_by(AppUser.username).all()
        form.user_id.choices = [(u.id, u.username) for u in assignable_users]
    else:
        del form.user_id

    # Xử lý khi form hợp lệ
    if form.validate_on_submit():
        user_id_to_assign = current_user.id
        if (current_user.is_super_admin() or current_user.is_admin()) and 'user_id' in form:
            user_id_to_assign = form.user_id.data
            
        new_store = WooCommerceStore(
            name=form.name.data,
            store_url=form.store_url.data,
            consumer_key=form.consumer_key.data,
            consumer_secret=form.consumer_secret.data,
            note=form.note.data,
            user_id=user_id_to_assign
        )
        db.session.add(new_store)
        db.session.commit()
        flash(f'Đã thêm cửa hàng "{new_store.name}" thành công! Bạn có thể kéo dữ liệu đơn hàng ngay bây giờ.', 'success')
        return redirect(url_for('stores.manage'))
    
    return render_template('stores/add_edit_store.html', title='Thêm Cửa hàng mới', form=form)

@stores_bp.route('/edit/<int:store_id>', methods=['GET', 'POST'])
@login_required
def edit(store_id):
    """Chỉnh sửa thông tin cửa hàng."""
    store = WooCommerceStore.query.get_or_404(store_id)
    
    # Kiểm tra quyền
    is_owner = (store.user_id == current_user.id)
    is_managed_by_admin = (current_user.is_admin() and store.owner and store.owner.parent_id == current_user.id)
    if not (current_user.is_super_admin() or is_owner or is_managed_by_admin):
        flash('Bạn không có quyền chỉnh sửa cửa hàng này.', 'danger')
        return redirect(url_for('stores.manage'))

    form = StoreForm(obj=store)
    
    # Logic gán người dùng
    if current_user.is_super_admin() or current_user.is_admin():
        if current_user.is_super_admin():
            assignable_users = AppUser.query.filter(AppUser.role.in_(['user', 'admin'])).order_by(AppUser.username).all()
        else: # is_admin
            assignable_users = [current_user] + current_user.children.order_by(AppUser.username).all()
        form.user_id.choices = [(u.id, u.username) for u in assignable_users]
    else:
        del form.user_id

    # Xử lý khi form hợp lệ
    if form.validate_on_submit():
        store.name = form.name.data
        store.store_url = form.store_url.data
        store.consumer_key = form.consumer_key.data
        store.consumer_secret = form.consumer_secret.data
        store.note = form.note.data
        if (current_user.is_super_admin() or current_user.is_admin()) and 'user_id' in form:
            store.user_id = form.user_id.data
        db.session.commit()
        flash(f'Đã cập nhật cửa hàng "{store.name}" thành công!', 'success')
        return redirect(url_for('stores.manage'))

    if 'user_id' in form:
        form.user_id.data = store.user_id
        
    return render_template('stores/add_edit_store.html', title='Chỉnh sửa Cửa hàng', form=form, store_id=store_id)

@stores_bp.route('/delete/<int:store_id>', methods=['POST'])
@login_required
def delete(store_id):
    """Xóa cửa hàng."""
    store = WooCommerceStore.query.get_or_404(store_id)
    
    # Kiểm tra quyền
    is_owner = (store.user_id == current_user.id)
    is_managed_by_admin = (current_user.is_admin() and store.owner and store.owner.parent_id == current_user.id)
    if not (current_user.is_super_admin() or is_owner or is_managed_by_admin):
        flash('Bạn không có quyền xóa cửa hàng này.', 'danger')
        return redirect(url_for('stores.manage'))
    
    store_name = store.name
    db.session.delete(store)
    db.session.commit()
    flash(f'Đã xóa cửa hàng "{store_name}" thành công.', 'success')
    return redirect(url_for('stores.manage'))

@stores_bp.route('/fetch/<int:store_id>', methods=['POST'])
@login_required
def fetch_orders(store_id):
    """Gửi yêu cầu lấy đơn hàng mới cho một cửa hàng."""
    store = WooCommerceStore.query.get_or_404(store_id)

    # Kiểm tra quyền
    is_owner = (store.user_id == current_user.id)
    is_managed_by_admin = (current_user.is_admin() and store.owner and store.owner.parent_id == current_user.id)
    if not (current_user.is_super_admin() or is_owner or is_managed_by_admin):
        flash('Bạn không có quyền thực hiện hành động này.', 'danger')
        return redirect(url_for('stores.manage'))

    try:
        check_single_store(store.id)
        flash(f'Đã gửi yêu cầu lấy dữ liệu cho cửa hàng "{store.name}". Quá trình có thể mất vài phút.', 'info')
    except Exception as e:
        flash(f'Có lỗi xảy ra khi lấy dữ liệu cho cửa hàng "{store.name}": {e}', 'danger')
        
    return redirect(url_for('stores.manage'))

@stores_bp.route('/sync-history/<int:store_id>', methods=['POST'])
@login_required
def sync_history(store_id):
    """Bắt đầu tác vụ nền để đồng bộ toàn bộ lịch sử đơn hàng."""
    store = WooCommerceStore.query.get_or_404(store_id)

    # Kiểm tra quyền
    is_owner = (store.user_id == current_user.id)
    is_managed_by_admin = (current_user.is_admin() and store.owner and store.owner.parent_id == current_user.id)
    if not (current_user.is_super_admin() or is_owner or is_managed_by_admin):
        flash('Bạn không có quyền thực hiện hành động này.', 'danger')
        return redirect(url_for('stores.manage'))

    job_id = str(uuid.uuid4())
    new_task = BackgroundTask(job_id=job_id, name=f"Đồng bộ lịch sử: {store.name}", user_id=current_user.id, status='queued')
    db.session.add(new_task)
    db.session.commit()

    # Lấy đối tượng app hiện tại để truyền vào thread
    app = current_app._get_current_object()
    executor.submit(sync_history_for_store, app, store.id, job_id)
    
    flash(f'Đã bắt đầu tác vụ đồng bộ lịch sử cho "{store.name}". Xem tiến trình ở tab "Tiến trình".', 'success')
    return redirect(url_for('stores.manage'))