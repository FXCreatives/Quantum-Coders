from flask import Blueprint, request, jsonify
from .models import db, Class, Schedule, Enrollment, User
from .utils import auth_required
from datetime import datetime, time, timedelta
from sqlalchemy import and_

schedule_bp = Blueprint('schedule', __name__)

# Day mapping for better readability
DAYS_OF_WEEK = {
    0: 'Monday',
    1: 'Tuesday', 
    2: 'Wednesday',
    3: 'Thursday',
    4: 'Friday',
    5: 'Saturday',
    6: 'Sunday'
}

def time_to_string(time_obj):
    """Convert time object to string"""
    return time_obj.strftime('%H:%M') if time_obj else None

def string_to_time(time_str):
    """Convert time string to time object"""
    try:
        return datetime.strptime(time_str, '%H:%M').time()
    except ValueError:
        return None

@schedule_bp.post('/classes/<int:class_id>/schedule')
@auth_required(roles=['lecturer'])
def create_class_schedule(class_id):
    """Create or update class schedule"""
    try:
        # Verify lecturer owns this class
        cls = Class.query.get_or_404(class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        data = request.get_json(force=True)
        schedules_data = data.get('schedules', [])
        
        if not schedules_data:
            return jsonify({'error': 'Schedule data is required'}), 400
        
        # Delete existing schedules for this class
        Schedule.query.filter_by(class_id=class_id).delete()
        
        created_schedules = []
        
        for schedule_item in schedules_data:
            day_of_week = schedule_item.get('day_of_week')
            start_time_str = schedule_item.get('start_time')
            end_time_str = schedule_item.get('end_time')
            location = schedule_item.get('location', '')
            
            # Validation
            if day_of_week is None or day_of_week < 0 or day_of_week > 6:
                return jsonify({'error': 'Invalid day_of_week. Must be 0-6 (Monday-Sunday)'}), 400
            
            start_time = string_to_time(start_time_str)
            end_time = string_to_time(end_time_str)
            
            if not start_time or not end_time:
                return jsonify({'error': 'Invalid time format. Use HH:MM format'}), 400
            
            if start_time >= end_time:
                return jsonify({'error': 'Start time must be before end time'}), 400
            
            # Create schedule entry
            schedule = Schedule(
                class_id=class_id,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                location=location,
                is_active=True
            )
            db.session.add(schedule)
            created_schedules.append({
                'day_of_week': day_of_week,
                'day_name': DAYS_OF_WEEK[day_of_week],
                'start_time': start_time_str,
                'end_time': end_time_str,
                'location': location
            })
        
        db.session.commit()
        
        return jsonify({
            'message': 'Class schedule created successfully',
            'schedules': created_schedules
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create schedule', 'details': str(e)}), 500

@schedule_bp.get('/classes/<int:class_id>/schedule')
@auth_required()
def get_class_schedule(class_id):
    """Get class schedule"""
    try:
        # Verify access to this class
        cls = Class.query.get_or_404(class_id)
        
        if request.user_role == 'lecturer':
            if cls.lecturer_id != request.user_id:
                return jsonify({'error': 'Forbidden'}), 403
        else:  # student
            enrollment = Enrollment.query.filter_by(
                class_id=class_id, student_id=request.user_id
            ).first()
            if not enrollment:
                return jsonify({'error': 'Not enrolled in this class'}), 403
        
        # Get schedules
        schedules = Schedule.query.filter_by(
            class_id=class_id, is_active=True
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
        
        schedule_list = []
        for schedule in schedules:
            schedule_list.append({
                'id': schedule.id,
                'day_of_week': schedule.day_of_week,
                'day_name': DAYS_OF_WEEK[schedule.day_of_week],
                'start_time': time_to_string(schedule.start_time),
                'end_time': time_to_string(schedule.end_time),
                'location': schedule.location,
                'duration_minutes': int((datetime.combine(datetime.today(), schedule.end_time) - 
                                       datetime.combine(datetime.today(), schedule.start_time)).total_seconds() / 60)
            })
        
        return jsonify({
            'class_info': {
                'id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code
            },
            'schedules': schedule_list
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch schedule', 'details': str(e)}), 500

@schedule_bp.get('/lecturer/schedule/weekly')
@auth_required(roles=['lecturer'])
def get_lecturer_weekly_schedule():
    """Get lecturer's complete weekly schedule"""
    try:
        # Get all classes for this lecturer
        classes = Class.query.filter_by(lecturer_id=request.user_id).all()
        class_ids = [c.id for c in classes]
        
        if not class_ids:
            return jsonify({'weekly_schedule': {}, 'classes': []}), 200
        
        # Get all schedules for lecturer's classes
        schedules = db.session.query(Schedule, Class).join(
            Class, Schedule.class_id == Class.id
        ).filter(
            Schedule.class_id.in_(class_ids),
            Schedule.is_active == True
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
        
        # Organize by day
        weekly_schedule = {day: [] for day in DAYS_OF_WEEK.values()}
        
        for schedule, cls in schedules:
            day_name = DAYS_OF_WEEK[schedule.day_of_week]
            weekly_schedule[day_name].append({
                'schedule_id': schedule.id,
                'class_id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'start_time': time_to_string(schedule.start_time),
                'end_time': time_to_string(schedule.end_time),
                'location': schedule.location,
                'duration_minutes': int((datetime.combine(datetime.today(), schedule.end_time) - 
                                       datetime.combine(datetime.today(), schedule.start_time)).total_seconds() / 60)
            })
        
        return jsonify({
            'weekly_schedule': weekly_schedule,
            'classes': [
                {
                    'id': c.id,
                    'course_name': c.course_name,
                    'course_code': c.course_code
                } for c in classes
            ]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch weekly schedule', 'details': str(e)}), 500

@schedule_bp.get('/student/schedule/weekly')
@auth_required(roles=['student'])
def get_student_weekly_schedule():
    """Get student's complete weekly schedule"""
    try:
        # Get all enrolled classes
        enrolled_classes = db.session.query(Class).join(
            Enrollment, Enrollment.class_id == Class.id
        ).filter(Enrollment.student_id == request.user_id).all()
        
        class_ids = [c.id for c in enrolled_classes]
        
        if not class_ids:
            return jsonify({'weekly_schedule': {}, 'classes': []}), 200
        
        # Get all schedules for enrolled classes
        schedules = db.session.query(Schedule, Class).join(
            Class, Schedule.class_id == Class.id
        ).filter(
            Schedule.class_id.in_(class_ids),
            Schedule.is_active == True
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
        
        # Organize by day
        weekly_schedule = {day: [] for day in DAYS_OF_WEEK.values()}
        
        for schedule, cls in schedules:
            day_name = DAYS_OF_WEEK[schedule.day_of_week]
            weekly_schedule[day_name].append({
                'schedule_id': schedule.id,
                'class_id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'programme': cls.programme,
                'start_time': time_to_string(schedule.start_time),
                'end_time': time_to_string(schedule.end_time),
                'location': schedule.location,
                'duration_minutes': int((datetime.combine(datetime.today(), schedule.end_time) - 
                                       datetime.combine(datetime.today(), schedule.start_time)).total_seconds() / 60)
            })
        
        return jsonify({
            'weekly_schedule': weekly_schedule,
            'classes': [
                {
                    'id': c.id,
                    'course_name': c.course_name,
                    'course_code': c.course_code,
                    'programme': c.programme
                } for c in enrolled_classes
            ]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch weekly schedule', 'details': str(e)}), 500

@schedule_bp.get('/schedule/today')
@auth_required()
def get_today_schedule():
    """Get today's schedule for the current user"""
    try:
        today = datetime.now().weekday()  # 0=Monday, 6=Sunday
        
        if request.user_role == 'lecturer':
            # Get lecturer's classes
            classes = Class.query.filter_by(lecturer_id=request.user_id).all()
            class_ids = [c.id for c in classes]
        else:
            # Get student's enrolled classes
            enrolled_classes = db.session.query(Class).join(
                Enrollment, Enrollment.class_id == Class.id
            ).filter(Enrollment.student_id == request.user_id).all()
            class_ids = [c.id for c in enrolled_classes]
        
        if not class_ids:
            return jsonify({'today_schedule': [], 'day': DAYS_OF_WEEK[today]}), 200
        
        # Get today's schedules
        schedules = db.session.query(Schedule, Class).join(
            Class, Schedule.class_id == Class.id
        ).filter(
            Schedule.class_id.in_(class_ids),
            Schedule.day_of_week == today,
            Schedule.is_active == True
        ).order_by(Schedule.start_time).all()
        
        today_schedule = []
        current_time = datetime.now().time()
        
        for schedule, cls in schedules:
            # Determine status
            if current_time < schedule.start_time:
                status = 'upcoming'
            elif schedule.start_time <= current_time <= schedule.end_time:
                status = 'ongoing'
            else:
                status = 'completed'
            
            today_schedule.append({
                'schedule_id': schedule.id,
                'class_id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'start_time': time_to_string(schedule.start_time),
                'end_time': time_to_string(schedule.end_time),
                'location': schedule.location,
                'status': status,
                'duration_minutes': int((datetime.combine(datetime.today(), schedule.end_time) - 
                                       datetime.combine(datetime.today(), schedule.start_time)).total_seconds() / 60)
            })
        
        return jsonify({
            'today_schedule': today_schedule,
            'day': DAYS_OF_WEEK[today],
            'current_time': current_time.strftime('%H:%M')
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch today\'s schedule', 'details': str(e)}), 500

@schedule_bp.put('/schedule/<int:schedule_id>')
@auth_required(roles=['lecturer'])
def update_schedule(schedule_id):
    """Update a specific schedule entry"""
    try:
        schedule = Schedule.query.get_or_404(schedule_id)
        
        # Verify lecturer owns the class
        cls = Class.query.get(schedule.class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        data = request.get_json(force=True)
        
        # Update fields if provided
        if 'start_time' in data:
            start_time = string_to_time(data['start_time'])
            if not start_time:
                return jsonify({'error': 'Invalid start_time format'}), 400
            schedule.start_time = start_time
        
        if 'end_time' in data:
            end_time = string_to_time(data['end_time'])
            if not end_time:
                return jsonify({'error': 'Invalid end_time format'}), 400
            schedule.end_time = end_time
        
        if 'location' in data:
            schedule.location = data['location']
        
        if 'is_active' in data:
            schedule.is_active = bool(data['is_active'])
        
        # Validate times
        if schedule.start_time >= schedule.end_time:
            return jsonify({'error': 'Start time must be before end time'}), 400
        
        db.session.commit()
        
        return jsonify({
            'message': 'Schedule updated successfully',
            'schedule': {
                'id': schedule.id,
                'day_of_week': schedule.day_of_week,
                'day_name': DAYS_OF_WEEK[schedule.day_of_week],
                'start_time': time_to_string(schedule.start_time),
                'end_time': time_to_string(schedule.end_time),
                'location': schedule.location,
                'is_active': schedule.is_active
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update schedule', 'details': str(e)}), 500

@schedule_bp.delete('/schedule/<int:schedule_id>')
@auth_required(roles=['lecturer'])
def delete_schedule(schedule_id):
    """Delete a schedule entry"""
    try:
        schedule = Schedule.query.get_or_404(schedule_id)
        
        # Verify lecturer owns the class
        cls = Class.query.get(schedule.class_id)
        if cls.lecturer_id != request.user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        db.session.delete(schedule)
        db.session.commit()
        
        return jsonify({'message': 'Schedule deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete schedule', 'details': str(e)}), 500

@schedule_bp.get('/schedule/conflicts')
@auth_required(roles=['lecturer'])
def check_schedule_conflicts():
    """Check for scheduling conflicts in lecturer's classes"""
    try:
        # Get all classes for this lecturer
        classes = Class.query.filter_by(lecturer_id=request.user_id).all()
        class_ids = [c.id for c in classes]
        
        if not class_ids:
            return jsonify({'conflicts': []}), 200
        
        # Get all schedules
        schedules = db.session.query(Schedule, Class).join(
            Class, Schedule.class_id == Class.id
        ).filter(
            Schedule.class_id.in_(class_ids),
            Schedule.is_active == True
        ).order_by(Schedule.day_of_week, Schedule.start_time).all()
        
        conflicts = []
        
        # Check for overlapping schedules on the same day
        for i, (schedule1, class1) in enumerate(schedules):
            for j, (schedule2, class2) in enumerate(schedules[i+1:], i+1):
                if schedule1.day_of_week == schedule2.day_of_week:
                    # Check for time overlap
                    if (schedule1.start_time < schedule2.end_time and 
                        schedule1.end_time > schedule2.start_time):
                        conflicts.append({
                            'type': 'time_overlap',
                            'day': DAYS_OF_WEEK[schedule1.day_of_week],
                            'classes': [
                                {
                                    'id': class1.id,
                                    'name': class1.course_name,
                                    'code': class1.course_code,
                                    'time': f"{time_to_string(schedule1.start_time)}-{time_to_string(schedule1.end_time)}",
                                    'location': schedule1.location
                                },
                                {
                                    'id': class2.id,
                                    'name': class2.course_name,
                                    'code': class2.course_code,
                                    'time': f"{time_to_string(schedule2.start_time)}-{time_to_string(schedule2.end_time)}",
                                    'location': schedule2.location
                                }
                            ]
                        })
        
        return jsonify({
            'conflicts': conflicts,
            'total_conflicts': len(conflicts)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to check conflicts', 'details': str(e)}), 500