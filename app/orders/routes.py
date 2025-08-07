# app/orders/routes.py

from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from woocommerce import API

from . import orders_bp
from app.models import WooCommerceOrder, WooCommerceStore, Setting, OrderLineItem, AppUser
from app.decorators import can_view_orders_required
from sqlalchemy import or_, func
from app import db
import json
from datetime import datetime

from app.services import get_visible_orders_query, get_visible_stores_query

@orders_bp.route('/')
@login_required
@can_view_orders_required
def manage_all_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search_query = request.args.get('search_query', '').strip()
    selected_store_id = request.args.get('store_id', type=int)
    selected_status = request.args.get('status', '')
    # === THÊM MỚI: Lấy tham số lọc theo người dùng ===
    selected_admin_id = request.args.get('admin_id', type=int)
    selected_user_id = request.args.get('user_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    base_query = get_visible_orders_query(current_user)\
        .join(WooCommerceStore, WooCommerceOrder.store_id == WooCommerceStore.id)\
        .outerjoin(AppUser, WooCommerceStore.user_id == AppUser.id)\
        .add_columns(
            WooCommerceOrder,
            AppUser.username.label('owner_username')
        )
    
    query = base_query

    # === THÊM MỚI: Logic lấy danh sách người dùng cho bộ lọc ===
    admins_for_filter = []
    users_for_filter = []
    if current_user.is_super_admin():
        admins_for_filter = AppUser.query.filter(AppUser.role.in_(['admin', 'super_admin'])).order_by(AppUser.username).all()
        if selected_admin_id:
            admin_owner = AppUser.query.get(selected_admin_id)
            if admin_owner:
                users_for_filter = admin_owner.children.order_by(AppUser.username).all()
    elif current_user.is_admin():
        users_for_filter = current_user.children.order_by(AppUser.username).all()
    
    # === THÊM MỚI: Áp dụng bộ lọc theo người dùng vào câu truy vấn ===
    if selected_user_id:
        # Nếu một user cụ thể được chọn, lọc theo user đó
        query = query.filter(WooCommerceStore.user_id == selected_user_id)
    elif selected_admin_id:
        # Nếu một admin được chọn (và không có user cụ thể), lọc theo tất cả user con của admin đó
        admin_owner = AppUser.query.get(selected_admin_id)
        if admin_owner:
            child_ids = [child.id for child in admin_owner.children]
            # Super Admin có thể xem cả đơn của chính Admin đó
            if admin_owner.is_super_admin() or admin_owner.is_admin():
                 child_ids.append(admin_owner.id)
            query = query.filter(WooCommerceStore.user_id.in_(child_ids))

    if search_query:
        search_conditions = [
            WooCommerceOrder.customer_name.ilike(f'%{search_query}%'),
            WooCommerceOrder.billing_phone.ilike(f'%{search_query}%'),
            WooCommerceOrder.billing_email.ilike(f'%{search_query}%'),
            OrderLineItem.product_name.ilike(f'%{search_query}%'),
            OrderLineItem.sku.ilike(f'%{search_query}%')
        ]
        try:
            order_id_num = int(search_query)
            search_conditions.append(WooCommerceOrder.wc_order_id == order_id_num)
        except ValueError:
            pass
        
        query = query.join(WooCommerceOrder.line_items).filter(or_(*search_conditions))

    if selected_store_id:
        query = query.filter(WooCommerceOrder.store_id == selected_store_id)

    if selected_status:
        query = query.filter(WooCommerceOrder.status == selected_status)

    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(WooCommerceOrder.order_created_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        query = query.filter(WooCommerceOrder.order_created_at <= end_date)

    pagination = query.order_by(WooCommerceOrder.order_created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    orders_with_owner = []
    for row in pagination.items:
        order = row.WooCommerceOrder
        order.owner_username = row.owner_username or 'Chưa gán'
        orders_with_owner.append(order)

    stores_for_filter = get_visible_stores_query(current_user).order_by(WooCommerceStore.name).all()

    try:
        columns_config_json = Setting.get_value('ORDER_TABLE_COLUMNS', '[]')
        columns_config = json.loads(columns_config_json or '[]')
    except (json.JSONDecodeError, TypeError):
        columns_config = []
    
    statuses = [
        ('pending', 'Chờ thanh toán'), ('processing', 'Đang xử lý'),
        ('on-hold', 'Tạm giữ'), ('completed', 'Hoàn thành'),
        ('cancelled', 'Đã hủy'), ('refunded', 'Đã hoàn tiền'),
        ('failed', 'Thất bại')
    ]
    
    return render_template(
        'orders/manage_orders.html',
        title='Quản lý Đơn hàng',
        orders=orders_with_owner,
        pagination=pagination,
        search_query=search_query,
        selected_store_id=selected_store_id,
        start_date=start_date_str,
        end_date=end_date_str,
        stores_for_filter=stores_for_filter,
        columns_config=columns_config,
        statuses=statuses,
        selected_status=selected_status,
        # === THÊM MỚI: Truyền các biến mới ra template ===
        admins_for_filter=admins_for_filter,
        users_for_filter=users_for_filter,
        selected_admin_id=selected_admin_id,
        selected_user_id=selected_user_id
    )

@orders_bp.route('/update_note/<int:order_id>', methods=['POST'])
@login_required
def update_note(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    data = request.get_json()
    if 'note' in data:
        order.note = data['note']
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ghi chú đã được cập nhật.'})
    return jsonify({'success': False, 'message': 'Dữ liệu không hợp lệ.'}), 400

@orders_bp.route('/update_status/<int:order_id>', methods=['POST'])
@login_required
def update_status(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    data = request.get_json()
    new_status = data.get('status')

    if not new_status:
        return jsonify({'success': False, 'message': 'Trạng thái mới không được cung cấp.'}), 400

    store = order.store
    if not store:
        return jsonify({'success': False, 'message': 'Không tìm thấy cửa hàng liên kết.'}), 404

    try:
        wcapi = API(
            url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
            version="wc/v3",
            timeout=20
        )
        payload = {"status": new_status}
        response = wcapi.put(f"orders/{order.wc_order_id}", payload)

        if response.status_code == 200:
            order.status = new_status
            db.session.commit()
            return jsonify({'success': True, 'message': 'Cập nhật trạng thái thành công!', 'new_status': new_status})
        else:
            error_message = response.json().get('message', 'Lỗi không xác định từ WooCommerce.')
            return jsonify({'success': False, 'message': error_message}), response.status_code

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Lỗi hệ thống: {str(e)}'}), 500
