# app/settings/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, IntegerField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Optional

# --- Các Form cho Cài đặt Hệ thống ---

class SystemTelegramForm(FlaskForm):
    """Form cho các cài đặt Telegram của hệ thống."""
    telegram_bot_token = StringField('Bot Token (Hệ thống)', validators=[Optional()])
    telegram_chat_id = StringField('Chat ID (Kênh hệ thống)', validators=[Optional()])
    telegram_send_delay_seconds = IntegerField(
        'Độ trễ mặc định khi gửi tin (giây)',
        validators=[DataRequired(), NumberRange(min=0)],
        default=2
    )
    submit_telegram = SubmitField('Lưu Cài đặt Telegram')


class SystemWorkerForm(FlaskForm):
    """Form cho các cài đặt tác vụ nền (worker)."""
    check_interval_minutes = IntegerField(
        'Tần suất kiểm tra đơn hàng (phút)',
        validators=[DataRequired(), NumberRange(min=1)],
        default=5
    )
    fetch_product_images = BooleanField('Tự động lấy ảnh sản phẩm khi đồng bộ')
    submit_worker = SubmitField('Lưu Cài đặt Worker')


class SystemTableForm(FlaskForm):
    """Form để lưu cấu hình bảng đơn hàng."""
    order_table_columns = HiddenField('Cấu hình cột bảng đơn hàng', validators=[DataRequired()])
    submit_table = SubmitField('Lưu Cấu hình Bảng')


class SystemTemplateForm(FlaskForm):
    """Form cho các template tin nhắn mặc định của hệ thống."""
    telegram_template_new_order = TextAreaField(
        'Template cho đơn hàng mới',
        validators=[DataRequired()],
        render_kw={'rows': 10}
    )
    telegram_template_system_test = TextAreaField(
        'Template cho tin nhắn thử của hệ thống',
        validators=[DataRequired()],
        render_kw={'rows': 4}
    )
    submit_template = SubmitField('Lưu Templates')


# --- Form cho Cài đặt Cá nhân ---

class PersonalSettingsForm(FlaskForm):
    """Form cho người dùng (vai trò User và Admin) tự cài đặt Telegram."""
    telegram_bot_token = StringField('Bot Token Cá nhân', validators=[Optional()])
    telegram_chat_id = StringField('Chat ID Cá nhân', validators=[Optional()])
    telegram_enabled = BooleanField('Bật thông báo Telegram cá nhân')

    telegram_send_delay_seconds = IntegerField(
        'Độ trễ gửi tin nhắn (giây)',
        validators=[Optional(), NumberRange(min=0)]
    )
    telegram_template_new_order = TextAreaField(
        'Template cá nhân cho đơn hàng mới',
        validators=[Optional()],
        render_kw={'rows': 10}
    )
    submit = SubmitField('Lưu thay đổi')
