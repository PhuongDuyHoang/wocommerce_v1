# app/orders/routes.py

from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from . import orders_bp
from app.models import WooCommerceOrder, WooCommerceStore, Setting, OrderLineItem
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
    search_query = request.args.get('search_query', '').strip()
    selected_store_id = request.args.get('store_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    base_query = get_visible_orders_query(current_user)

    if search_query:
        search_conditions = [
            WooCommerceOrder.customer_name.ilike(f'%{search_query}%'),
            WooCommerceOrder.billing_phone.ilike(f'%{search_query}%'),
            WooCommerceOrder.billing_email.ilike(f'%{search_query}%'),
            OrderLineItem.product_name.ilike(f'%{search_query}%'),
            OrderLineItem.sku.ilike(f'%{search_query}%'),
            OrderLineItem.variations.ilike(f'%{search_query}%')
        ]
        if search_query.isdigit():
            search_conditions.append(WooCommerceOrder.wc_order_id == int(search_query))
        
        base_query = base_query.join(WooCommerceOrder.line_items).filter(or_(*search_conditions)).distinct()

    if selected_store_id:
        base_query = base_query.filter(WooCommerceOrder.store_id == selected_store_id)

    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        base_query = base_query.filter(WooCommerceOrder.order_created_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        base_query = base_query.filter(WooCommerceOrder.order_created_at <= end_date)

    # --- MODIFIED: Implemented a two-step query to fix the eager loading issue ---

    # Step 1: Paginate on a query that only selects the IDs of the parent objects.
    # This query can have complex joins and distinct clauses.
    paginated_id_query = base_query.with_entities(WooCommerceOrder.id).order_by(WooCommerceOrder.order_created_at.desc())
    pagination = paginated_id_query.paginate(page=page, per_page=30, error_out=False)
    order_ids_for_page = [item.id for item in pagination.items]

    # Step 2: Fetch the full objects for the IDs on the current page.
    # This "clean" query can now safely use eager loading options.
    if order_ids_for_page:
        orders = WooCommerceOrder.query.filter(WooCommerceOrder.id.in_(order_ids_for_page))\
            .options(
                db.selectinload(WooCommerceOrder.line_items),
                db.joinedload(WooCommerceOrder.store)
            )\
            .order_by(WooCommerceOrder.order_created_at.desc())\
            .all()
    else:
        orders = []

    # --- End of modification ---

    for order in orders:
        order.owner_username = order.store.owner.username if order.store and order.store.owner else "Chưa gán"

    stores_for_filter = get_visible_stores_query(current_user).order_by(WooCommerceStore.name).all()

    columns_config_setting = Setting.query.get('ORDER_TABLE_COLUMNS')
    columns_config = json.loads(columns_config_setting.value) if columns_config_setting else []

    return render_template(
        'orders/manage_orders.html',
        title='Quản lý Đơn hàng',
        orders=orders,
        pagination=pagination,
        search_query=search_query,
        selected_store_id=selected_store_id,
        start_date=start_date_str,
        end_date=end_date_str,
        stores_for_filter=stores_for_filter,
        columns_config=columns_config
    )