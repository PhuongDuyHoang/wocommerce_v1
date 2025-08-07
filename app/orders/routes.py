# app/orders/routes.py

from flask import render_template, request, jsonify, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, desc
from woocommerce import API
from decimal import Decimal, ROUND_DOWN
import json

from . import orders_bp
from app import db
from app.models import WooCommerceOrder, WooCommerceStore, Setting, AppUser, OrderLineItem
from app.services import get_visible_orders_query, get_visible_stores_query


@orders_bp.route('/')
@login_required
def manage_all_orders():
    page = request.args.get('page', 1, type=int)
    base_query = db.session.query(WooCommerceOrder, WooCommerceStore, AppUser.username.label('owner_username'))\
        .join(WooCommerceStore, WooCommerceOrder.store_id == WooCommerceStore.id)\
        .outerjoin(AppUser, WooCommerceStore.user_id == AppUser.id)

    visible_orders_subquery = get_visible_orders_query(current_user).with_entities(WooCommerceOrder.id).subquery()
    base_query = base_query.filter(WooCommerceOrder.id.in_(visible_orders_subquery))

    search_query = request.args.get('search_query')
    selected_store_id = request.args.get('store_id', type=int)
    selected_status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    selected_admin_id = request.args.get('admin_id', type=int)
    selected_user_id = request.args.get('user_id', type=int)

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
            return jsonify({'success': True, 'message': f'Đã cập nhật trạng thái thành công!', 'new_status': order.status})
        else:
            return jsonify({'success': False, 'message': response.json().get('message', 'Lỗi WooCommerce.')}), response.status_code
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi kết nối: {str(e)}'}), 500


@orders_bp.route('/get_refund_details/<int:order_id>')
@login_required
def get_refund_details(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    store = order.store
    try:
        wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=20)
        
        order_response = wcapi.get(f"orders/{order.wc_order_id}")
        order_response.raise_for_status()
        order_data = order_response.json()
        
        refunds_response = wcapi.get(f"orders/{order.wc_order_id}/refunds")
        refunds_response.raise_for_status()
        refunds_data = refunds_response.json()

        # === START: SỬA LỖI - Đọc đúng trường 'amount' thay vì 'total' ===
        # Số tiền hoàn lại là một số dương trong đối tượng refund
        total_refunded = sum(Decimal(r.get('amount', '0')) for r in refunds_data)
        # === END: SỬA LỖI ===

        original_total = Decimal(order_data.get('total', '0'))
        refundable_amount = original_total - total_refunded

        return jsonify({
            'success': True,
            'payment_method_title': order_data.get('payment_method_title', 'N/A'),
            'payment_method': order_data.get('payment_method', 'N/A'),
            'transaction_id': order_data.get('transaction_id', ''),
            'total_amount': str(original_total),
            'currency': order_data.get('currency', 'USD'),
            'total_refunded': str(total_refunded), # Gửi đi tổng số dương
            'refundable_amount': str(refundable_amount.quantize(Decimal('0.01'), rounding=ROUND_DOWN)),
            'refunds': [
                {
                    'id': r.get('id'),
                    'reason': r.get('reason') or 'Không có lý do',
                    # === START: SỬA LỖI - Gửi đúng trường 'amount' cho frontend ===
                    'amount': r.get('amount', '0'),
                    # === END: SỬA LỖI ===
                    'date': r.get('date_created')
                } for r in refunds_data
            ]
        })

    except Exception as e:
        current_app.logger.error(f"Error getting refund details for order {order_id}: {e}")
        return jsonify({'success': False, 'message': f'Không thể lấy chi tiết hoàn tiền: {str(e)}'}), 500


@orders_bp.route('/process_refund/<int:order_id>', methods=['POST'])
@login_required
def process_refund(order_id):
    order = get_visible_orders_query(current_user).filter_by(id=order_id).first_or_404()
    store = order.store
    data = request.get_json()
    if not data or 'amount' not in data: return jsonify({'success': False, 'message': 'Số tiền hoàn là bắt buộc.'}), 400
    try:
        amount_to_refund = Decimal(data['amount'])
        if amount_to_refund <= 0: return jsonify({'success': False, 'message': 'Số tiền hoàn phải lớn hơn 0.'}), 400
    except Exception:
        return jsonify({'success': False, 'message': 'Số tiền không hợp lệ.'}), 400
    reason = data.get('reason', '')
    api_refund_flag = data.get('api_refund', True)
    try:
        wcapi = API(url=store.store_url, consumer_key=store.consumer_key, consumer_secret=store.consumer_secret, version="wc/v3", timeout=30)
        refund_payload = {'amount': str(amount_to_refund),'reason': reason,'api_refund': api_refund_flag }
        response = wcapi.post(f"orders/{order.wc_order_id}/refunds", refund_payload)
        if response.status_code == 201:
            from app.worker import check_single_store_job
            check_single_store_job(current_app._get_current_object(), store.id)
            return jsonify({'success': True, 'message': 'Yêu cầu hoàn tiền đã được xử lý thành công!'})
        else:
            return jsonify({'success': False, 'message': response.json().get('message', 'Lỗi WooCommerce.')}), response.status_code
    except Exception as e:
        current_app.logger.error(f"Error processing refund for order {order_id}: {e}")
        return jsonify({'success': False, 'message': f'Lỗi kết nối: {str(e)}'}), 500