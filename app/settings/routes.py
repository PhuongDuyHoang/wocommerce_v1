# app/settings/routes.py

from flask import render_template, redirect, url_for, flash, current_app, request, jsonify
from flask_login import current_user, login_required
import json
import asyncio

from . import settings_bp
from .forms import SystemTelegramForm, SystemWorkerForm, PersonalSettingsForm, SystemTableForm, SystemTemplateForm
from app import db, worker
from app.models import Setting, AppUser
from app.notifications import send_telegram_message, send_test_telegram_message
from app.decorators import super_admin_required

@settings_bp.route('/system', methods=['GET', 'POST'])
@login_required
@super_admin_required
def system():
    telegram_form = SystemTelegramForm()
    worker_form = SystemWorkerForm()
    table_form = SystemTableForm()
    template_form = SystemTemplateForm()

    if telegram_form.submit_telegram.data and telegram_form.validate_on_submit():
        Setting.set_value('TELEGRAM_BOT_TOKEN', telegram_form.telegram_bot_token.data)
        Setting.set_value('TELEGRAM_CHAT_ID', telegram_form.telegram_chat_id.data)
        Setting.set_value('TELEGRAM_SEND_DELAY_SECONDS', str(telegram_form.telegram_send_delay_seconds.data))
        flash('Đã cập nhật cài đặt Telegram của hệ thống.', 'success')
        return redirect(url_for('settings.system'))

    if worker_form.submit_worker.data and worker_form.validate_on_submit():
        old_interval = Setting.get_value('CHECK_INTERVAL_MINUTES', '5')
        new_interval = str(worker_form.check_interval_minutes.data)
        
        Setting.set_value('CHECK_INTERVAL_MINUTES', new_interval)
        Setting.set_value('FETCH_PRODUCT_IMAGES', str(worker_form.fetch_product_images.data))
        
        if old_interval != new_interval:
            flash('Đã cập nhật cài đặt Worker. Đang khởi động lại bộ lập lịch...', 'info')
            worker.init_scheduler(current_app._get_current_object())
        else:
            flash('Đã cập nhật cài đặt Worker.', 'success')
            
        return redirect(url_for('settings.system'))

    if table_form.submit_table.data and table_form.validate_on_submit():
        Setting.set_value('ORDER_TABLE_COLUMNS', table_form.order_table_columns.data)
        flash('Đã cập nhật cấu hình bảng đơn hàng.', 'success')
        return redirect(url_for('settings.system'))

    if template_form.submit_template.data and template_form.validate_on_submit():
        Setting.set_value('DEFAULT_TELEGRAM_TEMPLATE_NEW_ORDER', template_form.telegram_template_new_order.data)
        Setting.set_value('DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST', template_form.telegram_template_system_test.data)
        flash('Đã cập nhật các template tin nhắn của hệ thống.', 'success')
        return redirect(url_for('settings.system'))

    # Populate forms on GET request
    if request.method == 'GET':
        telegram_form.telegram_bot_token.data = Setting.get_value('TELEGRAM_BOT_TOKEN', '')
        telegram_form.telegram_chat_id.data = Setting.get_value('TELEGRAM_CHAT_ID', '')
        telegram_form.telegram_send_delay_seconds.data = int(Setting.get_value('TELEGRAM_SEND_DELAY_SECONDS', current_app.config['DEFAULT_TELEGRAM_SEND_DELAY_SECONDS']))
        
        worker_form.check_interval_minutes.data = int(Setting.get_value('CHECK_INTERVAL_MINUTES', current_app.config['DEFAULT_CHECK_INTERVAL_MINUTES']))
        worker_form.fetch_product_images.data = Setting.get_value('FETCH_PRODUCT_IMAGES', 'False').lower() == 'true'

        template_form.telegram_template_new_order.data = Setting.get_value('DEFAULT_TELEGRAM_TEMPLATE_NEW_ORDER', current_app.config['DEFAULT_TELEGRAM_TEMPLATE_NEW_ORDER'])
        template_form.telegram_template_system_test.data = Setting.get_value('DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST', current_app.config['DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST'])

    # === SỬA LỖI: BỌC TRONG TRY-EXCEPT ĐỂ XỬ LÝ DỮ LIỆU HỎNG ===
    try:
        order_columns_config_json = Setting.get_value('ORDER_TABLE_COLUMNS', '[]')
        # Xử lý trường hợp giá trị là None hoặc rỗng
        if not order_columns_config_json:
            order_columns_config_json = '[]'
        order_columns_config = json.loads(order_columns_config_json)
    except (json.JSONDecodeError, TypeError):
        # Bắt lỗi nếu JSON không hợp lệ hoặc giá trị là None
        order_columns_config = []
        flash('Cấu hình cột bảng bị lỗi hoặc không tồn tại, đã tạm thời đặt lại về mặc định.', 'warning')
        # Tự động sửa lỗi bằng cách lưu lại giá trị mặc định vào DB
        Setting.set_value('ORDER_TABLE_COLUMNS', '[]')
    # === KẾT THÚC SỬA LỖI ===
    
    enable_registration_status = Setting.get_value('ENABLE_USER_REGISTRATION', 'False').lower() == 'true'

    return render_template(
        'settings/system_settings.html', 
        title='Cài đặt Hệ thống',
        telegram_form=telegram_form,
        worker_form=worker_form,
        table_form=table_form,
        template_form=template_form,
        order_columns_config=order_columns_config,
        enable_registration_status=enable_registration_status
    )


