from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import json
import re
from .models import User

# Create your views here.

class RegisterView(View):
    def post(self, request, role):
        try:
            data = json.loads(request.body)
            fullname = data.get('fullname', '').strip()
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
            confirm_password = data.get('confirm_password', '')
            student_id = data.get('student_id', '').strip()

            # Validation
            if not all([fullname, email, password]):
                return JsonResponse({'error': 'Missing required fields'}, status=400)

            if password != confirm_password:
                return JsonResponse({'error': 'Passwords do not match'}, status=400)

            # Email validation
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                return JsonResponse({'error': 'Invalid email format'}, status=400)

            # Password validation
            if len(password) < 8:
                return JsonResponse({'error': 'Password must be at least 8 characters long'}, status=400)

            if User.objects.filter(email=email).exists():
                return JsonResponse({'error': 'Email already registered'}, status=400)

            if role == 'student' and not student_id:
                return JsonResponse({'error': 'Student ID is required for students'}, status=400)

            # Create user
            user = User.objects.create_user(
                username=email,  # Use email as username
                email=email,
                password=password,
                first_name=fullname.split()[0] if fullname else '',
                last_name=' '.join(fullname.split()[1:]) if len(fullname.split()) > 1 else '',
                role=role,
                student_id=student_id if role == 'student' else None,
                is_verified=False
            )

            # Auto login
            login(request, user)

            return JsonResponse({
                'success': True,
                'message': 'Registration successful',
                'user': {
                    'id': user.id,
                    'fullname': user.fullname,
                    'email': user.email,
                    'role': user.role,
                    'student_id': user.student_id,
                    'is_verified': user.is_verified
                }
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

class LoginView(View):
    def post(self, request, role):
        try:
            data = json.loads(request.body)
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')

            if not email or not password:
                return JsonResponse({'error': 'Email and password required'}, status=400)

            user = authenticate(request, username=email, password=password)
            if user and user.role == role:
                login(request, user)
                user.last_login_at = timezone.now()
                user.save()

                next_url = '/lecturer/dashboard/' if role == 'lecturer' else '/student/dashboard/'

                return JsonResponse({
                    'success': True,
                    'message': 'Login successful',
                    'user': {
                        'id': user.id,
                        'fullname': user.fullname,
                        'email': user.email,
                        'role': user.role,
                        'student_id': user.student_id,
                        'is_verified': user.is_verified
                    },
                    'redirect_url': next_url
                })
            else:
                return JsonResponse({'error': 'Invalid credentials'}, status=401)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

@login_required
def profile_view(request):
    if request.method == 'GET':
        user = request.user
        return JsonResponse({
            'id': user.id,
            'fullname': user.fullname,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
            'student_id': user.student_id,
            'is_verified': user.is_verified
        })
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            user = request.user

            if 'fullname' in data:
                names = data['fullname'].split()
                user.first_name = names[0] if names else ''
                user.last_name = ' '.join(names[1:]) if len(names) > 1 else ''

            if 'phone' in data:
                user.phone = data['phone']

            if 'student_id' in data and user.role == 'student':
                user.student_id = data['student_id']

            user.save()

            return JsonResponse({'message': 'Profile updated successfully'})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully')
    return redirect('/')

# Frontend template views
def home_view(request):
    return render(request, 'welcome_page/index.html')

def account_view(request):
    return render(request, 'welcome_page/account.html')

def lecturer_login_view(request):
    return render(request, 'lecturer_login.html')

def student_login_view(request):
     if request.method == 'POST':
        user_type = request.POST.get('user_type', '').strip()
        if user_type == 'lecturer':
            return redirect('lecturer_login/')
        elif user_type == 'student':
            return redirect('student_login/')

        return render(request, 'welcome_page/student_login.html')

def lecturer_create_account_view(request):
    return render(request, 'welcome_page/lecturer_create_account.html')

def student_create_account_view(request):
    return render(request, 'welcome_page/student_create_account.html')

@login_required
def lecturer_dashboard_view(request):
    if request.user.role != 'lecturer':
        return redirect('/student/dashboard/')
    return render(request, 'lecturer_page/lecturer_home.html')

@login_required
def student_dashboard_view(request):
    if request.user.role != 'student':
        return redirect('/lecturer/dashboard/')
    return render(request, 'student_page/student_home.html')
