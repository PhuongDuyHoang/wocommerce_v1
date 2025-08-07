# app/designs/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, URL, Length

class DesignForm(FlaskForm):
    """
    Form để thêm hoặc chỉnh sửa một Design.
    """
    name = StringField(
        'Tên Design', 
        validators=[
            DataRequired(message="Tên design không được để trống."),
            Length(min=3, max=255, message="Tên design phải có từ 3 đến 255 ký tự.")
        ]
    )
    image_url = StringField(
        'Đường dẫn Ảnh (Google Drive)', 
        validators=[
            DataRequired(message="Đường dẫn ảnh không được để trống."),
            URL(message="Đường dẫn ảnh không hợp lệ."),
            Length(max=1000, message="Đường dẫn ảnh không được vượt quá 1000 ký tự.")
        ]
    )
    submit = SubmitField('Lưu Design')