// Authentication helper for session-based auth
class AuthManager {
    constructor() {
        this.apiBaseUrl = window.getApiUrl ? window.getApiUrl('') : '/api';
        this.token = null;
        this.user = null;
    }

    // Initialize auth state
    async init() {
        console.log('[AUTH] Initializing auth');
        // Restore token from storage if exists
        const storedToken = sessionStorage.getItem('tapin_token');
        if (storedToken) {
            this.token = storedToken;
            console.log('[AUTH] Restored token from storage');
        }
    
        // If no token, check session via health
        if (!this.token) {
            try {
                const response = await fetch('/api/health', {
                    method: 'GET',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                console.log('[AUTH] /api/health response (no token):', { status: response.status, ok: response.ok });
            
                if (response.ok) {
                    // Session valid but no token - redirect to login to get proper JWT
                    console.log('[AUTH] Session valid but no token, redirecting to login');
                    window.location.href = '/account';
                    return false;
                }
            } catch (error) {
                console.error('Health check failed:', error);
            }
            return false;
        }
    
        // Validate existing token by fetching user profile
        try {
            const userData = await this.apiCall('/profile/me');
            if (userData && !userData.error) {
                this.user = userData;
                console.log('[AUTH] Token valid, user loaded:', { id: userData.id, role: userData.role });
                return true;
            } else {
                console.log('[AUTH] Token invalid, logging out');
                this.logout();
                return false;
            }
        } catch (error) {
            console.error('Token validation failed:', error);
            this.logout();
            return false;
        }
    }

    // Registration method
    async register(userData) {
        try {
            const response = await fetch('/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(userData),
                credentials: 'same-origin'
            });

            const data = await response.json();
            console.log('[AUTH] Register response:', data);

            if (response.ok && data.token) {
                this.token = data.token;
                this.user = data.user;
                sessionStorage.setItem('tapin_token', this.token);
                console.log('[AUTH] Registration successful, token captured');
                window.location.href = data.redirect_url;
                return { success: true, message: data.message };
            } else {
                return { success: false, error: data.error || 'Registration failed' };
            }
        } catch (error) {
            console.error('[AUTH] Register error:', error);
            return { success: false, error: error.message };
        }
    }

    // Login method
    async login(credentials) {
        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(credentials),
                credentials: 'same-origin'
            });

            const data = await response.json();
            console.log('[AUTH] Login response:', data);

            if (response.ok && data.token) {
                this.token = data.token;
                this.user = data.user;
                sessionStorage.setItem('tapin_token', this.token);
                console.log('[AUTH] Login successful, token captured');
                window.location.href = data.redirect_url;
                return { success: true, message: data.message };
            } else {
                return { success: false, error: data.message || 'Login failed' };
            }
        } catch (error) {
            console.error('[AUTH] Login error:', error);
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
    logout(reason = 'unknown') {
        console.log(`[AUTH] Logout called with reason: ${reason}`);
        this.token = null;
        this.user = null;
        sessionStorage.removeItem('tapin_token');
        // Only redirect if server session needs clearing (always for now, but log)
        console.log('[AUTH] Clearing client state, redirecting to server logout');
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
        let token = sessionStorage.getItem('tapin_token');
        if (token) {
            this.token = token;
        }
        return this.token;
    }

    // Check user role
    hasRole(role) {
        return this.user && this.user.role === role;
    }

    // API call helper with authentication
    async apiCall(endpoint, options = {}) {
        const url = this.apiBaseUrl + endpoint;
        const tokenToSend = this.token ? this.token.substring(0, 20) + '...' : 'no token';
        console.log('API Call:', { url, method: options.method || 'GET', body: options.body ? '[redacted]' : undefined, token: tokenToSend });
        
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
            const status = response.status;
            const statusText = response.statusText;
            console.log('API Response for', url, ':', { status, statusText, ok: response.ok });
            if (endpoint.includes('/profile/me')) {
                console.log('[AUTH/DEBUG] Specific response for /me:', { ok: response.ok, status });
            }
    
            if (response.status === 401) {
                console.error('[AUTH] 401 Unauthorized - likely invalid/expired token');
                // Token expired or invalid
                this.logout();
                return { error: 'Authentication required. Please log in again.' };
            }
    
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: 'Request failed', statusText }));
                console.error('API Error Response:', { status: response.status, error: errorData.error || statusText, endpoint });
                return { error: errorData.error || `HTTP ${status}: ${statusText}` };
            }
    
            const data = await response.json();
            if (endpoint.includes('/profile/me')) {
                console.log('[AUTH/DEBUG] /me success data:', data);
            }
            return data;
        } catch (error) {
            console.error('API call failed (network/fetch error):', error, { url, endpoint });
            return { error: `Network error: ${error.message}` };
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