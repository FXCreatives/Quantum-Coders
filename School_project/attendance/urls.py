from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'attendance'

urlpatterns = [
    # Home and welcome pages
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Authentication URLs
    path('login/', auth_views.LoginView.as_view(template_name='attendance/login.html'), name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('register/', views.register, name='register'),

    # Student URLs
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/classes/', views.student_classes, name='student_classes'),
    path('student/class/<int:class_id>/', views.student_class_detail, name='student_class_detail'),
    path('student/attendance/', views.student_attendance_history, name='student_attendance_history'),
    path('student/check-in/<int:class_id>/', views.student_check_in, name='student_check_in'),
    path('student/join-class/', views.join_class, name='join_class'),

    # Teacher URLs
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/classes/', views.teacher_classes, name='teacher_classes'),
    path('teacher/class/<int:class_id>/', views.teacher_class_detail, name='teacher_class_detail'),
    path('teacher/class/<int:class_id>/attendance/', views.take_attendance, name='take_attendance'),
    path('teacher/class/<int:class_id>/attendance/<str:date>/', views.attendance_detail, name='attendance_detail'),
    path('teacher/class/<int:class_id>/reports/', views.class_reports, name='class_reports'),

    # Administrator URLs
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/', views.admin_users, name='admin_users'),
    path('admin/classes/', views.admin_classes, name='admin_classes'),
    path('admin/reports/', views.admin_reports, name='admin_reports'),
    path('admin/settings/', views.admin_settings, name='admin_settings'),

    # Class Management (Admin/Teacher)
    path('class/create/', views.create_class, name='create_class'),
    path('class/<int:class_id>/edit/', views.edit_class, name='edit_class'),
    path('class/<int:class_id>/delete/', views.delete_class, name='delete_class'),
    path('class/<int:class_id>/geo-fence/', views.manage_geo_fence, name='manage_geo_fence'),

    # User Management (Admin)
    path('user/<int:user_id>/profile/', views.user_profile, name='user_profile'),
    path('user/<int:user_id>/edit/', views.edit_user, name='edit_user'),

    # Attendance Management
    path('attendance/mark/', views.mark_attendance, name='mark_attendance'),
    path('attendance/bulk-mark/', views.bulk_mark_attendance, name='bulk_mark_attendance'),

    # API Endpoints for AJAX requests
    path('api/classes/', views.api_classes, name='api_classes'),
    path('api/class/<int:class_id>/students/', views.api_class_students, name='api_class_students'),
    path('api/attendance/check-in/', views.api_check_in, name='api_check_in'),
    path('api/location/verify/', views.api_verify_location, name='api_verify_location'),
    path('api/geo-fence/<int:class_id>/', views.api_geo_fence, name='api_geo_fence'),

    # Settings and Profile
    path('profile/', views.profile, name='profile'),
    path('settings/', views.settings, name='settings'),

    # Utility URLs
    path('about/', views.about, name='about'),
    path('help/', views.help, name='help'),
]