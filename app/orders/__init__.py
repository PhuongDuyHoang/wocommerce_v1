# app/orders/__init__.py

from flask import Blueprint

# Tạo một Blueprint tên là 'orders'.
# Tên này sẽ được dùng trong các hàm url_for, ví dụ: url_for('orders.manage_all_orders')
orders_bp = Blueprint('orders', __name__)

# Import file routes của module orders để đăng ký các route vào blueprint này.
from . import routes