{% extends "base.html" %}

{% block content %}
<div class="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center pt-3 pb-2 mb-3 border-bottom">
    <h1 class="h2">{{ title }}</h1>
</div>

<div class="row justify-content-center">
    <div class="col-lg-8">
        <div class="card shadow-sm">
            <div class="card-header">
                <h5 class="mb-0"><i class="bi bi-box-fill me-2"></i>Cài đặt Nhà cung cấp Fulfillment</h5>
            </div>
            <form action="{{ url_for('settings.fulfill') }}" method="post" novalidate>
                {{ form.hidden_tag() }} {# Chống tấn công CSRF #}
                <div class="card-body">
                    <p class="text-muted">
                        Đây là nơi bạn quản lý API Key cho các nhà cung cấp dịch vụ fulfillment. 
                        Các key này sẽ được sử dụng để tự động gửi đơn hàng.
                    </p>
                    <hr>
                    
                    <div class="mb-3">
                        <h6 class="mb-0">
                            <img src="https://mangoteeprints.com/wp-content/uploads/2024/05/cropped-MANGOTEE-LOGO-web-2-e1715845019777-300x121.png" alt="MangoTee Logo" style="height: 24px; margin-right: 8px;">
                            MangoTee
                        </h6>
                        <div class="form-text my-2">Nhập API Key được cung cấp bởi MangoTee.</div>
                        {{ form.mangotee_api_key.label(class="form-label visually-hidden") }}
                        {{ form.mangotee_api_key(class="form-control") }}
                        {% for error in form.mangotee_api_key.errors %}
                            <div class="invalid-feedback d-block">{{ error }}</div>
                        {% endfor %}
                    </div>

                    </div>
                <div class="card-footer text-end bg-light">
                    {{ form.submit(class="btn btn-primary") }}
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}