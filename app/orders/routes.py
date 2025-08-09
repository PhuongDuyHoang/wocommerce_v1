# app/orders/routes.py

from flask import render_template, request, jsonify, abort, current_app, Response
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, desc, select
from sqlalchemy.orm import joinedload
from woocommerce import API
from decimal import Decimal
import json
import html # <<< THÊM MỚI: Cần thiết để làm sạch dữ liệu
from jinja2.exceptions import TemplateNotFound
import io
import datetime
import openpyxl
from urllib.parse import urlparse

from . import orders_bp
from app import db
from app.models import (
    WooCommerceOrder, 
    WooCommerceStore, 
    Setting, 
    AppUser, 
    OrderLineItem,
    FulfillmentSetting
)
from app.services import get_visible_orders_query, get_visible_stores_query
from app.services.fulfillment_service import get_fulfillment_service


# ... (Tất cả các hàm từ manage_all_orders đến api_get_fulfillment_products giữ nguyên không đổi) ...
@orders_bp.route('/')
@login_required
def manage_all_orders():
    page = request.args.get('page', 1, type=int)
    base_query = db.session.query(WooCommerceOrder, WooCommerceStore, AppUser.username.label('owner_username'))\
        .join(WooCommerceStore, WooCommerceOrder.store_id == WooCommerceStore.id)\
        .outerjoin(AppUser, WooCommerceStore.user_id == AppUser.id)
    
    visible_orders_subquery = get_visible_orders_query(current_user).with_entities(WooCommerceOrder.id).subquery()
    base_query = base_query.filter(WooCommerceOrder.id.in_(select(visible_orders_subquery)))

    search_query = request.args.get('search_query')
    selected_store_id = request.args.get('store_id', type=int)
    selected_status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    selected_admin_id = request.args.get('admin_id', type=int)
    selected_user_id = request.args.get('user_id', type=int)
    selected_fulfillment_status = request.args.get('fulfillment_status')

    if search_query:
        search_term = f"%{search_query}%"
        try:
            search_int = int(search_query)
            base_query = base_query.filter(or_(
                WooCommerceOrder.wc_order_id == search_int,
                WooCommerceOrder.customer_name.ilike(search_term),
                WooCommerceOrder.billing_phone.ilike(search_term),
                WooCommerceOrder.billing_email.ilike(search_term),
                WooCommerceOrder.line_items.any(or_(
                    OrderLineItem.product_name.ilike(search_term),
                    OrderLineItem.sku.ilike(search_term)
                ))
            ))
        except ValueError:
            base_query = base_query.filter(or_(
                WooCommerceOrder.customer_name.ilike(search_term),
                WooCommerceOrder.billing_phone.ilike(search_term),
                WooCommerceOrder.billing_email.ilike(search_term),
                WooCommerceOrder.line_items.any(or_(
                    OrderLineItem.product_name.ilike(search_term),
                    OrderLineItem.sku.ilike(search_term)
                ))
            ))
    
    if selected_store_id:
        base_query = base_query.filter(WooCommerceOrder.store_id == selected_store_id)
    if selected_status:
        base_query = base_query.filter(WooCommerceOrder.status == selected_status)
    if start_date:
        base_query = base_query.filter(WooCommerceOrder.order_created_at >= start_date)
    if end_date:
        base_query = base_query.filter(WooCommerceOrder.order_created_at <= end_date)

    if selected_fulfillment_status == 'fulfilled':
        base_query = base_query.filter(WooCommerceOrder.note.ilike('%[Fulfilled by%'))
    elif selected_fulfillment_status == 'not_fulfilled':
        base_query = base_query.filter(or_(
            WooCommerceOrder.note == None,
            WooCommerceOrder.note.notilike('%[Fulfilled by%')
        ))

    user_ids_to_filter = None
    if current_user.is_super_admin() and (selected_admin_id or selected_user_id):
        if selected_user_id:
            user_ids_to_filter = [selected_user_id]
        elif selected_admin_id:
            admin = AppUser.query.get(selected_admin_id)
            if admin:
                user_ids_to_filter = [child.id for child in admin.children] + [admin.id]
    elif current_user.is_admin() and selected_user_id:
        user_ids_to_filter = [selected_user_id]
    
    if user_ids_to_filter:
        base_query = base_query.filter(WooCommerceStore.user_id.in_(user_ids_to_filter))

    orders_pagination = base_query.order_by(desc(WooCommerceOrder.order_created_at)).paginate(page=page, per_page=30, error_out=False)
    
    orders_with_details = []
    for order_obj, store_obj, owner_username_str in orders_pagination.items:
        order_obj.store = store_obj
        order_obj.owner_username = owner_username_str or 'Chưa gán'
        order_obj.is_fulfilled = '[Fulfilled by' in (order_obj.note or '')
        orders_with_details.append(order_obj)
    
    stores_for_filter = get_visible_stores_query(current_user).order_by(WooCommerceStore.name).all()
    admins_for_filter, users_for_filter = [], []
    if current_user.is_super_admin():
        admins_for_filter = AppUser.query.filter(AppUser.role.in_(['admin', 'super_admin'])).all()
        if selected_admin_id:
            admin_user = AppUser.query.get(selected_admin_id)
            if admin_user:
                users_for_filter = admin_user.children.all()
        else:
            users_for_filter = AppUser.query.filter(AppUser.role == 'user').all()
    elif current_user.is_admin():
        users_for_filter = current_user.children.all()
    
    statuses = [('processing', 'Đang xử lý'), ('completed', 'Hoàn thành'), ('on-hold', 'Tạm giữ'), ('pending', 'Chờ thanh toán'), ('cancelled', 'Đã hủy'), ('refunded', 'Đã hoàn tiền'), ('failed', 'Thất bại')]
    columns_config_json = Setting.get_value('ORDER_TABLE_COLUMNS', '[]')
    columns_config = json.loads(columns_config_json)
    
    query_params = request.args.copy()
    query_params.pop('page', None)
    
    return render_template(
        'orders/manage_orders.html', title='Quản lý Đơn hàng',
        orders=orders_with_details, pagination=orders_pagination,
        columns_config=columns_config,
        query_params=query_params,
        search_query=search_query, selected_store_id=selected_store_id,
        selected_status=selected_status, start_date=start_date, end_date=end_date,
        selected_admin_id=selected_admin_id, selected_user_id=selected_user_id,
        selected_fulfillment_status=selected_fulfillment_status,
        stores_for_filter=stores_for_filter, admins_for_filter=admins_for_filter,
        users_for_filter=users_for_filter, statuses=statuses
    )

