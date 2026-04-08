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

type ViewMode = 'dashboard' | 'detail';

export function AdminLayout({ onLogout }: AdminLayoutProps) {
    const [view, setView] = useState<ViewMode>('dashboard');
    const [selectedScholarship, setSelectedScholarship] = useState<Scholarship | null>(null);
    const [mode, setMode] = useState<AdminMode>('CREATE');
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

    // 點擊側欄某筆獎學金 → 進入 detail 頁
    const handleSelectScholarship = (s: Scholarship) => {
        setSelectedScholarship(s);
        setMode('UPDATE');
        setView('detail');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // 來源萃取完成 → 進入 detail 頁（新增模式）
    const handleExtracted = (data: Scholarship) => {
        setSelectedScholarship(data);
        setMode('CREATE');
        setView('detail');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // 儲存/刪除完成 → 返回 dashboard
    const handleSaved = () => {
        setRefreshTrigger(n => n + 1);
        setSelectedScholarship(null);
        setView('dashboard');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handleDeleted = () => {
        setRefreshTrigger(n => n + 1);
        setSelectedScholarship(null);
        setMode('CREATE');
        setView('dashboard');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // 返回 dashboard 按鈕
    const handleBack = () => {
        setSelectedScholarship(null);
        setView('dashboard');
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        {view === 'detail' && (
                            <button
                                onClick={handleBack}
                                className="back-btn"
                                id="btn-back"
                            >
                                ← 返回總覽
                            </button>
                        )}
                        <h1>{view === 'dashboard' ? '資料庫建檔' : '資料庫編輯'}</h1>
                    </div>
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
                    {view === 'dashboard' && (
                        <ExtractionSection
                            onExtracted={handleExtracted}
                            onUnauthorized={handleUnauthorized}
                            onToast={showToast}
                            urlRef={extractedUrlRef}
                        />
                    )}

                    {view === 'detail' && selectedScholarship && (
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