# app/commands.py

import click
from flask.cli import with_appcontext
from flask import current_app
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
import os
import sqlalchemy as sa
import json

from . import db
from .models import Setting

@click.command('seed-db')
@with_appcontext
def seed_db_command():
    """(An toàn) Thêm hoặc cập nhật các cài đặt mặc định vào database."""
    
    # === PHẦN SỬA LỖI: Luôn cập nhật giá trị cột để sửa lỗi dữ liệu hỏng ===
    click.echo('Đang kiểm tra và cập nhật cài đặt cột bảng đơn hàng...')
    default_columns = [
        {"key": "order_created_at", "label": "Ngày tạo", "visible": True, "type": "datetime", "width": "120px"},
        {"key": "store_name", "label": "Cửa hàng", "visible": True, "type": "text", "width": "150px"},
        {"key": "wc_order_id", "label": "Mã ĐH", "visible": True, "type": "number", "width": "80px"},
        {"key": "image", "label": "Ảnh SP", "visible": False, "type": "image", "width": "100px"},
        {"key": "products", "label": "Sản phẩm", "visible": True, "type": "list", "width": "30%"},
        {"key": "customer_name", "label": "Khách hàng", "visible": True, "type": "text", "width": "150px"},
        {"key": "total", "label": "Tổng tiền", "visible": True, "type": "currency", "width": "120px"},
        {"key": "status", "label": "Trạng thái", "visible": True, "type": "badge", "width": "120px"},
        {"key": "note", "label": "Ghi Chú Seller", "visible": True, "type": "text", "width": "20%"},
        # === START: THÊM CỘT HÀNH ĐỘNG MỚI ===
        {"key": "actions", "label": "Hành động", "visible": True, "type": "actions", "width": "110px"},
        # === END: THÊM CỘT HÀNH ĐỘNG MỚI ===
        {"key": "owner_username", "label": "Người dùng", "visible": False, "type": "text", "width": "100px"},
        {"key": "payment_method_title", "label": "Phương thức TT", "visible": False, "type": "text", "width": "150px"},
        {"key": "shipping_total", "label": "Phí Ship", "visible": False, "type": "currency", "width": "100px"},
        {"key": "customer_note", "label": "Ghi chú khách", "visible": False, "type": "text", "width": "200px"},
        {"key": "billing_phone", "label": "SĐT", "visible": False, "type": "text", "width": "120px"},
        {"key": "billing_email", "label": "Email", "visible": False, "type": "text", "width": "180px"},
        {"key": "billing_address", "label": "Địa chỉ TT", "visible": False, "type": "text", "width": "250px"},
        {"key": "shipping_address", "label": "Địa chỉ Ship", "visible": False, "type": "text", "width": "250px"}
    ]
    
    setting_columns = Setting.query.get('ORDER_TABLE_COLUMNS')
    if setting_columns is None:
        # Nếu chưa có thì tạo mới
        click.echo('Tạo mới cài đặt cột bảng đơn hàng...')
        setting_columns = Setting(key='ORDER_TABLE_COLUMNS')
        db.session.add(setting_columns)
    
    # Luôn gán lại giá trị đúng để ghi đè dữ liệu hỏng
    setting_columns.value = json.dumps(default_columns)
    # === KẾT THÚC PHẦN SỬA LỖI ===

    if Setting.query.get('ENABLE_USER_REGISTRATION') is None:
        click.echo('Đang thêm cài đặt mặc định cho phép đăng ký...')
        setting_registration = Setting(key='ENABLE_USER_REGISTRATION', value='False')
        db.session.add(setting_registration)
    else:
        click.echo('Cài đặt cho phép đăng ký đã tồn tại, bỏ qua.')
        
    db.session.commit()
    click.echo('Hoàn tất việc thêm/cập nhật dữ liệu mặc định.')


@click.command('reset-db')
@with_appcontext
def reset_db_command():
    """
    (NGUY HIỂM) Lệnh "Đập đi xây lại": Xóa sạch triệt để, xây dựng lại và thêm dữ liệu mặc định.
    """
    click.confirm(
        'CẢNH BÁO: Lệnh này sẽ XÓA TOÀN BỘ DỮ LIỆU. Bạn có chắc chắn muốn tiếp tục không?',
        abort=True
    )
    
    click.echo('Đang xóa tất cả các bảng (bao gồm cả lịch sử migration)...')
    db.drop_all()
    db.session.execute(sa.text('DROP TABLE IF EXISTS alembic_version'))
    db.session.commit()
    
    click.echo('Đang xây dựng lại cấu trúc database từ đầu (upgrade to head)...')
    try:
        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_cfg.set_main_option('sqlalchemy.url', current_app.config['SQLALCHEMY_DATABASE_URI'])
        alembic_command.upgrade(alembic_cfg, "head")
    except Exception as e:
        click.echo(f"Lỗi khi chạy alembic upgrade: {e}")
        return

    click.echo('Đang tự động thêm dữ liệu mặc định...')
    click.get_current_context().invoke(seed_db_command)
    
    click.echo('Hoàn tất quy trình "đập đi xây lại"!')


def register_commands(app):
    """Đăng ký các lệnh CLI với ứng dụng Flask."""
    app.cli.add_command(seed_db_command)
    app.cli.add_command(reset_db_command)