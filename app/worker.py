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
from .notifications import send_telegram_message

scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
executor = ThreadPoolExecutor(max_workers=2)

def _extract_order_details(order_data: dict, wcapi: API, should_fetch_images: bool) -> dict:
    # ... (Nội dung không đổi)
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
        "customer_note": order_data.get('customer_note', ''),
        "billing_phone": order_data.get('billing', {}).get('phone', ''),
        "billing_email": order_data.get('billing', {}).get('email', ''),
        "billing_address": format_address(order_data.get('billing')),
        "shipping_address": format_address(order_data.get('shipping')),
    }
    
    return {'order': order_level_data, 'line_items': line_items_data}

def format_products_for_notification(line_items) -> str:
    # ... (Nội dung không đổi)
    if not line_items: return "- Không có sản phẩm."
    lines = []
    for item in line_items:
        line = f"\\- {item.product_name} \\(SL: {item.quantity}\\)"
        variations = item.variations_list
        variations_str = ", ".join(variations)
        if variations_str:
            safe_variations = variations_str.replace('`', '\\`').replace('*', '\\*')
            line += f"\n  `{safe_variations}`"
        lines.append(line)
    return "\n".join(lines)

def sync_history_for_store(app, store_id: int, job_id: str):
    # ... (Nội dung không đổi)
    with app.app_context():
        store = WooCommerceStore.query.get(store_id)
        task = BackgroundTask.query.filter_by(job_id=job_id).first()
        if not store or not task: return

        fetch_images_setting = Setting.query.get('FETCH_PRODUCT_IMAGES')
        should_fetch_images = fetch_images_setting.value.lower() == 'true' if fetch_images_setting else False
        
        task.status = 'running'
        db.session.commit()
        
        try:
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=30)
            page = 1
            total_synced = 0
            images_fixed = 0

            while True:
                task = BackgroundTask.query.filter_by(job_id=job_id).first()
                if not task or task.requested_cancellation:
                    if task:
                        task.status = 'cancelled'; db.session.commit()
                    return

                task.log = f"Đang lấy trang {page} (Lấy ảnh: {'Bật' if should_fetch_images else 'Tắt'}). Đã sửa: {images_fixed} ảnh."
                db.session.commit()
                orders_page = wcapi.get("orders", params={'per_page': 50, 'page': page}).json()
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
                    
                    elif should_fetch_images:
                        api_line_items = {item['wc_line_item_id']: item for item in full_details['line_items']}
                        
                        for line_item_db in existing_order.line_items:
                            if not line_item_db.image_url:
                                api_item = api_line_items.get(line_item_db.wc_line_item_id)
                                if api_item and api_item.get('product_id'):
                                    try:
                                        product_data = wcapi.get(f"products/{api_item.get('product_id')}").json()
                                        if product_data and product_data.get('images'):
                                            line_item_db.image_url = product_data['images'][0].get('src')
                                            images_fixed += 1
                                    except Exception as e:
                                        print(f"Không thể lấy ảnh cho sản phẩm ID {api_item.get('product_id')} (sửa lỗi): {e}")

                db.session.commit()
                task.progress = total_synced
                db.session.commit()
                page += 1

            task.status = 'complete'
            task.log = f"Hoàn tất! Đã thêm {total_synced} đơn hàng mới và sửa {images_fixed} ảnh bị thiếu."
            task.total = total_synced
            task.end_time = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task = BackgroundTask.query.filter_by(job_id=job_id).first()
            if task:
                task.status = 'failed'
                task.log = f"Lỗi: {str(e)[:500]}"
                task.total = task.progress
                task.end_time = datetime.utcnow()
                db.session.commit()
            db.session.rollback()

def check_single_store_job(app, store_id):
    """Tác vụ chạy nền cho MỘT cửa hàng duy nhất."""
    with app.app_context():
        store = db.session.get(WooCommerceStore, store_id)
        if not store or not store.is_active:
            # print(f"Bỏ qua kiểm tra cho cửa hàng ID {store_id} vì không hoạt động.")
            return

        print(f"--- Bắt đầu kiểm tra đơn hàng cho: '{store.name}' ---")
        
        latest_order_time = None
        
        try:
            setting = db.session.get(Setting, 'FETCH_PRODUCT_IMAGES')
            should_fetch_images = setting.value.lower() == 'true' if setting else False
            
            wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=20)
            params = {'orderby': 'date', 'order': 'asc'}
            if store.last_notified_order_timestamp:
                params['after'] = (store.last_notified_order_timestamp + timedelta(seconds=1)).isoformat()
            
            new_orders_response = wcapi.get("orders", params=params).json()
            
            if not isinstance(new_orders_response, list):
                print(f"Lỗi API cho '{store.name}': {new_orders_response.get('message', 'Không rõ')}")
                return

            if not new_orders_response:
                print(f"Không có đơn hàng mới cho '{store.name}'.")
            else:
                for order_data in new_orders_response:
                    # --- MODIFIED: Robust transaction handling for each order ---
                    try:
                        # Kiểm tra sự tồn tại của đơn hàng
                        exists = db.session.query(WooCommerceOrder.id).filter_by(wc_order_id=order_data['id'], store_id=store.id).first() is not None
                        if not exists:
                            full_details = _extract_order_details(order_data, wcapi, should_fetch_images)
                            new_order = WooCommerceOrder(store_id=store.id, **full_details['order'])
                            db.session.add(new_order)
                            for item_data in full_details['line_items']:
                                item_data.pop('product_id', None) 
                                new_item = OrderLineItem(order=new_order, **item_data)
                                db.session.add(new_item)
                            
                            # Commit ngay sau khi thêm một đơn hàng để lưu nó ngay lập tức
                            db.session.commit()
                            
                            # Cập nhật thời gian của đơn hàng mới nhất đã được LƯU THÀNH CÔNG
                            latest_order_time = new_order.order_created_at
                            
                            # Gửi thông báo
                            if store.user_id:
                                notification_data = {"store_name": store.name, "order_id": new_order.wc_order_id, "customer_name": new_order.customer_name or "Khách lẻ", "total_amount": f"${new_order.total:,.2f}", "currency": new_order.currency, "status": new_order.status, "payment_method": new_order.payment_method_title, "product_list": format_products_for_notification(new_order.line_items)}
                                asyncio.run(send_telegram_message(message_type='new_order', data=notification_data, user_id=store.user_id))

                    except Exception as single_order_error:
                        print(f"LỖI khi xử lý đơn hàng WC_ID {order_data.get('id')}: {single_order_error}")
                        db.session.rollback() # Rollback lỗi của đơn hàng này và tiếp tục với các đơn hàng khác
                        continue # Bỏ qua đơn hàng bị lỗi

            # Cập nhật timestamp MỘT LẦN sau khi vòng lặp kết thúc
            if latest_order_time:
                store.last_notified_order_timestamp = latest_order_time
            
            store.last_checked = datetime.now(timezone.utc)
            db.session.commit()
            print(f"--- Hoàn tất kiểm tra cho '{store.name}', đã xử lý {len(new_orders_response)} đơn hàng. ---")

        except Exception as e:
            print(f"LỖI nghiêm trọng khi kiểm tra '{store.name}': {e}")
            db.session.rollback()

def add_or_update_store_job(app, store_id):
    # ... (Nội dung không đổi)
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
    # ... (Nội dung không đổi)
    job_id = f'check_store_{store_id}'
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        print(f"Đã xóa tác vụ cho cửa hàng ID: {store_id}.")

def init_scheduler(app):
    # ... (Nội dung không đổi)
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