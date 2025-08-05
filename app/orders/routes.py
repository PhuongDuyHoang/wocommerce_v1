# app/orders/routes.py

from flask import render_template, request
from flask_login import current_user, login_required
from . import orders_bp
from app import db
from app.models import WooCommerceOrder, WooCommerceStore, AppUser, Setting # <<< Thêm Setting
from app.decorators import can_view_orders_required
import json
from datetime import datetime

@orders_bp.route('/')
@login_required
@can_view_orders_required
def manage_all_orders():
    """Hiển thị trang quản lý tất cả đơn hàng với bộ lọc và phân trang."""
    page = request.args.get('page', 1, type=int)
    per_page = 50 

    search_query = request.args.get('search_query', '').strip()
    selected_store_id = request.args.get('store_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    query = WooCommerceOrder.query.join(WooCommerceStore).join(AppUser)

    accessible_store_ids = []
    # Super Admin có thể xem tất cả store, trừ khi có bộ lọc được áp dụng
    stores_for_filter_query = WooCommerceStore.query
    if current_user.is_super_admin():
        pass
    elif current_user.is_admin():
        managed_user_ids = [user.id for user in current_user.children]
        managed_user_ids.append(current_user.id)
        stores_for_filter_query = stores_for_filter_query.filter(WooCommerceStore.user_id.in_(managed_user_ids))
        accessible_store_ids = [store.id for store in stores_for_filter_query.all()]
        query = query.filter(WooCommerceOrder.store_id.in_(accessible_store_ids))
    else: # User thường
        stores_for_filter_query = stores_for_filter_query.filter_by(user_id=current_user.id)
        accessible_store_ids = [store.id for store in stores_for_filter_query.all()]
        query = query.filter(WooCommerceOrder.store_id.in_(accessible_store_ids))

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(db.or_(WooCommerceOrder.wc_order_id.like(search_term), WooCommerceOrder.customer_name.ilike(search_term)))
    
    if selected_store_id:
        query = query.filter(WooCommerceOrder.store_id == selected_store_id)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(WooCommerceOrder.order_created_at >= start_date)
        except ValueError:
            pass 

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(WooCommerceOrder.order_created_at <= end_date)
        except ValueError:
            pass

    query = query.order_by(WooCommerceOrder.order_created_at.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
    orders = pagination.items
    
    # ### PHẦN BỔ SUNG: TẢI CẤU HÌNH CỘT TỪ DATABASE ###
    columns_config_setting = Setting.query.get('ORDER_TABLE_COLUMNS')
    if columns_config_setting and columns_config_setting.value:
        try:
            columns_config = json.loads(columns_config_setting.value)
        except json.JSONDecodeError:
            columns_config = [] # Fallback nếu JSON lỗi
    else:
        columns_config = [] # Fallback nếu chưa có setting
    # #######################################################

    # Bổ sung các thuộc tính cần thiết vào đối tượng order để template dễ xử lý
    for order in orders:
        # Xử lý JSON sản phẩm
        if order.products_json:
            try:
                order.products = json.loads(order.products_json)
            except json.JSONDecodeError:
                order.products = []
        else:
            order.products = []
        
        # Thêm các thuộc tính phẳng để template dễ truy cập
        order.store_name = order.store.name if order.store else 'N/A'
        order.owner_username = order.store.owner.username if order.store and order.store.owner else 'Chưa gán'


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
        columns_config=columns_config # <<< Gửi cấu hình cột ra template
    )