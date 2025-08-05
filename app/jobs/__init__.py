# app/jobs/__init__.py

from flask import Blueprint

# Tạo một Blueprint tên là 'jobs'.
# Tên này sẽ được dùng trong các hàm url_for, ví dụ: url_for('jobs.view')
jobs_bp = Blueprint('jobs', __name__)

# Import file routes của module jobs để đăng ký các route vào blueprint này.
from . import routes