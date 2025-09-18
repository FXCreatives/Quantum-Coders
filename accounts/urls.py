from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # API routes
    path('api/auth/register/<str:role>/', views.RegisterView.as_view(), name='register'),
    path('api/auth/login/<str:role>/', views.LoginView.as_view(), name='login'),
    path('api/auth/me/', views.profile_view, name='profile'),
    path('api/auth/logout/', views.logout_view, name='logout'),

    # Frontend routes
    path('', views.home_view, name='home'),
    path('account/', views.account_view, name='account'),
    path('lecturer_login/', views.lecturer_login_view, name='lecturer_login'),
    path('student_login/', views.student_login_view, name='student_login'),
    path('lecturer_create_account/', views.lecturer_create_account_view, name='lecturer_create_account'),
    path('student_create_account/', views.student_create_account_view, name='student_create_account'),
    path('lecturer/dashboard/', views.lecturer_dashboard_view, name='lecturer_dashboard'),
    path('student/dashboard/', views.student_dashboard_view, name='student_dashboard'),
]