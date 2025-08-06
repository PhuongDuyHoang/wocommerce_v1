# app/stores/routes.py

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from . import stores_bp
from .forms import StoreForm
from app import db
# MODIFIED: Import the new helper functions from worker
from app import worker
from app.models import WooCommerceStore, AppUser, BackgroundTask
from app.decorators import can_add_store_required
from app.services import get_visible_stores_query, get_visible_user_ids, can_user_modify_store
import uuid

@stores_bp.route('/')
@login_required
def manage():
    # ... (Nội dung không đổi)
    page = request.args.get('page', 1, type=int)

    base_query = get_visible_stores_query(current_user)
    stores_pagination = base_query.order_by(WooCommerceStore.name).paginate(page=page, per_page=30)
    
    return render_template(
        'stores/manage_stores.html', 
        title='Quản lý Cửa hàng', 
        stores=stores_pagination.items, 
        pagination=stores_pagination
    )

@stores_bp.route('/add', methods=['GET', 'POST'])
@login_required
@can_add_store_required
def add():
    # ... (Nội dung không đổi)
    form = StoreForm()

    if current_user.is_super_admin() or current_user.is_admin():
        visible_ids = get_visible_user_ids(current_user)
        users_for_choices = AppUser.query.filter(AppUser.id.in_(visible_ids)).order_by(AppUser.username).all()
        form.user_id.choices = [(user.id, user.username) for user in users_for_choices]
        form.user_id.choices.insert(0, (0, 'Chưa gán'))
    else:
        if 'user_id' in form:
            del form.user_id

    if form.validate_on_submit():
        new_store = WooCommerceStore(
            name=form.name.data,
            store_url=form.store_url.data,
            consumer_key=form.consumer_key.data,
            consumer_secret=form.consumer_secret.data,
            note=form.note.data,
        )

        if 'user_id' in form and form.user_id.data > 0:
            new_store.user_id = form.user_id.data
        elif 'user_id' not in form or form.user_id.data == 0:
             if not current_user.is_super_admin():
                new_store.user_id = current_user.id

        db.session.add(new_store)
        db.session.commit()
        
        # MODIFIED: Add a job for the new store
        worker.add_or_update_store_job(current_app._get_current_object(), new_store.id)
        
        flash(f'Đã thêm cửa hàng "{new_store.name}" thành công!', 'success')
        return redirect(url_for('stores.manage'))
        
    return render_template('stores/add_edit_store.html', title='Thêm Cửa hàng', form=form)


@stores_bp.route('/edit/<int:store_id>', methods=['GET', 'POST'])
@login_required
def edit(store_id):
    store = WooCommerceStore.query.get_or_404(store_id)
    
    if not can_user_modify_store(current_user, store):
        flash('Bạn không có quyền chỉnh sửa cửa hàng này.', 'danger')
        return redirect(url_for('stores.manage'))

    form = StoreForm(obj=store)

    if current_user.is_super_admin() or current_user.is_admin():
        visible_ids = get_visible_user_ids(current_user)
        users_for_choices = AppUser.query.filter(AppUser.id.in_(visible_ids)).order_by(AppUser.username).all()
        form.user_id.choices = [(user.id, user.username) for user in users_for_choices]
        form.user_id.choices.insert(0, (0, 'Chưa gán'))
    else:
        if 'user_id' in form:
            del form.user_id
        
    if form.validate_on_submit():
        form.populate_obj(store)
        if 'user_id' in form and form.user_id.data == 0:
            store.user_id = None
        db.session.commit()

        # MODIFIED: Update the job for the edited store
        worker.add_or_update_store_job(current_app._get_current_object(), store.id)

        flash(f'Đã cập nhật cửa hàng "{store.name}"!', 'success')
        return redirect(url_for('stores.manage'))
        
    if 'user_id' in form:
        form.user_id.data = store.user_id or 0

    return render_template('stores/add_edit_store.html', title=f'Sửa: {store.name}', form=form)


@stores_bp.route('/delete/<int:store_id>', methods=['POST'])
@login_required
def delete(store_id):
    store = WooCommerceStore.query.get_or_404(store_id)
    
    if not can_user_modify_store(current_user, store):
        flash('Bạn không có quyền xóa cửa hàng này.', 'danger')
        return redirect(url_for('stores.manage'))
        
    db.session.delete(store)
    db.session.commit()

    # MODIFIED: Remove the job for the deleted store
    worker.remove_store_job(store_id)

    flash(f'Đã xóa cửa hàng "{store.name}".', 'success')
    return redirect(url_for('stores.manage'))


@stores_bp.route('/fetch/<int:store_id>', methods=['POST'])
@login_required
def fetch_orders(store_id):
    # ... (Nội dung không đổi)
    store = WooCommerceStore.query.get_or_404(store_id)
    
    if not can_user_modify_store(current_user, store):
        flash('Bạn không có quyền thực hiện hành động này.', 'danger')
        return redirect(url_for('stores.manage'))
        
    try:
        # MODIFIED: Run the single job check immediately
        worker.check_single_store_job(current_app._get_current_object(), store_id)
        flash(f'Đã yêu cầu kiểm tra đơn hàng mới cho "{store.name}".', 'info')
    except Exception as e:
        flash(f'Lỗi khi kiểm tra đơn hàng: {e}', 'danger')
        
    return redirect(url_for('stores.manage'))


@stores_bp.route('/sync-history/<int:store_id>', methods=['POST'])
@login_required
def sync_history(store_id):
    # ... (Nội dung không đổi)
    store = WooCommerceStore.query.get_or_404(store_id)
    
    if not can_user_modify_store(current_user, store):
        flash('Bạn không có quyền thực hiện hành động này.', 'danger')
        return redirect(url_for('stores.manage'))

    job_id = str(uuid.uuid4())
    new_task = BackgroundTask(
        job_id=job_id,
        name=f"Đồng bộ lịch sử cho: {store.name}",
        user_id=current_user.id
    )
    db.session.add(new_task)
    db.session.commit()
    
    worker.executor.submit(worker.sync_history_for_store, current_app._get_current_object(), store_id, job_id)
    
    flash(f'Đã bắt đầu tác vụ đồng bộ lịch sử cho "{store.name}".', 'success')
    return redirect(url_for('jobs.view'))