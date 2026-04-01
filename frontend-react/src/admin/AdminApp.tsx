import { useState, useEffect } from 'react';
import { AdminLogin } from './AdminLogin';
import { AdminLayout } from './AdminLayout';
import './admin.css';
export function AdminApp() {
    const [token, setToken] = useState<string>(() => localStorage.getItem('admin_jwt') || '');
    useEffect(() => {
        document.title = '獎學金知識庫管理中心';
    }, []);
    const handleLoginSuccess = (newToken: string) => {
        setToken(newToken);
    };
    const handleLogout = () => {
        setToken('');
    };
    if (!token) {
        return <AdminLogin onLoginSuccess={handleLoginSuccess} />;
    }
    return <AdminLayout onLogout={handleLogout} />;
}
