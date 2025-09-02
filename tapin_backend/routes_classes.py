from flask import Blueprint, request, jsonify
from .models import db, User, Class, Enrollment
from .utils import auth_required
import random

classes_bp = Blueprint('classes', __name__)

@classes_bp.post('')
@auth_required(roles=['lecturer'])
def create_class():
    data = request.get_json(force=True)
    cls = Class(
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
    return jsonify({'id': cls.id, 'join_pin': cls.join_pin}), 201

@classes_bp.get('')
@auth_required()
def list_classes():
    role = request.user_role
    if role == 'lecturer':
        rows = Class.query.filter_by(lecturer_id=request.user_id).all()
    else:
        rows = db.session.query(Class).join(Enrollment, Enrollment.class_id == Class.id)\
            .filter(Enrollment.student_id == request.user_id).all()
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
    cls = Class.query.filter_by(join_pin=pin).first()
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
    rows = db.session.query(User).join(Enrollment, Enrollment.student_id == User.id)\
        .filter(Enrollment.class_id == class_id).all()
    return jsonify([{'id': u.id, 'name': u.name, 'email': u.email} for u in rows])
