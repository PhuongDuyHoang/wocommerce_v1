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
        Payload hiện được chuẩn bị hoàn toàn ở phía frontend,
        hàm này chỉ đóng vai trò gửi đi và xử lý kết quả trả về.
        :param order_payload: Dữ liệu đơn hàng đã được chuẩn bị.
        :return: Tuple (success, message_or_data)
        """
        endpoint = f"{self.base_url}/orders"
        
        mangotee_payload = order_payload
        
        # === START: ĐIỀU CHỈNH NHỎ ĐỂ TƯƠNG THÍCH API ===
        # API MangoTee yêu cầu trường "name", không phải "first_name", "last_name"
        if 'shipping_address' in mangotee_payload:
            addr = mangotee_payload['shipping_address']
            first_name = addr.pop('first_name', '')
            last_name = addr.pop('last_name', '')
            addr['name'] = f"{first_name} {last_name}".strip()
        
        # Đổi tên "postcode" thành "zip" theo yêu cầu của API
        if 'postcode' in mangotee_payload.get('shipping_address', {}):
             mangotee_payload['shipping_address']['zip'] = mangotee_payload['shipping_address'].pop('postcode')

        mangotee_payload["shipping_method"] = "standard" # Luôn là standard
        # === END: ĐIỀU CHỈNH NHỎ ĐỂ TƯƠNG THÍCH API ===

        try:
            response = requests.post(endpoint, headers=self.headers, json=mangotee_payload, timeout=30)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get('success'):
                success_message = f"Gửi đơn thành công! MangoTee Order ID: {response_data.get('order', {}).get('id')}"
                return True, success_message
            else:
                error_message = response_data.get('message', 'Lỗi không xác định từ MangoTee.')
                return False, error_message

        except requests.exceptions.HTTPError as e:
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
        Lấy danh sách sản phẩm từ MangoTee.
        Đã cải thiện xử lý lỗi chi tiết hơn.
        :return: Tuple (success, message_or_data)
        """
        endpoint = f"{self.base_url}/products"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=20)
            response.raise_for_status()
            response_data = response.json()
            if response_data.get('success'):
                 return True, response_data
            else:
                error_message = response_data.get('message', 'Lỗi không xác định từ MangoTee khi lấy sản phẩm.')
                return False, error_message
        except requests.exceptions.HTTPError as e:
            try:
                error_details = e.response.json().get('message', e.response.text)
            except:
                error_details = str(e)
            current_app.logger.error(f"MangoTee API HTTP Error (get_products): {error_details}")
            return False, f"Lỗi từ MangoTee API: {error_details}"
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"MangoTee API Connection Error (get_products): {e}")
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"An unknown error occurred during MangoTee get_products: {e}")
            return False, f"Lỗi không xác định: {e}"

    def get_product_variants(self, sku):
        """
        Lấy chi tiết các biến thể của một sản phẩm dựa trên SKU gốc.
        :param sku: SKU của sản phẩm gốc (base product).
        :return: Tuple (success, message_or_data)
        """
        endpoint = f"{self.base_url}/products/{sku}"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=20)
            response.raise_for_status()
            response_data = response.json()

            if response_data.get('success'):
                product_data = response_data.get('product', {})
                variants = product_data.get('variants', [])
                return True, variants
            else:
                error_message = response_data.get('message', 'Lỗi không xác định từ MangoTee khi lấy biến thể.')
                return False, error_message

        except requests.exceptions.HTTPError as e:
            try:
                error_details = e.response.json().get('message', e.response.text)
            except:
                error_details = str(e)
            current_app.logger.error(f"MangoTee API HTTP Error (get_product_variants for {sku}): {error_details}")
            return False, f"Lỗi từ MangoTee API: {error_details}"
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"MangoTee API Connection Error (get_product_variants for {sku}): {e}")
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"An unknown error occurred during MangoTee get_product_variants for {sku}: {e}")
            return False, f"Lỗi không xác định: {e}"


# Có thể thêm các class service cho nhà cung cấp khác ở đây trong tương lai
# class PrintfulService:
#     def __init__(self, api_key):
#         ...
#     def create_order(self, order_payload):
#         ...