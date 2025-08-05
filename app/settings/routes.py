# app/settings/routes.py

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
import asyncio
import json

from . import settings_bp
from .forms import SystemSettingsForm, UserSettingsForm
from app import db, worker
from app.models import Setting
from app.decorators import super_admin_required
from app.notifications import send_telegram_message

@settings_bp.route('/system', methods=['GET', 'POST'])
@login_required
@super_admin_required
def system():
    """Trang cài đặt toàn bộ hệ thống cho Super Admin."""
    form = SystemSettingsForm()

    # ### PHẦN 1: ĐỊNH NGHĨA CẤU TRÚC CỘT MẶC ĐỊNH ###
    DEFAULT_COLUMNS = [
        {'key': 'order_created_at', 'label': 'Ngày tạo', 'visible': True, 'type': 'datetime'},
        {'key': 'store_name', 'label': 'Cửa hàng', 'visible': True, 'type': 'text'},
        {'key': 'owner_username', 'label': 'Người dùng', 'visible': True, 'type': 'text'},
        {'key': 'wc_order_id', 'label': 'Mã ĐH', 'visible': True, 'type': 'text'},
        {'key': 'customer_name', 'label': 'Khách hàng', 'visible': True, 'type': 'text'},
        {'key': 'total', 'label': 'Tổng tiền', 'visible': True, 'type': 'currency'},
        {'key': 'status', 'label': 'Trạng thái', 'visible': True, 'type': 'status'},
        {'key': 'payment_method_title', 'label': 'Thanh toán', 'visible': False, 'type': 'text'},
        {'key': 'products', 'label': 'Sản phẩm', 'visible': True, 'type': 'products'},
    ]
    
    if form.validate_on_submit():
        # ### PHẦN 2: CẬP NHẬT LOGIC LƯU CÀI ĐẶT ###
        settings_to_update = {
            'TELEGRAM_BOT_TOKEN': form.telegram_bot_token.data,
            'TELEGRAM_CHAT_ID': form.telegram_chat_id.data,
            'TELEGRAM_SEND_DELAY_SECONDS': str(form.telegram_send_delay_seconds.data),
            'CHECK_INTERVAL_MINUTES': str(form.check_interval_minutes.data),
            'telegram_template_new_order': form.telegram_template_new_order.data,
            'telegram_template_system_test': form.telegram_template_system_test.data,
            'ORDER_TABLE_COLUMNS': form.order_table_columns.data # Thêm cài đặt mới
        }

        original_interval_setting = Setting.query.get('CHECK_INTERVAL_MINUTES')
        original_interval = original_interval_setting.value if original_interval_setting else None

        for key, value in settings_to_update.items():
            setting = Setting.query.get(key)
            if setting:
                setting.value = value
            else:
                db.session.add(Setting(key=key, value=value))
        
        db.session.commit()

        if original_interval != str(form.check_interval_minutes.data):
            worker.init_scheduler(current_app._get_current_object())
            flash('Chu kỳ kiểm tra đã được cập nhật và bộ lập lịch đã được khởi động lại.', 'info')

        flash('Cài đặt hệ thống đã được lưu thành công!', 'success')
        return redirect(url_for('settings.system'))

    # ### PHẦN 3: CẬP NHẬT LOGIC TẢI CÀI ĐẶT (CHO GET REQUEST) ###
    if request.method == 'GET':
        settings_from_db = {s.key: s.value for s in Setting.query.all()}
        form.telegram_bot_token.data = settings_from_db.get('TELEGRAM_BOT_TOKEN')
        form.telegram_chat_id.data = settings_from_db.get('TELEGRAM_CHAT_ID')
        form.telegram_send_delay_seconds.data = int(settings_from_db.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
        form.check_interval_minutes.data = int(settings_from_db.get('CHECK_INTERVAL_MINUTES', 5))
        form.telegram_template_new_order.data = settings_from_db.get('telegram_template_new_order')
        form.telegram_template_system_test.data = settings_from_db.get('telegram_template_system_test')
    
    # Xử lý tải hoặc tạo mới cài đặt cột
    order_columns_setting = Setting.query.get('ORDER_TABLE_COLUMNS')
    if not order_columns_setting:
        # Nếu chưa có, tạo cài đặt mặc định và lưu vào DB
        default_columns_json = json.dumps(DEFAULT_COLUMNS, ensure_ascii=False)
        new_setting = Setting(key='ORDER_TABLE_COLUMNS', value=default_columns_json)
        db.session.add(new_setting)
        db.session.commit()
        order_columns_config = DEFAULT_COLUMNS
    else:
        # Nếu có, tải và parse JSON
        try:
            order_columns_config = json.loads(order_columns_setting.value)
        except json.JSONDecodeError:
            order_columns_config = DEFAULT_COLUMNS # Dùng mặc định nếu JSON bị lỗi

    reg_setting = Setting.query.get('ENABLE_REGISTRATION')
    enable_registration_status = (reg_setting.value.lower() == 'true') if reg_setting else False

    return render_template('settings/system_settings.html', 
                           title='Cài đặt Hệ thống', 
                           form=form,
                           enable_registration_status=enable_registration_status,
                           order_columns_config=order_columns_config) # Gửi cấu hình cột ra template


@settings_bp.route('/system/toggle_registration', methods=['POST'])
@login_required
@super_admin_required
def toggle_registration():
    setting = Setting.query.get('ENABLE_REGISTRATION')
    if setting:
        new_value = 'False' if setting.value.lower() == 'true' else 'True'
        setting.value = new_value
        db.session.commit()
        flash(f'Chức năng đăng ký đã được {"BẬT" if new_value == "True" else "TẮT"}.', 'success')
    return redirect(url_for('settings.system'))


@settings_bp.route('/system/test_telegram', methods=['POST'])
@login_required
@super_admin_required
def test_system_telegram():
    try:
        asyncio.run(send_telegram_message(message_type='system_test', data={}, user_id=None))
        flash('Đã gửi tin nhắn kiểm tra. Vui lòng kiểm tra Telegram của bạn.', 'info')
    except Exception as e:
        flash(f'Lỗi khi gửi tin nhắn Telegram: {e}', 'danger')
    return redirect(url_for('settings.system'))


@settings_bp.route('/personal', methods=['GET', 'POST'])
@login_required
def personal():
    form = UserSettingsForm(obj=current_user)
    if form.validate_on_submit():
        current_user.telegram_bot_token = form.telegram_bot_token.data
        current_user.telegram_chat_id = form.telegram_chat_id.data
        current_user.telegram_enabled = form.telegram_enabled.data
        if current_user.can_customize_telegram_delay:
            current_user.telegram_send_delay_seconds = form.telegram_send_delay_seconds.data
        if current_user.can_customize_telegram_templates:
            current_user.telegram_template_new_order = form.telegram_template_new_order.data
            current_user.telegram_template_user_test = form.telegram_template_user_test.data
        db.session.commit()
        flash('Cài đặt cá nhân của bạn đã được lưu thành công!', 'success')
        return redirect(url_for('settings.personal'))
    return render_template('settings/user_settings.html', title='Cài đặt Cá nhân', form=form)


@settings_bp.route('/personal/test_telegram', methods=['POST'])
@login_required
def test_personal_telegram():
    if not current_user.telegram_enabled or not current_user.telegram_bot_token or not current_user.telegram_chat_id:
        flash('Vui lòng bật và điền đầy đủ thông tin Telegram cá nhân trước khi thử.', 'warning')
        return redirect(url_for('settings.personal'))
    try:
        asyncio.run(send_telegram_message(message_type='user_test', data={}, user_id=current_user.id))
        flash('Đã gửi tin nhắn kiểm tra. Vui lòng kiểm tra Telegram của bạn.', 'info')
    except Exception as e:
        flash(f'Lỗi khi gửi tin nhắn Telegram: {e}', 'danger')
    return redirect(url_for('settings.personal'))