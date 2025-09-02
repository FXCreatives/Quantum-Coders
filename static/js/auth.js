// Authentication helper for session-based auth
class AuthManager {
    constructor() {
        this.apiBaseUrl = window.getApiUrl ? window.getApiUrl('') : '/api';
        this.token = null;
        this.user = null;
    }

    // Initialize auth state
    async init() {
        // Check if user is logged in via session
        try {
            // First check if we have a session by making a request to a protected route
            const response = await fetch('/api/health', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                // User is authenticated via session
                this.user = { authenticated: true };
                // Generate a temporary token for API calls
                this.token = btoa(JSON.stringify({
                    session_auth: true,
                    exp: Date.now() + (24 * 60 * 60 * 1000) // 24 hours
                }));
                sessionStorage.setItem('tapin_token', this.token);
                return true;
            } else {
                this.logout();
                return false;
            }
        } catch (error) {
            console.error('Auth initialization failed:', error);
            this.logout();
            return false;
        }
    }

    // Registration method
    async register(userData) {
        try {
            const formData = new FormData();
            formData.append('fullname', userData.fullname);
            formData.append('email', userData.email);
            formData.append('password', userData.password);
            formData.append('confirm-password', userData.confirmPassword);

            if (userData.student_id) {
                formData.append('student_id', userData.student_id);
            }

            const response = await fetch('/register', {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            });

            if (response.ok) {
                // Registration successful, redirect will happen automatically
                return { success: true, message: 'Registration successful' };
            } else {
                const errorText = await response.text();
                return { success: false, error: errorText };
            }
        } catch (error) {
            return { success: false, error: error.message };
        }
    }

    // Login method
    async login(credentials) {
        try {
            const formData = new FormData();
            formData.append('email', credentials.email);
            formData.append('password', credentials.password);

            const response = await fetch('/login', {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            });

            if (response.ok) {
                // Redirect will happen automatically
                window.location.reload();
                return { success: true };
            } else {
                const errorText = await response.text();
                return { success: false, error: errorText };
            }
        } catch (error) {
            return { success: false, error: error.message };
        }
    }

    // Student login with student ID
    async studentLogin(credentials) {
        try {
            const formData = new FormData();
            formData.append('fullname', credentials.studentId); // Student ID
            formData.append('email', credentials.email || '');
            formData.append('password', credentials.password);

            const response = await fetch('/login_student', {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            });

            if (response.ok) {
                // Redirect will happen automatically
                window.location.reload();
                return { success: true };
            } else {
                const errorText = await response.text();
                return { success: false, error: errorText };
            }
        } catch (error) {
            return { success: false, error: error.message };
        }
    }

    // Logout method
    logout() {
        this.token = null;
        this.user = null;
        sessionStorage.removeItem('tapin_token');
        // Redirect to logout endpoint
        window.location.href = '/logout';
    }

    // Check if user is authenticated
    isAuthenticated() {
        return this.user !== null && this.token !== null;
    }

    // Get current user
    getCurrentUser() {
        return this.user;
    }

    // Get auth token
    getToken() {
        return this.token;
    }

    // Check user role
    hasRole(role) {
        return this.user && this.user.role === role;
    }

    // API call helper with authentication
    async apiCall(endpoint, options = {}) {
        const url = this.apiBaseUrl + endpoint;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {})
            },
            credentials: 'same-origin'
        };

        const finalOptions = { ...defaultOptions, ...options };
        if (options.headers) {
            finalOptions.headers = { ...defaultOptions.headers, ...options.headers };
        }

        try {
            const response = await fetch(url, finalOptions);

            if (response.status === 401) {
                // Token expired or invalid
                this.logout();
                return { error: 'Authentication required' };
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: 'Request failed' }));
                return { error: errorData.error || 'Request failed' };
            }

            return await response.json();
        } catch (error) {
            console.error('API call failed:', error);
            return { error: error.message };
        }
    }
}

// Global auth manager instance
const authManager = new AuthManager();

// Initialize auth when DOM is loaded (only on protected pages)
document.addEventListener('DOMContentLoaded', async () => {
    // Skip auth initialization on registration/login pages
    const currentPath = window.location.pathname;
    const authPages = ['/account', '/lecturer_login', '/student_login',
                      '/lecturer_create_account', '/student_create_account',
                      '/lecturer_forgot_password', '/student_forgot_password',
                      '/reset_password'];

    if (authPages.some(page => currentPath.includes(page))) {
        return; // Don't initialize auth on auth pages
    }

    const isAuthenticated = await authManager.init();

    if (!isAuthenticated) {
        // Redirect to login if not authenticated and not on auth pages
        window.location.href = '/account';
    }
});

// Export for use in other scripts
window.AuthManager = AuthManager;
window.authManager = authManager;