# app/services/fulfillment_service.py

import requests
import json
from flask import current_app

class MangoTeeService:
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("API key is required for MangoTeeService")
        self.api_key = api_key
        self.base_url = "https://developers.mangoteeprints.com/api/v1"
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def create_order(self, order_payload, printer):
        """
        Gửi một đơn hàng mới đến MangoTee.
        - printer: Là một query parameter trên URL.
        - order_payload: Là nội dung JSON trong body của request.
        """
        endpoint = f"{self.base_url}/orders/create"
        params = {'Printer': printer}

        try:
            # API của MangoTee yêu cầu body phải là một danh sách, kể cả khi chỉ gửi 1 đơn hàng.
            response = requests.post(endpoint, headers=self.headers, params=params, json=[order_payload], timeout=30)

            current_app.logger.info(f"MANGO_RESPONSE: Status={response.status_code}, Body={response.text}")
            
            response.raise_for_status()
            
            response_data = response.json()

            if isinstance(response_data, dict) and 'added_orders' in response_data:
                added_orders_list = response_data['added_orders']
                
                if isinstance(added_orders_list, list) and len(added_orders_list) > 0:
                    # === SỬA LỖI TẠI ĐÂY ===
                    # API trả về một danh sách các chuỗi ID, không phải danh sách các object.
                    # Lấy trực tiếp phần tử đầu tiên chính là ID đơn hàng.
                    mangotee_order_id = added_orders_list[0]
                    success_message = f"Gửi đơn thành công! MangoTee Order ID: {mangotee_order_id}"
                    return True, success_message
                    # ========================
                else:
                    return False, "Yêu cầu hợp lệ nhưng MangoTee không tạo đơn hàng. Vui lòng kiểm tra lại thông tin sản phẩm (SKU, màu sắc, size) và thử lại."
            else:
                error_message = response_data.get('message', 'Lỗi không xác định từ MangoTee.')
                return False, error_message

        except requests.exceptions.HTTPError as e:
            error_details = f"Lỗi HTTP {e.response.status_code}"
            try:
                error_json = e.response.json()
                if 'detail' in error_json:
                    if isinstance(error_json['detail'], list):
                        messages = [f"{item.get('loc', [''])[1]}: {item.get('msg', '')}" for item in error_json['detail']]
                        error_details = ", ".join(messages)
                    else:
                        error_details = str(error_json['detail'])
                else:
                    error_details = e.response.text
            except:
                error_details = e.response.text
            return False, f"Lỗi từ MangoTee API: {error_details}"
        except requests.exceptions.RequestException as e:
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"Lỗi không xác định trong MangoTeeService: {e}")
            return False, f"Lỗi không xác định: {e}"

    def get_products(self):
        endpoint = f"{self.base_url}/products"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=30)
            response.raise_for_status()
            products_list = response.json()
            if not isinstance(products_list, list):
                return True, {"products": []}
            return True, {"products": products_list}
        except Exception as e:
            return False, f"Lỗi khi lấy sản phẩm từ MangoTee: {e}"

FULFILLMENT_SERVICES = { 'mangotee': MangoTeeService }

def get_fulfillment_service(provider_name, api_key):
    service_class = FULFILLMENT_SERVICES.get(provider_name)
    if not service_class: return None
    try: return service_class(api_key=api_key)
    except (ValueError, TypeError): return None