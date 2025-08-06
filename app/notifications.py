# app/notifications.py

import asyncio
import httpx
from jinja2 import Environment
import re

from .models import AppUser, Setting, db

def escape_markdown_v2(text: str) -> str:
    """
    Hàm thoát các ký tự đặc biệt cho định dạng MarkdownV2 của Telegram.
    """
    if not isinstance(text, str):
        text = str(text)
    # Các ký tự cần thoát: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def send_telegram_message(app, message_type: str, data: dict, user_id: int):
    """
    Hàm gửi tin nhắn Telegram thông minh.
    MODIFIED: Tách riêng logic cho system_test để đảm bảo nó chỉ gửi đến kênh hệ thống.
    """
    with app.app_context():
        system_settings = {s.key: s.value for s in Setting.query.all()}
        system_bot_token = system_settings.get('TELEGRAM_BOT_TOKEN')
        system_chat_id = system_settings.get('TELEGRAM_CHAT_ID')
        jinja_env = Environment()

        # --- SPECIAL CASE: System Test ---
        # Logic này chỉ chạy khi test kênh hệ thống, hoàn toàn bỏ qua user_id
        if message_type == 'system_test':
            if system_bot_token and system_chat_id:
                try:
                    template_content = system_settings.get('DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST', app.config.get('DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST'))
                    render_data = {'bot_username': escape_markdown_v2('BotHeThong')}
                    template = jinja_env.from_string(template_content)
                    message = template.render(render_data)
                    
                    url = f"https://api.telegram.org/bot{system_bot_token}/sendMessage"
                    payload = {'chat_id': system_chat_id, 'text': message, 'parse_mode': 'MarkdownV2'}
                    
                    async with httpx.AsyncClient() as client:
                        response = await client.post(url, json=payload, timeout=10)
                        if response.status_code >= 400:
                            print(f"Lỗi từ API Telegram ({response.status_code}) cho kênh hệ thống {system_chat_id}: {response.text}")
                        else:
                            print(f"Đã gửi thông báo thử đến kênh hệ thống: {system_chat_id}")
                except Exception as e:
                    print(f"LỖI khi gửi thông báo thử đến kênh hệ thống {system_chat_id}: {e}")
            else:
                print("Thông báo: Không thể gửi tin nhắn thử vì Bot Token hoặc Chat ID của hệ thống chưa được cấu hình.")
            return # Kết thúc hàm ngay sau khi xử lý system_test

        # --- Logic cho các thông báo liên quan đến người dùng ---
        event_user = db.session.get(AppUser, user_id)
        if not event_user:
            print(f"Thông báo: Không tìm thấy người dùng với ID {user_id} để gửi thông báo.")
            return

        unique_send_tasks = set()
        recipients = []

        if message_type == 'new_order':
            recipients.append(event_user)
            if event_user.parent and event_user.parent.is_admin():
                recipients.append(event_user.parent)
        elif message_type == 'user_test':
            recipients.append(event_user)

        # 1. Tạo các tác vụ gửi tin cho User và Admin (nếu có)
        for user in recipients:
            if user.telegram_enabled and user.telegram_chat_id:
                token_to_use = user.telegram_bot_token or system_bot_token
                chat_id_to_use = user.telegram_chat_id
                
                if token_to_use and chat_id_to_use:
                    delay = user.telegram_send_delay_seconds if user.can_customize_telegram_delay and user.telegram_send_delay_seconds is not None else int(system_settings.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
                    
                    template_content = None
                    if user.can_customize_telegram_templates:
                        template_content = getattr(user, f'telegram_template_{message_type}', None)
                    
                    if not template_content:
                        template_content = system_settings.get(f'DEFAULT_TELEGRAM_TEMPLATE_{message_type.upper()}')
                    
                    if not template_content:
                        template_content = app.config.get(f'DEFAULT_TELEGRAM_TEMPLATE_{message_type.upper()}')

                    if template_content:
                        unique_send_tasks.add((token_to_use, chat_id_to_use, delay, template_content))

        # 2. Đối với đơn hàng mới, LUÔN gửi thêm một bản sao đến kênh hệ thống (nếu được cấu hình)
        if message_type == 'new_order' and system_bot_token and system_chat_id:
            system_delay = int(system_settings.get('TELEGRAM_SEND_DELAY_SECONDS', 2))
            system_template = system_settings.get(f'DEFAULT_TELEGRAM_TEMPLATE_{message_type.upper()}', app.config.get(f'DEFAULT_TELEGRAM_TEMPLATE_{message_type.upper()}'))
            if system_template:
                 unique_send_tasks.add((system_bot_token, system_chat_id, system_delay, system_template))
        
        if not unique_send_tasks:
            print(f"Thông báo: Không có người nhận Telegram nào được cấu hình cho sự kiện '{message_type}' của user ID {user_id}.")
            return

        # --- Phần gửi tin nhắn ---
        render_data = {}
        for key, value in data.items():
            render_data[key] = escape_markdown_v2(value) if key != 'product_list' else value
        
        render_data.setdefault('username', escape_markdown_v2(event_user.username))
        render_data.setdefault('bot_username', escape_markdown_v2('BotHeThong'))

        async with httpx.AsyncClient() as client:
            for token, chat_id, delay, template_content in unique_send_tasks:
                try:
                    template = jinja_env.from_string(template_content)
                    message = template.render(render_data)
                    
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'MarkdownV2'}
                    
                    response = await client.post(url, json=payload, timeout=10)

                    if response.status_code >= 400:
                        print(f"Lỗi từ API Telegram ({response.status_code}) cho chat_id {chat_id}: {response.text}")
                    else:
                        print(f"Đã gửi thông báo đến chat_id: {chat_id}")
                    
                    if delay > 0:
                        await asyncio.sleep(delay)
                        
                except Exception as e:
                    print(f"LỖI khi gửi thông báo đến chat_id {chat_id}: {e}")