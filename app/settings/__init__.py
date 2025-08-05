# app/settings/__init__.py

from flask import Blueprint

# Tạo một Blueprint tên là 'settings'.
# Tên này sẽ được dùng trong các hàm url_for, ví dụ: url_for('settings.system')
settings_bp = Blueprint('settings', __name__)

# Import file routes của module settings để đăng ký các route vào blueprint này.
from . import routes