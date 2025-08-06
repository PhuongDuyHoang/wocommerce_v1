# app/orders/routes.py

from flask import render_template, request, jsonify
from flask_login import login_required, current_user
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

    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(WooCommerceOrder.order_created_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        query = query.filter(WooCommerceOrder.order_created_at <= end_date)

    # === DÒNG CODE ĐÃ ĐƯỢC SỬA ===
    # Thay vì paginate(page, per_page, ...), chúng ta dùng paginate(page=page, per_page=per_page, ...)
    pagination = query.order_by(WooCommerceOrder.order_created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    # === KẾT THÚC SỬA LỖI ===

    orders_with_owner = []
    for row in pagination.items:
        order = row.WooCommerceOrder
        order.owner_username = row.owner_username or 'Chưa gán'
        orders_with_owner.append(order)

    stores_for_filter = get_visible_stores_query(current_user).order_by(WooCommerceStore.name).all()

    try:
        columns_config_json = Setting.get_value('ORDER_TABLE_COLUMNS', '[]')
        if not columns_config_json:
            columns_config_json = '[]'
        columns_config = json.loads(columns_config_json)
    except (json.JSONDecodeError, TypeError):
        columns_config = []
    
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
        columns_config=columns_config
    )

@orders_bp.route('/update_note/<int:order_id>', methods=['POST'])
@login_required
def update_note(order_id):
    """API endpoint để cập nhật ghi chú cho một đơn hàng."""
    try:
        order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
        
        data = request.get_json()
        if 'note' in data:
            order.note = data['note']
            db.session.commit()
            return jsonify({'success': True, 'message': 'Ghi chú đã được cập nhật.'})
        return jsonify({'success': False, 'message': 'Dữ liệu không hợp lệ.'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

