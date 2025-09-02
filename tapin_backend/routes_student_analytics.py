from flask import Blueprint, request, jsonify
from .models import db, Class, AttendanceSession, AttendanceRecord, Enrollment, User
from .utils import auth_required
from datetime import datetime, timedelta
from sqlalchemy import func, and_

student_analytics_bp = Blueprint('student_analytics', __name__)

@student_analytics_bp.get('/student/dashboard')
@auth_required(roles=['student'])
def get_student_dashboard():
    """Get comprehensive dashboard data for student"""
    try:
        # Get all enrolled classes
        enrolled_classes = db.session.query(Class).join(
            Enrollment, Enrollment.class_id == Class.id
        ).filter(Enrollment.student_id == request.user_id).all()
        
        class_ids = [c.id for c in enrolled_classes]
        
        if not class_ids:
            return jsonify({
                'total_classes': 0,
                'overall_attendance_rate': 0,
                'classes_summary': [],
                'recent_sessions': [],
                'attendance_trends': []
            }), 200
        
        # Get all attendance records for this student
        all_records = db.session.query(AttendanceRecord, AttendanceSession, Class).join(
            AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
        ).join(
            Class, AttendanceSession.class_id == Class.id
        ).filter(
            AttendanceRecord.student_id == request.user_id,
            AttendanceSession.class_id.in_(class_ids)
        ).all()
        
        # Calculate overall statistics
        total_records = len(all_records)
        present_records = len([r for r in all_records if r.AttendanceRecord.status == 'Present'])
        overall_attendance_rate = (present_records / total_records * 100) if total_records > 0 else 0
        
        # Get class-wise summary
        classes_summary = []
        for cls in enrolled_classes:
            class_records = [r for r in all_records if r.Class.id == cls.id]
            class_present = len([r for r in class_records if r.AttendanceRecord.status == 'Present'])
            class_rate = (class_present / len(class_records) * 100) if class_records else 0
            
            # Get total sessions for this class
            total_sessions = AttendanceSession.query.filter_by(class_id=cls.id).count()
            
            classes_summary.append({
                'id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'programme': cls.programme,
                'attendance_rate': round(class_rate, 2),
                'sessions_attended': class_present,
                'total_sessions': len(class_records),
                'all_sessions': total_sessions,
                'status': 'excellent' if class_rate >= 90 else 'good' if class_rate >= 75 else 'warning' if class_rate >= 60 else 'critical'
            })
        
        # Get recent attendance sessions (last 10)
        recent_sessions = []
        recent_records = sorted(all_records, key=lambda x: x.AttendanceRecord.timestamp, reverse=True)[:10]
        
        for record, session, cls in recent_records:
            recent_sessions.append({
                'class_name': cls.course_name,
                'class_code': cls.course_code,
                'date': record.timestamp.date().isoformat(),
                'time': record.timestamp.time().strftime('%H:%M'),
                'status': record.status,
                'method': session.method
            })
        
        # Get attendance trends (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_records_30d = [r for r in all_records if r.AttendanceRecord.timestamp >= thirty_days_ago]
        
        # Group by date
        daily_attendance = {}
        for record, session, cls in recent_records_30d:
            date_str = record.timestamp.date().isoformat()
            if date_str not in daily_attendance:
                daily_attendance[date_str] = {'present': 0, 'total': 0}
            
            daily_attendance[date_str]['total'] += 1
            if record.status == 'Present':
                daily_attendance[date_str]['present'] += 1
        
        attendance_trends = []
        for date_str, data in sorted(daily_attendance.items()):
            rate = (data['present'] / data['total'] * 100) if data['total'] > 0 else 0
            attendance_trends.append({
                'date': date_str,
                'rate': round(rate, 2),
                'present': data['present'],
                'total': data['total']
            })
        
        return jsonify({
            'total_classes': len(enrolled_classes),
            'overall_attendance_rate': round(overall_attendance_rate, 2),
            'total_sessions_attended': present_records,
            'total_sessions': total_records,
            'classes_summary': classes_summary,
            'recent_sessions': recent_sessions,
            'attendance_trends': attendance_trends
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch student dashboard', 'details': str(e)}), 500

@student_analytics_bp.get('/student/class/<int:class_id>/analytics')
@auth_required(roles=['student'])
def get_student_class_analytics(class_id):
    """Get detailed analytics for a specific class"""
    try:
        # Verify student is enrolled in this class
        enrollment = Enrollment.query.filter_by(
            class_id=class_id, student_id=request.user_id
        ).first()
        
        if not enrollment:
            return jsonify({'error': 'Not enrolled in this class'}), 403
        
        # Get class info
        cls = Class.query.get_or_404(class_id)
        
        # Get all attendance records for this student in this class
        records = db.session.query(AttendanceRecord, AttendanceSession).join(
            AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
        ).filter(
            AttendanceSession.class_id == class_id,
            AttendanceRecord.student_id == request.user_id
        ).order_by(AttendanceRecord.timestamp.desc()).all()
        
        # Calculate statistics
        total_attended = len(records)
        present_count = len([r for r in records if r.AttendanceRecord.status == 'Present'])
        attendance_rate = (present_count / total_attended * 100) if total_attended > 0 else 0
        
        # Get total sessions conducted (including ones student didn't attend)
        total_sessions = AttendanceSession.query.filter_by(class_id=class_id).count()
        missed_sessions = total_sessions - total_attended
        
        # Get attendance history
        attendance_history = []
        for record, session in records:
            attendance_history.append({
                'date': record.timestamp.date().isoformat(),
                'time': record.timestamp.time().strftime('%H:%M'),
                'status': record.status,
                'method': session.method,
                'session_duration': int((session.expires_at - session.created_at).total_seconds() / 60)
            })
        
        # Get attendance by method
        method_stats = {}
        for record, session in records:
            method = session.method
            if method not in method_stats:
                method_stats[method] = {'total': 0, 'present': 0}
            
            method_stats[method]['total'] += 1
            if record.status == 'Present':
                method_stats[method]['present'] += 1
        
        method_breakdown = []
        for method, stats in method_stats.items():
            rate = (stats['present'] / stats['total'] * 100) if stats['total'] > 0 else 0
            method_breakdown.append({
                'method': method,
                'total': stats['total'],
                'present': stats['present'],
                'rate': round(rate, 2)
            })
        
        # Get weekly attendance pattern
        weekly_pattern = {}
        for record, session in records:
            day_name = record.timestamp.strftime('%A')
            if day_name not in weekly_pattern:
                weekly_pattern[day_name] = {'total': 0, 'present': 0}
            
            weekly_pattern[day_name]['total'] += 1
            if record.status == 'Present':
                weekly_pattern[day_name]['present'] += 1
        
        weekly_stats = []
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
            if day in weekly_pattern:
                stats = weekly_pattern[day]
                rate = (stats['present'] / stats['total'] * 100) if stats['total'] > 0 else 0
                weekly_stats.append({
                    'day': day,
                    'rate': round(rate, 2),
                    'sessions': stats['total']
                })
        
        # Calculate performance insights
        insights = []
        
        if attendance_rate >= 90:
            insights.append({
                'type': 'success',
                'message': 'Excellent attendance! Keep up the great work.',
                'icon': '🎉'
            })
        elif attendance_rate >= 75:
            insights.append({
                'type': 'info',
                'message': 'Good attendance rate. Try to maintain consistency.',
                'icon': '👍'
            })
        elif attendance_rate >= 60:
            insights.append({
                'type': 'warning',
                'message': 'Your attendance needs improvement. Consider setting reminders.',
                'icon': '⚠️'
            })
        else:
            insights.append({
                'type': 'danger',
                'message': 'Critical: Your attendance is very low. Please speak with your lecturer.',
                'icon': '🚨'
            })
        
        if missed_sessions > 0:
            insights.append({
                'type': 'info',
                'message': f'You have missed {missed_sessions} session(s) that you didn\'t mark attendance for.',
                'icon': '📝'
            })
        
        return jsonify({
            'class_info': {
                'id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'programme': cls.programme,
                'department': cls.department
            },
            'statistics': {
                'attendance_rate': round(attendance_rate, 2),
                'sessions_attended': present_count,
                'total_sessions_marked': total_attended,
                'total_sessions_conducted': total_sessions,
                'missed_sessions': missed_sessions
            },
            'attendance_history': attendance_history,
            'method_breakdown': method_breakdown,
            'weekly_pattern': weekly_stats,
            'insights': insights
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch class analytics', 'details': str(e)}), 500

@student_analytics_bp.get('/student/attendance-comparison')
@auth_required(roles=['student'])
def get_attendance_comparison():
    """Compare student's attendance with class averages"""
    try:
        # Get all enrolled classes
        enrolled_classes = db.session.query(Class).join(
            Enrollment, Enrollment.class_id == Class.id
        ).filter(Enrollment.student_id == request.user_id).all()
        
        comparison_data = []
        
        for cls in enrolled_classes:
            # Get student's attendance for this class
            student_records = db.session.query(AttendanceRecord).join(
                AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
            ).filter(
                AttendanceSession.class_id == cls.id,
                AttendanceRecord.student_id == request.user_id
            ).all()
            
            student_present = len([r for r in student_records if r.status == 'Present'])
            student_rate = (student_present / len(student_records) * 100) if student_records else 0
            
            # Get class average attendance
            all_class_records = db.session.query(AttendanceRecord).join(
                AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
            ).filter(AttendanceSession.class_id == cls.id).all()
            
            if all_class_records:
                class_present = len([r for r in all_class_records if r.status == 'Present'])
                class_average = (class_present / len(all_class_records) * 100)
            else:
                class_average = 0
            
            # Get total enrolled students for context
            total_students = Enrollment.query.filter_by(class_id=cls.id).count()
            
            comparison_data.append({
                'class_id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'student_rate': round(student_rate, 2),
                'class_average': round(class_average, 2),
                'difference': round(student_rate - class_average, 2),
                'total_students': total_students,
                'student_sessions': len(student_records),
                'performance': 'above_average' if student_rate > class_average else 'below_average' if student_rate < class_average else 'average'
            })
        
        return jsonify({
            'comparison': comparison_data,
            'summary': {
                'classes_above_average': len([c for c in comparison_data if c['performance'] == 'above_average']),
                'classes_below_average': len([c for c in comparison_data if c['performance'] == 'below_average']),
                'total_classes': len(comparison_data)
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch attendance comparison', 'details': str(e)}), 500

@student_analytics_bp.get('/student/attendance-goals')
@auth_required(roles=['student'])
def get_attendance_goals():
    """Get attendance goals and progress tracking"""
    try:
        # Get all enrolled classes
        enrolled_classes = db.session.query(Class).join(
            Enrollment, Enrollment.class_id == Class.id
        ).filter(Enrollment.student_id == request.user_id).all()
        
        goals_data = []
        
        for cls in enrolled_classes:
            # Get student's attendance records
            records = db.session.query(AttendanceRecord).join(
                AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id
            ).filter(
                AttendanceSession.class_id == cls.id,
                AttendanceRecord.student_id == request.user_id
            ).all()
            
            present_count = len([r for r in records if r.status == 'Present'])
            total_sessions = len(records)
            current_rate = (present_count / total_sessions * 100) if total_sessions > 0 else 0
            
            # Calculate what's needed for different goal rates
            goals = [75, 80, 85, 90, 95]
            goal_analysis = []
            
            for goal_rate in goals:
                if current_rate >= goal_rate:
                    status = 'achieved'
                    sessions_needed = 0
                else:
                    # Calculate sessions needed to reach goal
                    # Formula: (present + x) / (total + x) = goal/100
                    # Solving for x: x = (goal*total - 100*present) / (100 - goal)
                    if goal_rate < 100:
                        sessions_needed = max(0, int((goal_rate * total_sessions - 100 * present_count) / (100 - goal_rate)))
                        status = 'achievable' if sessions_needed <= 10 else 'challenging'
                    else:
                        sessions_needed = float('inf')
                        status = 'impossible' if total_sessions > present_count else 'achievable'
                
                goal_analysis.append({
                    'goal_rate': goal_rate,
                    'status': status,
                    'sessions_needed': sessions_needed if sessions_needed != float('inf') else None,
                    'current_gap': round(goal_rate - current_rate, 2)
                })
            
            goals_data.append({
                'class_id': cls.id,
                'course_name': cls.course_name,
                'course_code': cls.course_code,
                'current_rate': round(current_rate, 2),
                'present_count': present_count,
                'total_sessions': total_sessions,
                'goals': goal_analysis
            })
        
        return jsonify({
            'classes': goals_data,
            'recommendations': [
                {
                    'type': 'tip',
                    'message': 'Aim for at least 75% attendance to meet minimum requirements.',
                    'icon': '🎯'
                },
                {
                    'type': 'tip',
                    'message': 'Set up attendance reminders to help maintain consistency.',
                    'icon': '⏰'
                },
                {
                    'type': 'tip',
                    'message': 'Review your weekly attendance patterns to identify improvement areas.',
                    'icon': '📊'
                }
            ]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to fetch attendance goals', 'details': str(e)}), 500