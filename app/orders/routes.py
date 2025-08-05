# app/orders/routes.py

from flask import render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_ # <<< Thêm import or_
from . import orders_bp
from app import db
from app.models import WooCommerceOrder, WooCommerceStore, AppUser, Setting, OrderLineItem # <<< Thêm OrderLineItem
from app.decorators import can_view_orders_required
import json
from datetime import datetime

@orders_bp.route('/')
@login_required
@can_view_orders_required
def manage_all_orders():
    """Hiển thị trang quản lý tất cả đơn hàng với bộ lọc và phân trang."""
    page = request.args.get('page', 1, type=int)
    per_page = 30 # <<< Giảm số lượng mỗi trang xuống 30 theo yêu cầu trước

    search_query = request.args.get('search_query', '').strip()
    selected_store_id = request.args.get('store_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    query = WooCommerceOrder.query.options(
        db.selectinload(WooCommerceOrder.line_items),
        db.joinedload(WooCommerceOrder.store).joinedload(WooCommerceStore.owner)
    )

    accessible_store_ids = []
    stores_for_filter_query = WooCommerceStore.query
    if current_user.is_super_admin():
        pass
    elif current_user.is_admin():
        managed_user_ids = [user.id for user in current_user.children]
        managed_user_ids.append(current_user.id)
        stores_for_filter_query = stores_for_filter_query.filter(WooCommerceStore.user_id.in_(managed_user_ids))
        accessible_store_ids = [store.id for store in stores_for_filter_query.all()]
        query = query.filter(WooCommerceOrder.store_id.in_(accessible_store_ids))
    else:
        stores_for_filter_query = stores_for_filter_query.filter_by(user_id=current_user.id)
        accessible_store_ids = [store.id for store in stores_for_filter_query.all()]
        query = query.filter(WooCommerceOrder.store_id.in_(accessible_store_ids))

    # ### LOGIC TÌM KIẾM MỚI, MẠNH MẼ HƠN ###
    if search_query:
        search_term = f"%{search_query}%"
        # Join với bảng sản phẩm để có thể tìm kiếm theo tên sản phẩm, sku...
        query = query.join(OrderLineItem)

        # Tạo một danh sách các điều kiện tìm kiếm
        conditions = [
            WooCommerceOrder.customer_name.ilike(search_term),
            WooCommerceOrder.billing_phone.ilike(search_term),
            WooCommerceOrder.billing_email.ilike(search_term),
            OrderLineItem.product_name.ilike(search_term),
            OrderLineItem.sku.ilike(search_term),
            OrderLineItem.var1.ilike(search_term),
            OrderLineItem.var2.ilike(search_term),
            OrderLineItem.var3.ilike(search_term),
            OrderLineItem.var4.ilike(search_term),
            OrderLineItem.var5.ilike(search_term),
            OrderLineItem.var6.ilike(search_term),
        ]
        # Nếu người dùng nhập số, tìm cả theo Mã ĐH
        if search_query.isdigit():
            conditions.append(WooCommerceOrder.wc_order_id == int(search_query))
        
        # Áp dụng tất cả các điều kiện bằng OR và loại bỏ các kết quả trùng lặp
        query = query.filter(or_(*conditions)).distinct()
    # ###########################################
    
    if selected_store_id:
        query = query.filter(WooCommerceOrder.store_id == selected_store_id)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(WooCommerceOrder.order_created_at >= start_date)
        except ValueError: pass 

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(WooCommerceOrder.order_created_at <= end_date)
        except ValueError: pass

    query = query.order_by(WooCommerceOrder.order_created_at.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
    orders = pagination.items
    
    columns_config_setting = Setting.query.get('ORDER_TABLE_COLUMNS')
    if columns_config_setting and columns_config_setting.value:
        try:
            columns_config = json.loads(columns_config_setting.value)
        except json.JSONDecodeError: columns_config = []
    else:
        columns_config = []

    for order in orders:
        order.store_name = order.store.name if order.store else 'N/A'
        order.owner_username = order.store.owner.username if order.store and order.store.owner else 'Chưa gán'
        order.products = order.line_items.all()

    stores_for_filter = stores_for_filter_query.order_by(WooCommerceStore.name).all()

    return render_template(
        'orders/manage_orders.html',
        title='Quản lý Đơn hàng',
        orders=orders,
        pagination=pagination,
        stores_for_filter=stores_for_filter,
        search_query=search_query,
        selected_store_id=selected_store_id,
        start_date=start_date_str,
        end_date=end_date_str,
        columns_config=columns_config
    )