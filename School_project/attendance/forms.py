from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Class, AttendanceRecord

class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with role selection"""
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Administrator'),
    ]

    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True)
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'role')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']

        if commit:
            user.save()
            # Create user profile
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role']
            )
        return user

class UserProfileForm(forms.ModelForm):
    """Form for editing user profile"""
    class Meta:
        model = UserProfile
        fields = ['phone', 'location_permission_granted', 'location_data_retention_days']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'location_permission_granted': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'location_data_retention_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '365'}),
        }

class ClassForm(forms.ModelForm):
    """Form for creating/editing classes"""
    class Meta:
        model = Class
        fields = [
            'name', 'course_code', 'course_name', 'description',
            'level', 'section', 'geo_fence_lat', 'geo_fence_lng', 'geo_fence_radius'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'course_code': forms.TextInput(attrs={'class': 'form-control'}),
            'course_name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'level': forms.Select(attrs={'class': 'form-control'}),
            'section': forms.Select(attrs={'class': 'form-control'}),
            'geo_fence_lat': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'geo_fence_lng': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'geo_fence_radius': forms.NumberInput(attrs={'class': 'form-control', 'min': '10', 'max': '1000'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make geo-fence fields optional
        self.fields['geo_fence_lat'].required = False
        self.fields['geo_fence_lng'].required = False
        self.fields['geo_fence_radius'].required = False

class GeoFenceForm(forms.ModelForm):
    """Form for managing geo-fence settings"""
    class Meta:
        model = Class
        fields = ['geo_fence_lat', 'geo_fence_lng', 'geo_fence_radius']
        widgets = {
            'geo_fence_lat': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': 'any',
                'placeholder': 'Latitude (e.g., 40.7128)'
            }),
            'geo_fence_lng': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': 'any',
                'placeholder': 'Longitude (e.g., -74.0060)'
            }),
            'geo_fence_radius': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '10',
                'max': '1000',
                'placeholder': 'Radius in meters (e.g., 100)'
            }),
        }

class AttendanceForm(forms.ModelForm):
    """Form for marking attendance"""
    class Meta:
        model = AttendanceRecord
        fields = ['status', 'notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class BulkAttendanceForm(forms.Form):
    """Form for bulk attendance marking"""
    class_id = forms.IntegerField(widget=forms.HiddenInput())
    date = forms.DateField(widget=forms.HiddenInput())
    attendance_data = forms.CharField(widget=forms.HiddenInput())

class JoinClassForm(forms.Form):
    """Form for joining a class with PIN"""
    pin = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 6-digit PIN',
            'pattern': '[0-9]{6}',
            'title': 'Enter a 6-digit PIN'
        })
    )

class LocationCheckInForm(forms.Form):
    """Form for location-based check-in"""
    class_id = forms.IntegerField(widget=forms.HiddenInput())
    lat = forms.DecimalField(max_digits=10, decimal_places=8, widget=forms.HiddenInput())
    lng = forms.DecimalField(max_digits=11, decimal_places=8, widget=forms.HiddenInput())
    accuracy = forms.DecimalField(max_digits=6, decimal_places=2, required=False, widget=forms.HiddenInput())