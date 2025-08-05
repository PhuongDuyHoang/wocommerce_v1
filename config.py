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
    # Độ trễ mặc định giữa các tin nhắn Telegram để tránh bị giới hạn (tính bằng giây)
    DEFAULT_TELEGRAM_SEND_DELAY_SECONDS = int(os.environ.get('DEFAULT_TELEGRAM_SEND_DELAY_SECONDS', '2'))
    # Chu kỳ mặc định để worker kiểm tra đơn hàng mới trên tất cả các cửa hàng (tính bằng phút)
    DEFAULT_CHECK_INTERVAL_MINUTES = int(os.environ.get('DEFAULT_CHECK_INTERVAL_MINUTES', '5'))


    # --- TEMPLATE THÔNG BÁO TELEGRAM MẶC ĐỊNH CHO WOOCOMMERCE ---
    # Lưu ý: Các template này sử dụng cú pháp MarkdownV2 của Telegram.
    # Dấu *bao quanh* để in đậm, `bao quanh` để tạo khối mã đơn dòng.
    # Các ký tự đặc biệt như . ! - phải được thoát bằng dấu \ đứng trước (ví dụ: \. \! \-).

    # Template khi có đơn hàng mới
    DEFAULT_TELEGRAM_TEMPLATE_NEW_ORDER = """🛍️ Cửa hàng *{{ store_name }}* có đơn hàng mới\\!
--------------------------------------
Mã đơn hàng: `{{ order_id }}`
Khách hàng: `{{ customer_name }}`
Tổng tiền: *{{ total_amount }} {{ currency }}*
Trạng thái: `{{ status }}`
Sản phẩm:
{{ product_list }}
--------------------------------------
"""
    # Các biến có thể sử dụng cho template đơn hàng mới:
    # {{ store_name }}: Tên cửa hàng được cấu hình trong hệ thống.
    # {{ order_id }}: ID của đơn hàng từ WooCommerce.
    # {{ customer_name }}: Tên đầy đủ của khách hàng (kết hợp từ first_name và last_name).
    # {{ total_amount }}: Tổng giá trị đơn hàng.
    # {{ currency }}: Đơn vị tiền tệ (ví dụ: VND).
    # {{ status }}: Trạng thái của đơn hàng (ví dụ: processing, completed).
    # {{ payment_method }}: Phương thức thanh toán.
    # {{ product_list }}: Danh sách sản phẩm, mỗi sản phẩm trên một dòng (đã được định dạng sẵn).

    # Template cho tin nhắn thử nghiệm của hệ thống
    DEFAULT_TELEGRAM_TEMPLATE_SYSTEM_TEST = """🎉 Đây là tin nhắn thử từ WooCommerce Aggregator \\(Bot\\: @{{ bot_username }}\)\\. Cấu hình *Hệ thống* của bạn đã hoạt động\\!"""
    # Biến có thể sử dụng: {{ bot_username }}

    # Template cho tin nhắn thử nghiệm của người dùng cá nhân
    DEFAULT_TELEGRAM_TEMPLATE_USER_TEST = """🎉 Đây là tin nhắn thử từ tài khoản của bạn \\({{ username }}\)\\. Cấu hình Telegram của bạn đã hoạt động\\!"""
    # Biến có thể sử dụng: {{ username }}