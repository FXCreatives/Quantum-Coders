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

        // Check for auth_token in URL params (post-verification bootstrap)
        const urlParams = new URLSearchParams(window.location.search);
        const authTokenParam = urlParams.get('auth_token');
        if (authTokenParam) {
            console.log('[AUTH] Found auth_token in URL params, length:', authTokenParam.length);
            this.token = authTokenParam;
            sessionStorage.setItem('tapin_token', this.token);
            // Clean URL: remove param and replace history
            urlParams.delete('auth_token');
            const cleanUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '');
            window.history.replaceState({}, document.title, cleanUrl);
            console.log('[AUTH] Set token from URL and cleaned URL');
        }

        console.log('[AUTH] Initializing auth on path:', window.location.pathname);
        console.log('[AUTH] SessionStorage before restore:', { hasToken: !!sessionStorage.getItem('tapin_token') });
        // Restore token from storage if exists
        const storedToken = sessionStorage.getItem('tapin_token');
        if (storedToken) {
            this.token = storedToken;
            console.log('[AUTH] Restored token from storage, length:', storedToken.length);
        }
        console.log('[AUTH DEBUG] After restore - token present:', !!this.token);
    
        // If no token, check session via health - but skip redirect if likely post-login redirect
        if (!this.token) {
            console.log('[AUTH] No token in storage, checking /api/health');
            console.log('[AUTH DEBUG] Fetch options for health:', { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } });
            try {
                console.log('[AUTH DEBUG] Fetching /api/health - starting...');
                const response = await fetch('/api/health', {
                    method: 'GET',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                const healthData = await response.json();
                console.log('[AUTH] /api/health full response (no token):', { status: response.status, ok: response.ok, data: healthData });
                console.log('[AUTH DEBUG] /api/health - session valid:', response.ok && healthData.status === 'ok');
                
                if (response.ok && healthData.status === 'ok') {
                    // Session valid (cookies present) but no token - fetch fresh token
                    console.log('[AUTH] Session valid via cookies but no token; fetching fresh token from /api/get_token');
                    console.log('[AUTH DEBUG] Fetch options for get_token:', { method: 'GET', credentials: 'same-origin' });
                    try {
                        console.log('[AUTH DEBUG] Fetching /api/get_token - starting...');
                        const tokenResponse = await fetch('/api/get_token', {
                            method: 'GET',
                            credentials: 'same-origin'
                        });
                        console.log('[AUTH] /api/get_token response:', { status: tokenResponse.status, ok: tokenResponse.ok });
                        const tokenData = await tokenResponse.json();
                        console.log('[AUTH] /api/get_token data:', { hasToken: !!tokenData.token, error: tokenData.error });
                        console.log('[AUTH DEBUG] /api/get_token - success:', tokenResponse.ok && !!tokenData.token);
                        if (tokenResponse.ok && tokenData.token) {
                            this.token = tokenData.token;
                            sessionStorage.setItem('tapin_token', this.token);
                            console.log('[AUTH] Fresh token fetched and stored, length:', this.token.length, 'proceeding to validate /auth/me');
                            // Proceed to validation
                            console.log('[AUTH DEBUG] Calling apiCall /auth/me with token');
                            console.log('[AUTH DEBUG] Fetching /auth/me - starting...');
                            const userData = await this.apiCall('/auth/me');
                            console.log('[AUTH] /auth/me response:', { hasError: !!(userData && userData.error), data: userData, role: userData ? userData.role : 'none' });
                            console.log('[AUTH DEBUG] /auth/me - valid user:', !!(userData && !userData.error));
                            if (userData && !userData.error) {
                                this.user = userData;
                                console.log('[AUTH] Token valid, user loaded:', { id: userData.id, role: userData.role, verified: userData.is_verified });
                                // Trigger any waiting callbacks or reload classes
                                if (window.loadClassesAfterAuth) window.loadClassesAfterAuth();
                                return true;
                            } else {
                                console.log('[AUTH] Fresh token invalid (profile/me failed), logging out. Error:', userData ? userData.error : 'unknown');
                                this.logout();
                                return false;
                            }
                        } else {
                            console.log('[AUTH] Failed to fetch fresh token (status', tokenResponse.status, '), data:', tokenData, 'redirecting to login');
                            const currentPath = window.location.pathname;
                            let loginPath = '/account';
                            if (currentPath.includes('/lecturer/')) {
                              loginPath = '/lecturer_login';
                            } else if (currentPath.includes('/student/')) {
                              loginPath = '/student_login';
                            }
                            window.location.href = loginPath;
                            return false;
                        }
                    } catch (tokenError) {
                        console.error('Token fetch failed:', tokenError);
                        console.log('[AUTH] get_token exception details:', tokenError.message || tokenError);
                        const currentPath = window.location.pathname;
                        let loginPath = '/account';
                        if (currentPath.includes('/lecturer/')) {
                          loginPath = '/lecturer_login';
                        } else if (currentPath.includes('/student/')) {
                          loginPath = '/student_login';
                        }
                        window.location.href = loginPath;
                        return false;
                    }
                } else {
                    // No valid session, redirect
                    console.log('[AUTH] No valid session (health failed, status:', response.status, '), redirecting to login');
                    const currentPath = window.location.pathname;
                    let loginPath = '/account';
                    if (currentPath.includes('/lecturer/')) {
                      loginPath = '/lecturer_login';
                    } else if (currentPath.includes('/student/')) {
                      loginPath = '/student_login';
                    }
                    window.location.href = loginPath;
                    return false;
                }
            } catch (error) {
                console.error('Health check failed:', error);
                console.log('[AUTH] health exception details:', error.message || error);
                const currentPath = window.location.pathname;
                let loginPath = '/account';
                if (currentPath.includes('/lecturer/')) {
                  loginPath = '/lecturer_login';
                } else if (currentPath.includes('/student/')) {
                  loginPath = '/student_login';
                }
                window.location.href = loginPath;
                return false;
            }
        }
    
        // Validate existing token by fetching user profile
        console.log('[AUTH] Token present, validating via /auth/me');
        console.log('[AUTH DEBUG] Existing token length:', this.token ? this.token.length : 'none');
        try {
            console.log('[AUTH DEBUG] Calling apiCall /auth/me with existing token');
            console.log('[AUTH DEBUG] Fetching /auth/me - starting...');
            const userData = await this.apiCall('/auth/me');
            console.log('[AUTH] /auth/me response:', { hasError: !!(userData && userData.error), data: userData, role: userData ? userData.role : 'none' });
            console.log('[AUTH DEBUG] /auth/me - valid user:', !!(userData && !userData.error));
            if (userData && !userData.error) {
                this.user = userData;
                console.log('[AUTH] Token valid, user loaded:', { id: userData.id, role: userData.role, verified: userData.is_verified });
                return true;
            } else {
                console.log('[AUTH] Token invalid (me failed), error:', userData ? userData.error : 'unknown', 'logging out');
                this.logout();
                return false;
            }
        } catch (error) {
            console.error('Token validation failed:', error);
            console.log('[AUTH] /auth/me exception details:', error.message || error);
            this.logout();
            const currentPath = window.location.pathname;
            let loginPath = '/account';
            if (currentPath.includes('/lecturer/')) {
              loginPath = '/lecturer_login';
            } else if (currentPath.includes('/student/')) {
              loginPath = '/student_login';
            }
            window.location.href = loginPath;
            return false;
        }
    }

    // Registration method
    async register(userData) {
        try {
            const data = await safeFetch('/api/auth/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(userData),
                credentials: 'same-origin'
            });

            console.log('[AUTH] Register response:', data);

            // No token on register - account needs verification
            console.log('[AUTH] Registration successful, redirecting to verification');
            window.location.href = data.redirect_url || '/account';
            return { success: true, message: data.message || 'Registration successful. Please verify your email.' };
        } catch (error) {
            console.error('[AUTH] Register error:', error);
            return { success: false, error: error.message };
        }
    }

    // Forgot password method
    async forgotPassword(email, role) {
        try {
            const data = await safeFetch('/api/send-reset-link', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, role }),
                credentials: 'same-origin'
            });

            console.log('[AUTH] Forgot password response:', data);
            return { success: true, message: data.message || 'Reset link sent to your email.' };
        } catch (error) {
            console.error('[AUTH] Forgot password error:', error);
            return { success: false, error: error.message || 'Network error' };
        }
    }

    // Reset password method
    async resetPassword(token, role, password, confirmPassword) {
        if (password !== confirmPassword) {
            return { success: false, error: 'Passwords do not match' };
        }

        try {
            const data = await safeFetch('/api/reset-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ token, role, password }),
                credentials: 'same-origin'
            });

            console.log('[AUTH] Reset password response:', data);

            console.log('[AUTH] Password reset successful');
            // Clear any existing auth state
            this.logout('password_reset');
            return { success: true, message: data.message || 'Password reset successful. Please log in.' };
        } catch (error) {
            console.error('[AUTH] Reset password error:', error);
            return { success: false, error: error.message || 'Network error' };
        }
    }

    // Login method
    async login(credentials) {
        try {
            const data = await safeFetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(credentials),
                credentials: 'same-origin'
            });

            console.log('[AUTH] Login response:', data);

            this.token = data.token;
            this.user = data.user;
            sessionStorage.setItem('tapin_token', this.token);
            console.log('[AUTH] Login successful, token captured');
            window.location.href = data.redirect_url;
            return { success: true, message: data.message };
        } catch (error) {
            console.error('[AUTH] Login error:', error);
            return { success: false, error: error.message };
        }
    }

    // Student login with student ID (unified with general login via /api/auth/login)
    async studentLogin(credentials) {
        try {
            const loginCreds = {
                student_id: credentials.studentId,
                password: credentials.password
            };
            // If email is provided (optional), include it
            if (credentials.email) {
                loginCreds.email = credentials.email;
            }

            const result = await this.login(loginCreds);
            if (result.success) {
                // Backend handles redirect based on role/verification
                return result;
            } else {
                // Enhanced handling for verification error
                if (result.error && result.error.includes('verify')) {
                    const currentPath = window.location.pathname;
                    let initialHome = '/student/initial-home';
                    if (currentPath.includes('/lecturer/')) {
                        initialHome = '/lecturer/initial-home';
                    }
                    window.location.href = initialHome;
                    return { success: false, error: 'Please verify your email first.' };
                }
                return result;
            }
        } catch (error) {
            console.error('[AUTH] Student login error:', error);
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
        console.log('[API DEBUG] Starting fetch to:', url);
        
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
                console.log('[API DEBUG] Fetch completed for:', url, '- awaiting JSON...');
                const response = await fetch(url, finalOptions);
                const status = response.status;
                console.log('API Response for', url, ':', { status, ok: response.ok });
                console.log('[API DEBUG] Response status details:', { status, ok: response.ok, redirected: response.redirected });
                
                if (status === 401) {
                    console.log('[AUTH] 401 detected, attempting token refresh');
                    console.log('[AUTH DEBUG] 401 on:', url, '- starting refresh...');
                    // Attempt to refresh token using session
                    try {
                        console.log('[AUTH DEBUG] Fetching /api/get_token for refresh...');
                        const refreshResponse = await fetch('/api/get_token', {
                            method: 'GET',
                            credentials: 'same-origin'
                        });
                        console.log('[AUTH DEBUG] Refresh /api/get_token response:', { status: refreshResponse.status, ok: refreshResponse.ok });
                        if (refreshResponse.ok) {
                            const refreshData = await refreshResponse.json();
                            console.log('[AUTH DEBUG] Refresh data:', { hasToken: !!refreshData.token, error: refreshData.error });
                            if (refreshData.token) {
                                console.log('[AUTH] Token refreshed successfully');
                                this.token = refreshData.token;
                                sessionStorage.setItem('tapin_token', this.token);
                                console.log('[AUTH DEBUG] Retrying original call with new token...');
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
                        console.log('[AUTH DEBUG] Refresh exception:', refreshError.message || refreshError);
                        return { error: 'Session expired. Please log in again.' };
                    }
                }

                if (!response.ok) {
                    console.log('[API DEBUG] Non-ok response - parsing error...');
                    const errorData = await response.json().catch(() => ({ error: response.statusText }));
                    console.error('API Error Response:', { status, error: errorData.error || response.statusText, endpoint });
                    console.log('[API DEBUG] Error details:', { status, error: errorData.error || response.statusText, endpoint });
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

    const protectedPaths = ['/lecturer/', '/student/']; // Dashboard paths where server handles auth

    if (authPages.some(page => currentPath.includes(page))) {
        return; // Don't initialize auth on auth pages
    }

    // For protected paths, init auth but skip client redirect (trust server decorators)
    const isProtectedPath = protectedPaths.some(path => currentPath.startsWith(path));
    const isAuthenticated = await authManager.init();
    console.log('[AUTH GLOBAL] init() returned:', isAuthenticated, 'on path:', currentPath, 'protected:', isProtectedPath);

    if (!isAuthenticated && !isProtectedPath && !currentPath.includes('initial-home') && window.location.protocol !== 'file:') {
      // Only redirect if not on protected paths or initial-home (skip for direct file opens)
      console.log('[AUTH GLOBAL] Not authenticated, redirecting from:', currentPath);
      let loginPath = '/account';
      if (currentPath.includes('/lecturer/')) {
        loginPath = '/lecturer_login';
      } else if (currentPath.includes('/student/')) {
        loginPath = '/student_login';
      }
      window.location.href = loginPath;
    } else {
      console.log('[AUTH GLOBAL] Auth successful or protected path or initial-home, proceeding with page load');
    }
});

// Export for use in other scripts
window.AuthManager = AuthManager;
window.authManager = authManager;

// Global safeFetch wrapper for better error logging
async function safeFetch(url, opts={}) {
  try {
    const res = await fetch(url, opts);
    if (!res.ok) {
      const txt = await res.text();
      console.error(`safeFetch ${url} error:`, res.status, txt);
      throw new Error(`${res.status} ${txt}`);
    }
    return res.json();
  } catch(err) {
    console.error('safeFetch network error', err);
    throw err;
  }
}

// Global validatePassword function for password inputs
function validatePassword(passwordElId = 'password', feedbackId = 'password-feedback') {
    const passwordEl = document.getElementById(passwordElId);
    const feedback = document.getElementById(feedbackId);
    if (!passwordEl) {
        console.warn('validatePassword: no password element found');
        return;
    }
    const pwd = passwordEl.value || '';
    let score = 0;
    const rules = 5;

    // Update individual rules if feedback has them
    if (feedback) {
        // Length
        const lengthCheck = feedback.querySelector('#length-check');
        if (pwd.length >= 8) {
            if (lengthCheck) lengthCheck.innerHTML = '✓';
            score++;
        } else {
            if (lengthCheck) lengthCheck.innerHTML = '✗';
        }

        // Uppercase
        const uppercaseCheck = feedback.querySelector('#uppercase-check');
        if (/[A-Z]/.test(pwd)) {
            if (uppercaseCheck) uppercaseCheck.innerHTML = '✓';
            score++;
        } else {
            if (uppercaseCheck) uppercaseCheck.innerHTML = '✗';
        }

        // Lowercase
        const lowercaseCheck = feedback.querySelector('#lowercase-check');
        if (/[a-z]/.test(pwd)) {
            if (lowercaseCheck) lowercaseCheck.innerHTML = '✓';
            score++;
        } else {
            if (lowercaseCheck) lowercaseCheck.innerHTML = '✗';
        }

        // Number
        const numberCheck = feedback.querySelector('#number-check');
        if (/\d/.test(pwd)) {
            if (numberCheck) numberCheck.innerHTML = '✓';
            score++;
        } else {
            if (numberCheck) numberCheck.innerHTML = '✗';
        }

        // Special
        const specialCheck = feedback.querySelector('#special-check');
        if (/[!@#$%^&*(),.?":{}|<>]/.test(pwd)) {
            if (specialCheck) specialCheck.innerHTML = '✓';
            score++;
        } else {
            if (specialCheck) specialCheck.innerHTML = '✗';
        }

        // Strength meter if present
        const bar = feedback.querySelector('#strength-bar');
        const text = feedback.querySelector('#strength-text');
        if (bar && text) {
            const percentage = (score / rules) * 100;
            bar.style.width = percentage + '%';

            if (percentage < 40) {
                bar.style.background = 'red';
                text.textContent = 'Weak';
            } else if (percentage < 80) {
                bar.style.background = 'orange';
                text.textContent = 'Medium';
            } else {
                bar.style.background = 'green';
                text.textContent = 'Strong';
            }
        }

        // Show feedback if password entered
        if (pwd) {
            feedback.style.display = 'block';
        } else {
            feedback.style.display = 'none';
        }
    }

    return score >= 3; // Boolean if acceptable
}

// Ensure validatePassword is bound after DOM load
document.addEventListener('DOMContentLoaded', () => {
    const pwd = document.getElementById('password');
    if (pwd && !pwd.oninput) {
        pwd.oninput = () => validatePassword();
    }
    const confirmPwd = document.getElementById('confirm-password');
    if (confirmPwd) {
        confirmPwd.oninput = () => {
            if (pwd && pwd.value !== confirmPwd.value) {
                // Could add mismatch feedback here
            }
        };
    }
});