# app/worker.py

import atexit
import asyncio
from datetime import datetime, timezone, timedelta
import json
from woocommerce import API
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from concurrent.futures import ThreadPoolExecutor

from . import db
from .models import WooCommerceStore, WooCommerceOrder, Setting, BackgroundTask # <<< Thêm BackgroundTask
from .notifications import send_telegram_message

scheduler = BackgroundScheduler(daemon=True)
executor = ThreadPoolExecutor(max_workers=5) # Tạo thread pool để chạy tác vụ nền

def format_products_for_notification(products_json: str) -> str:
    """Định dạng danh sách sản phẩm từ JSON thành một chuỗi đẹp mắt cho Telegram."""
    try:
        products = json.loads(products_json)
        if not products:
            return "- Không có sản phẩm."
        
        lines = []
        for product in products:
            name = product.get('name', 'N/A')
            quantity = product.get('quantity', 0)
            lines.append(f"\\- {name} \\(SL: {quantity}\\)")
        return "\n".join(lines)
    except (json.JSONDecodeError, TypeError):
        return "- Lỗi định dạng sản phẩm."

def check_single_store(store_id: int):
    """Lấy các đơn hàng MỚI."""
    app = current_app._get_current_object()
    with app.app_context():
        store = WooCommerceStore.query.get(store_id)
        if not store or not store.is_active:
            print(f"Bỏ qua cửa hàng ID {store_id}.")
            return

        print(f"Bắt đầu kiểm tra đơn hàng MỚI cho: '{store.name}'...")

        try:
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=20)
            params = {'orderby': 'date', 'order': 'asc'}
            if store.last_notified_order_timestamp:
                after_time = store.last_notified_order_timestamp + timedelta(seconds=1)
                params['after'] = after_time.isoformat()

            new_orders_response = wcapi.get("orders", params=params).json()

            if not new_orders_response:
                print(f"Không có đơn hàng mới cho cửa hàng '{store.name}'.")
                store.last_checked = datetime.now(timezone.utc)
                db.session.commit()
                return
            
            latest_order_time = None
            for order_data in new_orders_response:
                exists = WooCommerceOrder.query.filter_by(wc_order_id=order_data['id'], store_id=store.id).first()
                if not exists:
                    products = [{'name': item['name'], 'quantity': item['quantity']} for item in order_data.get('line_items', [])]
                    new_order = WooCommerceOrder(wc_order_id=order_data['id'], store_id=store.id, status=order_data.get('status', 'N/A'), currency=order_data.get('currency', 'N/A'), total=float(order_data.get('total', 0.0)), customer_name=f"{order_data.get('billing', {}).get('first_name', '')} {order_data.get('billing', {}).get('last_name', '')}".strip(), payment_method_title=order_data.get('payment_method_title', 'N/A'), products_json=json.dumps(products, ensure_ascii=False), order_created_at=datetime.fromisoformat(order_data['date_created_gmt']).replace(tzinfo=timezone.utc))
                    db.session.add(new_order)
                    
                    notification_data = {
                        "store_name": store.name, "order_id": new_order.wc_order_id,
                        "customer_name": new_order.customer_name or "Khách lẻ", "total_amount": f"${new_order.total:,.2f}",
                        "currency": new_order.currency, "status": new_order.status,
                        "payment_method": new_order.payment_method_title, "product_list": format_products_for_notification(new_order.products_json)
                    }
                    if store.user_id:
                        asyncio.run(send_telegram_message(message_type='new_order', data=notification_data, user_id=store.user_id))
                    latest_order_time = new_order.order_created_at

            if latest_order_time:
                store.last_notified_order_timestamp = latest_order_time
            store.last_checked = datetime.now(timezone.utc)
            db.session.commit()
            print(f"Hoàn tất xử lý {len(new_orders_response)} đơn hàng mới cho '{store.name}'.")

        except Exception as e:
            print(f"LỖI khi kiểm tra đơn hàng mới cho '{store.name}': {e}")
            db.session.rollback()

