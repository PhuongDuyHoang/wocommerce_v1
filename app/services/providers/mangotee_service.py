# app/services/providers/mangotee_service.py

import requests
import json
from flask import current_app

class MangoTeeService:
    """
    Class chứa toàn bộ logic giao tiếp với API của nhà cung cấp MangoTee.
    """
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("API key là bắt buộc để khởi tạo MangoTeeService")
        self.api_key = api_key
        self.base_url = "https://developers.mangoteeprints.com/api/v1"
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def create_order(self, order_payload, printer):
        """
        Gửi một đơn hàng mới đến MangoTee.
        """
        endpoint = f"{self.base_url}/orders/create"
        params = {'Printer': printer}

        try:
            # API của MangoTee yêu cầu body của request phải là một danh sách.
            response = requests.post(endpoint, headers=self.headers, params=params, json=[order_payload], timeout=30)
            current_app.logger.info(f"MANGO_RESPONSE: Status={response.status_code}, Body={response.text}")
            response.raise_for_status()
            
            response_data = response.json()

            if isinstance(response_data, dict) and 'added_orders' in response_data:
                added_orders_list = response_data.get('added_orders', [])
                if isinstance(added_orders_list, list) and len(added_orders_list) > 0:
                    mangotee_order_id = added_orders_list[0]
                    success_message = f"Gửi đơn thành công! MangoTee Order ID: {mangotee_order_id}"
                    return True, success_message
                else:
                    return False, "Yêu cầu hợp lệ nhưng MangoTee không tạo đơn hàng. Vui lòng kiểm tra lại thông tin."
            else:
                error_message = response_data.get('message', 'Lỗi không xác định từ MangoTee.')
                return False, error_message

        except requests.exceptions.HTTPError as e:
            error_details = f"Lỗi HTTP {e.response.status_code}"
            try:
                error_json = e.response.json()
                if 'detail' in error_json:
                    detail = error_json['detail']
                    if isinstance(detail, list) and detail:
                        messages = [f"{item.get('loc', ['unknown'])[1]}: {item.get('msg', 'invalid')}" for item in detail]
                        error_details = ", ".join(messages)
                    else:
                        error_details = str(detail)
                else:
                    error_details = e.response.text
            except Exception:
                error_details = e.response.text
            return False, f"Lỗi từ MangoTee API: {error_details}"
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Lỗi kết nối đến MangoTee khi tạo đơn hàng: {e}")
            return False, f"Lỗi kết nối đến MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"Lỗi không xác định trong MangoTeeService.create_order: {e}")
            return False, f"Lỗi hệ thống không xác định: {e}"

    def get_products(self):
        """
        Lấy danh sách tất cả sản phẩm có sẵn từ MangoTee.
        """
        endpoint = f"{self.base_url}/products"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=30)
            response.raise_for_status()
            products_list = response.json()
            if not isinstance(products_list, list):
                current_app.logger.warning(f"API get_products của MangoTee không trả về một list. Phản hồi: {products_list}")
                return True, {"products": []}
            return True, {"products": products_list}
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Lỗi kết nối đến MangoTee khi lấy sản phẩm: {e}")
            return False, f"Lỗi kết nối khi lấy sản phẩm từ MangoTee: {e}"
        except Exception as e:
            current_app.logger.error(f"Lỗi không xác định trong MangoTeeService.get_products: {e}")
            return False, f"Lỗi hệ thống không xác định khi lấy sản phẩm: {e}"