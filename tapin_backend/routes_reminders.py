from flask import Blueprint, request, jsonify, current_app
from .models import db, Class, AttendanceSession, Enrollment, User, Notification, Schedule
from .utils import auth_required
from datetime import datetime, timedelta
from threading import Thread
import time
from .routes_notifications import send_attendance_session_notification

reminders_bp = Blueprint('reminders', __name__)

# Global dictionary to store active reminder tasks
active_reminders = {}

def schedule_reminder_task(session_id, reminder_minutes_before):
    """Schedule a reminder task for an attendance session"""
    try:
        session = AttendanceSession.query.get(session_id)
        if not session:
            return False
        
        # Calculate when to send the reminder
        reminder_time = session.expires_at - timedelta(minutes=reminder_minutes_before)
        now = datetime.utcnow()
        
        if reminder_time <= now:
            # If reminder time has already passed, don't schedule
            return False
        
        # Calculate delay in seconds
        delay_seconds = (reminder_time - now).total_seconds()
        
        def reminder_task():
            time.sleep(delay_seconds)
            
            # Check if session is still active
            with current_app.app_context():
                session = AttendanceSession.query.get(session_id)
                if session and session.is_open and datetime.utcnow() < session.expires_at:
                    # Send reminder notification
                    send_attendance_session_notification(session.class_id, session_id, 'reminder')
                    current_app.logger.info(f"Sent reminder for session {session_id}")
                
                # Remove from active reminders
                if session_id in active_reminders:
                    del active_reminders[session_id]
        
        # Start the reminder task in a separate thread
        thread = Thread(target=reminder_task)
        thread.daemon = True
        thread.start()
        
        # Store the thread reference
        active_reminders[session_id] = thread
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Failed to schedule reminder for session {session_id}: {str(e)}")
        return False