# ### HÀM MỚI ĐỂ ĐỒNG BỘ TOÀN BỘ LỊCH SỬ ###
def sync_history_for_store(store_id: int, job_id: str):
    """
    Lấy TOÀN BỘ lịch sử đơn hàng của một cửa hàng, xử lý theo từng trang.
    Không gửi thông báo để tránh spam.
    """
    app = current_app._get_current_object()
    with app.app_context():
        store = WooCommerceStore.query.get(store_id)
        task = BackgroundTask.query.filter_by(job_id=job_id).first()
        if not store or not task:
            return
        
        print(f"Bắt đầu đồng bộ LỊCH SỬ cho '{store.name}' (Job ID: {job_id})")
        task.status = 'running'
        db.session.commit()
        
        try:
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=30)
            page = 1
            total_synced = 0
            while True:
                task = BackgroundTask.query.filter_by(job_id=job_id).first()
                if task.requested_cancellation:
                    task.status = 'cancelled'
                    db.session.commit()
                    print(f"Đã hủy tác vụ đồng bộ lịch sử cho '{store.name}'.")
                    return

                print(f"Đang lấy trang {page} cho '{store.name}'...")
                task.log = f"Đang lấy trang {page}..."
                db.session.commit()

                orders_page = wcapi.get("orders", params={'per_page': 100, 'page': page}).json()
                if not orders_page:
                    break # Dừng lại khi không còn đơn hàng ở trang này

                for order_data in orders_page:
                    exists = WooCommerceOrder.query.filter_by(wc_order_id=order_data['id'], store_id=store.id).first()
                    if not exists:
                        products = [{'name': item['name'], 'quantity': item['quantity']} for item in order_data.get('line_items', [])]
                        history_order = WooCommerceOrder(wc_order_id=order_data['id'], store_id=store.id, status=order_data.get('status', 'N/A'), currency=order_data.get('currency', 'N/A'), total=float(order_data.get('total', 0.0)), customer_name=f"{order_data.get('billing', {}).get('first_name', '')} {order_data.get('billing', {}).get('last_name', '')}".strip(), payment_method_title=order_data.get('payment_method_title', 'N/A'), products_json=json.dumps(products, ensure_ascii=False), order_created_at=datetime.fromisoformat(order_data['date_created_gmt']).replace(tzinfo=timezone.utc))
                        db.session.add(history_order)
                        total_synced += 1
                
                db.session.commit()
                task.progress = total_synced
                db.session.commit()
                page += 1

            task.status = 'complete'
            task.log = f"Đồng bộ hoàn tất! Đã thêm {total_synced} đơn hàng mới."
            db.session.commit()
            print(f"Hoàn tất đồng bộ lịch sử cho '{store.name}'.")

        except Exception as e:
            print(f"LỖI khi đồng bộ lịch sử cho '{store.name}': {e}")
            task.status = 'failed'
            task.log = f"Lỗi: {e}"
            db.session.commit()
            db.session.rollback()

def run_sync_history_in_background(store_id: int, job_id: str):
    """Hàm trung gian để gọi tác vụ đồng bộ trong một thread riêng."""
    app = current_app._get_current_object()
    sync_history_for_store(store_id, job_id)
# ################################################

def check_all_stores_job():
    app = current_app._get_current_object()
    with app.app_context():
        print(f"\n--- Bắt đầu phiên kiểm tra đơn hàng định kỳ [{datetime.now()}] ---")
        active_stores = WooCommerceStore.query.filter_by(is_active=True).all()
        if not active_stores:
            print("Không có cửa hàng nào đang hoạt động để kiểm tra.")
            return

        for store in active_stores:
            try:
                check_single_store(store.id)
            except Exception as e:
                print(f"Lỗi không mong muốn khi gọi check_single_store cho ID {store.id}: {e}")
        
        print(f"--- Hoàn tất phiên kiểm tra định kỳ ---")

def init_scheduler(app):
    global scheduler
    with app.app_context():
        if scheduler.running:
            scheduler.shutdown(wait=False)
        
        scheduler = BackgroundScheduler(daemon=True)

        interval_setting = Setting.query.get('CHECK_INTERVAL_MINUTES')
        check_interval = 5
        if interval_setting and interval_setting.value and interval_setting.value.isdigit():
            check_interval = int(interval_setting.value)
        
        if not scheduler.get_job('main_check_job'):
            scheduler.add_job(func=check_all_stores_job, trigger='interval', minutes=check_interval, id='main_check_job', replace_existing=True)
            scheduler.start()
            print(f"Scheduler đã được khởi tạo và chạy với chu kỳ {check_interval} phút.")
            atexit.register(lambda: scheduler.shutdown())