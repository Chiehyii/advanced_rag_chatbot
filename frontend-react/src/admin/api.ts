import { Scholarship } from './types';
const getToken = (): string => localStorage.getItem('admin_jwt') || '';
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const headers = new Headers(options.headers);
    headers.set('Authorization', `Bearer ${getToken()}`);
    return fetch(url, { ...options, headers });
}
export async function apiLogin(username: string, password: string): Promise<string> {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
    });
    if (!res.ok) throw new Error('登入失敗');
    const data = await res.json();
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
export async function apiGetMetadataSchema() {
    const res = await fetch('/metadata_schema.json');
    return res.json();
}