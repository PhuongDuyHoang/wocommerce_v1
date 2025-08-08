# app/worker.py

import atexit
import asyncio
from datetime import datetime, timezone, timedelta
import json
from woocommerce import API
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from concurrent.futures import ThreadPoolExecutor
import html
import re

from app import db
from .models import WooCommerceStore, WooCommerceOrder, Setting, BackgroundTask, OrderLineItem
from .notifications import send_telegram_message, escape_markdown_v2

scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
executor = ThreadPoolExecutor(max_workers=2)

def _extract_order_details(order_data: dict, wcapi: API, should_fetch_images: bool) -> dict:
    line_items_data = []
    for item in order_data.get('line_items', []):
        variation_values = []
        for meta in item.get('meta_data', []):
            if not meta['key'].startswith('_'):
                display_value = meta.get('display_value')
                if isinstance(display_value, str):
                    if 'OFF on cart total' in display_value: continue
                    cleaned_value = re.sub(r'<.*?>', '', html.unescape(display_value)).replace('■', '').strip()
                    if cleaned_value: variation_values.append(cleaned_value)
        
        variations_json = json.dumps(variation_values) if variation_values else None
        
        image_url = None
        if should_fetch_images and item.get('product_id'):
            try:
                product_data = wcapi.get(f"products/{item.get('product_id')}").json()
                if product_data and product_data.get('images'):
                    image_url = product_data['images'][0].get('src')
            except Exception as e:
                print(f"Không thể lấy ảnh cho sản phẩm ID {item.get('product_id')}: {e}")

        line_items_data.append({
            'wc_line_item_id': item.get('id'),
            'product_name': item.get('name', 'N/A'),
            'quantity': item.get('quantity', 0),
            'sku': item.get('sku', 'N/A'),
            'price': float(item.get('price', 0.0)),
            'image_url': image_url,
            'variations': variations_json,
            'product_id': item.get('product_id') 
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
        "order_modified_at": datetime.fromisoformat(order_data['date_modified_gmt']).replace(tzinfo=timezone.utc),
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
        escaped_name = escape_markdown_v2(item.product_name)
        line = f"\\- {escaped_name} \\(SL: {item.quantity}\\)"
        
        variations = item.variations_list
        variations_str = ", ".join(variations)
        if variations_str:
            safe_variations_for_code = variations_str.replace('`', "'")
            line += f"\n  `{safe_variations_for_code}`"
        lines.append(line)
    return "\n".join(lines)

def sync_history_for_store(app, store_id: int, job_id: str):
    with app.app_context():
        store = WooCommerceStore.query.get(store_id)
        task = BackgroundTask.query.filter_by(job_id=job_id).first()
        if not store or not task: return

        store.is_syncing_history = True
        db.session.commit()
        
        fetch_images_setting = Setting.query.get('FETCH_PRODUCT_IMAGES')
        should_fetch_images = fetch_images_setting.value.lower() == 'true' if fetch_images_setting else False
        
        task.status = 'running'
        db.session.commit()
        
        try:
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=30)
            
            # === START: SỬA LỖI HIỂN THỊ TIẾN TRÌNH ===
            # Thay vì .head(), dùng .get() với per_page=1 để lấy header
            try:
                response = wcapi.get("orders", params={'per_page': 1})
                total_orders = int(response.headers.get('X-WP-Total', 0))
                task.total = total_orders
                db.session.commit()
            except Exception as e:
                print(f"Không thể lấy tổng số đơn hàng, sẽ không hiển thị Total: {e}")
                task.total = 0
                db.session.commit()
            # === END: SỬA LỖI HIỂN THỊ TIẾN TRÌNH ===
            
            page = 1
            total_synced = 0
            
            while True:
                task = BackgroundTask.query.filter_by(job_id=job_id).first()
                if not task or task.requested_cancellation:
                    if task: task.status = 'cancelled'
                    break

                task.log = f"Đang lấy trang {page}..."
                db.session.commit()
                # Sử dụng lại wcapi đã khởi tạo
                orders_page_response = wcapi.get("orders", params={'per_page': 50, 'page': page})
                orders_page = orders_page_response.json()
                if not orders_page: break

                for order_data in orders_page:
                    full_details = _extract_order_details(order_data, wcapi, should_fetch_images)
                    existing_order = WooCommerceOrder.query.filter_by(wc_order_id=order_data['id'], store_id=store.id).first()
                    
                    if not existing_order:
                        history_order = WooCommerceOrder(store_id=store.id, **full_details['order'])
                        db.session.add(history_order)
                        for item_data in full_details['line_items']:
                            item_data.pop('product_id', None)
                            new_item = OrderLineItem(order=history_order, **item_data)
                            db.session.add(new_item)
                    total_synced += 1

                db.session.commit()
                task.progress = total_synced
                db.session.commit()
                page += 1

            task.status = 'complete'
            task.log = f"Hoàn tất! Đã xử lý {total_synced} đơn hàng."
            task.end_time = datetime.now(timezone.utc)
            
        except Exception as e:
            if task:
                task.status = 'failed'
                task.log = f"Lỗi: {str(e)[:500]}"
                task.end_time = datetime.now(timezone.utc)
            db.session.rollback()
        finally:
            store.is_syncing_history = False
            db.session.commit()

def check_single_store_job(app, store_id):
    with app.app_context():
        store = db.session.get(WooCommerceStore, store_id)
        if not store or not store.is_active:
            return
            
        if store.is_syncing_history:
            print(f"--- Tạm dừng kiểm tra đơn mới cho '{store.name}' vì đang đồng bộ lịch sử. ---")
            return

        print(f"--- Bắt đầu đồng bộ đơn hàng cho: '{store.name}' ---")
        
        new_orders_to_notify = []
        updated_order_count = 0
        latest_modified_time = None

        try:
            setting = db.session.get(Setting, 'FETCH_PRODUCT_IMAGES')
            should_fetch_images = setting.value.lower() == 'true' if setting else False
            
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=20)
            
            params = {'orderby': 'modified', 'order': 'asc', 'per_page': 100}
            if store.last_checked:
                params['modified_after'] = store.last_checked.isoformat()
            else:
                params['modified_after'] = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            
            orders_response = wcapi.get("orders", params=params).json()
            
            if not isinstance(orders_response, list):
                print(f"Lỗi API cho '{store.name}': {orders_response.get('message', 'Không rõ')}")
                return

            if not orders_response:
                print(f"Không có đơn hàng mới hoặc cập nhật cho '{store.name}'.")
            else:
                for order_data in orders_response:
                    try:
                        full_details = _extract_order_details(order_data, wcapi, should_fetch_images)
                        
                        existing_order = WooCommerceOrder.query.filter_by(
                            wc_order_id=order_data['id'], store_id=store.id
                        ).first()

                        if existing_order:
                            print(f"Đang cập nhật đơn hàng WC_ID {order_data['id']}...")
                            for key, value in full_details['order'].items():
                                setattr(existing_order, key, value)
                            
                            OrderLineItem.query.filter_by(order_id=existing_order.id).delete()
                            for item_data in full_details['line_items']:
                                item_data.pop('product_id', None)
                                new_item = OrderLineItem(order=existing_order, **item_data)
                                db.session.add(new_item)
                            
                            updated_order_count += 1
                        else:
                            print(f"Đang thêm đơn hàng mới WC_ID {order_data['id']}...")
                            new_order = WooCommerceOrder(store_id=store.id, **full_details['order'])
                            db.session.add(new_order)
                            
                            for item_data in full_details['line_items']:
                                item_data.pop('product_id', None)
                                new_item = OrderLineItem(order=new_order, **item_data)
                                db.session.add(new_item)
                            
                            new_orders_to_notify.append(new_order)

                        db.session.commit()
                        
                        latest_modified_time = full_details['order']['order_modified_at']

                    except Exception as single_order_error:
                        print(f"LỖI khi xử lý đơn hàng WC_ID {order_data.get('id')}: {single_order_error}")
                        db.session.rollback()
                        continue

            if latest_modified_time:
                store.last_checked = latest_modified_time
                db.session.commit()

            print(f"--- Hoàn tất đồng bộ cho '{store.name}'. Đã thêm {len(new_orders_to_notify)} đơn mới, cập nhật {updated_order_count} đơn. ---")

        except Exception as e:
            print(f"LỖI nghiêm trọng khi đồng bộ '{store.name}': {e}")
            db.session.rollback()
            return

        if new_orders_to_notify and store.user_id:
            for order in new_orders_to_notify:
                try:
                    notification_data = {
                        "store_name": store.name, 
                        "order_id": order.wc_order_id, 
                        "customer_name": order.customer_name or "Khách lẻ", 
                        "total_amount": f"${order.total:,.2f}", 
                        "currency": order.currency, 
                        "status": order.status, 
                        "payment_method": order.payment_method_title, 
                        "product_list": format_products_for_notification(order.line_items)
                    }
                    asyncio.run(send_telegram_message(app, message_type='new_order', data=notification_data, user_id=store.user_id))
                except Exception as notify_error:
                    print(f"LỖI khi gửi thông báo cho đơn hàng {order.wc_order_id}: {notify_error}")

