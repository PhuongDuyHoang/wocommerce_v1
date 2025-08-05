# app/worker.py

import atexit
import asyncio
from datetime import datetime, timezone, timedelta
import json
from woocommerce import API
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from concurrent.futures import ThreadPoolExecutor
import html # Thư viện để xử lý mã HTML
import re   # Thư viện để xử lý biểu thức chính quy (Regular Expression)

from . import db
from .models import WooCommerceStore, WooCommerceOrder, Setting, BackgroundTask, OrderLineItem
from .notifications import send_telegram_message

scheduler = BackgroundScheduler(daemon=True)
executor = ThreadPoolExecutor(max_workers=5)


def _extract_order_details(order_data: dict) -> dict:
    """Hàm phụ trợ để trích xuất và chuẩn hóa toàn bộ chi tiết từ dữ liệu JSON của một đơn hàng."""
    
    line_items_data = []
    for item in order_data.get('line_items', []):
        variation_values = []
        for meta in item.get('meta_data', []):
            if not meta['key'].startswith('_'):
                
                display_value = meta.get('display_value')
                # ### LOGIC LỌC VÀ LÀM SẠCH BIẾN THỂ ###
                # 1. Chỉ xử lý nếu display_value là một chuỗi (bỏ qua các đối tượng phức tạp)
                if isinstance(display_value, str):
                    # 2. Bỏ qua các chuỗi khuyến mãi phổ biến
                    if 'OFF on cart total' in display_value:
                        continue
                    
                    # 3. Làm sạch dữ liệu
                    # Bỏ các thẻ HTML như <strong>
                    cleaned_value = re.sub(r'<.*?>', '', display_value)
                    # Chuyển các mã HTML entity (vd: &#9632;) thành ký tự thật
                    cleaned_value = html.unescape(cleaned_value)
                    # Bỏ các ký tự không mong muốn còn lại và khoảng trắng thừa
                    cleaned_value = cleaned_value.replace('■', '').strip()

                    # Chỉ thêm vào nếu sau khi làm sạch vẫn còn nội dung
                    if cleaned_value:
                        variation_values.append(cleaned_value)
                # ###########################################

        variations_dict = {}
        for i in range(6):
            key = f"var{i+1}"
            value = variation_values[i] if i < len(variation_values) else None
            variations_dict[key] = value

        line_items_data.append({
            'product_name': item.get('name', 'N/A'),
            'quantity': item.get('quantity', 0),
            'sku': item.get('sku', 'N/A'),
            'price': float(item.get('price', 0.0)),
            **variations_dict
        })

    def format_address(address_dict):
        if not address_dict: return ""
        parts = [address_dict.get('address_1'), address_dict.get('address_2'), address_dict.get('city'), address_dict.get('state'), address_dict.get('postcode'), address_dict.get('country')]
        return ", ".join(filter(None, parts))

    order_level_data = {
        "wc_order_id": order_data['id'],
        "status": order_data.get('status', 'N/A'),
        "currency": order_data.get('currency', 'N/A'),
        "total": float(order_data.get('total', 0.0)),
        "shipping_total": float(order_data.get('shipping_total', 0.0)),
        "customer_name": f"{order_data.get('billing', {}).get('first_name', '')} {order_data.get('billing', {}).get('last_name', '')}".strip(),
        "payment_method_title": order_data.get('payment_method_title', 'N/A'),
        "order_created_at": datetime.fromisoformat(order_data['date_created_gmt']).replace(tzinfo=timezone.utc),
        "customer_note": order_data.get('customer_note', ''),
        "billing_phone": order_data.get('billing', {}).get('phone', ''),
        "billing_email": order_data.get('billing', {}).get('email', ''),
        "billing_address": format_address(order_data.get('billing')),
        "shipping_address": format_address(order_data.get('shipping')),
    }
    
    return {'order': order_level_data, 'line_items': line_items_data}

def format_products_for_notification(line_items) -> str:
    if not line_items: return "- Không có sản phẩm."
    lines = []
    for item in line_items:
        line = f"\\- {item.product_name} \\(SL: {item.quantity}\\)"
        variations = filter(None, [item.var1, item.var2, item.var3, item.var4, item.var5, item.var6])
        variations_str = ", ".join(variations)
        if variations_str:
            safe_variations = variations_str.replace('`', '\\`').replace('*', '\\*')
            line += f"\n  `{safe_variations}`"
        lines.append(line)
    return "\n".join(lines)


