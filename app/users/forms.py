# app/users/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, BooleanField
from wtforms.validators import DataRequired, Optional, Length, EqualTo, ValidationError
from flask import request
from app.models import AppUser

class UserManagementForm(FlaskForm):
    """
    Form để Admin/Super Admin thêm hoặc chỉnh sửa người dùng.
    Form này có logic phức tạp để hiển thị/ẩn các trường dựa trên quyền của người dùng hiện tại.
    """
    username = StringField('Tên đăng nhập', validators=[DataRequired(), Length(min=4, max=64)])
    # Mật khẩu là tùy chọn khi chỉnh sửa, bắt buộc khi tạo mới
    password = PasswordField('Mật khẩu mới', validators=[Optional(), Length(min=6)])
    password2 = PasswordField('Xác nhận mật khẩu mới', validators=[Optional(), EqualTo('password', message='Mật khẩu không khớp.')])
    
    # Các trường chỉ Super Admin mới thấy
    role = SelectField('Vai trò', choices=[('user', 'User'), ('admin', 'Admin'), ('super_admin', 'Super Admin')], validators=[DataRequired()])
    parent = SelectField('Người quản lý (Admin)', coerce=int, validators=[Optional()])
    
    # Trường Admin và Super Admin đều thấy
    is_active = BooleanField('Kích hoạt tài khoản')

    # --- Các quyền được cấp cho User thường ---
    can_add_store = BooleanField('Quyền: Thêm/Sửa Cửa hàng')
    can_delete_store = BooleanField('Quyền: Xóa Cửa hàng')
    can_view_orders = BooleanField('Quyền: Xem Đơn hàng')
    
    # --- Các quyền chỉ Super Admin mới có thể cấp cho Admin ---
    can_customize_telegram_delay = BooleanField('Quyền: Tùy chỉnh độ trễ Telegram')
    can_customize_telegram_templates = BooleanField('Quyền: Tùy chỉnh Template Telegram')

    # Checkbox tiện ích
    full_permissions = BooleanField('Gán full quyền cơ bản')

    submit = SubmitField('Lưu thay đổi')

    def __init__(self, original_username=None, user_being_edited=None, current_user_logged_in=None, *args, **kwargs):
        super(UserManagementForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.user_being_edited = user_being_edited
        self.current_user_logged_in = current_user_logged_in

        # Nếu là form tạo người dùng mới, mật khẩu là bắt buộc
        if not self.user_being_edited:
            self.password.validators = [DataRequired(), Length(min=6)]
            self.password2.validators = [DataRequired(), EqualTo('password', message='Mật khẩu không khớp.')]

        # Chỉ Super Admin mới có thể thay đổi Role và Parent
        if self.current_user_logged_in and not self.current_user_logged_in.is_super_admin():
            del self.role
            del self.parent
            # Xóa luôn các quyền chỉ Super Admin mới được cấp
            del self.can_customize_telegram_delay
            del self.can_customize_telegram_templates
        else:
            # Nếu là Super Admin, tạo danh sách lựa chọn cho ô "Người quản lý"
            admins = AppUser.query.filter(AppUser.role.in_(['admin', 'super_admin'])).all()
            valid_parents = [(admin.id, admin.username) for admin in admins if not self.user_being_edited or admin.id != self.user_being_edited.id]
            self.parent.choices = [(0, 'Không có (cho Admin cấp cao)')] + valid_parents
            
            # Gán giá trị parent hiện tại cho form khi chỉnh sửa
            if request.method == 'GET' and self.user_being_edited:
                self.parent.data = self.user_being_edited.parent_id or 0


    def validate_username(self, username):
        """Kiểm tra tên đăng nhập đã tồn tại chưa, bỏ qua chính nó khi đang sửa."""
        if username.data != self.original_username:
            user = AppUser.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Tên đăng nhập này đã được sử dụng.')