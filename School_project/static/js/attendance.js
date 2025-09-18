// TapIn Attendance System JavaScript

// Global variables
let currentLocation = null;
let locationWatchId = null;
let isLocationSupported = 'geolocation' in navigator;

// Utility functions
function showAlert(message, type = 'info', duration = 5000) {
    const alertContainer = document.getElementById('alert-container') || createAlertContainer();

    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    alertContainer.appendChild(alert);

    // Auto-dismiss after duration
    if (duration > 0) {
        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, duration);
    }

    return alert;
}

function createAlertContainer() {
    const container = document.createElement('div');
    container.id = 'alert-container';
    container.className = 'position-fixed top-0 end-0 p-3';
    container.style.zIndex = '1050';
    document.body.appendChild(container);
    return container;
}

function setLoading(element, loading = true) {
    if (loading) {
        element.classList.add('loading');
        element.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading...';
        element.disabled = true;
    } else {
        element.classList.remove('loading');
        element.disabled = false;
    }
}

// Location/GPS functions
function requestLocationPermission() {
    return new Promise((resolve, reject) => {
        if (!isLocationSupported) {
            reject(new Error('Geolocation is not supported by this browser'));
            return;
        }

        navigator.permissions.query({ name: 'geolocation' }).then(result => {
            if (result.state === 'granted') {
                resolve(true);
            } else if (result.state === 'prompt') {
                // Request permission
                navigator.geolocation.getCurrentPosition(
                    () => resolve(true),
                    (error) => reject(error),
                    { timeout: 10000 }
                );
            } else {
                reject(new Error('Location permission denied'));
            }
        });
    });
}

function getCurrentLocation(options = {}) {
    return new Promise((resolve, reject) => {
        if (!isLocationSupported) {
            reject(new Error('Geolocation is not supported'));
            return;
        }

        const defaultOptions = {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 300000 // 5 minutes
        };

        navigator.geolocation.getCurrentPosition(
            (position) => {
                currentLocation = {
                    lat: position.coords.latitude,
                    lng: position.coords.longitude,
                    accuracy: position.coords.accuracy,
                    timestamp: position.timestamp
                };
                resolve(currentLocation);
            },
            (error) => {
                let errorMessage = 'Unable to get location';
                switch (error.code) {
                    case error.PERMISSION_DENIED:
                        errorMessage = 'Location permission denied. Please enable location services.';
                        break;
                    case error.POSITION_UNAVAILABLE:
                        errorMessage = 'Location information unavailable.';
                        break;
                    case error.TIMEOUT:
                        errorMessage = 'Location request timed out.';
                        break;
                }
                reject(new Error(errorMessage));
            },
            { ...defaultOptions, ...options }
        );
    });
}

function watchLocation(callback, options = {}) {
    if (!isLocationSupported) {
        console.warn('Geolocation not supported');
        return null;
    }

    const defaultOptions = {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 30000
    };

    locationWatchId = navigator.geolocation.watchPosition(
        (position) => {
            currentLocation = {
                lat: position.coords.latitude,
                lng: position.coords.longitude,
                accuracy: position.coords.accuracy,
                timestamp: position.timestamp
            };
            callback(currentLocation);
        },
        (error) => {
            console.error('Location watch error:', error);
            callback(null, error);
        },
        { ...defaultOptions, ...options }
    );

    return locationWatchId;
}

function stopWatchingLocation() {
    if (locationWatchId !== null) {
        navigator.geolocation.clearWatch(locationWatchId);
        locationWatchId = null;
    }
}

// API functions
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        credentials: 'same-origin',
    };

    try {
        const response = await fetch(url, { ...defaultOptions, ...options });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

function getCsrfToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : '';
}

// Check-in functions
async function performCheckIn(classId, locationData = null) {
    try {
        let location = locationData;
        if (!location) {
            location = await getCurrentLocation();
        }

        const data = {
            class_id: classId,
            lat: location.lat,
            lng: location.lng,
            accuracy: location.accuracy
        };

        const result = await apiRequest('/attendance/api/check-in/', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        return result;
    } catch (error) {
        throw new Error(`Check-in failed: ${error.message}`);
    }
}

async function verifyLocation(classId, lat, lng) {
    try {
        const result = await apiRequest(`/attendance/api/location/verify/?class_id=${classId}&lat=${lat}&lng=${lng}`);
        return result;
    } catch (error) {
        throw new Error(`Location verification failed: ${error.message}`);
    }
}

// Form validation
function validateForm(form) {
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;

    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(form)) {
                e.preventDefault();
                showAlert('Please fill in all required fields', 'danger');
            }
        });
    });

    // Real-time form validation
    const requiredInputs = document.querySelectorAll('input[required], select[required], textarea[required]');
    requiredInputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (!this.value.trim()) {
                this.classList.add('is-invalid');
            } else {
                this.classList.remove('is-invalid');
            }
        });

        input.addEventListener('input', function() {
            if (this.value.trim()) {
                this.classList.remove('is-invalid');
            }
        });
    });

    // Location permission requests
    const locationButtons = document.querySelectorAll('[data-request-location]');
    locationButtons.forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault();
            setLoading(button, true);

            try {
                await requestLocationPermission();
                showAlert('Location permission granted!', 'success');
                button.textContent = 'Location Enabled';
                button.classList.remove('btn-outline-primary');
                button.classList.add('btn-success');
            } catch (error) {
                showAlert(error.message, 'warning');
            } finally {
                setLoading(button, false);
            }
        });
    });

    // Check-in buttons
    const checkInButtons = document.querySelectorAll('[data-check-in]');
    checkInButtons.forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault();
            const classId = this.dataset.checkIn;
            setLoading(button, true);

            try {
                const result = await performCheckIn(classId);
                showAlert(result.message || 'Check-in successful!', 'success');

                // Update UI
                if (result.is_valid_location) {
                    this.textContent = 'Checked In ✓';
                    this.classList.remove('btn-success');
                    this.classList.add('btn-secondary');
                    this.disabled = true;
                }
            } catch (error) {
                showAlert(error.message, 'danger');
            } finally {
                setLoading(button, false);
            }
        });
    });

    // Auto-dismiss alerts
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        if (!alert.querySelector('.btn-close')) {
            setTimeout(() => {
                alert.remove();
            }, 5000);
        }
    });

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Export functions for global use
window.TapIn = {
    getCurrentLocation,
    requestLocationPermission,
    performCheckIn,
    verifyLocation,
    showAlert,
    setLoading,
    apiRequest
};