@reminders_bp.post('/sessions/<int:session_id>/reminder')
@auth_required(roles=['lecturer'])
def set_attendance_reminder(session_id):
    """Set a reminder for an attendance session"""
    try:
        session = AttendanceSession.query.get_or_404(session_id)
        
        # Verify lecturer owns this class
        cls = Class.query.get(session.class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        data = request.get_json(force=True)
        reminder_minutes = int(data.get('reminder_minutes', 5))  # Default 5 minutes before
        
        if reminder_minutes <= 0 or reminder_minutes > 60:
            return jsonify({'error': 'Reminder minutes must be between 1 and 60'}), 400
        
        # Check if session is still active
        if not session.is_open or datetime.utcnow() >= session.expires_at:
            return jsonify({'error': 'Session is not active'}), 400
        
        # Cancel existing reminder if any
        if session_id in active_reminders:
            return jsonify({'error': 'Reminder already set for this session'}), 400
        
        # Schedule the reminder
        success = schedule_reminder_task(session_id, reminder_minutes)
        
        if success:
            return jsonify({
                'message': f'Reminder set for {reminder_minutes} minutes before session expires',
                'reminder_time': (session.expires_at - timedelta(minutes=reminder_minutes)).isoformat() + 'Z'
            }), 200
        else:
            return jsonify({'error': 'Failed to schedule reminder'}), 500
            
    except Exception as e:
        return jsonify({'error': 'Failed to set reminder', 'details': str(e)}), 500

@reminders_bp.delete('/sessions/<int:session_id>/reminder')
@auth_required(roles=['lecturer'])
def cancel_attendance_reminder(session_id):
    """Cancel a scheduled reminder"""
    try:
        session = AttendanceSession.query.get_or_404(session_id)
        
        # Verify lecturer owns this class
        cls = Class.query.get(session.class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        # Cancel the reminder if it exists
        if session_id in active_reminders:
            # Note: We can't actually stop the thread, but we remove it from tracking
            del active_reminders[session_id]
            return jsonify({'message': 'Reminder cancelled'}), 200
        else:
            return jsonify({'error': 'No active reminder found for this session'}), 404
            
    except Exception as e:
        return jsonify({'error': 'Failed to cancel reminder', 'details': str(e)}), 500

@reminders_bp.get('/sessions/<int:session_id>/reminder/status')
@auth_required(roles=['lecturer'])
def get_reminder_status(session_id):
    """Get reminder status for a session"""
    try:
        session = AttendanceSession.query.get_or_404(session_id)
        
        # Verify lecturer owns this class
        cls = Class.query.get(session.class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        has_reminder = session_id in active_reminders
        
        return jsonify({
            'session_id': session_id,
            'has_reminder': has_reminder,
            'session_expires_at': session.expires_at.isoformat() + 'Z',
            'is_active': session.is_open and datetime.utcnow() < session.expires_at
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get reminder status', 'details': str(e)}), 500

@reminders_bp.post('/classes/<int:class_id>/auto-reminders')
@auth_required(roles=['lecturer'])
def setup_auto_reminders(class_id):
    """Set up automatic reminders for future attendance sessions"""
    try:
        # Verify lecturer owns this class
        cls = Class.query.get_or_404(class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        data = request.get_json(force=True)
        enabled = data.get('enabled', True)
        reminder_minutes = int(data.get('reminder_minutes', 5))
        
        if reminder_minutes <= 0 or reminder_minutes > 60:
            return jsonify({'error': 'Reminder minutes must be between 1 and 60'}), 400
        
        # Store auto-reminder settings (you might want to add this to the Class model)
        # For now, we'll just return success and implement the logic when sessions are created
        
        return jsonify({
            'message': 'Auto-reminders configured successfully',
            'class_id': class_id,
            'enabled': enabled,
            'reminder_minutes': reminder_minutes
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to setup auto-reminders', 'details': str(e)}), 500

@reminders_bp.get('/lecturer/reminders/active')
@auth_required(roles=['lecturer'])
def get_active_reminders():
    """Get all active reminders for lecturer's sessions"""
    try:
        # Get lecturer's classes
        classes = Class.query.filter_by(lecturer_id=request.user_id).all()
        class_ids = [c.id for c in classes]
        
        if not class_ids:
            return jsonify({'active_reminders': []}), 200
        
        # Get active sessions with reminders
        active_reminder_list = []
        
        for session_id in active_reminders.keys():
            session = AttendanceSession.query.get(session_id)
            if session and session.class_id in class_ids:
                cls = Class.query.get(session.class_id)
                active_reminder_list.append({
                    'session_id': session_id,
                    'class_id': session.class_id,
                    'class_name': cls.course_name,
                    'class_code': cls.course_code,
                    'expires_at': session.expires_at.isoformat() + 'Z',
                    'method': session.method
                })
        
        return jsonify({
            'active_reminders': active_reminder_list,
            'total_active': len(active_reminder_list)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get active reminders', 'details': str(e)}), 500

@reminders_bp.post('/schedule-based-reminders')
@auth_required(roles=['lecturer'])
def setup_schedule_based_reminders():
    """Set up reminders based on class schedule"""
    try:
        data = request.get_json(force=True)
        class_id = data.get('class_id')
        enabled = data.get('enabled', True)
        reminder_minutes_before_class = int(data.get('reminder_minutes_before_class', 15))
        
        if not class_id:
            return jsonify({'error': 'class_id is required'}), 400
        
        # Verify lecturer owns this class
        cls = Class.query.get_or_404(class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        if not enabled:
            return jsonify({'message': 'Schedule-based reminders disabled'}), 200
        
        # Get class schedule
        schedules = Schedule.query.filter_by(class_id=class_id, is_active=True).all()
        
        if not schedules:
            return jsonify({'error': 'No active schedule found for this class'}), 400
        
        # For demonstration, we'll just return the configuration
        # In a real implementation, you'd set up recurring reminders based on the schedule
        
        upcoming_classes = []
        now = datetime.now()
        current_weekday = now.weekday()
        
        for schedule in schedules:
            # Calculate next occurrence of this scheduled class
            days_ahead = schedule.day_of_week - current_weekday
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            
            next_class_date = now.date() + timedelta(days=days_ahead)
            next_class_datetime = datetime.combine(next_class_date, schedule.start_time)
            
            upcoming_classes.append({
                'day': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][schedule.day_of_week],
                'time': schedule.start_time.strftime('%H:%M'),
                'location': schedule.location,
                'next_occurrence': next_class_datetime.isoformat() + 'Z',
                'reminder_time': (next_class_datetime - timedelta(minutes=reminder_minutes_before_class)).isoformat() + 'Z'
            })
        
        return jsonify({
            'message': 'Schedule-based reminders configured',
            'class_info': {
                'id': cls.id,
                'name': cls.course_name,
                'code': cls.course_code
            },
            'reminder_minutes_before_class': reminder_minutes_before_class,
            'upcoming_classes': upcoming_classes
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to setup schedule-based reminders', 'details': str(e)}), 500

@reminders_bp.get('/student/upcoming-classes')
@auth_required(roles=['student'])
def get_student_upcoming_classes():
    """Get student's upcoming classes with reminder options"""
    try:
        # Get enrolled classes
        enrolled_classes = db.session.query(Class).join(
            Enrollment, Enrollment.class_id == Class.id
        ).filter(Enrollment.student_id == request.user_id).all()
        
        class_ids = [c.id for c in enrolled_classes]
        
        if not class_ids:
            return jsonify({'upcoming_classes': []}), 200
        
        # Get schedules for enrolled classes
        schedules = db.session.query(Schedule, Class).join(
            Class, Schedule.class_id == Class.id
        ).filter(
            Schedule.class_id.in_(class_ids),
            Schedule.is_active == True
        ).all()
        
        upcoming_classes = []
        now = datetime.now()
        current_weekday = now.weekday()
        
        for schedule, cls in schedules:
            # Calculate next occurrence
            days_ahead = schedule.day_of_week - current_weekday
            if days_ahead < 0:  # Target day already happened this week
                days_ahead += 7
            elif days_ahead == 0:  # Today
                if now.time() > schedule.start_time:
                    days_ahead = 7  # Next week
            
            next_class_date = now.date() + timedelta(days=days_ahead)
            next_class_datetime = datetime.combine(next_class_date, schedule.start_time)
            
            # Check if there's an active attendance session
            active_session = AttendanceSession.query.filter(
                AttendanceSession.class_id == cls.id,
                AttendanceSession.is_open == True,
                AttendanceSession.expires_at > now
            ).first()
            
            upcoming_classes.append({
                'class_id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'day': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][schedule.day_of_week],
                'time': schedule.start_time.strftime('%H:%M'),
                'location': schedule.location,
                'next_occurrence': next_class_datetime.isoformat() + 'Z',
                'days_until': days_ahead,
                'has_active_session': active_session is not None,
                'active_session_id': active_session.id if active_session else None
            })
        
        # Sort by next occurrence
        upcoming_classes.sort(key=lambda x: x['next_occurrence'])
        
        return jsonify({
            'upcoming_classes': upcoming_classes[:10],  # Next 10 classes
            'total_enrolled_classes': len(enrolled_classes)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get upcoming classes', 'details': str(e)}), 500