def add_or_update_store_job(app, store_id):
    with app.app_context():
        store = WooCommerceStore.query.get(store_id)
        setting = Setting.query.get('CHECK_INTERVAL_MINUTES')
        interval = int(setting.value) if setting and setting.value.isdigit() else 5
        job_id = f'check_store_{store_id}'

        if store and store.is_active:
            scheduler.add_job(
                func=check_single_store_job,
                trigger='interval',
                minutes=interval,
                id=job_id,
                replace_existing=True,
                args=[app, store_id],
                max_instances=1
            )
            print(f"Đã thêm/cập nhật tác vụ cho cửa hàng '{store.name}' (ID: {store_id}) với chu kỳ {interval} phút.")
        else:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
                print(f"Đã xóa tác vụ cho cửa hàng ID: {store_id} vì không hoạt động.")

def remove_store_job(store_id):
    job_id = f'check_store_{store_id}'
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        print(f"Đã xóa tác vụ cho cửa hàng ID: {store_id}.")

def init_scheduler(app):
    global scheduler
    with app.app_context():
        if scheduler.running:
            try:
                scheduler.shutdown(wait=False)
            except Exception as e:
                print(f"Lỗi khi tắt scheduler cũ: {e}")
        
        scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
        scheduler.start()
        
        print("--- Bắt đầu lập lịch cho các cửa hàng ---")
        active_stores = WooCommerceStore.query.filter_by(is_active=True).all()
        for store in active_stores:
            add_or_update_store_job(app, store.id)
        
        print(f"--- Hoàn tất lập lịch cho {len(active_stores)} cửa hàng ---")
        atexit.register(lambda: scheduler.shutdown())