// Authentication helper for session-based auth
class AuthManager {
    constructor() {
        this.apiBaseUrl = window.getApiUrl ? window.getApiUrl('') : '/api';
        this.token = null;
        this.user = null;
    }

    // Initialize auth state
    async init() {
        // Detect if running from local file (file://) - not supported for API calls due to CORS
        if (window.location.protocol === 'file:') {
            console.error('[AUTH] Detected file:// protocol. Cannot make API calls due to CORS restrictions.');
            alert('This page cannot be opened directly as a local HTML file. Please run the Flask server with "python tapin_backend/app.py" (or equivalent) and access via http://localhost:5000/lecturer/dashboard in your browser.');
            return false;
        }

        console.log('[AUTH] Initializing auth on path:', window.location.pathname);
        console.log('[AUTH] SessionStorage before restore:', { hasToken: !!sessionStorage.getItem('tapin_token') });
        // Restore token from storage if exists
        const storedToken = sessionStorage.getItem('tapin_token');
        if (storedToken) {
            this.token = storedToken;
            console.log('[AUTH] Restored token from storage, length:', storedToken.length);
        }
    
        // If no token, check session via health - but skip redirect if likely post-login redirect
        if (!this.token) {
            console.log('[AUTH] No token in storage, checking /api/health');
            try {
                const response = await fetch('/api/health', {
                    method: 'GET',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                const healthData = await response.json();
                console.log('[AUTH] /api/health full response (no token):', { status: response.status, ok: response.ok, data: healthData });
                
                if (response.ok && healthData.status === 'ok') {
                    // Session valid (cookies present) but no token - fetch fresh token
                    console.log('[AUTH] Session valid via cookies but no token; fetching fresh token from /api/get_token');
                    try {
                        const tokenResponse = await fetch('/api/get_token', {
                            method: 'GET',
                            credentials: 'same-origin'
                        });
                        const tokenData = await tokenResponse.json();
                        if (tokenResponse.ok && tokenData.token) {
                            this.token = tokenData.token;
                            sessionStorage.setItem('tapin_token', this.token);
                            console.log('[AUTH] Fresh token fetched and stored, proceeding to validate');
                            // Proceed to validation
                            const userData = await this.apiCall('/profile/me');
                            if (userData && !userData.error) {
                                this.user = userData;
                                console.log('[AUTH] Token valid, user loaded:', { id: userData.id, role: userData.role });
                                // Trigger any waiting callbacks or reload classes
                                if (window.loadClassesAfterAuth) window.loadClassesAfterAuth();
                                return true;
                            } else {
                                console.log('[AUTH] Fresh token invalid, logging out');
                                this.logout();
                                return false;
                            }
                        } else {
                            console.log('[AUTH] Failed to fetch fresh token, redirecting to login');
                            window.location.href = '/account';
                            return false;
                        }
                    } catch (tokenError) {
                        console.error('Token fetch failed:', tokenError);
                        window.location.href = '/account';
                        return false;
                    }
                } else {
                    // No valid session, redirect
                    console.log('[AUTH] No valid session, redirecting to login');
                    window.location.href = '/account';
                    return false;
                }
            } catch (error) {
                console.error('Health check failed:', error);
                window.location.href = '/account';
                return false;
            }
        }
    
        // Validate existing token by fetching user profile
        console.log('[AUTH] Token present, validating via /profile/me');
        try {
            const userData = await this.apiCall('/profile/me');
            console.log('[AUTH] /profile/me response:', { hasError: !!(userData && userData.error), userRole: userData ? userData.role : 'none' });
            if (userData && !userData.error) {
                this.user = userData;
                console.log('[AUTH] Token valid, user loaded:', { id: userData.id, role: userData.role });
                return true;
            } else {
                console.log('[AUTH] Token invalid (me failed), logging out');
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

    // API call helper with authentication and token refresh on 401
    async apiCall(endpoint, options = {}) {
        const url = this.apiBaseUrl + endpoint;
        let currentToken = this.getToken();
        const tokenToSend = currentToken ? currentToken.substring(0, 20) + '...' : 'no token';
        console.log('API Call:', { url, method: options.method || 'GET', body: options.body ? '[redacted]' : undefined, token: tokenToSend, hasUser: !!this.user });
        
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {})
            },
            credentials: 'same-origin'
        };
    
        const finalOptions = { ...defaultOptions, ...options };
        if (options.headers) {
            finalOptions.headers = { ...defaultOptions.headers, ...options.headers };
        }

        // Recursive function to retry after refresh
        const attemptCall = async (retryToken = null) => {
            let tokenForCall = retryToken || currentToken;
            if (tokenForCall) {
                finalOptions.headers['Authorization'] = `Bearer ${tokenForCall}`;
            }

            try {
                const response = await fetch(url, finalOptions);
                const status = response.status;
                console.log('API Response for', url, ':', { status, ok: response.ok });
                
                if (status === 401) {
                    console.log('[AUTH] 401 detected, attempting token refresh');
                    // Attempt to refresh token using session
                    try {
                        const refreshResponse = await fetch('/api/get_token', {
                            method: 'GET',
                            credentials: 'same-origin'
                        });
                        if (refreshResponse.ok) {
                            const refreshData = await refreshResponse.json();
                            if (refreshData.token) {
                                console.log('[AUTH] Token refreshed successfully');
                                this.token = refreshData.token;
                                sessionStorage.setItem('tapin_token', this.token);
                                // Retry the original call with new token
                                return await attemptCall(refreshData.token);
                            } else {
                                console.log('[AUTH] Refresh failed: no token in response');
                                return { error: 'Session expired. Please log in again.' };
                            }
                        } else {
                            console.log('[AUTH] Refresh failed: server returned', refreshResponse.status);
                            return { error: 'Session expired. Please log in again.' };
                        }
                    } catch (refreshError) {
                        console.error('[AUTH] Token refresh failed:', refreshError);
                        return { error: 'Session expired. Please log in again.' };
                    }
                }

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: response.statusText }));
                    console.error('API Error Response:', { status, error: errorData.error || response.statusText, endpoint });
                    return { error: errorData.error || `HTTP ${status}: ${response.statusText}` };
                }

                const data = await response.json();
                console.log('[AUTH] API call succeeded for', endpoint);
                return data;
            } catch (error) {
                console.error('API call failed (network/fetch error):', error, { url, endpoint });
                return { error: `Network error: ${error.message}` };
            }
        };

        return await attemptCall();
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

    if (!isAuthenticated && window.location.protocol !== 'file:') {
        // Redirect to login if not authenticated and not on auth pages (skip for direct file opens)
        window.location.href = '/account';
    }
});

// Export for use in other scripts
window.AuthManager = AuthManager;
window.authManager = authManager;