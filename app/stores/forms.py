# app/stores/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, URL, Optional

class StoreForm(FlaskForm):
    """
    Form để thêm hoặc chỉnh sửa thông tin một cửa hàng WooCommerce.
    """
    name = StringField(
        'Tên gợi nhớ cho cửa hàng', 
        validators=[DataRequired(message="Vui lòng nhập tên cho cửa hàng."), 
                    Length(max=100, message="Tên không được vượt quá 100 ký tự.")]
    )
    store_url = StringField(
        'URL của cửa hàng', 
        validators=[DataRequired(message="Vui lòng nhập URL."), 
                    URL(message="URL không hợp lệ."),
                    Length(max=255)]
    )
    consumer_key = TextAreaField(
        'Consumer Key', 
        validators=[DataRequired(message="Vui lòng nhập Consumer Key."), 
                    Length(max=255)],
        render_kw={"rows": 2}
    )
    consumer_secret = TextAreaField(
        'Consumer Secret', 
        validators=[DataRequired(message="Vui lòng nhập Consumer Secret."), 
                    Length(max=255)],
        render_kw={"rows": 2}
    )
    note = TextAreaField(
        'Ghi chú', 
        validators=[Optional()],
        render_kw={"rows": 3}
    )
    # Trường này sẽ được sử dụng bởi Admin/Super Admin để gán cửa hàng cho người dùng khác
    user_id = SelectField(
        'Gán cho người dùng', 
        coerce=int, 
        validators=[Optional()]
    )
    submit = SubmitField('Lưu thông tin')