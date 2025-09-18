from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import math

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=15, blank=True)
    location_permission_granted = models.BooleanField(default=False)
    location_data_retention_days = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

class Class(models.Model):
    name = models.CharField(max_length=200)
    course_code = models.CharField(max_length=20, unique=True)
    course_name = models.CharField(max_length=200)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='teaching_classes')
    description = models.TextField(blank=True)

    # Geolocation fields for geo-fencing
    geo_fence_lat = models.DecimalField(
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Latitude of geo-fence center"
    )
    geo_fence_lng = models.DecimalField(
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Longitude of geo-fence center"
    )
    geo_fence_radius = models.PositiveIntegerField(
        default=100,
        help_text="Radius of geo-fence in meters",
        validators=[MinValueValidator(10), MaxValueValidator(1000)]
    )

    # Class details
    level = models.CharField(max_length=10, choices=[
        ('100', '100 Level'),
        ('200', '200 Level'),
        ('300', '300 Level'),
        ('400', '400 Level'),
        ('500', '500 Level'),
    ])
    section = models.CharField(max_length=50, choices=[
        ('morning', 'Full Time (Morning)'),
        ('evening', 'Part Time (Evening)'),
        ('weekend', 'Distance (Weekend)'),
    ])

    join_pin = models.CharField(max_length=6, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Classes"

    def __str__(self):
        return f"{self.course_code} - {self.course_name}"

    def generate_join_pin(self):
        """Generate a random 6-digit PIN for class joining"""
        import random
        self.join_pin = str(random.randint(100000, 999999))
        self.save()

class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    class_enrolled = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['student', 'class_enrolled']

    def __str__(self):
        return f"{self.student.username} in {self.class_enrolled.course_code}"

class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ('P', 'Present'),
        ('A', 'Absent'),
        ('L', 'Late'),
        ('E', 'Excused'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_records')
    class_session = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='A')

    # Location data from student's device
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_in_lat = models.DecimalField(
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Latitude reported by student's device"
    )
    check_in_lng = models.DecimalField(
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Longitude reported by student's device"
    )
    check_in_accuracy = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="GPS accuracy in meters reported by device"
    )

    # Server-side verification results
    verified_distance = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Calculated distance from geo-fence center in meters"
    )
    is_valid_location = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)

    # Metadata
    marked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marked_attendance'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'class_session', 'date']
        ordering = ['-date', '-check_in_time']

    def __str__(self):
        return f"{self.student.username} - {self.class_session.course_code} - {self.date}"

    def calculate_distance(self):
        """Calculate Haversine distance between check-in location and geo-fence center"""
        if (self.check_in_lat is None or self.check_in_lng is None or
            self.class_session.geo_fence_lat is None or self.class_session.geo_fence_lng is None):
            return None

        # Haversine formula implementation
        lat1 = float(self.check_in_lat)
        lon1 = float(self.check_in_lng)
        lat2 = float(self.class_session.geo_fence_lat)
        lon2 = float(self.class_session.geo_fence_lng)

        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        # Earth's radius in meters
        R = 6371000
        distance = R * c

        return round(distance, 2)

    def verify_location(self):
        """Verify if the check-in location is within the geo-fence"""
        if not self.check_in_lat or not self.check_in_lng:
            self.is_valid_location = False
            self.verification_notes = "No location data provided"
            return False

        distance = self.calculate_distance()
        if distance is None:
            self.is_valid_location = False
            self.verification_notes = "Geo-fence not configured for this class"
            return False

        self.verified_distance = distance

        # Check accuracy threshold (reject if accuracy > 100m)
        if self.check_in_accuracy and self.check_in_accuracy > 100:
            self.is_valid_location = False
            self.verification_notes = f"GPS accuracy too low: {self.check_in_accuracy}m (max allowed: 100m)"
            return False

        # Check distance threshold
        if distance <= self.class_session.geo_fence_radius:
            self.is_valid_location = True
            self.verification_notes = f"Valid location: {distance}m from center (within {self.class_session.geo_fence_radius}m radius)"
            return True
        else:
            self.is_valid_location = False
            self.verification_notes = f"Outside geo-fence: {distance}m from center (radius: {self.class_session.geo_fence_radius}m)"
            return False

    def save(self, *args, **kwargs):
        # Auto-verify location when saving if location data is present
        if self.check_in_lat and self.check_in_lng and not self.verified_distance:
            self.verify_location()
        super().save(*args, **kwargs)
