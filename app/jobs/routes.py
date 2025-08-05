# app/jobs/routes.py

from flask import render_template, jsonify, flash, redirect, url_for
from flask_login import current_user, login_required
from . import jobs_bp
from app import db
from app.models import BackgroundTask
from app.decorators import admin_or_super_admin_required

@jobs_bp.route('/')
@login_required
def view():
    """Hiển thị trang chính của Tiến trình chạy ngầm."""
    return render_template('jobs/jobs.html', title='Tiến trình chạy ngầm')


@jobs_bp.route('/status')
@login_required
def status():
    """API endpoint để lấy trạng thái của các tác vụ dưới dạng JSON."""
    query = BackgroundTask.query.order_by(BackgroundTask.start_time.desc())

    if current_user.is_super_admin():
        tasks = query.all()
    elif current_user.is_admin():
        managed_user_ids = [user.id for user in current_user.children]
        managed_user_ids.append(current_user.id)
        tasks = query.filter(BackgroundTask.user_id.in_(managed_user_ids)).all()
    else:
        tasks = query.filter_by(user_id=current_user.id).all()

    tasks_data = [{
        'job_id': task.job_id, 'name': task.name, 'status': task.status,
        'progress': task.progress, 'total': task.total, 'log': task.log,
        'start_time': task.start_time.strftime('%d-%m-%Y %H:%M:%S') if task.start_time else 'N/A',
        'end_time': task.end_time.strftime('%d-%m-%Y %H:%M:%S') if task.end_time else None,
        'user': task.user.username if task.user else 'N/A'
    } for task in tasks]
    
    return jsonify(tasks_data)


@jobs_bp.route('/cancel/<job_id>', methods=['POST'])
@login_required
def cancel(job_id):
    """API endpoint để hủy một tác vụ đang chạy."""
    task = BackgroundTask.query.filter_by(job_id=job_id).first_or_404()
    
    can_cancel = False
    if current_user.is_super_admin() or task.user_id == current_user.id or \
       (current_user.is_admin() and task.user and task.user.parent_id == current_user.id):
        can_cancel = True

    if not can_cancel:
        return jsonify({'status': 'error', 'message': 'Bạn không có quyền hủy tác vụ này.'}), 403

    if task.status in ['running', 'queued']:
        task.requested_cancellation = True
        task.status = 'cancelling'
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Đã gửi yêu cầu hủy.'})
    else:
        return jsonify({'status': 'error', 'message': 'Không thể hủy tác vụ đã hoàn thành hoặc thất bại.'}), 400


@jobs_bp.route('/delete/<job_id>', methods=['POST'])
@login_required
@admin_or_super_admin_required
def delete(job_id):
    """API endpoint để xóa một tác vụ đã hoàn thành."""
    task = BackgroundTask.query.filter_by(job_id=job_id).first_or_404()

    if current_user.is_admin():
        is_own_task = task.user_id == current_user.id
        is_child_task = task.user and task.user.parent_id == current_user.id
        if not (is_own_task or is_child_task):
             return jsonify({'status': 'error', 'message': 'Bạn không có quyền xóa tác vụ này.'}), 403

    if task.status in ['complete', 'failed', 'cancelled', 'cancelling']:
        db.session.delete(task)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Đã xóa tác vụ thành công.'})
    else:
        return jsonify({'status': 'error', 'message': 'Chỉ có thể xóa các tác vụ đã kết thúc hoặc bị kẹt.'}), 400

# ### THAY ĐỔI ROUTE NÀY ###
@jobs_bp.route('/delete_all', methods=['POST']) # Đổi tên route
@login_required
@admin_or_super_admin_required
def delete_all(): # Đổi tên hàm
    """Xóa TOÀN BỘ tác vụ (theo quyền của người dùng)."""
    # Bỏ bộ lọc theo trạng thái, lấy tất cả tác vụ
    query = BackgroundTask.query
    
    # Giới hạn quyền xóa cho Admin (chỉ xóa của mình và của user con)
    if current_user.is_admin():
        managed_user_ids = [user.id for user in current_user.children]
        managed_user_ids.append(current_user.id)
        query = query.filter(BackgroundTask.user_id.in_(managed_user_ids))
        
    tasks_to_delete = query.all()
    num_deleted = len(tasks_to_delete)

    for task in tasks_to_delete:
        db.session.delete(task)
    
    db.session.commit()
    flash(f'Đã xóa thành công {num_deleted} tác vụ.', 'success') # Cập nhật thông báo
    return redirect(url_for('jobs.view'))
# ###########################