# run.py
from app import create_app, worker

# Tạo một instance của ứng dụng Flask bằng cách sử dụng App Factory
# App Factory (create_app) sẽ được định nghĩa trong file app/__init__.py
app = create_app()

if __name__ == '__main__':
    # Khởi tạo và chạy bộ lập lịch tác vụ nền (để kiểm tra đơn hàng)
    # Tác vụ này cần chạy trong "application context" để có thể truy cập
    # vào cơ sở dữ liệu và các cấu hình khác của app.
    with app.app_context():
        worker.init_scheduler(app)
    
    # Chạy ứng dụng Flask
    # host='0.0.0.0' cho phép các thiết bị khác trong cùng mạng có thể truy cập vào web của bạn.
    # port=5001 là cổng chạy ứng dụng, bạn có thể thay đổi nếu muốn.
    # debug=True sẽ tự động tải lại server khi bạn thay đổi code và hiển thị lỗi chi tiết.
    # Khi triển khai thực tế (production), bạn nên đặt debug=False.
    app.run(host='0.0.0.0', port=7001, debug=True)