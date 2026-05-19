import { Scholarship } from './types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const CSRF_STORAGE_KEY = 'tcu_admin_csrf_token';

function getStoredCsrfToken(): string {
    return sessionStorage.getItem(CSRF_STORAGE_KEY) || '';
}

function storeCsrfToken(token: string | null | undefined): void {
    if (token) {
        sessionStorage.setItem(CSRF_STORAGE_KEY, token);
    }
}

async function storeCsrfTokenFromResponse(res: Response): Promise<void> {
    try {
        const contentType = res.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) return;
        const body = await res.clone().json();
        storeCsrfToken(body?.csrf_token);
    } catch {
        // Response bodies are best-effort for CSRF rotation.
    }
}

async function ensureCsrfToken(force = false): Promise<string> {
    const current = getStoredCsrfToken();
    if (current && !force) return current;

    const res = await fetch(`${API_BASE_URL}/api/csrf`, {
        method: 'GET',
        credentials: 'include',
    });
    if (!res.ok) return '';

    await storeCsrfTokenFromResponse(res);
    return getStoredCsrfToken();
}

function isUnsafeMethod(method: string | undefined): boolean {
    const normalized = (method || 'GET').toUpperCase();
    return !['GET', 'HEAD', 'OPTIONS'].includes(normalized);
}

export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const headers = new Headers(options.headers);
    headers.set('X-Requested-With', 'XMLHttpRequest');
    if (isUnsafeMethod(options.method)) {
        const csrfToken = await ensureCsrfToken();
        if (csrfToken) headers.set('X-CSRF-Token', csrfToken);
    }
    const fullUrl = url.startsWith('/') ? `${API_BASE_URL}${url}` : url;

    let res = await fetch(fullUrl, { ...options, headers, credentials: 'include' });
    await storeCsrfTokenFromResponse(res);

    if (res.status === 401) {
        try {
            const csrfToken = await ensureCsrfToken(true);
            const refreshRes = await fetch(`${API_BASE_URL}/api/refresh`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
                },
            });
            await storeCsrfTokenFromResponse(refreshRes);

            if (refreshRes.ok) {
                if (isUnsafeMethod(options.method)) {
                    const refreshedCsrfToken = getStoredCsrfToken();
                    if (refreshedCsrfToken) headers.set('X-CSRF-Token', refreshedCsrfToken);
                }
                res = await fetch(fullUrl, { ...options, headers, credentials: 'include' });
                await storeCsrfTokenFromResponse(res);
            }
        } catch (err) {
            console.error("Refresh token failed", err);
        }
    }

    return res;
}

export async function apiLogin(username: string, password: string): Promise<void> {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const res = await fetch(`${API_BASE_URL}/api/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
    });
    await storeCsrfTokenFromResponse(res);
    if (!res.ok) throw new Error('Login failed');
}

export async function apiCheckAuth(): Promise<boolean> {
    const res = await authFetch('/api/me');
    return res.ok;
}

export async function apiLogout(): Promise<void> {
    await authFetch('/api/logout', { method: 'POST' }).catch(() => undefined);
    sessionStorage.removeItem(CSRF_STORAGE_KEY);
}

export async function apiListScholarships(): Promise<Scholarship[]> {
    const res = await authFetch('/api/scholarships');
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (result.status !== 'success') throw new Error('Failed to fetch');
    return result.data;
}

export async function apiGetScholarship(code: string): Promise<Scholarship> {
    const res = await authFetch(`/api/scholarships/${code}`);
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Load Error');
    return result.data;
}

export async function apiExtractInfo(url: string, text: string): Promise<Scholarship> {
    const res = await authFetch('/api/extract_info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, text }),
    });
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Extraction Server Error');
    return result.data;
}

export async function apiSaveScholarship(payload: Scholarship): Promise<string> {
    const res = await authFetch('/api/scholarships', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Save Error');
    return result.message;
}

export async function apiUpdateScholarship(code: string, payload: Scholarship): Promise<string> {
    const res = await authFetch(`/api/scholarships/${code}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Update Error');
    return result.message;
}

export async function apiDeleteScholarship(code: string): Promise<void> {
    const res = await authFetch(`/api/scholarships/${code}`, { method: 'DELETE' });
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Delete Error');
}

export async function apiDiscardPending(code: string): Promise<void> {
    const res = await authFetch(`/api/scholarships/${code}/discard_pending`, { method: 'PATCH' });
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Discard Error');
}

export async function apiGetMetadataSchema() {
    const res = await fetch(`${API_BASE_URL}/metadata_schema.json`);
    return res.json();
}

export async function apiGetDashboardSummary() {
    const res = await authFetch('/api/dashboard/summary');
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (result.status !== 'success') throw new Error('Failed to fetch dashboard summary');
    return result.data;
}

export async function apiGetDashboardTrends(startDate?: string, endDate?: string) {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    const res = await authFetch(`/api/dashboard/trends?${params.toString()}`);
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (result.status !== 'success') throw new Error('Failed to fetch dashboard trends');
    return result.data;
}

export async function apiGetDashboardRecent(limit: number = 20) {
    const res = await authFetch(`/api/dashboard/recent?limit=${limit}`);
    if (res.status === 401) throw new Error('UNAUTHORIZED');
    const result = await res.json();
    if (result.status !== 'success') throw new Error('Failed to fetch dashboard recent');
    return result.data;
}
