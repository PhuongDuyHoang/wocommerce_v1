# app/settings/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField, TextAreaField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Optional, NumberRange

# MODIFIED: Split SystemSettingsForm into multiple logical forms

class TelegramSettingsForm(FlaskForm):
    """Form for system-wide Telegram settings."""
    telegram_bot_token = StringField('Bot Token hệ thống', validators=[Optional()])
    telegram_chat_id = StringField('Chat ID kênh hệ thống', validators=[Optional()])
    telegram_send_delay_seconds = IntegerField(
        'Độ trễ gửi tin (giây)',
        default=2,
        validators=[DataRequired(), NumberRange(min=0, max=60)]
    )
    submit = SubmitField('Lưu Cài đặt Telegram')

class WorkerSettingsForm(FlaskForm):
    """Form for background worker and data fetching settings."""
    check_interval_minutes = IntegerField(
        'Chu kỳ kiểm tra đơn hàng (phút)',
        default=5,
        validators=[DataRequired(), NumberRange(min=1, max=1440)]
    )
    fetch_product_images = BooleanField('Tải ảnh sản phẩm (chậm)')
    submit = SubmitField('Lưu Cài đặt Worker')

class OrderTableSettingsForm(FlaskForm):
    """Form for saving the order table column configuration."""
    order_table_columns = HiddenField('Cấu hình cột bảng đơn hàng')
    submit = SubmitField('Lưu Cấu hình Bảng')

class TemplateSettingsForm(FlaskForm):
    """Form for system-wide message templates."""
    telegram_template_new_order = TextAreaField('Template cho đơn hàng mới', render_kw={'rows': 8})
    telegram_template_system_test = TextAreaField('Template cho tin nhắn thử hệ thống', render_kw={'rows': 3})
    submit = SubmitField('Lưu Cấu hình Template')

# UserSettingsForm remains the same
class UserSettingsForm(FlaskForm):
    """
    Form cho người dùng (bao gồm cả Admin) cấu hình các cài đặt cá nhân.
    """
    telegram_bot_token = StringField('Telegram Bot Token (Cá nhân)', validators=[Optional()])
    telegram_chat_id = StringField('Telegram Chat ID (Cá nhân)', validators=[Optional()])
    telegram_enabled = BooleanField('Bật thông báo Telegram cá nhân')
    telegram_send_delay_seconds = IntegerField('Độ trễ gửi Telegram cá nhân (giây)', validators=[Optional(), NumberRange(min=0, max=60)])
    telegram_template_new_order = TextAreaField('Template: Đơn hàng mới (Cá nhân)', validators=[Optional()], render_kw={"rows": 6})
    telegram_template_user_test = TextAreaField('Template: Tin nhắn thử cá nhân', validators=[Optional()], render_kw={"rows": 3})
    submit = SubmitField('Lưu Cài đặt Cá nhân')