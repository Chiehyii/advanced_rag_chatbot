import { useState } from 'react';
import { apiLogin } from './api';
import './admin.css';
interface AdminLoginProps {
    onLoginSuccess: (token: string) => void;
}
export function AdminLogin({ onLoginSuccess }: AdminLoginProps) {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            const token = await apiLogin(username, password);
            localStorage.setItem('admin_jwt', token);
            onLoginSuccess(token);
        } catch {
            setError('帳號或密碼錯誤');
        } finally {
            setLoading(false);
            setPassword('');
        }
    };
    return (
        <div className="login-overlay active">
            <div className="login-box glass-panel">
                <div className="logo large">✦</div>
                <h2>管理員登入</h2>
                <p>請輸入您的帳號密碼以繼續</p>
                <form onSubmit={handleSubmit}>
                    <div className="input-group">
                        <label>帳號 (Username)</label>
                        <input
                            type="text"
                            id="l-username"
                            required
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                        />
                    </div>
                    <div className="input-group">
                        <label>密碼 (Password)</label>
                        <input
                            type="password"
                            id="l-password"
                            required
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                        />
                    </div>
                    <button type="submit" className="magic-btn" id="btn-login" disabled={loading}>
                        {loading ? '登入中...' : '登 入'}
                    </button>
                </form>
                {error && <div className="login-error">{error}</div>}
            </div>
        </div>
    );
}