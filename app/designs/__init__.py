# app/designs/__init__.py

from flask import Blueprint

# Tạo một Blueprint tên là 'designs'. 
# Tên này sẽ được dùng trong các hàm url_for, ví dụ: url_for('designs.manage')
designs_bp = Blueprint('designs', __name__)

# Import file routes của module designs để đăng ký các route vào blueprint này.
from . import routes