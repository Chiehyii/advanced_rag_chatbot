import { useState, useRef, useCallback } from 'react';
import { AdminSidebar } from './AdminSidebar';
import { ExtractionSection } from './ExtractionSection';
import { ScholarshipForm } from './ScholarshipForm';
import { Scholarship, AdminMode } from './types';
import './admin.css';
interface AdminLayoutProps {
    onLogout: () => void;
}
interface ToastState {
    message: string;
    type: 'success' | 'error';
    visible: boolean;
}
export function AdminLayout({ onLogout }: AdminLayoutProps) {
    const [selectedScholarship, setSelectedScholarship] = useState<Scholarship | null>(null);
    const [mode, setMode] = useState<AdminMode>('CREATE');
    const [showForm, setShowForm] = useState(false);
    const [toast, setToast] = useState<ToastState>({ message: '', type: 'success', visible: false });
    const [refreshTrigger, setRefreshTrigger] = useState(0);
    const extractedUrlRef = useRef<string>('');
    const showToast = (message: string, type: 'success' | 'error') => {
        setToast({ message, type, visible: true });
        setTimeout(() => setToast(t => ({ ...t, visible: false })), 3000);
    };
    const handleUnauthorized = useCallback(() => {
        localStorage.removeItem('admin_jwt');
        onLogout();
        showToast('驗證過期，請重新登入', 'error');
    }, [onLogout]);
    const handleSelectScholarship = (s: Scholarship) => {
        setSelectedScholarship(s);
        setMode('UPDATE');
        setShowForm(true);
        setTimeout(() => {
            document.getElementById('result-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    };
    const handleExtracted = (data: Scholarship) => {
        setSelectedScholarship(data);
        setMode('CREATE');
        setShowForm(true);
        setTimeout(() => {
            document.getElementById('result-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    };
    const handleSaved = () => {
        setRefreshTrigger(n => n + 1);
        setShowForm(false);
        setSelectedScholarship(null);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    const handleDeleted = () => {
        setRefreshTrigger(n => n + 1);
        setShowForm(false);
        setSelectedScholarship(null);
        setMode('CREATE');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    return (
        <div className="app-container">
            <AdminSidebar
                onSelect={handleSelectScholarship}
                onUnauthorized={handleUnauthorized}
                refreshTrigger={refreshTrigger}
            />
            <main className="main-stage">
                <header className="top-bar glass-panel">
                    <h1>獎學金建檔</h1>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                        <div className="status-indicator" id="status-indicator">
                            <span className="dot green" />
                            系統已連線
                        </div>
                        <button
                            onClick={() => { localStorage.removeItem('admin_jwt'); onLogout(); }}
                            style={{
                                background: 'none', border: '1px solid #cbd5e1', borderRadius: 8,
                                padding: '6px 14px', cursor: 'pointer', fontSize: '0.85rem', color: '#64748b',
                            }}>
                            登出
                        </button>
                    </div>
                </header>
                <div className="content-wrapper">
                    <ExtractionSection
                        onExtracted={handleExtracted}
                        onUnauthorized={handleUnauthorized}
                        onToast={showToast}
                        urlRef={extractedUrlRef}
                    />
                    {showForm && selectedScholarship && (
                        <ScholarshipForm
                            initialData={selectedScholarship}
                            mode={mode}
                            onSaved={handleSaved}
                            onDeleted={handleDeleted}
                            onUnauthorized={handleUnauthorized}
                            onToast={showToast}
                        />
                    )}
                </div>
            </main>
            {/* Toast */}
            <div id="toast" className={`toast ${toast.visible ? 'show' : ''} ${toast.type}`}>
                {toast.message}
            </div>
        </div>
    );
}