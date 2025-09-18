from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
import json
import math
from datetime import datetime, date, timedelta

from .models import UserProfile, Class, Enrollment, AttendanceRecord
from .forms import (
    CustomUserCreationForm, UserProfileForm, ClassForm, GeoFenceForm,
    AttendanceForm, BulkAttendanceForm, JoinClassForm, LocationCheckInForm
)

# Utility functions
def get_user_role(user):
    """Get user role from profile"""
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return None

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate Haversine distance between two points"""
    R = 6371000  # Earth's radius in meters

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

# Authentication Views
def home(request):
    """Home page view"""
    if request.user.is_authenticated:
        return redirect('attendance:dashboard')
    return render(request, 'attendance/home.html')

@login_required
def dashboard(request):
    """Main dashboard - redirects based on user role"""
    role = get_user_role(request.user)
    if role == 'admin':
        return redirect('attendance:admin_dashboard')
    elif role == 'teacher':
        return redirect('attendance:teacher_dashboard')
    elif role == 'student':
        return redirect('attendance:student_dashboard')
    else:
        messages.error(request, 'Your account role is not configured properly.')
        return redirect('attendance:home')

def register(request):
    """User registration view"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Account created successfully! Please log in.')
            return redirect('attendance:login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'attendance/register.html', {'form': form})

def custom_logout(request):
    """Custom logout view with proper session cleanup"""
    if request.user.is_authenticated:
        username = request.user.username
        logout(request)
        messages.success(request, f'Goodbye {username}! You have been successfully logged out.')
    else:
        messages.info(request, 'You are not logged in.')

    return redirect('attendance:home')

# Student Views
@login_required
def student_dashboard(request):
    """Student dashboard"""
    if get_user_role(request.user) != 'student':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    # Get student's enrollments and recent attendance
    enrollments = Enrollment.objects.filter(
        student=request.user,
        is_active=True
    ).select_related('class_enrolled')

    recent_attendance = AttendanceRecord.objects.filter(
        student=request.user
    ).select_related('class_session').order_by('-date')[:10]

    context = {
        'enrollments': enrollments,
        'recent_attendance': recent_attendance,
    }
    return render(request, 'attendance/student_dashboard.html', context)

@login_required
def student_classes(request):
    """Student's enrolled classes"""
    if get_user_role(request.user) != 'student':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    enrollments = Enrollment.objects.filter(
        student=request.user,
        is_active=True
    ).select_related('class_enrolled')

    context = {
        'enrollments': enrollments,
    }
    return render(request, 'attendance/student_classes.html', context)

@login_required
def student_class_detail(request, class_id):
    """Student view of specific class"""
    if get_user_role(request.user) != 'student':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    class_obj = get_object_or_404(Class, id=class_id)
    enrollment = get_object_or_404(Enrollment, student=request.user, class_enrolled=class_obj)

    # Get attendance records for this class
    attendance_records = AttendanceRecord.objects.filter(
        student=request.user,
        class_session=class_obj
    ).order_by('-date')

    context = {
        'class': class_obj,
        'attendance_records': attendance_records,
    }
    return render(request, 'attendance/student_class_detail.html', context)

@login_required
def student_attendance_history(request):
    """Student's complete attendance history"""
    if get_user_role(request.user) != 'student':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    attendance_records = AttendanceRecord.objects.filter(
        student=request.user
    ).select_related('class_session').order_by('-date')

    # Pagination
    paginator = Paginator(attendance_records, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
    }
    return render(request, 'attendance/student_attendance_history.html', context)

@login_required
def student_check_in(request, class_id):
    """Student check-in for attendance"""
    if get_user_role(request.user) != 'student':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    class_obj = get_object_or_404(Class, id=class_id)

    # Check if student is enrolled
    try:
        enrollment = Enrollment.objects.get(student=request.user, class_enrolled=class_obj, is_active=True)
    except Enrollment.DoesNotExist:
        messages.error(request, 'You are not enrolled in this class.')
        return redirect('attendance:student_classes')

    context = {
        'class': class_obj,
    }
    return render(request, 'attendance/student_check_in.html', context)

@login_required
def join_class(request):
    """Student joins a class using PIN"""
    if get_user_role(request.user) != 'student':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    if request.method == 'POST':
        form = JoinClassForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data['pin']
            try:
                class_obj = Class.objects.get(join_pin=pin, is_active=True)
                # Check if already enrolled
                if Enrollment.objects.filter(student=request.user, class_enrolled=class_obj).exists():
                    messages.warning(request, 'You are already enrolled in this class.')
                else:
                    Enrollment.objects.create(student=request.user, class_enrolled=class_obj)
                    messages.success(request, f'Successfully joined {class_obj.course_name}!')
                return redirect('attendance:student_class_detail', class_id=class_obj.id)
            except Class.DoesNotExist:
                messages.error(request, 'Invalid PIN. Please check and try again.')
    else:
        form = JoinClassForm()

    return render(request, 'attendance/join_class.html', {'form': form})

# Teacher Views
@login_required
def teacher_dashboard(request):
    """Teacher dashboard"""
    if get_user_role(request.user) != 'teacher':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    # Get teacher's classes
    classes = Class.objects.filter(teacher=request.user, is_active=True)

    # Get recent attendance sessions
    recent_sessions = AttendanceRecord.objects.filter(
        class_session__teacher=request.user
    ).values('class_session', 'date').distinct().order_by('-date')[:5]

    context = {
        'classes': classes,
        'recent_sessions': recent_sessions,
    }
    return render(request, 'attendance/teacher_dashboard.html', context)

@login_required
def teacher_classes(request):
    """Teacher's classes"""
    if get_user_role(request.user) != 'teacher':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    classes = Class.objects.filter(teacher=request.user, is_active=True)

    context = {
        'classes': classes,
    }
    return render(request, 'attendance/teacher_classes.html', context)

@login_required
def teacher_class_detail(request, class_id):
    """Teacher view of specific class"""
    if get_user_role(request.user) != 'teacher':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    class_obj = get_object_or_404(Class, id=class_id, teacher=request.user)

    # Get enrolled students
    enrollments = Enrollment.objects.filter(
        class_enrolled=class_obj,
        is_active=True
    ).select_related('student')

    # Get recent attendance
    recent_attendance = AttendanceRecord.objects.filter(
        class_session=class_obj
    ).order_by('-date')[:10]

    context = {
        'class': class_obj,
        'enrollments': enrollments,
        'recent_attendance': recent_attendance,
    }
    return render(request, 'attendance/teacher_class_detail.html', context)

@login_required
def take_attendance(request, class_id):
    """Take attendance for a class"""
    if get_user_role(request.user) != 'teacher':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')

    class_obj = get_object_or_404(Class, id=class_id, teacher=request.user)
    today = date.today()

    if request.method == 'POST':
        # Process attendance marking
        attendance_data = {}
        for key, value in request.POST.items():
            if key.startswith('status_'):
                student_id = key.split('_')[1]
                attendance_data[int(student_id)] = value

        # Create attendance records
        for student_id, status in attendance_data.items():
            student = get_object_or_404(User, id=student_id)
            AttendanceRecord.objects.update_or_create(
                student=student,
                class_session=class_obj,
                date=today,
                defaults={
                    'status': status,
                    'marked_by': request.user,
                }
            )

        messages.success(request, 'Attendance marked successfully!')
        return redirect('attendance:teacher_class_detail', class_id=class_id)

    # Get enrolled students
    enrollments = Enrollment.objects.filter(
        class_enrolled=class_obj,
        is_active=True
    ).select_related('student')

    # Check if attendance already taken today
    existing_attendance = AttendanceRecord.objects.filter(
        class_session=class_obj,
        date=today
    ).select_related('student')

    existing_dict = {record.student.id: record for record in existing_attendance}

    context = {
        'class': class_obj,
        'enrollments': enrollments,
        'existing_attendance': existing_dict,
        'today': today,
    }
    return render(request, 'attendance/take_attendance.html', context)

# API Views
@csrf_exempt
@require_POST
@login_required
def api_check_in(request):
    """API endpoint for student check-in with location data"""
    try:
        data = json.loads(request.body)
        class_id = data.get('class_id')
        lat = data.get('lat')
        lng = data.get('lng')
        accuracy = data.get('accuracy', 0)

        if not all([class_id, lat, lng]):
            return JsonResponse({'error': 'Missing required data'}, status=400)

        class_obj = get_object_or_404(Class, id=class_id)

        # Check if student is enrolled
        try:
            enrollment = Enrollment.objects.get(
                student=request.user,
                class_enrolled=class_obj,
                is_active=True
            )
        except Enrollment.DoesNotExist:
            return JsonResponse({'error': 'Not enrolled in this class'}, status=403)

        # Create attendance record with location data
        attendance, created = AttendanceRecord.objects.update_or_create(
            student=request.user,
            class_session=class_obj,
            date=date.today(),
            defaults={
                'check_in_time': timezone.now(),
                'check_in_lat': lat,
                'check_in_lng': lng,
                'check_in_accuracy': accuracy,
                'marked_by': request.user,
            }
        )

        # Verify location
        is_valid = attendance.verify_location()
        attendance.save()

        response_data = {
            'success': True,
            'created': created,
            'is_valid_location': is_valid,
            'verification_notes': attendance.verification_notes,
            'distance': attendance.verified_distance,
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def api_verify_location(request):
    """API endpoint to verify location without creating attendance record"""
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    class_id = request.GET.get('class_id')

    if not all([lat, lng, class_id]):
        return JsonResponse({'error': 'Missing parameters'}, status=400)

    try:
        class_obj = get_object_or_404(Class, id=class_id)

        # Calculate distance
        if class_obj.geo_fence_lat and class_obj.geo_fence_lng:
            distance = haversine_distance(
                float(lat), float(lng),
                float(class_obj.geo_fence_lat), float(class_obj.geo_fence_lng)
            )

            is_in_range = distance <= class_obj.geo_fence_radius

            return JsonResponse({
                'distance': round(distance, 2),
                'radius': class_obj.geo_fence_radius,
                'is_in_range': is_in_range,
            })
        else:
            return JsonResponse({'error': 'Geo-fence not configured'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Placeholder views for remaining functionality
@login_required
def admin_dashboard(request):
    """Admin dashboard"""
    if get_user_role(request.user) != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')
    return render(request, 'attendance/admin_dashboard.html')

@login_required
def create_class(request):
    """Create new class"""
    if get_user_role(request.user) not in ['admin', 'teacher']:
        messages.error(request, 'Access denied.')
        return redirect('attendance:dashboard')
    return render(request, 'attendance/create_class.html')

@login_required
def profile(request):
    """User profile"""
    return render(request, 'attendance/profile.html')

@login_required
def settings(request):
    """User settings"""
    return render(request, 'attendance/settings.html')

def about(request):
    """About page"""
    return render(request, 'attendance/about.html')

def help(request):
    """Help page"""
    return render(request, 'attendance/help.html')

# Additional placeholder views
@login_required
def attendance_detail(request, class_id, date):
    return render(request, 'attendance/attendance_detail.html')

@login_required
def class_reports(request, class_id):
    return render(request, 'attendance/class_reports.html')

@login_required
def admin_users(request):
    return render(request, 'attendance/admin_users.html')

@login_required
def admin_classes(request):
    return render(request, 'attendance/admin_classes.html')

@login_required
def admin_reports(request):
    return render(request, 'attendance/admin_reports.html')

@login_required
def admin_settings(request):
    return render(request, 'attendance/admin_settings.html')

@login_required
def edit_class(request, class_id):
    return render(request, 'attendance/edit_class.html')

@login_required
def delete_class(request, class_id):
    return render(request, 'attendance/delete_class.html')

@login_required
def manage_geo_fence(request, class_id):
    return render(request, 'attendance/manage_geo_fence.html')

@login_required
def user_profile(request, user_id):
    return render(request, 'attendance/user_profile.html')

@login_required
def edit_user(request, user_id):
    return render(request, 'attendance/edit_user.html')

@login_required
def mark_attendance(request):
    return render(request, 'attendance/mark_attendance.html')

@login_required
def bulk_mark_attendance(request):
    return render(request, 'attendance/bulk_mark_attendance.html')

@login_required
def api_classes(request):
    return JsonResponse({'classes': []})

@login_required
def api_class_students(request, class_id):
    return JsonResponse({'students': []})

@login_required
def api_geo_fence(request, class_id):
    return JsonResponse({'geo_fence': {}})
