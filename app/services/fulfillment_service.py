# app/services/fulfillment_service.py

from flask import current_app

# --- IMPORT CÁC SERVICE TỪ THƯ MỤC PROVIDERS ---
# Mỗi nhà cung cấp có một file riêng và được import tại đây.
from .providers.mangotee_service import MangoTeeService
# from .providers.printify_service import PrintifyService # Ví dụ: import nhà cung cấp mới

# --- ĐĂNG KÝ CÁC NHÀ CUNG CẤP ---
# Đây là "danh bạ" các nhà cung cấp fulfillment được hệ thống hỗ trợ.
FULFILLMENT_SERVICES = {
    'mangotee': MangoTeeService,
    # 'printify': PrintifyService, # Thêm nhà cung cấp mới vào đây
}

# --- FACTORY FUNCTION ---
def get_fulfillment_service(provider_name, api_key):
    """
    Factory function để lấy một instance của service fulfillment.
    
    Args:
        provider_name (str): Tên của nhà cung cấp (ví dụ: 'mangotee').
        api_key (str): API key để khởi tạo service.

    Returns:
        Một instance của service hoặc None nếu không tìm thấy hoặc có lỗi.
    """
    service_class = FULFILLMENT_SERVICES.get(provider_name)

    if not service_class:
        current_app.logger.error(f"Yêu cầu một service không được hỗ trợ: '{provider_name}'")
        return None
    
    try:
        # Khởi tạo một instance từ Class đã tìm thấy với API key được cung cấp.
        return service_class(api_key=api_key)
    except (ValueError, TypeError) as e:
        current_app.logger.error(f"Lỗi khi khởi tạo service '{provider_name}': {e}")
        return None