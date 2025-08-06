# app/stores/routes.py

from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from woocommerce import API
import requests
import json
from datetime import datetime, timezone # Thêm import này

from . import stores_bp
from .forms import StoreForm
from app import db
from app import worker
from app.models import WooCommerceStore, AppUser, BackgroundTask
from app.decorators import can_add_store_required
from app.services import get_visible_stores_query, get_visible_user_ids, can_user_modify_store
import uuid

def _check_woo_connection(url, key, secret):
    """
    Hàm helper để kiểm tra kết nối đến WooCommerce API.
    """
    if not url or not key or not secret:
        return False, "URL, Consumer Key, và Consumer Secret không được để trống."
    try:
        wcapi = API(
            url=url,
            consumer_key=key,
            consumer_secret=secret,
            version="wc/v3",
            timeout=20
        )
        response = wcapi.get("system_status")
        
        try:
            response_data = response.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
            return False, f"Kết nối thành công (Mã: {response.status_code}) nhưng phản hồi không phải là JSON hợp lệ. Vui lòng kiểm tra các plugin bảo mật hoặc caching."

        if response.status_code == 200 and 'environment' in response_data:
             return True, "Kết nối thành công! API WooCommerce hoạt động bình thường."
        elif 'message' in response_data:
            return False, f"Lỗi từ WooCommerce (Mã: {response.status_code}): {response_data['message']}"
        else:
            return False, f"Phản hồi API không hợp lệ (Mã: {response.status_code}). Vui lòng kiểm tra các plugin bảo mật hoặc cấu hình REST API."

    except requests.exceptions.SSLError:
        return False, "Lỗi SSL. Vui lòng kiểm tra chứng chỉ SSL của website hoặc thử với http:// thay vì https://."
    except requests.exceptions.RequestException as e:
        return False, f"Lỗi kết nối mạng. Vui lòng kiểm tra lại URL hoặc cài đặt tường lửa. Chi tiết: {e}"
    except Exception as e:
        return False, f"Lỗi không mong muốn: {str(e)}"

@stores_bp.route('/')
@login_required
def manage():
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

        # === PHẦN ĐƯỢC THÊM VÀO ĐỂ SỬA LỖI ===
        # Đặt mốc thời gian ban đầu để chỉ lấy các đơn hàng mới từ bây giờ.
        new_store.last_notified_order_timestamp = datetime.now(timezone.utc)
        # === KẾT THÚC PHẦN SỬA LỖI ===

        if 'user_id' in form and form.user_id.data > 0:
            new_store.user_id = form.user_id.data
        elif 'user_id' not in form or form.user_id.data == 0:
             if not current_user.is_super_admin():
                new_store.user_id = current_user.id
        
        db.session.add(new_store)
        db.session.commit()
        worker.add_or_update_store_job(current_app._get_current_object(), new_store.id)
        flash(f'Đã thêm cửa hàng "{new_store.name}" thành công! Hệ thống sẽ chỉ thông báo cho các đơn hàng mới kể từ bây giờ.', 'success')
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
        worker.add_or_update_store_job(current_app._get_current_object(), store.id)
        flash(f'Đã cập nhật cửa hàng "{store.name}"!', 'success')
        return redirect(url_for('stores.manage'))
        
    if 'user_id' in form:
        form.user_id.data = store.user_id or 0

    return render_template('stores/add_edit_store.html', title=f'Sửa: {store.name}', form=form, store=store)


@stores_bp.route('/delete/<int:store_id>', methods=['POST'])
@login_required
def delete(store_id):
    store = WooCommerceStore.query.get_or_404(store_id)
    if not can_user_modify_store(current_user, store):
        flash('Bạn không có quyền xóa cửa hàng này.', 'danger')
        return redirect(url_for('stores.manage'))
    worker.remove_store_job(store_id)
    db.session.delete(store)
    db.session.commit()
    flash(f'Đã xóa cửa hàng "{store.name}".', 'success')
    return redirect(url_for('stores.manage'))


@stores_bp.route('/fetch/<int:store_id>', methods=['POST'])
@login_required
def fetch_orders(store_id):
    store = WooCommerceStore.query.get_or_404(store_id)
    if not can_user_modify_store(current_user, store):
        flash('Bạn không có quyền thực hiện hành động này.', 'danger')
        return redirect(url_for('stores.manage'))
    try:
        worker.check_single_store_job(current_app._get_current_object(), store_id)
        flash(f'Đã yêu cầu kiểm tra đơn hàng mới cho "{store.name}".', 'info')
    except Exception as e:
        flash(f'Lỗi khi kiểm tra đơn hàng: {e}', 'danger')
    return redirect(url_for('stores.manage'))


@stores_bp.route('/sync-history/<int:store_id>', methods=['POST'])
@login_required
def sync_history(store_id):
    store = WooCommerceStore.query.get_or_404(store_id)
    if not can_user_modify_store(current_user, store):
        flash('Bạn không có quyền thực hiện hành động này.', 'danger')
        return redirect(url_for('stores.manage'))

    job_id = str(uuid.uuid4())
    new_task = BackgroundTask(
        job_id=job_id, name=f"Đồng bộ lịch sử cho: {store.name}", user_id=current_user.id
    )
    db.session.add(new_task)
    db.session.commit()
    worker.executor.submit(worker.sync_history_for_store, current_app._get_current_object(), store_id, job_id)
    flash(f'Đã bắt đầu tác vụ đồng bộ lịch sử cho "{store.name}".', 'success')
    return redirect(url_for('jobs.view'))

@stores_bp.route('/check_connection', methods=['POST'])
@login_required
def check_connection():
    data = request.get_json()
    url = data.get('store_url')
    key = data.get('consumer_key')
    secret = data.get('consumer_secret')
    
    success, message = _check_woo_connection(url, key, secret)
    
    return jsonify({'success': success, 'message': message})