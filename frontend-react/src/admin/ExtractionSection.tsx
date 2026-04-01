import { useState } from 'react';
import { apiExtractInfo } from './api';
import { Scholarship } from './types';
import './admin.css';
interface ExtractionSectionProps {
    onExtracted: (data: Scholarship) => void;
    onUnauthorized: () => void;
    onToast: (msg: string, type: 'success' | 'error') => void;
    urlRef: React.MutableRefObject<string>;
}
export function ExtractionSection({ onExtracted, onUnauthorized, onToast, urlRef }: ExtractionSectionProps) {
    const [url, setUrl] = useState('');
    const [text, setText] = useState('');
    const [loading, setLoading] = useState(false);
    const handleExtract = async () => {
        if (!url.trim() && !text.trim()) {
            onToast('請提供網址或貼上內容！', 'error');
            return;
        }
        setLoading(true);
        try {
            const data = await apiExtractInfo(url.trim(), text.trim());
            urlRef.current = url.trim();
            onExtracted(data);
            onToast('✨ AI 分析完成！', 'success');
        } catch (err: any) {
            if (err.message === 'UNAUTHORIZED') { onUnauthorized(); return; }
            onToast(err.message, 'error');
        } finally {
            setLoading(false);
        }
    };
    return (
        <section className="extraction-section glass-panel slide-up">
            <div className="section-title">
                <h3>1. 來源萃取</h3>
                <p>輸入網址或直接貼上原始文字，讓 AI 幫您一鍵解析</p>
            </div>
            <div className="input-group">
                <label htmlFor="source-url">獎學金網址 (URL)</label>
                <input
                    type="url"
                    id="source-url"
                    placeholder="https://yizhu.tcu.edu.tw/?p=1923"
                    value={url}
                    onChange={e => setUrl(e.target.value)}
                />
            </div>
            <div className="divider"><span>或</span></div>
            <div className="input-group">
                <label htmlFor="source-text">原始文字 (若無網址可直接貼上)</label>
                <textarea
                    id="source-text"
                    rows={4}
                    placeholder="請將網頁文字複製貼上於此..."
                    value={text}
                    onChange={e => setText(e.target.value)}
                />
            </div>
            <button className="magic-btn" id="btn-extract" onClick={handleExtract} disabled={loading}>
                {loading ? (
                    <>
                        <div className="spinner" style={{ width: 20, height: 20, margin: 0 }} />
                        <span className="btn-text">AI 正在閱讀並萃取資訊中...</span>
                    </>
                ) : (
                    <>
                        <span className="btn-icon">✨</span>
                        <span className="btn-text">讓 AI 預先處理</span>
                        <div className="shimmer" />
                    </>
                )}
            </button>
        </section>
    );
}