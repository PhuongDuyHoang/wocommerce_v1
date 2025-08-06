# app/notifications.py

import asyncio
import httpx
from jinja2 import Environment
# MODIFIED: Removed current_app from here, as we will pass the app instance directly.
# from flask import current_app 

from . import db
from .models import AppUser, Setting

# MODIFIED: The function now accepts the 'app' instance as its first argument.
async def send_telegram_message(app, message_type: str, data: dict, user_id: int):
    """
    Hàm gửi tin nhắn Telegram thông minh, có khả năng gửi đến nhiều người nhận
    (chủ sở hữu, admin quản lý, kênh hệ thống) và ưu tiên cài đặt cá nhân.

    Args:
        app: The Flask application instance.
        message_type: Loại tin nhắn (vd: 'new_order', 'system_test').
        data: Dict chứa dữ liệu để render vào template.
        user_id: ID của người dùng sở hữu đối tượng gây ra sự kiện (vd: chủ cửa hàng).
    """
    # MODIFIED: The app_context is now created from the passed 'app' object.
    with app.app_context():
        # --- Bước 1: Lấy thông tin cài đặt hệ thống ---
        system_settings = {s.key: s.value for s in Setting.query.all()}
        system_bot_token = system_settings.get('TELEGRAM_BOT_TOKEN')
        system_chat_id = system_settings.get('TELEGRAM_CHAT_ID')
        
        # --- Bước 2: Xác định tất cả người nhận tiềm năng ---
        recipients = []
        owner = db.session.get(AppUser, user_id) if user_id else None

        if owner:
            recipients.append(owner)
            if owner.parent and owner.parent.is_admin():
                recipients.append(owner.parent)

        # --- Bước 3: Xây dựng danh sách gửi tin duy nhất để tránh gửi lặp ---
        unique_send_tasks = set()

        for user in recipients:
            if user.telegram_enabled:
                # Ưu tiên thông tin cá nhân, nếu không có thì dùng của hệ thống
                token_to_use = user.telegram_bot_token or system_bot_token
                chat_id_to_use = user.telegram_chat_id # Người dùng cá nhân phải có chat_id riêng
                
                if token_to_use and chat_id_to_use:
                    delay = user.telegram_send_delay_seconds if user.can_customize_telegram_delay and user.telegram_send_delay_seconds is not None else int(system_settings.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
                    
                    template = None
                    if user.can_customize_telegram_templates:
                        template = getattr(user, f'telegram_template_{message_type}', None)
                    
                    if not template:
                        template = system_settings.get(f'DEFAULT_TELEGRAM_TEMPLATE_{message_type.upper()}')

                    if template:
                        unique_send_tasks.add((
                            token_to_use,
                            chat_id_to_use,
                            delay,
                            template
                        ))

        # Luôn thêm kênh hệ thống nếu là tin nhắn thử của hệ thống
        if message_type == 'system_test' and system_bot_token and system_chat_id:
            system_delay = int(system_settings.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
            system_template = system_settings.get('DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST')
            if system_template:
                 unique_send_tasks.add((
                    system_bot_token,
                    system_chat_id,
                    system_delay,
                    system_template
                ))
        
        if not unique_send_tasks:
            print("Thông báo: Không có người nhận Telegram nào được cấu hình cho sự kiện này.")
            return

        # --- Bước 4: Render và gửi tin nhắn ---
        jinja_env = Environment()
        
        data.setdefault('username', owner.username if owner else 'N/A')
        data.setdefault('bot_username', 'BotHeThong')

        async with httpx.AsyncClient() as client:
            for token, chat_id, delay, template_content in unique_send_tasks:
                try:
                    template = jinja_env.from_string(template_content)
                    message = template.render(data)
                    
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = {
                        'chat_id': chat_id,
                        'text': message,
                        'parse_mode': 'MarkdownV2' # Sử dụng MarkdownV2 cho an toàn
                    }
                    
                    response = await client.post(url, json=payload, timeout=10)

                    if response.status_code >= 400:
                        print(f"Lỗi từ API Telegram ({response.status_code}) cho chat_id {chat_id}: {response.text}")
                    else:
                        print(f"Đã gửi thông báo đến chat_id: {chat_id}")
                    
                    if delay > 0:
                        await asyncio.sleep(delay)
                        
                except Exception as e:
                    print(f"LỖI khi gửi thông báo đến chat_id {chat_id}: {e}")