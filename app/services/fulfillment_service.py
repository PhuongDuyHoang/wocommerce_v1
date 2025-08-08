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

    # --- START: SỬA LỖI 'list' object has no attribute 'get' ---
    def get_products(self):
        """
        Lấy danh sách sản phẩm từ MangoTee.
        """
        endpoint = f"{self.base_url}/products"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=20)
            response.raise_for_status()
            response_data = response.json()
            
            # API MangoTee trả về một list trực tiếp khi thành công.
            if isinstance(response_data, list):
                # Gói lại dữ liệu để tương thích với frontend
                return True, {"products": response_data}
            # Nếu không phải list, có thể là một object lỗi
            else:
                error_message = response_data.get('message', 'Phản hồi từ MangoTee không đúng định dạng.')
                return False, error_message

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"MangoTee API Connection Error (get_products): {e}")
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"An unknown error occurred during MangoTee get_products: {e}")
            return False, f"Lỗi không xác định: {e}"
    # --- END: SỬA LỖI ---


    def get_product_variants(self, sku):
        """
        Lấy chi tiết các biến thể của một sản phẩm dựa trên SKU gốc.
        """
        endpoint = f"{self.base_url}/products/{sku}"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=20)
            response.raise_for_status()
            response_data = response.json()

            # API này có thể trả về một object chứa product khi thành công
            if isinstance(response_data, dict) and response_data.get('id'):
                variants = response_data.get('variants', [])
                return True, variants
            else:
                error_message = response_data.get('message', 'Không tìm thấy sản phẩm hoặc định dạng phản hồi sai.')
                return False, error_message

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"MangoTee API Connection Error (get_product_variants for {sku}): {e}")
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"An unknown error occurred during MangoTee get_product_variants for {sku}): {e}")
            return False, f"Lỗi không xác định: {e}"


# --- CẤU TRÚC MỞ RỘNG CHO NHIỀU NHÀ CUNG CẤP ---
FULFILLMENT_SERVICES = {
    'mangotee': MangoTeeService,
}

def get_fulfillment_service(provider_name, api_key):
    """
    Factory function: Tự động tìm và khởi tạo lớp service phù hợp
    dựa trên tên của nhà cung cấp.
    """
    service_class = FULFILLMENT_SERVICES.get(provider_name)
    if not service_class:
        return None
    try:
        return service_class(api_key=api_key)
    except (ValueError, TypeError):
        return None