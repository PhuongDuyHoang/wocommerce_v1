# app/notifications.py

import asyncio
import httpx
from jinja2 import Environment
from flask import current_app

from . import db
from .models import AppUser, Setting

async def send_telegram_message(message_type: str, data: dict, user_id: int):
    """
    Hàm gửi tin nhắn Telegram thông minh, có khả năng gửi đến nhiều người nhận
    (chủ sở hữu, admin quản lý, kênh hệ thống) và ưu tiên cài đặt cá nhân.

    Args:
        message_type: Loại tin nhắn (vd: 'new_order', 'system_test').
        data: Dict chứa dữ liệu để render vào template.
        user_id: ID của người dùng sở hữu đối tượng gây ra sự kiện (vd: chủ cửa hàng).
    """
    app = current_app._get_current_object()
    with app.app_context():
        # --- Bước 1: Lấy thông tin cài đặt hệ thống ---
        system_settings = {s.key: s.value for s in Setting.query.all()}
        system_bot_token = system_settings.get('TELEGRAM_BOT_TOKEN')
        system_chat_id = system_settings.get('TELEGRAM_CHAT_ID')
        
        # --- Bước 2: Xác định tất cả người nhận tiềm năng ---
        recipients = []
        owner = AppUser.query.get(user_id) if user_id else None

        if owner:
            recipients.append(owner)
            # Thêm admin quản lý nếu có
            if owner.parent and owner.parent.is_admin():
                recipients.append(owner.parent)

        # --- Bước 3: Xây dựng danh sách gửi tin duy nhất để tránh gửi lặp ---
        # Mỗi item là một tuple: (bot_token, chat_id, delay, template_content)
        unique_send_tasks = set()

        # Thêm các kênh cá nhân vào danh sách
        for user in recipients:
            if user.telegram_enabled and user.telegram_bot_token and user.telegram_chat_id:
                delay = user.telegram_send_delay_seconds if user.can_customize_telegram_delay and user.telegram_send_delay_seconds is not None else int(system_settings.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
                
                template = None
                if user.can_customize_telegram_templates:
                    template = getattr(user, f'telegram_template_{message_type}', None)
                
                # Nếu không có template cá nhân, dùng template hệ thống
                if not template:
                    template = system_settings.get(f'telegram_template_{message_type}')

                if template:
                    unique_send_tasks.add((
                        user.telegram_bot_token,
                        user.telegram_chat_id,
                        delay,
                        template
                    ))

        # Luôn thêm kênh hệ thống vào danh sách (nếu được cấu hình)
        if system_bot_token and system_chat_id:
            system_delay = int(system_settings.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
            system_template = system_settings.get(f'telegram_template_{message_type}')
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
        
        # Thêm biến mặc định cho các template test
        data.setdefault('username', owner.username if owner else 'N/A')
        data.setdefault('bot_username', 'BotHeThong') # Placeholder

        async with httpx.AsyncClient() as client:
            for token, chat_id, delay, template_content in unique_send_tasks:
                try:
                    template = jinja_env.from_string(template_content)
                    message = template.render(data)
                    
                    # API URL của Telegram
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = {
                        'chat_id': chat_id,
                        'text': message,
                        'parse_mode': 'Markdown' # Hoặc 'HTML' nếu bạn thích
                    }
                    
                    response = await client.post(url, json=payload, timeout=10)
                    response.raise_for_status() # Ném lỗi nếu request không thành công
                    
                    print(f"Đã gửi thông báo đến chat_id: {chat_id}")
                    
                    # Áp dụng độ trễ
                    if delay > 0:
                        await asyncio.sleep(delay)
                        
                except Exception as e:
                    print(f"LỖI khi gửi thông báo đến chat_id {chat_id}: {e}")