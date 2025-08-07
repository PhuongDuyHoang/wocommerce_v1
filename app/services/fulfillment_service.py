# app/services/fulfillment_service.py

import requests
from flask import current_app

class MangoTeeService:
    """
    Lớp chứa logic để giao tiếp với API của MangoTee.
    """
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("API key is required for MangoTeeService")
        self.api_key = api_key
        self.base_url = "https://developers.mangoteeprints.com/api/v1"
        self.headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }

    def create_order(self, order_payload):
        """
        Gửi một đơn hàng mới đến MangoTee.
        :param order_payload: Dữ liệu đơn hàng đã được chuẩn bị.
        :return: Tuple (success, message_or_data)
        """
        endpoint = f"{self.base_url}/orders"
        
        # Lọc ra những sản phẩm hợp lệ (có design_image_url)
        valid_line_items = [
            item for item in order_payload.get('line_items', []) if item.get('design_image_url')
        ]
        
        if not valid_line_items:
            return False, "Không có sản phẩm nào hợp lệ để fulfill."

        # Xây dựng payload cuối cùng theo đúng định dạng của MangoTee
        mangotee_payload = {
            "reference_id": order_payload.get('reference_id'),
            "shipping_address": order_payload.get('shipping_address'),
            "line_items": [
                {
                    "sku": item['sku'],
                    "quantity": item['quantity'],
                    "image_url": item['design_image_url'],
                    # Giả định mặc định là in ở mặt trước.
                    # Trong tương lai có thể mở rộng để người dùng chọn.
                    "print_areas": {"front": item['design_image_url']} 
                } for item in valid_line_items
            ],
            "shipping_method": "standard" # Mặc định
        }

        try:
            response = requests.post(endpoint, headers=self.headers, json=mangotee_payload, timeout=30)
            response.raise_for_status()  # Báo lỗi nếu status code là 4xx hoặc 5xx
            
            response_data = response.json()
            if response_data.get('success'):
                success_message = f"Gửi đơn thành công! MangoTee Order ID: {response_data.get('order', {}).get('id')}"
                return True, success_message
            else:
                # Trả về lỗi cụ thể từ MangoTee
                error_message = response_data.get('message', 'Lỗi không xác định từ MangoTee.')
                return False, error_message

        except requests.exceptions.HTTPError as e:
            # Cố gắng đọc lỗi chi tiết hơn từ response
            try:
                error_details = e.response.json().get('message', e.response.text)
            except:
                error_details = str(e)
            current_app.logger.error(f"MangoTee API HTTP Error: {error_details}")
            return False, f"Lỗi từ MangoTee API: {error_details}"
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"MangoTee API Connection Error: {e}")
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"An unknown error occurred during MangoTee fulfillment: {e}")
            return False, f"Lỗi không xác định: {e}"

    def get_products(self):
        """
        Lấy danh sách sản phẩm từ MangoTee (để dùng trong tương lai).
        :return: Tuple (success, message_or_data)
        """
        endpoint = f"{self.base_url}/products"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=20)
            response.raise_for_status()
            return True, response.json()
        except Exception as e:
            return False, f"Không thể lấy danh sách sản phẩm từ MangoTee: {e}"

# Có thể thêm các class service cho nhà cung cấp khác ở đây trong tương lai
# class PrintfulService:
#     def __init__(self, api_key):
#         ...
#     def create_order(self, order_payload):
#         ...