# app/settings/routes.py

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
from . import settings_bp
from .forms import (
    TelegramSettingsForm, WorkerSettingsForm, OrderTableSettingsForm, 
    TemplateSettingsForm, UserSettingsForm
)
from app import db, worker
from app.models import Setting, AppUser
from app.decorators import super_admin_required
from app.notifications import send_telegram_message
import json
import asyncio

@settings_bp.route('/system', methods=['GET', 'POST'])
@login_required
@super_admin_required
def system():
    # Khởi tạo tất cả các form với prefix để WTForms tự tạo name riêng biệt
    telegram_form = TelegramSettingsForm(prefix='telegram')
    worker_form = WorkerSettingsForm(prefix='worker')
    table_form = OrderTableSettingsForm(prefix='table')
    template_form = TemplateSettingsForm(prefix='template')

    # MODIFIED: Check for the WTForms-generated name (prefix-fieldname)
    if request.method == 'POST':
        # Check which form was submitted by looking for its submit button's name
        if 'telegram-submit' in request.form and telegram_form.validate_on_submit():
            save_setting('TELEGRAM_BOT_TOKEN', telegram_form.telegram_bot_token.data or '')
            save_setting('TELEGRAM_CHAT_ID', telegram_form.telegram_chat_id.data or '')
            save_setting('TELEGRAM_SEND_DELAY_SECONDS', telegram_form.telegram_send_delay_seconds.data)
            flash('Đã lưu cài đặt Telegram!', 'success')
        
        elif 'worker-submit' in request.form and worker_form.validate_on_submit():
            old_interval_setting = Setting.query.get('CHECK_INTERVAL_MINUTES')
            old_interval = old_interval_setting.value if old_interval_setting else None
            new_interval = worker_form.check_interval_minutes.data
            
            if old_interval and old_interval != str(new_interval):
                 worker.init_scheduler(current_app._get_current_object())
                 flash(f'Đã cập nhật chu kỳ Worker thành {new_interval} phút.', 'info')
            
            save_setting('CHECK_INTERVAL_MINUTES', new_interval)
            save_setting('FETCH_PRODUCT_IMAGES', worker_form.fetch_product_images.data)
            flash('Đã lưu cài đặt Worker & Dữ liệu!', 'success')

        elif 'table-submit' in request.form and table_form.validate_on_submit():
            save_setting('ORDER_TABLE_COLUMNS', table_form.order_table_columns.data)
            flash('Đã lưu cấu hình bảng đơn hàng!', 'success')

        elif 'template-submit' in request.form and template_form.validate_on_submit():
            save_setting('TELEGRAM_TEMPLATE_NEW_ORDER', template_form.telegram_template_new_order.data)
            save_setting('TELEGRAM_TEMPLATE_SYSTEM_TEST', template_form.telegram_template_system_test.data)
            flash('Đã lưu cấu hình Template!', 'success')
            
        return redirect(url_for('settings.system'))

    # Process GET request to populate forms with data from DB
    settings = {s.key: s.value for s in Setting.query.all()}
    
    telegram_form.telegram_bot_token.data = settings.get('TELEGRAM_BOT_TOKEN')
    telegram_form.telegram_chat_id.data = settings.get('TELEGRAM_CHAT_ID')
    telegram_form.telegram_send_delay_seconds.data = int(settings.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
    
    worker_form.check_interval_minutes.data = int(settings.get('CHECK_INTERVAL_MINUTES', 5))
    worker_form.fetch_product_images.data = settings.get('FETCH_PRODUCT_IMAGES', 'false').lower() == 'true'

    template_form.telegram_template_new_order.data = settings.get('TELEGRAM_TEMPLATE_NEW_ORDER')
    template_form.telegram_template_system_test.data = settings.get('TELEGRAM_TEMPLATE_SYSTEM_TEST')

    DEFAULT_COLUMNS = [
        {'key': 'wc_order_id', 'label': 'Mã ĐH', 'visible': True, 'type': 'numeric', 'width': '90px'},
        {'key': 'store_name', 'label': 'Cửa hàng', 'visible': True, 'type': 'text', 'width': '15%'},
        {'key': 'owner_username', 'label': 'Người dùng', 'visible': False, 'type': 'text', 'width': '120px'},
        {'key': 'customer_name', 'label': 'Khách hàng', 'visible': True, 'type': 'text', 'width': '15%'},
        {'key': 'products', 'label': 'Sản phẩm & Biến thể', 'visible': True, 'type': 'custom', 'width': '35%'},
        {'key': 'total', 'label': 'Tổng tiền', 'visible': True, 'type': 'currency', 'width': '120px'},
        {'key': 'shipping_total', 'label': 'Phí Ship', 'visible': False, 'type': 'currency', 'width': '100px'},
        {'key': 'status', 'label': 'Trạng thái', 'visible': True, 'type': 'badge', 'width': '120px'},
        {'key': 'payment_method_title', 'label': 'Thanh toán', 'visible': True, 'type': 'text', 'width': '120px'},
        {'key': 'order_created_at', 'label': 'Ngày tạo', 'visible': True, 'type': 'datetime', 'width': '140px'},
    ]
    order_columns_config = get_or_create_column_config(DEFAULT_COLUMNS)
    
    enable_registration_status = settings.get('ENABLE_REGISTRATION', 'false').lower() == 'true'

    return render_template(
        'settings/system_settings.html', 
        title='Cài đặt Hệ thống', 
        telegram_form=telegram_form,
        worker_form=worker_form,
        table_form=table_form,
        template_form=template_form,
        enable_registration_status=enable_registration_status, 
        order_columns_config=order_columns_config
    )

def save_setting(key, value):
    """Helper function to save a setting to the DB."""
    setting = Setting.query.get(key.upper())
    str_value = str(value)
    if setting:
        if setting.value != str_value:
            setting.value = str_value
    else:
        db.session.add(Setting(key=key.upper(), value=str_value))
    db.session.commit()

def get_or_create_column_config(default_columns):
    """Helper function to get or create/update the column configuration."""
    setting = Setting.query.get('ORDER_TABLE_COLUMNS')
    if not setting or not setting.value:
        config = default_columns
        save_setting('ORDER_TABLE_COLUMNS', json.dumps(config))
        return config
    
    saved_config = json.loads(setting.value)
    saved_keys = {c['key'] for c in saved_config}
    needs_update = False
    
    for i, saved_col in enumerate(saved_config):
        default_col = next((c for c in default_columns if c['key'] == saved_col['key']), None)
        if default_col:
            for prop in ['label', 'type', 'width']:
                if prop not in saved_col:
                    saved_config[i][prop] = default_col[prop]
                    needs_update = True
    
    for default_col in default_columns:
        if default_col['key'] not in saved_keys:
            saved_config.append(default_col)
            needs_update = True
    
    if needs_update:
        save_setting('ORDER_TABLE_COLUMNS', json.dumps(saved_config))
        
    return saved_config
    
@settings_bp.route('/system/toggle_registration', methods=['POST'])
@login_required
@super_admin_required
def toggle_registration():
    setting = Setting.query.get('ENABLE_REGISTRATION')
    if not setting:
        db.session.add(Setting(key='ENABLE_REGISTRATION', value='false'))
        db.session.commit()
        setting = Setting.query.get('ENABLE_REGISTRATION')

    current_status = setting.value.lower() == 'true'
    setting.value = str(not current_status)
    db.session.commit()
    flash(f'Chức năng đăng ký đã được {"Tắt" if current_status else "Bật"}.', 'success')
    return redirect(url_for('settings.system'))

@settings_bp.route('/system/test_telegram', methods=['POST'])
@login_required
@super_admin_required
def test_system_telegram():
    asyncio.run(send_telegram_message(message_type='system_test', data={}, user_id=current_user.id))
    flash('Đã gửi tin nhắn thử đến kênh hệ thống.', 'info')
    return redirect(url_for('settings.system'))

@settings_bp.route('/personal', methods=['GET', 'POST'])
@login_required
def personal():
    form = UserSettingsForm()
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
        flash('Đã lưu cài đặt cá nhân của bạn.', 'success')
        return redirect(url_for('settings.personal'))
        
    form.telegram_bot_token.data = current_user.telegram_bot_token
    form.telegram_chat_id.data = current_user.telegram_chat_id
    form.telegram_enabled.data = current_user.telegram_enabled
    if current_user.can_customize_telegram_delay:
        form.telegram_send_delay_seconds.data = current_user.telegram_send_delay_seconds
    if current_user.can_customize_telegram_templates:
        form.telegram_template_new_order.data = current_user.telegram_template_new_order
        form.telegram_template_user_test.data = current_user.telegram_template_user_test
    return render_template('settings/user_settings.html', title='Cài đặt Cá nhân', form=form)

@settings_bp.route('/personal/test_telegram', methods=['POST'])
@login_required
def test_personal_telegram():
    if not current_user.telegram_enabled or not current_user.telegram_chat_id:
        flash('Vui lòng bật và điền Chat ID Telegram cá nhân trước khi thử.', 'warning')
        return redirect(url_for('settings.personal'))
        
    asyncio.run(send_telegram_message(message_type='user_test', data={}, user_id=current_user.id))
    flash('Đã gửi tin nhắn thử đến kênh cá nhân của bạn.', 'info')
    return redirect(url_for('settings.personal'))