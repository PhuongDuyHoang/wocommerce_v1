# app/services/fulfillment_service.py

import requests
import json
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
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def create_order(self, order_payload):
        """
        Gửi một đơn hàng mới đến MangoTee.
        """
        endpoint = f"{self.base_url}/orders"
        
        mangotee_payload = order_payload
        
        if 'shipping_address' in mangotee_payload:
            addr = mangotee_payload['shipping_address']
            first_name = addr.pop('first_name', '')
            last_name = addr.pop('last_name', '')
            addr['name'] = f"{first_name} {last_name}".strip()
        
        if 'postcode' in mangotee_payload.get('shipping_address', {}):
             mangotee_payload['shipping_address']['zip'] = mangotee_payload['shipping_address'].pop('postcode')

        mangotee_payload["shipping_method"] = "standard"

        try:
            response = requests.post(endpoint, headers=self.headers, json=mangotee_payload, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            if response_data.get('success'):
                success_message = f"Gửi đơn thành công! MangoTee Order ID: {response_data.get('order', {}).get('id')}"
                return True, success_message
            else:
                return False, response_data.get('message', 'Lỗi không xác định từ MangoTee.')
        except requests.exceptions.HTTPError as e:
            try:
                error_details = e.response.json().get('message', e.response.text)
            except:
                error_details = str(e)
            return False, f"Lỗi từ MangoTee API: {error_details}"
        except requests.exceptions.RequestException as e:
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            return False, f"Lỗi không xác định: {e}"

    def get_products(self):
        """
        Lấy danh sách phẳng của TẤT CẢ các biến thể sản phẩm từ MangoTee.
        """
        endpoint = f"{self.base_url}/products"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=30) # Tăng timeout
            response.raise_for_status()
            
            products_list = response.json()
            
            if not isinstance(products_list, list):
                current_app.logger.error(f"MangoTee API /products response was not a list: {products_list}")
                return True, {"products": []}

            return True, {"products": products_list}
        except requests.exceptions.RequestException as e:
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except json.JSONDecodeError as e:
            current_app.logger.error(f"MangoTee API JSON Decode Error (get_products): {e}")
            current_app.logger.error(f"Response text that failed to parse: {response.text}")
            return False, "Lỗi: Phản hồi từ MangoTee không phải là định dạng JSON hợp lệ."
        except Exception as e:
            return False, f"Lỗi không xác định: {e}"

# --- START: LOẠI BỎ HÀM GET_PRODUCT_VARIANTS KHÔNG CẦN THIẾT ---
# --- END: LOẠI BỎ HÀM GET_PRODUCT_VARIANTS KHÔNG CẦN THIẾT ---

FULFILLMENT_SERVICES = {
    'mangotee': MangoTeeService,
}

def get_fulfillment_service(provider_name, api_key):
    service_class = FULFILLMENT_SERVICES.get(provider_name)
    if not service_class:
        return None
    try:
        return service_class(api_key=api_key)
    except (ValueError, TypeError):
        return None