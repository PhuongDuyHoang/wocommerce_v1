# app/services/__init__.py

from app.models import AppUser, WooCommerceStore, WooCommerceOrder
from sqlalchemy import func
from app import db
from datetime import datetime, timedelta, timezone
import json

def get_visible_user_ids(current_user):
    if current_user.is_super_admin():
        user_ids = [user.id for user in AppUser.query.with_entities(AppUser.id).all()]
    elif current_user.is_admin():
        child_ids = [child.id for child in current_user.children.with_entities(AppUser.id).all()]
        user_ids = [current_user.id] + child_ids
    else:
        user_ids = [current_user.id]
    return user_ids

def get_visible_stores_query(current_user):
    if current_user.is_super_admin():
        return WooCommerceStore.query
    visible_ids = get_visible_user_ids(current_user)
    return WooCommerceStore.query.filter(WooCommerceStore.user_id.in_(visible_ids))

def can_user_modify_store(user, store):
    if not user or not store:
        return False
    if user.is_super_admin():
        return True
    if user.id == store.user_id:
        return True
    if user.is_admin() and store.owner and store.owner.parent_id == user.id:
        return True
    return False

def get_visible_orders_query(current_user):
    if current_user.is_super_admin():
        return WooCommerceOrder.query
    visible_stores_query = get_visible_stores_query(current_user).with_entities(WooCommerceStore.id)
    visible_store_ids = [item.id for item in visible_stores_query.all()]
    if not visible_store_ids:
        return WooCommerceOrder.query.filter(db.false())
    return WooCommerceOrder.query.filter(WooCommerceOrder.store_id.in_(visible_store_ids))

def get_dashboard_statistics(current_user, start_date=None, end_date=None):
    orders_query = get_visible_orders_query(current_user)
    stores_query = get_visible_stores_query(current_user)

    if start_date:
        orders_query = orders_query.filter(WooCommerceOrder.order_created_at >= start_date)
    if end_date:
        end_date_inclusive = datetime.strptime(end_date, '%Y-%m-%d').date() + timedelta(days=1)
        orders_query = orders_query.filter(WooCommerceOrder.order_created_at < end_date_inclusive)

    total_revenue = orders_query.with_entities(func.sum(WooCommerceOrder.total)).scalar() or 0
    total_orders = orders_query.count()
    total_stores = stores_query.count()
    
    time_24h_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    new_orders_24h = get_visible_orders_query(current_user).filter(WooCommerceOrder.order_created_at >= time_24h_ago).count()

    top_stores_query = orders_query.join(WooCommerceStore)\
        .with_entities(WooCommerceStore.name, func.sum(WooCommerceOrder.total).label('revenue'))\
        .group_by(WooCommerceStore.name)\
        .order_by(func.sum(WooCommerceOrder.total).desc())\
        .limit(5)
    top_stores = top_stores_query.all()

    # === START: SỬA LỖI MÚI GIỜ & TỐI ƯU TRUY VẤN BIỂU ĐỒ ===
    base_chart_query = get_visible_orders_query(current_user)
    today_utc = datetime.now(timezone.utc).date()
    seven_days_ago_utc = today_utc - timedelta(days=6)

    # Truy vấn một lần duy nhất để lấy doanh thu của 7 ngày gần nhất
    revenue_by_day_result = base_chart_query \
        .filter(WooCommerceOrder.order_created_at >= seven_days_ago_utc) \
        .with_entities(
            func.date_trunc('day', WooCommerceOrder.order_created_at).label('order_day'),
            func.sum(WooCommerceOrder.total)
        ) \
        .group_by('order_day').all()

    # Tạo một từ điển để tra cứu doanh thu theo ngày
    revenue_map = {result.order_day.date(): result[1] for result in revenue_by_day_result}
    
    chart_labels = []
    chart_data = []
    for i in range(6, -1, -1):
        day = today_utc - timedelta(days=i)
        daily_revenue = revenue_map.get(day, 0) # Lấy doanh thu từ map, mặc định là 0
            
        chart_labels.append(day.strftime('%d-%m'))
        chart_data.append(round(float(daily_revenue), 2))
    # === END: SỬA LỖI MÚI GIỜ & TỐI ƯU TRUY VẤN BIỂU ĐỒ ===

    return {
        "total_revenue": f"${total_revenue:,.2f}",
        "total_orders": total_orders,
        "total_stores": total_stores,
        "new_orders_24h": new_orders_24h,
        "top_stores": top_stores,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data)
    }