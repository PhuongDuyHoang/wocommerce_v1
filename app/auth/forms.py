# app/auth/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, ValidationError, Length
from app.models import AppUser

class LoginForm(FlaskForm):
    """Form cho người dùng đăng nhập."""
    username = StringField('Tên đăng nhập', validators=[DataRequired(message="Vui lòng nhập tên đăng nhập.")])
    password = PasswordField('Mật khẩu', validators=[DataRequired(message="Vui lòng nhập mật khẩu.")])
    submit = SubmitField('Đăng nhập')


class RegistrationForm(FlaskForm):
    """Form cho người dùng mới đăng ký."""
    username = StringField('Tên đăng nhập', validators=[DataRequired(), Length(min=4, max=64, message="Tên đăng nhập phải từ 4 đến 64 ký tự.")])
    password = PasswordField('Mật khẩu', validators=[DataRequired(), Length(min=6, message="Mật khẩu phải có ít nhất 6 ký tự.")])
    password2 = PasswordField(
        'Nhập lại mật khẩu', 
        validators=[DataRequired(), EqualTo('password', message='Mật khẩu không khớp.')]
    )
    submit = SubmitField('Đăng ký')

    def validate_username(self, username):
        """Kiểm tra xem username đã tồn tại trong database chưa."""
        user = AppUser.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Tên đăng nhập này đã được sử dụng.')


class ChangePasswordForm(FlaskForm):
    """Form cho người dùng đổi mật khẩu."""
    current_password = PasswordField('Mật khẩu hiện tại', validators=[DataRequired()])
    new_password = PasswordField('Mật khẩu mới', validators=[DataRequired(), Length(min=6, message="Mật khẩu mới phải có ít nhất 6 ký tự.")])
    new_password_confirm = PasswordField(
        'Xác nhận mật khẩu mới', 
        validators=[DataRequired(), EqualTo('new_password', message='Mật khẩu mới không khớp.')]
    )
    submit = SubmitField('Đổi mật khẩu')