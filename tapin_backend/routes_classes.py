from flask import Blueprint, request, jsonify
from tapin_backend.models import db, User, Course, Enrollment
from .utils import auth_required
import random

classes_bp = Blueprint('classes', __name__)

@classes_bp.post('')
@auth_required(roles=['lecturer'])
def create_class():
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logging.info(f"[CLASSES] Create class POST attempt for user_id: {getattr(request, 'user_id', 'Unknown')}, role: {getattr(request, 'user_role', 'Unknown')}")
    try:
        data = request.get_json(force=True)
        logging.info(f"[CLASSES] Received data: {data}")
        if not data:
            logging.warning("[CLASSES] No JSON data received")
            return jsonify({'error': 'No JSON data received'}), 400
        
        # Validate required fields
        required = ['programme', 'faculty', 'department', 'course_name', 'course_code', 'level', 'section']
        missing = [field for field in required if field not in data or not data[field]]
        if missing:
            logging.warning(f"[CLASSES] Missing fields: {missing}")
            return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400
        
        cls = Course(
            lecturer_id=request.user_id,
            programme=data['programme'],
            faculty=data['faculty'],
            department=data['department'],
            course_name=data['course_name'],
            course_code=data['course_code'],
            level=data['level'],
            section=data['section'],
            join_pin=data.get('join_pin') or str(random.randint(100000, 999999))
        )
        db.session.add(cls)
        db.session.commit()
        logging.info(f"[CLASSES] Class created successfully, id: {cls.id}")
        return jsonify({'id': cls.id, 'join_pin': cls.join_pin, 'message': 'Class created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        logging.error(f"[CLASSES] Error creating class: {str(e)}")
        return jsonify({'error': 'Failed to create class', 'details': str(e)}), 500

@classes_bp.get('')
@auth_required()
def list_classes():
    print(f"[CLASSES] List classes GET for role: {request.user_role}, user_id: {request.user_id}")
    role = request.user_role
    if role == 'lecturer':
        rows = Course.query.filter_by(lecturer_id=request.user_id).all()
    else:
        rows = db.session.query(Course).join(Enrollment, Enrollment.class_id == Course.id)\
            .filter(Enrollment.student_id == request.user_id).all()
    print(f"[CLASSES] Found {len(rows)} classes")
    return jsonify([{
        'id': c.id,
        'programme': c.programme,
        'faculty': c.faculty,
        'department': c.department,
        'course_name': c.course_name,
        'course_code': c.course_code,
        'level': c.level,
        'section': c.section,
        'join_pin': c.join_pin if role=='lecturer' else None
    } for c in rows])

@classes_bp.post('/join')
@auth_required(roles=['student'])
def join_class():
    data = request.get_json(force=True)
    pin = data.get('join_pin')
    if not pin:
        return jsonify({'error': 'join_pin is required'}), 400
    cls = Course.query.filter_by(join_pin=pin).first()
    if not cls:
        return jsonify({'error': 'Invalid PIN'}), 404
    existing = Enrollment.query.filter_by(class_id=cls.id, student_id=request.user_id).first()
    if existing:
        return jsonify({'message': 'Already enrolled', 'class_id': cls.id})
    enr = Enrollment(class_id=cls.id, student_id=request.user_id)
    db.session.add(enr)
    db.session.commit()
    return jsonify({'message': 'Joined class', 'class_id': cls.id})

@classes_bp.get('/<int:class_id>/students')
@auth_required(roles=['lecturer'])
def list_students(class_id):
    rows = db.session.query(User).join(Enrollment, Enrollment.class_id == class_id)\
        .filter(Enrollment.class_id == class_id).all()
    return jsonify([{'id': u.id, 'fullname': u.fullname, 'email': u.email} for u in rows])

@classes_bp.delete('/<int:class_id>')
@auth_required(roles=['lecturer'])
def delete_class(class_id):
    cls = Course.query.filter_by(id=class_id, lecturer_id=request.user_id).first_or_404()
    db.session.delete(cls)
    db.session.commit()
    return jsonify({'message': 'Class deleted successfully'})

@classes_bp.delete('/<int:class_id>/enrollment')
@auth_required(roles=['student'])
def leave_class(class_id):
    enrollment = Enrollment.query.filter_by(class_id=class_id, student_id=request.user_id).first()
    if not enrollment:
        return jsonify({'error': 'Not enrolled in this class'}), 404
    db.session.delete(enrollment)
    db.session.commit()
    return jsonify({'message': 'Successfully left the class'})
