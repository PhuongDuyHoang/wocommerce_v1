# app/notifications.py

import asyncio
import httpx
from jinja2 import Environment, TemplateError
import re

from .models import AppUser, Setting, db

def escape_markdown_v2(text: str) -> str:
    """Hàm thoát các ký tự đặc biệt cho định dạng MarkdownV2 của Telegram."""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def send_test_telegram_message(bot_token: str, chat_id: str, template_content: str) -> (bool, str):
    """
    Hàm chuyên dụng để gửi một tin nhắn thử nghiệm cho một template cụ thể.
    Sử dụng dữ liệu mẫu và trả về (status, message).
    """
    if not bot_token or not chat_id:
        return False, "Bot Token hoặc Chat ID không được để trống."

    dummy_data = {
        "store_name": "Cửa hàng Test",
        "order_id": 12345,
        "customer_name": "Nguyễn Văn A",
        "total_amount": "$99.99",
        "currency": "USD",
        "status": "processing",
        "payment_method": "Chuyển khoản ngân hàng",
        "product_list": escape_markdown_v2("- 1x Áo Thun Thử Nghiệm (Size: M)\n- 2x Quần Jean Mẫu (Màu: Xanh)")
    }
    
    render_data = {}
    for key, value in dummy_data.items():
        render_data[key] = escape_markdown_v2(value) if key != 'product_list' else value

    try:
        jinja_env = Environment()
        template = jinja_env.from_string(template_content)
        message = template.render(render_data)
    except TemplateError as e:
        return False, f"Lỗi cú pháp Template: {e}"
    except Exception as e:
        return False, f"Lỗi không xác định khi render template: {e}"

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'MarkdownV2'}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10)

        if response.status_code >= 400:
            return False, f"Lỗi từ API Telegram ({response.status_code}): {response.text}"
        else:
            return True, "Gửi tin nhắn thử thành công!"
    except Exception as e:
        return False, f"Lỗi khi kết nối đến Telegram: {e}"

async def send_telegram_message(app, message_type: str, data: dict, user_id: int):
    """
    Hàm gửi tin nhắn Telegram thông minh.
    MODIFIED: Cải thiện logic xác định người nhận và thêm log chi tiết.
    """
    with app.app_context():
        system_settings = {s.key: s.value for s in Setting.query.all()}
        system_bot_token = system_settings.get('TELEGRAM_BOT_TOKEN')
        system_chat_id = system_settings.get('TELEGRAM_CHAT_ID')
        jinja_env = Environment()

        if message_type == 'system_test':
            # ... (Phần này giữ nguyên)
            return

        event_user = db.session.get(AppUser, user_id)
        if not event_user:
            print(f"Thông báo: Không tìm thấy người dùng với ID {user_id} để gửi thông báo.")
            return

        unique_send_tasks = set()
        
        # --- LOGIC MỚI: Xử lý người nhận cho đơn hàng mới ---
        if message_type == 'new_order':
            print(f"--- Bắt đầu xử lý thông báo đơn hàng cho user: '{event_user.username}' ---")
            potential_recipients = []
            
            # 1. Thêm chính người dùng sở hữu cửa hàng
            potential_recipients.append(event_user)
            print(f"[+] Đã thêm user '{event_user.username}' vào danh sách nhận tin.")

            # 2. Thêm admin quản lý của người dùng đó (nếu có)
            if event_user.parent and event_user.parent.is_admin():
                potential_recipients.append(event_user.parent)
                print(f"[+] Đã thêm admin quản lý '{event_user.parent.username}' vào danh sách nhận tin.")
            else:
                print(f"[-] User '{event_user.username}' không có admin quản lý hoặc người quản lý không phải vai trò 'admin'.")

            # 3. Luôn gửi một bản sao đến kênh hệ thống (nếu được cấu hình)
            if system_bot_token and system_chat_id:
                # Tạo một "người nhận ảo" cho hệ thống để xử lý chung
                system_recipient = AppUser(username="System", telegram_bot_token=system_bot_token, telegram_chat_id=system_chat_id, telegram_enabled=True)
                system_recipient.can_customize_telegram_delay = False # Hệ thống dùng delay mặc định
                system_recipient.can_customize_telegram_templates = False # Hệ thống dùng template mặc định
                potential_recipients.append(system_recipient)
                print("[+] Đã thêm kênh hệ thống vào danh sách nhận tin.")

            # 4. Lọc danh sách người nhận và tạo tác vụ gửi tin
            for user in potential_recipients:
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
                            print(f"    -> Đã tạo tác vụ gửi tin cho '{user.username}' đến chat_id: {chat_id_to_use}")
                else:
                    print(f"    -> Bỏ qua '{user.username}' vì chưa bật hoặc chưa cấu hình Telegram.")
            print("-----------------------------------------------------------------")
        
        # --- Logic cho user test (giữ nguyên) ---
        elif message_type == 'user_test':
            if event_user.telegram_enabled and event_user.telegram_chat_id:
                token_to_use = event_user.telegram_bot_token or system_bot_token
                template_content = system_settings.get(f'DEFAULT_TELEGRAM_TEMPLATE_{message_type.upper()}', app.config.get(f'DEFAULT_TELEGRAM_TEMPLATE_{message_type.upper()}'))
                unique_send_tasks.add((token_to_use, event_user.telegram_chat_id, 0, template_content))

        if not unique_send_tasks:
            print(f"Thông báo: Không có tác vụ gửi tin nào được tạo cho sự kiện '{message_type}' của user ID {user_id}.")
            return

        # --- Phần gửi tin nhắn (giữ nguyên) ---
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