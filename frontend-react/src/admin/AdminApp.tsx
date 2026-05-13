import { useState, useEffect } from 'react';
import { AdminLogin } from './AdminLogin';
import { AdminLayout } from './AdminLayout';
import { apiCheckAuth } from './api';
import './admin.css';

export function AdminApp() {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isCheckingAuth, setIsCheckingAuth] = useState(true);

    useEffect(() => {
        document.title = '獎學金知識庫管理中心';
        apiCheckAuth()
            .then(setIsAuthenticated)
            .finally(() => setIsCheckingAuth(false));
    }, []);

    const handleLoginSuccess = () => {
        setIsAuthenticated(true);
    };

    const handleLogout = () => {
        setIsAuthenticated(false);
    };

    if (isCheckingAuth) {
        return <div style={{ padding: '20px', textAlign: 'center' }}>Loading...</div>;
    }

    if (!isAuthenticated) {
        return <AdminLogin onLoginSuccess={handleLoginSuccess} />;
    }

    return <AdminLayout onLogout={handleLogout} />;
}
