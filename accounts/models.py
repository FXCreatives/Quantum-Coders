from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class User(AbstractUser):
    ROLE_CHOICES = [
        ('lecturer', 'Lecturer'),
        ('student', 'Student'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    student_id = models.CharField(max_length=50, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    avatar_url = models.URLField(blank=True, null=True)
    last_login_at = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.fullname} ({self.role})"
    
    @property
    def fullname(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

class Course(models.Model):
    lecturer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses')
    programme = models.CharField(max_length=120)
    faculty = models.CharField(max_length=120)
    department = models.CharField(max_length=120)
    course_name = models.CharField(max_length=160)
    class_name = models.CharField(max_length=160)
    course_code = models.CharField(max_length=60, unique=True)
    level = models.CharField(max_length=20)
    section = models.CharField(max_length=40)
    semester = models.CharField(max_length=20, default='Fall')
    join_pin = models.CharField(max_length=10)
    join_code = models.CharField(max_length=32, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.course_code} - {self.course_name}"

class Enrollment(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('dropped', 'Dropped'),
    ]
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    joined_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = ['course', 'student']
    
    def __str__(self):
        return f"{self.student.fullname} in {self.course.course_name}"

class AttendanceSession(models.Model):
    METHOD_CHOICES = [
        ('geo', 'Geolocation'),
        ('pin', 'PIN'),
        ('qr', 'QR Code'),
    ]
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='attendance_sessions')
    lecturer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_sessions')
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    pin_code = models.CharField(max_length=10, blank=True, null=True)
    lecturer_lat = models.FloatField(blank=True, null=True)
    lecturer_lng = models.FloatField(blank=True, null=True)
    radius_m = models.IntegerField(default=120)
    expires_at = models.DateTimeField()
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"Session for {self.course.course_name} - {self.method}"

class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Late', 'Late'),
    ]
    
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_records')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Present')
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = ['session', 'student']
    
    def __str__(self):
        return f"{self.student.fullname} - {self.status}"

class Announcement(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='announcements', blank=True, null=True)
    title = models.CharField(max_length=160)
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return self.title

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    text = models.CharField(max_length=500)
    read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"Notification for {self.user.fullname}"

class Schedule(models.Model):
    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=200, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.course.course_name} - {self.get_day_of_week_display()}"