@orders_bp.route('/update_note/<int:order_id>', methods=['POST'])
@login_required
def update_note(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    data = request.get_json()
    if data is None or 'note' not in data: return jsonify({'success': False, 'message': 'Dữ liệu không hợp lệ'}), 400
    order.note = data.get('note', '')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Đã lưu ghi chú.'})

@orders_bp.route('/update_status/<int:order_id>', methods=['POST'])
@login_required
def update_status(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    data = request.get_json()
    if data is None or 'status' not in data: return jsonify({'success': False, 'message': 'Dữ liệu không hợp lệ'}), 400
    new_status = data.get('status')
    store = order.store
    try:
        wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=20)
        response = wcapi.put(f"orders/{order.wc_order_id}", {"status": new_status})
        if response.status_code == 200:
            updated_order_data = response.json()
            order.status = updated_order_data.get('status', new_status)
            db.session.commit()
            return jsonify({'success': True, 'message': f'Đã cập nhật trạng thái!', 'new_status': order.status})
        else:
            return jsonify({'success': False, 'message': response.json().get('message', 'Lỗi WooCommerce.')}), response.status_code
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi kết nối: {str(e)}'}), 500

@orders_bp.route('/get_refund_details/<int:order_id>')
@login_required
def get_refund_details(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    try:
        wcapi = API(url=order.store.store_url, consumer_key=order.store.consumer_key, consumer_secret=order.store.consumer_secret, version="wc/v3", timeout=20)
        order_response = wcapi.get(f"orders/{order.wc_order_id}")
        order_response.raise_for_status()
        order_data = order_response.json()
        refunds_response = wcapi.get(f"orders/{order.wc_order_id}/refunds")
        refunds_response.raise_for_status()
        refunds_data = refunds_response.json()
        total_refunded = sum(Decimal(r.get('amount', '0')) for r in refunds_data)
        refundable_amount = Decimal(order_data.get('total', '0')) - total_refunded
        return jsonify({
            'success': True,
            'payment_method': order_data.get('payment_method', 'N/A'),
            'payment_method_title': order_data.get('payment_method_title', 'N/A'),
            'total_amount': str(order_data.get('total', '0')),
            'currency': order_data.get('currency', 'USD'),
            'total_refunded': str(total_refunded),
            'refundable_amount': str(refundable_amount),
            'refunds': [{'reason': r.get('reason') or 'N/A','amount': r.get('amount', '0'),'date': r.get('date_created')} for r in refunds_data]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Không thể lấy chi tiết hoàn tiền: {str(e)}'}), 500

@orders_bp.route('/process_refund/<int:order_id>', methods=['POST'])
@login_required
def process_refund(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    data = request.get_json()
    try:
        wcapi = API(url=order.store.store_url, consumer_key=order.store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=30)
        response = wcapi.post(f"orders/{order.wc_order_id}/refunds", data)
        if response.status_code == 201:
            from app.worker import check_single_store_job
            check_single_store_job(current_app._get_current_object(), order.store.id)
            return jsonify({'success': True, 'message': 'Hoàn tiền thành công!'})
        else:
            return jsonify({'success': False, 'message': response.json().get('message', 'Lỗi WooCommerce.')}), response.status_code
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi kết nối: {str(e)}'}), 500

@orders_bp.route('/get_fulfillment_template/<provider_name>')
@login_required
def get_fulfillment_template(provider_name):
    if provider_name not in ['mangotee']:
        abort(404)
    try:
        return render_template(f'orders/{provider_name}.html')
    except TemplateNotFound:
        current_app.logger.error(f"CRITICAL: Không tìm thấy file template 'orders/{provider_name}.html'")
        abort(404)

@orders_bp.route('/api/fulfillment_details/<int:order_id>')
@login_required
def api_get_fulfillment_details(order_id):
    order = get_visible_orders_query(current_user).filter(WooCommerceOrder.id == order_id).first_or_404()
    try:
        wcapi = API(url=order.store.store_url, consumer_key=order.store.consumer_key, consumer_secret=order.store.consumer_secret, version="wc/v3", timeout=15)
        woo_order_response = wcapi.get(f"orders/{order.wc_order_id}")
        woo_order_response.raise_for_status()
        woo_order_data = woo_order_response.json()
        data_payload = {
            "wc_order_id": order.wc_order_id,
            "store_name": order.store.name,
            "shipping_address": woo_order_data.get('shipping', {}),
            "billing": woo_order_data.get('billing', {}),
            "line_items": [{"id": item.get('id'),"name": item.get('name'),"quantity": item.get('quantity'),"sku": item.get('sku')} for item in woo_order_data.get('line_items', [])]
        }
        return jsonify({"success": True, "data": data_payload})
    except Exception as e:
        current_app.logger.error(f"Fulfillment API Error for WC Order ID {order.wc_order_id}: {e}")
        return jsonify({"success": False, "message": f'Lỗi khi lấy dữ liệu từ WooCommerce: {e}'}), 500

def get_user_and_setting(provider_name):
    user_with_key = current_user
    if not (current_user.is_super_admin() or current_user.is_admin()):
        user_with_key = current_user.parent
    if not user_with_key: return None, None
    setting = FulfillmentSetting.query.filter_by(user_id=user_with_key.id, provider_name=provider_name).first()
    return user_with_key, setting

@orders_bp.route('/process_fulfillment/<int:order_id>', methods=['POST'])
@login_required
def process_fulfillment(order_id):
    order = get_visible_orders_query(current_user).filter(WooCommerceOrder.id == order_id).first_or_404()
    data = request.json
    provider_name = data.get('provider')
    printer_value = data.get('printer')
    order_payload = data.get('payload')
    if not all([provider_name, printer_value, order_payload]):
        return jsonify({"success": False, "message": "Dữ liệu gửi lên không hợp lệ."}), 400
    user, setting = get_user_and_setting(provider_name)
    if not user: return jsonify({"success": False, "message": "Lỗi xác thực quyền."}), 403
    if not setting or not setting.api_key: return jsonify({"success": False, "message": f"Chưa cấu hình API Key cho {provider_name}."}), 400
    service = get_fulfillment_service(provider_name, setting.api_key)
    if not service: return jsonify({"success": False, "message": "Nhà cung cấp không được hỗ trợ."}), 404
    success, message = service.create_order(order_payload, printer_value)
    if success:
        note_content = f"\n[Fulfilled by {provider_name.title()} - {message}]"
        order.note = (order.note or '') + note_content
        db.session.commit()
    return jsonify({"success": success, "message": message})

@orders_bp.route('/api/fulfillment_products/<provider_name>')
@login_required
def api_get_fulfillment_products(provider_name):
    user, setting = get_user_and_setting(provider_name)
    if not user: return jsonify({"success": False, "message": "Lỗi xác thực."}), 403
    if not setting or not setting.api_key: return jsonify({"success": False, "message": f"Chưa cấu hình API key cho {provider_name}."}), 400
    service = get_fulfillment_service(provider_name, setting.api_key)
    if not service: return jsonify({"success": False, "message": "Nhà cung cấp không được hỗ trợ."}), 404
    success, data = service.get_products()
    return jsonify({"success": success, "message": "OK" if success else data, "data": data if success else None})


@orders_bp.route('/export')
@login_required
def export_orders():
    order_ids_str = request.args.get('ids')
    if not order_ids_str:
        return "Không có đơn hàng nào được chọn.", 400

    order_ids = [int(id) for id in order_ids_str.split(',')]
    
    orders_from_db = get_visible_orders_query(current_user).options(
        joinedload(WooCommerceOrder.store)
    ).filter(WooCommerceOrder.id.in_(order_ids)).all()

    api_clients = {}
    all_rows_data = []

    raw_orders_data = []
    for order_db in orders_from_db:
        if not order_db.store:
            continue
        
        store_id = order_db.store.id
        if store_id not in api_clients:
            try:
                api_clients[store_id] = API(
                    url=order_db.store.store_url,
                    consumer_key=order_db.store.consumer_key,
                    consumer_secret=order_db.store.consumer_secret,
                    version="wc/v3",
                    timeout=20
                )
            except Exception as e:
                current_app.logger.error(f"Failed to create API client for store {order_db.store.name}: {e}")
                continue
        
        wcapi = api_clients[store_id]
        
        try:
            response = wcapi.get(f"orders/{order_db.wc_order_id}")
            response.raise_for_status()
            order_api_data = response.json()
            order_api_data['_store_url'] = order_db.store.store_url 
            raw_orders_data.append(order_api_data)
        except Exception as e:
            current_app.logger.error(f"Failed to get data for WC Order ID {order_db.wc_order_id}: {e}")

    for order_data in raw_orders_data:
        billing_info = order_data.get('billing', {})
        
        common_info = {
            "DOMAIN": urlparse(order_data.get('_store_url', '')).netloc,
            "Date Order": order_data.get('date_created', '').replace('T', ' '),
            "ID ORDER": order_data.get('id', ''),
            "TOTAL": order_data.get('total', ''),
            "Fee Shipping": order_data.get('shipping_total', ''),
            "NOTE": order_data.get('customer_note', ''),
            "FULL NAME": f"{billing_info.get('first_name', '')} {billing_info.get('last_name', '')}".strip(),
            "ADDRESS 1": billing_info.get('address_1', ''),
            "ADDRESS 2": billing_info.get('address_2', ''),
            "CITY": billing_info.get('city', ''),
            "ZIPCODE": billing_info.get('postcode', ''),
            "STATE": billing_info.get('state', ''),
            "COUNTRY": billing_info.get('country', ''),
            "PHONE": billing_info.get('phone', ''),
            "Email": billing_info.get('email', '')
        }

        for item in order_data.get('line_items', []):
            meta_data = item.get('meta_data', [])
            variations = []
            for meta in meta_data:
                display_value = meta.get('display_value')
                # <<< SỬA ĐỔI: Thêm logic làm sạch dữ liệu biến thể >>>
                if isinstance(display_value, str):
                    # Giải mã các ký tự HTML (vd: &#9632; -> ■)
                    cleaned_value = html.unescape(display_value)
                    # Loại bỏ ký tự khối vuông và các khoảng trắng ở đầu
                    cleaned_value = cleaned_value.lstrip('■ \t\n\r')
                    variations.append(cleaned_value)
            
            padded_variations = (variations + [''] * 6)[:6]

            row = {**common_info}
            row.update({
                "Item Price": item.get('price', ''),
                "TITLE PRODUCT": item.get('name', ''),
                "URl PRODUCT": '', 
                "IMAGE": '',       
                "SKU PRODUCT": item.get('sku', ''),
                "VAR 1": padded_variations[0],
                "VAR 2": padded_variations[1],
                "VAR 3": padded_variations[2],
                "VAR 4": padded_variations[3],
                "VAR 5": padded_variations[4],
                "VAR 6": padded_variations[5],
                "QUANTITY": item.get('quantity', '')
            })
            all_rows_data.append(row)

    if not all_rows_data:
        return "Không có dữ liệu sản phẩm để xuất.", 404

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Detailed Orders Export"
    
    headers = [
        "DOMAIN", "Date Order", "ID ORDER", "TOTAL", "Item Price", "Fee Shipping",
        "TITLE PRODUCT", "URl PRODUCT", "IMAGE", "SKU PRODUCT",
        "VAR 1", "VAR 2", "VAR 3", "VAR 4", "VAR 5", "VAR 6",
        "QUANTITY", "NOTE", "FULL NAME", "ADDRESS 1", "ADDRESS 2",
        "CITY", "ZIPCODE", "STATE", "COUNTRY", "PHONE", "Email"
    ]
    sheet.append(headers)

    for row_dict in all_rows_data:
        row_to_append = []
        for header in headers:
            value = row_dict.get(header, '')
            if isinstance(value, (dict, list)):
                try:
                    value = json.dumps(value, ensure_ascii=False)
                except TypeError:
                    value = str(value)
            row_to_append.append(value)
        sheet.append(row_to_append)

    excel_stream = io.BytesIO()
    workbook.save(excel_stream)
    excel_stream.seek(0)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"detailed_orders_{timestamp}.xlsx"

    return Response(
        excel_stream,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment;filename={filename}'}
    )