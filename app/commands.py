import click
from flask.cli import with_appcontext
from . import db

@click.command('init-db')
@click.option('--drop', is_flag=True, help='Xóa các bảng hiện có trước.')
@with_appcontext
def init_db_command(drop):
    """Xóa dữ liệu hiện có và tạo các bảng mới."""
    if drop:
        click.echo('Đã xóa tất cả các bảng trong database.')
        db.drop_all()
    
    db.create_all()
    click.echo('Đã khởi tạo database.')

def register_commands(app):
    """Đăng ký các lệnh CLI với ứng dụng Flask."""
    app.cli.add_command(init_db_command)