@settings_bp.route('/personal', methods=['GET', 'POST'])
@login_required
def personal():
    form = PersonalSettingsForm()
    if form.validate_on_submit():
        current_user.telegram_bot_token = form.telegram_bot_token.data
        current_user.telegram_chat_id = form.telegram_chat_id.data
        current_user.telegram_enabled = form.telegram_enabled.data
        
        if current_user.can_customize_telegram_delay:
            current_user.telegram_send_delay_seconds = form.telegram_send_delay_seconds.data
        if current_user.can_customize_telegram_templates:
            current_user.telegram_template_new_order = form.telegram_template_new_order.data

        db.session.commit()
        flash('Đã cập nhật cài đặt cá nhân của bạn.', 'success')
        return redirect(url_for('settings.personal'))

    if request.method == 'GET':
        form.telegram_bot_token.data = current_user.telegram_bot_token
        form.telegram_chat_id.data = current_user.telegram_chat_id
        form.telegram_enabled.data = current_user.telegram_enabled
        
        if current_user.can_customize_telegram_delay:
            form.telegram_send_delay_seconds.data = current_user.telegram_send_delay_seconds
        if current_user.can_customize_telegram_templates:
            form.telegram_template_new_order.data = current_user.telegram_template_new_order

    return render_template('settings/user_settings.html', title='Cài đặt Cá nhân', form=form)


@settings_bp.route('/test-telegram/system', methods=['POST'])
@login_required
@super_admin_required
def test_system_telegram():
    flash('Đã yêu cầu gửi tin nhắn thử đến kênh hệ thống.', 'info')
    app = current_app._get_current_object()
    asyncio.run(send_telegram_message(app=app, message_type='system_test', data={}, user_id=current_user.id))
    return redirect(url_for('settings.system'))

@settings_bp.route('/test-telegram/personal', methods=['POST'])
@login_required
def test_personal_telegram():
    if not current_user.telegram_enabled or not current_user.telegram_chat_id:
        flash('Vui lòng bật và điền đầy đủ thông tin Telegram trước khi thử.', 'danger')
        return redirect(url_for('settings.personal'))
        
    flash('Đã yêu cầu gửi tin nhắn thử đến kênh cá nhân của bạn.', 'info')
    app = current_app._get_current_object()
    asyncio.run(send_telegram_message(app=app, message_type='user_test', data={}, user_id=current_user.id))
    return redirect(url_for('settings.personal'))


@settings_bp.route('/toggle-registration', methods=['POST'])
@login_required
@super_admin_required
def toggle_registration():
    current_status = Setting.get_value('ENABLE_USER_REGISTRATION', 'False').lower() == 'true'
    new_status = not current_status
    Setting.set_value('ENABLE_USER_REGISTRATION', str(new_status))
    flash(f"Đã {'bật' if new_status else 'tắt'} chức năng đăng ký người dùng mới.", "success")
    return redirect(url_for('settings.system'))


@settings_bp.route('/test-template/system/new-order', methods=['POST'])
@login_required
@super_admin_required
def test_system_new_order_template():
    template_content = request.form.get('template_content')
    bot_token = Setting.get_value('TELEGRAM_BOT_TOKEN')
    chat_id = Setting.get_value('TELEGRAM_CHAT_ID')
    
    success, message = asyncio.run(send_test_telegram_message(bot_token, chat_id, template_content))
    return jsonify({'success': success, 'message': message})


@settings_bp.route('/test-template/personal/new-order', methods=['POST'])
@login_required
def test_personal_new_order_template():
    template_content = request.form.get('template_content')
    
    # Ưu tiên token cá nhân, nếu không có thì dùng token hệ thống
    bot_token = current_user.telegram_bot_token or Setting.get_value('TELEGRAM_BOT_TOKEN')
    chat_id = current_user.telegram_chat_id

    if not chat_id:
         return jsonify({'success': False, 'message': 'Bạn phải điền Chat ID cá nhân để thử.'})

    success, message = asyncio.run(send_test_telegram_message(bot_token, chat_id, template_content))
    return jsonify({'success': success, 'message': message})
