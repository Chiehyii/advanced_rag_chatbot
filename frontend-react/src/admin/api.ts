import { Scholarship } from './types';
const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const getToken = (): string => localStorage.getItem('admin_jwt') || '';
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const headers = new Headers(options.headers);
    headers.set('Authorization', `Bearer ${getToken()}`);
    const fullUrl = url.startsWith('/') ? `${API_BASE_URL}${url}` : url;
    
    let res = await fetch(fullUrl, { ...options, headers });
    
    if (res.status === 401) {
        const refreshToken = localStorage.getItem('admin_refresh_jwt');
        if (refreshToken) {
            try {
                const refreshRes = await fetch(`${API_BASE_URL}/api/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken })
                });
                
                if (refreshRes.ok) {
                    const data = await refreshRes.json();
                    localStorage.setItem('admin_jwt', data.access_token);
                    // Retry original request with new token
                    headers.set('Authorization', `Bearer ${data.access_token}`);
                    res = await fetch(fullUrl, { ...options, headers });
                } else {
                    // Refresh failed, clear tokens
                    localStorage.removeItem('admin_jwt');
                    localStorage.removeItem('admin_refresh_jwt');
                }
            } catch (err) {
                console.error("Refresh token failed", err);
            }
        }
    }
    
    return res;
}
export async function apiLogin(username: string, password: string): Promise<string> {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const res = await fetch(`${API_BASE_URL}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
    });
    if (!res.ok) throw new Error('登入失敗');
    const data = await res.json();
    if (data.refresh_token) {
        localStorage.setItem('admin_refresh_jwt', data.refresh_token);
    }
    return data.access_token;
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

// --- Dashboard APIs ---
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