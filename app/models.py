# app/models.py
from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import json

class AppUser(UserMixin, db.Model):
    __tablename__ = 'app_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    can_add_store = db.Column(db.Boolean, default=False, nullable=False)
    can_delete_store = db.Column(db.Boolean, default=False, nullable=False)
    can_edit_store = db.Column(db.Boolean, default=False, nullable=False)
    can_view_orders = db.Column(db.Boolean, default=False, nullable=False)
    telegram_bot_token = db.Column(db.String(255), nullable=True)
    telegram_chat_id = db.Column(db.String(255), nullable=True)
    telegram_enabled = db.Column(db.Boolean, default=False, nullable=False)
    telegram_send_delay_seconds = db.Column(db.Integer, nullable=True)
    can_customize_telegram_templates = db.Column(db.Boolean, default=False, nullable=False)
    can_customize_telegram_delay = db.Column(db.Boolean, default=False, nullable=False)
    telegram_template_new_order = db.Column(db.Text, nullable=True)
    telegram_template_user_test = db.Column(db.Text, nullable=True)
    stores = db.relationship('WooCommerceStore', backref='owner', lazy='dynamic', cascade="all, delete-orphan")
    children = db.relationship('AppUser', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    # === START: Thêm relationship tới Design ===
    designs = db.relationship('Design', backref='owner', lazy='dynamic', cascade="all, delete-orphan")
    # === END: Thêm relationship tới Design ===
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def is_super_admin(self): return self.role == 'super_admin'
    def is_admin(self): return self.role == 'admin'

class WooCommerceStore(db.Model):
    __tablename__ = 'woocommerce_store'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    store_url = db.Column(db.String(255), nullable=False, unique=True)
    consumer_key = db.Column(db.String(255), nullable=False)
    consumer_secret = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_checked = db.Column(db.DateTime(timezone=True), default=None, nullable=True)
    note = db.Column(db.Text, nullable=True)
    orders = db.relationship('WooCommerceOrder', backref='store', lazy='dynamic', cascade="all, delete-orphan")
    def __repr__(self): return f'<WooCommerceStore {self.name}>'

class WooCommerceOrder(db.Model):
    __tablename__ = 'woocommerce_order'
    id = db.Column(db.Integer, primary_key=True)
    wc_order_id = db.Column(db.Integer, nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('woocommerce_store.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    total = db.Column(db.Float, nullable=False)
    customer_name = db.Column(db.String(255), nullable=True)
    payment_method_title = db.Column(db.String(100), nullable=True)
    order_created_at = db.Column(db.DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    order_modified_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    shipping_total = db.Column(db.Float, nullable=True)
    customer_note = db.Column(db.Text, nullable=True)
    billing_phone = db.Column(db.String(100), nullable=True)
    billing_email = db.Column(db.String(255), nullable=True)
    billing_address = db.Column(db.String(500), nullable=True)
    shipping_address = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)
    line_items = db.relationship('OrderLineItem', backref='order', cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint('wc_order_id', 'store_id', name='_wc_order_store_uc'),)
    def __repr__(self): return f'<WooCommerceOrder ID:{self.wc_order_id} from Store ID:{self.store_id}>'

class OrderLineItem(db.Model):
    __tablename__ = 'order_line_item'
    id = db.Column(db.Integer, primary_key=True)
    wc_line_item_id = db.Column(db.Integer, nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('woocommerce_order.id'), nullable=False)
    product_name = db.Column(db.String(500), nullable=False)
    sku = db.Column(db.String(100), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(1000), nullable=True)
    variations = db.Column(db.Text, nullable=True)
    def __repr__(self): return f'<LineItem {self.product_name} for Order ID:{self.order_id}>'
    @property
    def variations_list(self):
        if not self.variations: return []
        try: return json.loads(self.variations)
        except json.JSONDecodeError: return []

class Setting(db.Model):
    __tablename__ = 'setting'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    @classmethod
    def get_value(cls, key, default=None):
        setting = cls.query.get(key)
        return setting.value if setting else default
    @classmethod
    def set_value(cls, key, value):
        setting = cls.query.get(key)
        if setting: setting.value = str(value)
        else:
            setting = cls(key=key, value=str(value))
            db.session.add(setting)
        db.session.commit()

class BackgroundTask(db.Model):
    __tablename__ = 'background_task'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), index=True, unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    user = db.relationship('AppUser')
    start_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='queued', index=True)
    progress = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    log = db.Column(db.Text)
    requested_cancellation = db.Column(db.Boolean, default=False)
    def __repr__(self): return f'<Task {self.name} {self.id}>'

# === START: THÊM MODEL MỚI CHO DESIGN ===
class Design(db.Model):
    __tablename__ = 'design'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), index=True, nullable=False)
    image_url = db.Column(db.String(1000), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Design {self.name}>'
# === END: THÊM MODEL MỚI CHO DESIGN ===

# === START: THÊM MODEL MỚI CHO FULFILLMENT SETTING ===
class FulfillmentSetting(db.Model):
    __tablename__ = 'fulfillment_setting'
    id = db.Column(db.Integer, primary_key=True)
    provider_name = db.Column(db.String(50), nullable=False, index=True) # VD: "mangotee"
    api_key = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'provider_name', name='_user_provider_uc'),)

    def __repr__(self):
        return f'<FulfillmentSetting for User ID {self.user_id} - {self.provider_name}>'
# === END: THÊM MODEL MỚI CHO FULFILLMENT SETTING ===