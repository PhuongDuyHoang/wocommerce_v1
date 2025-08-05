# app/users/__init__.py

from flask import Blueprint

# Tạo một Blueprint tên là 'users'.
# Tên này sẽ được dùng trong các hàm url_for, ví dụ: url_for('users.manage')
users_bp = Blueprint('users', __name__)

# Import file routes của module users để đăng ký các route vào blueprint này.
from . import routes