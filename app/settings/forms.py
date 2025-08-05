# app/settings/forms.py

from flask_wtf import FlaskForm
from wtforms import TextAreaField, StringField, IntegerField, BooleanField, SubmitField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Optional, Length

class SystemSettingsForm(FlaskForm):
    """
    Form cho Super Admin cấu hình các cài đặt chung của toàn bộ hệ thống.
    """
    # Cài đặt Telegram hệ thống
    telegram_bot_token = TextAreaField(
        'Telegram Bot Token (Hệ thống)', 
        validators=[Optional(), Length(max=255)], 
        render_kw={"rows": 2}
    )
    telegram_chat_id = StringField(
        'Telegram Chat ID (Hệ thống)', 
        validators=[Optional(), Length(max=255)]
    )
    telegram_send_delay_seconds = IntegerField(
        'Độ trễ gửi Telegram (giây)',
        validators=[DataRequired(), NumberRange(min=0, max=60)],
        default=2
    )
    
    # Cài đặt Worker
    check_interval_minutes = IntegerField(
        'Chu kỳ kiểm tra đơn hàng (phút)',
        validators=[DataRequired(), NumberRange(min=1, max=1440)], # Tối thiểu 1 phút, tối đa 24 giờ
        default=5
    )

    # ### THÊM TRƯỜNG ẨN ĐỂ LƯU CẤU HÌNH CỘT ###
    order_table_columns = HiddenField('Cấu hình cột bảng đơn hàng')
    # ###########################################

    # Template hệ thống
    telegram_template_new_order = TextAreaField(
        'Template: Đơn hàng mới',
        validators=[Optional()],
        render_kw={"rows": 6}
    )
    telegram_template_system_test = TextAreaField(
        'Template: Tin nhắn thử hệ thống',
        validators=[Optional()],
        render_kw={"rows": 3}
    )
    
    submit = SubmitField('Lưu Cài đặt Hệ thống')


class UserSettingsForm(FlaskForm):
    """
    Form cho người dùng (bao gồm cả Admin) cấu hình các cài đặt cá nhân.
    Các cài đặt này sẽ ghi đè cài đặt hệ thống nếu được điền.
    """
    # Cài đặt Telegram cá nhân
    telegram_bot_token = StringField(
        'Telegram Bot Token (Cá nhân)', 
        validators=[Optional(), Length(max=255)]
    )
    telegram_chat_id = StringField(
        'Telegram Chat ID (Cá nhân)', 
        validators=[Optional(), Length(max=255)]
    )
    telegram_enabled = BooleanField('Bật thông báo Telegram cá nhân')
    
    # Cài đặt độ trễ cá nhân (chỉ hiển thị nếu được cấp quyền)
    telegram_send_delay_seconds = IntegerField(
        'Độ trễ gửi Telegram cá nhân (giây)',
        validators=[Optional(), NumberRange(min=0, max=60)]
    )

    # Template cá nhân (chỉ hiển thị nếu được cấp quyền)
    telegram_template_new_order = TextAreaField(
        'Template: Đơn hàng mới (Cá nhân)',
        validators=[Optional()],
        render_kw={"rows": 6}
    )
    telegram_template_user_test = TextAreaField(
        'Template: Tin nhắn thử cá nhân',
        validators=[Optional()],
        render_kw={"rows": 3}
    )
    
    submit = SubmitField('Lưu Cài đặt Cá nhân')