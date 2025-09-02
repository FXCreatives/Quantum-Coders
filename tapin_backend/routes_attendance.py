from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from .models import db, Class, AttendanceSession, AttendanceRecord, Enrollment
from .utils import auth_required, distance_m
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

attendance_bp = Blueprint('attendance', __name__)

# -------------------------
# Lecturer opens attendance session
# -------------------------
@attendance_bp.post('/classes/<int:class_id>/sessions')
@auth_required(roles=['lecturer'])
def open_session(class_id):
    try:
        data = request.get_json(force=True)
        method = data.get('method')  # 'geo' or 'pin'
        duration_sec = int(data.get('duration_sec', 300))

        if method not in ('geo', 'pin'):
            return jsonify({'error': 'Invalid method'}), 400
        if method == 'pin' and not data.get('pin_code'):
            return jsonify({'error': 'PIN code required for PIN-based attendance'}), 400

        cls = Class.query.get_or_404(class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403

        sess = AttendanceSession(
            class_id=class_id,
            method=method,
            pin_code=data.get('pin_code') if method == 'pin' else None,
            lecturer_lat=data.get('lecturer_lat') if method == 'geo' else None,
            lecturer_lng=data.get('lecturer_lng') if method == 'geo' else None,
            radius_m=int(data.get('radius_m', 120)),
            expires_at=datetime.utcnow() + timedelta(seconds=duration_sec),
            is_open=True
        )
        db.session.add(sess)
        db.session.commit()

        logging.info(f"Attendance session {sess.id} opened by lecturer {request.user_id}")
        return jsonify({'session_id': sess.id, 'expires_at': sess.expires_at.isoformat() + 'Z'}), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error opening attendance session: {e}")
        return jsonify({'error': 'Failed to open session', 'details': str(e)}), 500


# -------------------------
# Get active session for a class
# -------------------------
@attendance_bp.get('/classes/<int:class_id>/sessions/active')
@auth_required()
def get_active_session(class_id):
    now = datetime.utcnow()
    sess = AttendanceSession.query.filter(
        AttendanceSession.class_id == class_id,
        AttendanceSession.is_open == True,
        AttendanceSession.expires_at > now
    ).order_by(AttendanceSession.id.desc()).first()

    if not sess:
        return jsonify({'active': False}), 200

    payload = {
        'active': True,
        'session_id': sess.id,
        'method': sess.method,
        'expires_at': sess.expires_at.isoformat() + 'Z',
        'radius_m': sess.radius_m,
        'lecturer_lat': sess.lecturer_lat,
        'lecturer_lng': sess.lecturer_lng,
        'needs_pin': bool(sess.pin_code)
    }
    return jsonify(payload), 200


# -------------------------
# Student marks attendance
# -------------------------
@attendance_bp.post('/attendance/mark')
@auth_required(roles=['student'])
def mark_attendance():
    try:
        data = request.get_json(force=True)
        session_id = int(data.get('session_id'))
        sess = AttendanceSession.query.get_or_404(session_id)

        # Ensure student is enrolled in the class
        enrolled = Enrollment.query.filter_by(class_id=sess.class_id, student_id=request.user_id).first()
        if not enrolled:
            return jsonify({'error': 'Not enrolled in this class'}), 403

        # Check if session is still open
        if not sess.is_open or datetime.utcnow() > sess.expires_at:
            return jsonify({'error': 'Session is closed'}), 400

        # Validate attendance method
        if sess.method == 'pin':
            pin = str(data.get('pin') or '')
            if pin != (sess.pin_code or ''):
                return jsonify({'error': 'Invalid PIN'}), 400
        else:
            lat = data.get('lat')
            lng = data.get('lng')
            if lat is None or lng is None or sess.lecturer_lat is None or sess.lecturer_lng is None:
                return jsonify({'error': 'Location required'}), 400
            distance = distance_m(float(lat), float(lng), float(sess.lecturer_lat), float(sess.lecturer_lng))
            if distance > (sess.radius_m or 120):
                return jsonify({'error': 'Out of allowed radius'}), 400

        # Record attendance (prevent duplicates)
        existing_record = AttendanceRecord.query.filter_by(session_id=session_id, student_id=request.user_id).first()
        if existing_record:
            return jsonify({'message': 'Already marked', 'status': existing_record.status}), 200

        rec = AttendanceRecord(session_id=session_id, student_id=request.user_id, status='Present')
        db.session.add(rec)
        db.session.commit()

        logging.info(f"Attendance marked for student {request.user_id} in session {session_id}")
        return jsonify({'message': 'Attendance marked', 'status': 'Present'}), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error marking attendance: {e}")
        return jsonify({'error': 'Failed to mark attendance', 'details': str(e)}), 500


# -------------------------
# Get attendance history
# -------------------------
@attendance_bp.get('/classes/<int:class_id>/attendance/history')
@auth_required()
def history(class_id):
    try:
        if request.user_role == 'student':
            # Student: fetch their own history
            q = db.session.query(AttendanceRecord, AttendanceSession).join(
                AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
            ).filter(
                AttendanceSession.class_id == class_id,
                AttendanceRecord.student_id == request.user_id
            )
        else:
            # Lecturer: fetch for all students, optionally filter by student_id
            student_id = request.args.get('student_id')
            q = db.session.query(AttendanceRecord, AttendanceSession).join(
                AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
            ).filter(
                AttendanceSession.class_id == class_id
            )
            if student_id:
                q = q.filter(AttendanceRecord.student_id == int(student_id))

        rows = q.order_by(AttendanceRecord.timestamp.desc()).limit(100).all()

        if request.user_role == 'student':
            result = [
                {
                    'date': r.AttendanceRecord.timestamp.date().isoformat(),
                    'status': r.AttendanceRecord.status
                }
                for r in rows
            ]
        else:
            result = [
                {
                    'student_id': r.AttendanceRecord.student_id,
                    'date': r.AttendanceRecord.timestamp.isoformat() + 'Z',
                    'status': r.AttendanceRecord.status
                }
                for r in rows
            ]

        return jsonify(result), 200

    except Exception as e:
        logging.error(f"Error fetching attendance history: {e}")
        return jsonify({'error': 'Failed to fetch attendance history', 'details': str(e)}), 500


# -------------------------
# Lecturer closes attendance session
# -------------------------
@attendance_bp.patch('/sessions/<int:session_id>/close')
@auth_required(roles=['lecturer'])
def close_session(session_id):
    try:
        sess = AttendanceSession.query.get_or_404(session_id)
        cls = Class.query.get(sess.class_id)

        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403

        sess.is_open = False
        db.session.commit()

        logging.info(f"Attendance session {session_id} closed by lecturer {request.user_id}")
        return jsonify({
            'message': 'Session closed',
            'session_id': sess.id,
            'closed_at': datetime.utcnow().isoformat() + 'Z'
        }), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error closing session: {e}")
        return jsonify({'error': 'Failed to close session', 'details': str(e)}), 500
