# app/models.py
from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class AppUser(UserMixin, db.Model):
    """Mô hình người dùng: Super Admin, Admin, và User."""
    __tablename__ = 'app_user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # Vai trò: 'super_admin', 'admin', 'user'
    role = db.Column(db.String(20), default='user', nullable=False)
    # ID của admin quản lý user này (quan hệ cha-con)
    parent_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # --- CÁC QUYỀN ĐƯỢC ĐIỀU CHỈNH CHO WOOCOMMERCE ---
    can_add_store = db.Column(db.Boolean, default=False, nullable=False)
    can_delete_store = db.Column(db.Boolean, default=False, nullable=False)
    can_edit_store = db.Column(db.Boolean, default=False, nullable=False)
    can_view_orders = db.Column(db.Boolean, default=False, nullable=False) # Quyền xem tất cả đơn hàng

    # --- CÀI ĐẶT CÁ NHÂN (VẪN GIỮ NGUYÊN) ---
    telegram_bot_token = db.Column(db.String(255), nullable=True)
    telegram_chat_id = db.Column(db.String(255), nullable=True)
    telegram_enabled = db.Column(db.Boolean, default=False, nullable=False)
    telegram_send_delay_seconds = db.Column(db.Integer, nullable=True)

    # Quyền tùy chỉnh template và độ trễ
    can_customize_telegram_templates = db.Column(db.Boolean, default=False, nullable=False)
    can_customize_telegram_delay = db.Column(db.Boolean, default=False, nullable=False)

    # Template cá nhân (điều chỉnh cho WooCommerce)
    telegram_template_new_order = db.Column(db.Text, nullable=True)
    telegram_template_user_test = db.Column(db.Text, nullable=True)

    # --- CÁC MỐI QUAN HỆ ---
    # Mối quan hệ với các cửa hàng mà người dùng này sở hữu
    stores = db.relationship('WooCommerceStore', backref='owner', lazy='dynamic', cascade="all, delete-orphan")
    # Mối quan hệ tự tham chiếu để quản lý user con
    children = db.relationship('AppUser', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_super_admin(self):
        return self.role == 'super_admin'

    def is_admin(self):
        return self.role == 'admin'


class WooCommerceStore(db.Model):
    """Mô hình chứa thông tin của một cửa hàng WooCommerce."""
    __tablename__ = 'woocommerce_store'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    store_url = db.Column(db.String(255), nullable=False, unique=True)
    # Trong môi trường production, các khóa này nên được mã hóa
    consumer_key = db.Column(db.String(255), nullable=False)
    consumer_secret = db.Column(db.String(255), nullable=False)
    # ID của người dùng sở hữu cửa hàng này
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False) # Bật/tắt việc kiểm tra cửa hàng này
    # Lần cuối cùng kiểm tra đơn hàng thành công
    last_checked = db.Column(db.DateTime, default=None, nullable=True)
    # Ghi chú
    note = db.Column(db.Text, nullable=True)
    # Timestamp của đơn hàng mới nhất đã được thông báo
    last_notified_order_timestamp = db.Column(db.DateTime, nullable=True)

    # Mối quan hệ với các đơn hàng thuộc cửa hàng này
    orders = db.relationship('WooCommerceOrder', backref='store', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<WooCommerceStore {self.name}>'


class WooCommerceOrder(db.Model):
    """Mô hình chứa thông tin của một đơn hàng được tổng hợp về."""
    __tablename__ = 'woocommerce_order'

    id = db.Column(db.Integer, primary_key=True) # ID tự tăng của DB chúng ta
    wc_order_id = db.Column(db.Integer, nullable=False, index=True) # ID của đơn hàng trên web WooCommerce
    store_id = db.Column(db.Integer, db.ForeignKey('woocommerce_store.id'), nullable=False)

    status = db.Column(db.String(50), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    total = db.Column(db.Float, nullable=False)
    customer_name = db.Column(db.String(255), nullable=True)
    payment_method_title = db.Column(db.String(100), nullable=True)
    # Lưu danh sách sản phẩm dưới dạng JSON text
    products_json = db.Column(db.Text, nullable=True)
    # Thời gian đơn hàng được tạo trên web WooCommerce (lưu ở múi giờ UTC)
    order_created_at = db.Column(db.DateTime, nullable=False, index=True)

    # Thiết lập một constraint để đảm bảo cặp (wc_order_id, store_id) là duy nhất
    __table_args__ = (db.UniqueConstraint('wc_order_id', 'store_id', name='_wc_order_store_uc'),)

    def __repr__(self):
        return f'<WooCommerceOrder ID:{self.wc_order_id} from Store ID:{self.store_id}>'


class Setting(db.Model):
    """Mô hình cài đặt chung của hệ thống (key-value)."""
    __tablename__ = 'setting'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)


class BackgroundTask(db.Model):
    """Mô hình theo dõi các tác vụ chạy nền."""
    __tablename__ = 'background_task'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), index=True, unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(256), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    user = db.relationship('AppUser')
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='queued', index=True)
    progress = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    log = db.Column(db.Text)
    requested_cancellation = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Task {self.name} {self.id}>'