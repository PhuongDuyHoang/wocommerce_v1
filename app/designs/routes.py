# app/designs/routes.py

from flask import render_template, request, jsonify, flash
from flask_login import login_required, current_user
from sqlalchemy import desc, or_

from . import designs_bp
from .forms import DesignForm
from app import db
from app.models import Design

@designs_bp.route('/', methods=['GET'])
@login_required
def manage():
    """
    Hiển thị trang quản lý design với tìm kiếm và phân trang.
    """
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search_query', '', type=str)
    
    base_query = Design.query
    
    if search_query:
        search_term = f"%{search_query}%"
        base_query = base_query.filter(Design.name.ilike(search_term))

    designs_pagination = base_query.order_by(desc(Design.created_at)).paginate(
        page=page, per_page=30, error_out=False
    )
    
    form = DesignForm()

    return render_template(
        'designs/manage_designs.html', 
        title='Quản lý Design',
        designs=designs_pagination,
        form=form,
        search_query=search_query
    )

@designs_bp.route('/add', methods=['POST'])
@login_required
def add():
    """
    Xử lý việc thêm một design mới.
    """
    form = DesignForm()
    if form.validate_on_submit():
        new_design = Design(
            name=form.name.data,
            image_url=form.image_url.data,
            user_id=current_user.id
        )
        db.session.add(new_design)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Thêm design thành công!'})
    
    return jsonify({'success': False, 'errors': form.errors}), 400

@designs_bp.route('/details/<int:design_id>', methods=['GET'])
@login_required
def get_details(design_id):
    """
    Lấy thông tin chi tiết của một design để điền vào form chỉnh sửa.
    """
    design = db.session.get(Design, design_id)
    if not design:
        return jsonify({'success': False, 'message': 'Không tìm thấy design.'}), 404
    
    return jsonify({
        'success': True,
        'name': design.name,
        'image_url': design.image_url
    })

@designs_bp.route('/edit/<int:design_id>', methods=['POST'])
@login_required
def edit(design_id):
    """
    Xử lý việc cập nhật một design đã có.
    """
    design = db.session.get(Design, design_id)
    if not design:
        return jsonify({'success': False, 'message': 'Không tìm thấy design.'}), 404

    form = DesignForm()
    if form.validate_on_submit():
        design.name = form.name.data
        design.image_url = form.image_url.data
        db.session.commit()
        return jsonify({'success': True, 'message': 'Cập nhật design thành công!'})
        
    return jsonify({'success': False, 'errors': form.errors}), 400

@designs_bp.route('/delete/<int:design_id>', methods=['POST'])
@login_required
def delete(design_id):
    """
    Xóa một design.
    """
    design = db.session.get(Design, design_id)
    if not design:
        return jsonify({'success': False, 'message': 'Không tìm thấy design.'}), 404

    db.session.delete(design)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Đã xóa design.'})

@designs_bp.route('/delete-selected', methods=['POST'])
@login_required
def delete_selected():
    """
    Xóa nhiều design được chọn.
    """
    ids_to_delete = request.json.get('ids')
    if not ids_to_delete:
        return jsonify({'success': False, 'message': 'Không có design nào được chọn.'}), 400

    db.session.query(Design).filter(Design.id.in_(ids_to_delete)).delete(synchronize_session=False)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Đã xóa {len(ids_to_delete)} design.'})

# === START: THÊM ROUTE API ĐỂ LẤY TẤT CẢ DESIGN ===
@designs_bp.route('/api/all', methods=['GET'])
@login_required
def api_get_all_designs():
    """
    API endpoint để trả về danh sách tất cả các design cho Javascript.
    """
    # Trong tương lai có thể thêm logic quyền hạn ở đây
    all_designs = Design.query.order_by(Design.name).all()
    
    designs_list = [
        {'id': d.id, 'name': d.name, 'image_url': d.image_url} 
        for d in all_designs
    ]
    
    return jsonify({'success': True, 'designs': designs_list})
# === END: THÊM ROUTE API ĐỂ LẤY TẤT CẢ DESIGN ===