def check_single_store(store_id: int):
    app = current_app._get_current_object()
    with app.app_context():
        store = WooCommerceStore.query.get(store_id)
        if not store or not store.is_active: return
        print(f"Bắt đầu kiểm tra đơn hàng MỚI cho: '{store.name}'...")
        try:
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=20)
            params = {'orderby': 'date', 'order': 'asc'}
            if store.last_notified_order_timestamp:
                params['after'] = (store.last_notified_order_timestamp + timedelta(seconds=1)).isoformat()
            
            new_orders_response = wcapi.get("orders", params=params).json()
            if not new_orders_response:
                store.last_checked = datetime.now(timezone.utc)
                db.session.commit()
                return
            
            latest_order_time = None
            for order_data in new_orders_response:
                if not WooCommerceOrder.query.filter_by(wc_order_id=order_data['id'], store_id=store.id).first():
                    full_details = _extract_order_details(order_data)
                    new_order = WooCommerceOrder(store_id=store.id, **full_details['order'])
                    db.session.add(new_order)
                    for item_data in full_details['line_items']:
                        new_item = OrderLineItem(order=new_order, **item_data)
                        db.session.add(new_item)
                    db.session.commit()

                    notification_data = {"store_name": store.name, "order_id": new_order.wc_order_id, "customer_name": new_order.customer_name or "Khách lẻ", "total_amount": f"${new_order.total:,.2f}", "currency": new_order.currency, "status": new_order.status, "payment_method": new_order.payment_method_title, "product_list": format_products_for_notification(new_order.line_items.all())}
                    if store.user_id:
                        asyncio.run(send_telegram_message(message_type='new_order', data=notification_data, user_id=store.user_id))
                    latest_order_time = new_order.order_created_at
            
            if latest_order_time: store.last_notified_order_timestamp = latest_order_time
            store.last_checked = datetime.now(timezone.utc)
            db.session.commit()
        except Exception as e:
            print(f"LỖI khi kiểm tra đơn hàng mới cho '{store.name}': {e}")
            db.session.rollback()


def sync_history_for_store(app, store_id: int, job_id: str):
    with app.app_context():
        store = WooCommerceStore.query.get(store_id)
        task = BackgroundTask.query.filter_by(job_id=job_id).first()
        if not store or not task: return
        
        task.status = 'running'
        db.session.commit()
        
        try:
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=30)
            page = 1
            total_synced = 0
            while True:
                task = BackgroundTask.query.filter_by(job_id=job_id).first()
                if not task or task.requested_cancellation:
                    if task:
                        task.status = 'cancelled'
                        db.session.commit()
                    print(f"Đã hủy hoặc không tìm thấy tác vụ đồng bộ cho '{store.name}'.")
                    return

                task.log = f"Đang lấy trang {page}..."
                db.session.commit()
                orders_page = wcapi.get("orders", params={'per_page': 100, 'page': page}).json()
                if not orders_page: break

                for order_data in orders_page:
                    if not WooCommerceOrder.query.filter_by(wc_order_id=order_data['id'], store_id=store.id).first():
                        full_details = _extract_order_details(order_data)
                        history_order = WooCommerceOrder(store_id=store.id, **full_details['order'])
                        db.session.add(history_order)
                        for item_data in full_details['line_items']:
                            new_item = OrderLineItem(order=history_order, **item_data)
                            db.session.add(new_item)
                        total_synced += 1
                
                db.session.commit()
                task.progress = total_synced
                db.session.commit()
                page += 1

            task.status = 'complete'
            task.log = f"Đồng bộ hoàn tất! Đã thêm {total_synced} đơn hàng mới."
            task.total = total_synced
            task.end_time = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            print(f"LỖI khi đồng bộ lịch sử cho '{store.name}': {e}")
            task = BackgroundTask.query.filter_by(job_id=job_id).first()
            if task:
                task.status = 'failed'
                task.log = f"Lỗi: {str(e)[:500]}"
                task.total = task.progress
                task.end_time = datetime.utcnow()
                db.session.commit()
            db.session.rollback()

def check_all_stores_job():
    app = current_app._get_current_object()
    with app.app_context():
        print(f"\n--- Bắt đầu phiên kiểm tra đơn hàng định kỳ [{datetime.now()}] ---")
        for store in WooCommerceStore.query.filter_by(is_active=True).all():
            try: check_single_store(store.id)
            except Exception as e: print(f"Lỗi không mong muốn khi gọi check_single_store cho ID {store.id}: {e}")
        print(f"--- Hoàn tất phiên kiểm tra định kỳ ---")

def init_scheduler(app):
    global scheduler
    with app.app_context():
        if scheduler.running: scheduler.shutdown(wait=False)
        scheduler = BackgroundScheduler(daemon=True)
        setting = Setting.query.get('CHECK_INTERVAL_MINUTES')
        interval = int(setting.value) if setting and setting.value.isdigit() else 5
        scheduler.add_job(func=check_all_stores_job, trigger='interval', minutes=interval, id='main_check_job', replace_existing=True)
        scheduler.start()
        print(f"Scheduler đã được khởi tạo và chạy với chu kỳ {interval} phút.")
        atexit.register(lambda: scheduler.shutdown())