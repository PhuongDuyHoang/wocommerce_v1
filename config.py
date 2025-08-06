# config.py
import os
from dotenv import load_dotenv

# Tải các biến từ file .env (nếu có)
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """
    Lớp cấu hình chính cho ứng dụng.
    Các giá trị có thể được lấy từ biến môi trường hoặc đặt giá trị mặc định.
    """
    # --- Cấu hình cơ bản của Flask ---
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ban-se-khong-bao-gio-doan-ra-dau'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'postgresql://woo:PhuongDuy33@localhost:5432/woo'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Cấu hình Telegram Bot (có thể được ghi đè trong Cài đặt hệ thống trên web) ---
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    TELEGRAM_ENABLED = os.environ.get('TELEGRAM_ENABLED', 'False').lower() in ('true', '1', 't')

    # --- Cấu hình tác vụ nền mặc định ---
    DEFAULT_TELEGRAM_SEND_DELAY_SECONDS = int(os.environ.get('DEFAULT_TELEGRAM_SEND_DELAY_SECONDS', '2'))
    DEFAULT_CHECK_INTERVAL_MINUTES = int(os.environ.get('DEFAULT_CHECK_INTERVAL_MINUTES', '5'))


    # --- MODIFIED: Added default Telegram message templates ---
    # Lưu ý: Các template này sử dụng cú pháp MarkdownV2 của Telegram.
    # Các ký tự đặc biệt như ., !, -, # phải được thoát bằng dấu \ đứng trước (ví dụ: \., \!, \-).
    # Điều này rất quan trọng để Telegram không hiểu nhầm là cú pháp định dạng.

    # Template khi có đơn hàng mới
    DEFAULT_TELEGRAM_TEMPLATE_NEW_ORDER = """🛍️ Cửa hàng *{{ store_name }}* có đơn hàng mới\\!
--------------------------------------
Mã ĐH: `#{{ order_id }}`
Khách hàng: `{{ customer_name }}`
Tổng tiền: *{{ total_amount }} {{ currency }}*
Trạng thái: `{{ status }}`
Thanh toán: `{{ payment_method }}`
--------------------------------------
*Sản phẩm:*
{{ product_list }}
"""
    
    # Template cho tin nhắn thử nghiệm của hệ thống
    DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST = """🎉 Đây là tin nhắn thử từ *Hệ thống* của bạn\\. Cấu hình Telegram đã hoạt động chính xác\\!"""
    
    # Template cho tin nhắn thử nghiệm của người dùng cá nhân
    DEFAULT_TELEGRAM_TEMPLATE_USER_TEST = """🎉 Đây là tin nhắn thử từ tài khoản *{{ username }}* của bạn\\. Cấu hình Telegram cá nhân đã hoạt động chính xác\\!"""