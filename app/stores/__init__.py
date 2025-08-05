# app/stores/__init__.py

from flask import Blueprint

# Tạo một Blueprint tên là 'stores'.
# Tên này sẽ được dùng trong các hàm url_for, ví dụ: url_for('stores.manage')
stores_bp = Blueprint('stores', __name__)

# Import file routes của module stores để đăng ký các route vào blueprint này.
from . import routes