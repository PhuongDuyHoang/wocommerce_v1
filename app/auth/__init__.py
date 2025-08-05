# app/auth/__init__.py

from flask import Blueprint

# Tạo một Blueprint tên là 'auth'. 
# Tên 'auth' này sẽ được sử dụng để định danh các route trong module này,
# ví dụ: url_for('auth.login').
auth_bp = Blueprint('auth', __name__)

# Import file routes.py ở cuối cùng để đăng ký các route vào blueprint này.
# Việc import ở cuối giúp tránh lỗi circular import.
from . import routes