# app/services/__init__.py

# === START: SỬA LỖI - Thay đổi đường dẫn import ===
from app.models import AppUser, WooCommerceStore, WooCommerceOrder
# === END: SỬA LỖI ===
from sqlalchemy import func
from app import db
from datetime import datetime, timedelta
import json

def get_visible_user_ids(current_user):
    """
    Trả về một danh sách các ID người dùng mà current_user có quyền xem.
    """
    if current_user.is_super_admin():
        # Super admin thấy tất cả user
        user_ids = [user.id for user in AppUser.query.with_entities(AppUser.id).all()]
    elif current_user.is_admin():
        # Admin thấy chính họ và các user con của họ
        child_ids = [child.id for child in current_user.children.with_entities(AppUser.id).all()]
        user_ids = [current_user.id] + child_ids
    else:
        # User thường chỉ thấy chính họ
        user_ids = [current_user.id]
    return user_ids

def get_visible_stores_query(current_user):
    """
    Trả về một SQLAlchemy query object cho WooCommerceStore đã được lọc theo quyền.
    """
    if current_user.is_super_admin():
        # Super admin thấy tất cả cửa hàng
        return WooCommerceStore.query
    
    # Lấy danh sách ID user mà người dùng hiện tại được phép xem
    visible_ids = get_visible_user_ids(current_user)
    return WooCommerceStore.query.filter(WooCommerceStore.user_id.in_(visible_ids))

def can_user_modify_store(user, store):
    """
    Kiểm tra xem một user có quyền sửa/xóa/tương tác với một store cụ thể không.
    """
    if not user or not store:
        return False
    # Super admin có toàn quyền
    if user.is_super_admin():
        return True
    # User là chủ sở hữu của cửa hàng
    if user.id == store.user_id:
        return True
    # User là admin và cửa hàng này thuộc về một user con của admin đó
    if user.is_admin() and store.owner and store.owner.parent_id == user.id:
        return True
    return False

def get_visible_orders_query(current_user):
    """
    Trả về một SQLAlchemy query object cho WooCommerceOrder đã được lọc theo quyền.
    """
    if current_user.is_super_admin():
        # Super admin thấy tất cả đơn hàng
        return WooCommerceOrder.query

    # Lấy query cho các cửa hàng mà người dùng được phép xem
    visible_stores_query = get_visible_stores_query(current_user).with_entities(WooCommerceStore.id)
    visible_store_ids = [item.id for item in visible_stores_query.all()]

    # Nếu không có cửa hàng nào để xem, trả về một query rỗng
    if not visible_store_ids:
        return WooCommerceOrder.query.filter(db.false())
    
    # Lọc đơn hàng dựa trên store_id
    return WooCommerceOrder.query.filter(WooCommerceOrder.store_id.in_(visible_store_ids))

def get_dashboard_statistics(current_user, start_date=None, end_date=None):
    """
    Tính toán tất cả các số liệu thống kê cho trang Dashboard dựa trên quyền hạn.
    """
    # Lấy các truy vấn cơ sở đã được lọc theo quyền
    orders_query = get_visible_orders_query(current_user)
    stores_query = get_visible_stores_query(current_user)

    # Áp dụng bộ lọc ngày tháng nếu có
    if start_date:
        orders_query = orders_query.filter(WooCommerceOrder.order_created_at >= start_date)
    if end_date:
        # Thêm một ngày để bao gồm cả ngày kết thúc
        end_date_inclusive = end_date + timedelta(days=1)
        orders_query = orders_query.filter(WooCommerceOrder.order_created_at < end_date_inclusive)

    # 1. Tổng doanh thu
    total_revenue = orders_query.with_entities(func.sum(WooCommerceOrder.total)).scalar() or 0

    # 2. Tổng số đơn hàng
    total_orders = orders_query.count()

    # 3. Tổng số cửa hàng (không bị ảnh hưởng bởi bộ lọc ngày)
    total_stores = stores_query.count()

    # 4. Đơn hàng mới trong 24h (không bị ảnh hưởng bởi bộ lọc ngày)
    time_24h_ago = datetime.utcnow() - timedelta(hours=24)
    new_orders_24h = get_visible_orders_query(current_user).filter(WooCommerceOrder.order_created_at >= time_24h_ago).count()

    # 5. Top cửa hàng theo doanh thu
    top_stores_query = orders_query.join(WooCommerceStore)\
        .with_entities(WooCommerceStore.name, func.sum(WooCommerceOrder.total).label('revenue'))\
        .group_by(WooCommerceStore.name)\
        .order_by(func.sum(WooCommerceOrder.total).desc())\
        .limit(5)
    top_stores = top_stores_query.all()

    # 6. Dữ liệu biểu đồ doanh thu 7 ngày gần nhất (không bị ảnh hưởng bởi bộ lọc ngày)
    chart_labels = []
    chart_data = []
    base_chart_query = get_visible_orders_query(current_user)
    today = datetime.utcnow().date()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        
        daily_revenue = base_chart_query\
            .filter(WooCommerceOrder.order_created_at >= day_start)\
            .filter(WooCommerceOrder.order_created_at < day_end)\
            .with_entities(func.sum(WooCommerceOrder.total).label('daily_total'))\
            .scalar() or 0
            
        chart_labels.append(day.strftime('%d-%m'))
        chart_data.append(round(daily_revenue, 2))

    return {
        "total_revenue": f"${total_revenue:,.2f}",
        "total_orders": total_orders,
        "total_stores": total_stores,
        "new_orders_24h": new_orders_24h,
        "top_stores": top_stores,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data)
    }