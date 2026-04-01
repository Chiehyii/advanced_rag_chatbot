import { useState, useEffect, useRef } from 'react';
import Select from 'react-select';
import { marked } from 'marked';
import { Scholarship, AdminMode, MetadataSchema } from './types';
import { apiSaveScholarship, apiUpdateScholarship, apiDeleteScholarship, apiGetMetadataSchema } from './api';
import './admin.css';
interface ScholarshipFormProps {
    initialData: Scholarship | null;
    mode: AdminMode;
    onSaved: () => void;
    onDeleted: () => void;
    onUnauthorized: () => void;
    onToast: (msg: string, type: 'success' | 'error') => void;
}
type OptionType = { value: string; label: string };
const toOptions = (arr: string[] = []): OptionType[] => arr.map(s => ({ value: s, label: s }));
const selectStyles = {
    control: (base: any) => ({
        ...base, borderRadius: 10, borderColor: '#cbd5e1', fontSize: '0.95rem', minHeight: 44,
        boxShadow: 'none', ':hover': { borderColor: '#6366f1' },
    }),
    multiValue: (base: any) => ({ ...base, backgroundColor: '#6366f1', borderRadius: 6 }),
    multiValueLabel: (base: any) => ({ ...base, color: '#fff' }),
    multiValueRemove: (base: any) => ({ ...base, color: '#fff', ':hover': { backgroundColor: '#4f46e5', color: '#fff' } }),
};
export function ScholarshipForm({ initialData, mode, onSaved, onDeleted, onUnauthorized, onToast }: ScholarshipFormProps) {
    const [schema, setSchema] = useState<MetadataSchema | null>(null);
    const [code, setCode] = useState('');
    const [title, setTitle] = useState('');
    const [link, setLink] = useState('');
    const [category, setCategory] = useState('');
    const [eduSelected, setEduSelected] = useState<OptionType[]>([]);
    const [tagsSelected, setTagsSelected] = useState<OptionType[]>([]);
    const [identitySelected, setIdentitySelected] = useState<OptionType[]>([]);
    const [date, setDate] = useState('');
    const [amount, setAmount] = useState('');
    const [contact, setContact] = useState('');
    const [description, setDescription] = useState('');
    const [markdown, setMarkdown] = useState('');
    const [saving, setSaving] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const previewRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        apiGetMetadataSchema().then(setSchema).catch(console.error);
    }, []);
    useEffect(() => {
        if (!initialData) return;
        setCode(initialData.scholarship_code || '');
        setTitle(initialData.title || '');
        setLink(initialData.link || '');
        setCategory(initialData.category || '');
        setEduSelected(toOptions(initialData.education_system));
        setTagsSelected(toOptions(initialData.tags));
        setIdentitySelected(toOptions(initialData.identity));
        setDate(initialData.application_date_text || '');
        setAmount(initialData.amount_summary || '');
        setContact(initialData.contact || '');
        setDescription(initialData.description || '');
        setMarkdown(initialData.markdown_content || '');
    }, [initialData]);
    useEffect(() => {
        if (previewRef.current) {
            previewRef.current.innerHTML = marked.parse(markdown) as string;
        }
    }, [markdown]);
    const buildPayload = (): Scholarship => ({
        scholarship_code: code,
        title,
        link,
        category,
        education_system: eduSelected.map(o => o.value),
        tags: tagsSelected.map(o => o.value),
        identity: identitySelected.map(o => o.value),
        application_date_text: date,
        amount_summary: amount,
        contact,
        description,
        markdown_content: markdown,
    });
    const handleSave = async () => {
        if (!title.trim() || !code.trim()) {
            onToast('標題與代碼不可為空！', 'error');
            return;
        }
        setSaving(true);
        try {
            if (mode === 'UPDATE') {
                await apiUpdateScholarship(code, buildPayload());
                onToast('✅ 更新成功！', 'success');
            } else {
                await apiSaveScholarship(buildPayload());
                onToast('✅ 新增成功！', 'success');
            }
            onSaved();
        } catch (err: any) {
            if (err.message === 'UNAUTHORIZED') { onUnauthorized(); return; }
            onToast('儲存失敗：' + err.message, 'error');
        } finally {
            setSaving(false);
        }
    };
    const handleDelete = async () => {
        if (!code) return;
        if (!confirm('確定要從資料庫與知識庫中完全刪除這筆資料嗎？此操作無法還原。')) return;
        setDeleting(true);
        try {
            await apiDeleteScholarship(code);
            onToast('✅ 刪除成功！', 'success');
            onDeleted();
        } catch (err: any) {
            if (err.message === 'UNAUTHORIZED') { onUnauthorized(); return; }
            onToast('刪除失敗：' + err.message, 'error');
        } finally {
            setDeleting(false);
        }
    };
    return (
        <section className="form-section glass-panel slide-up delay-1" id="result-section">
            <div className="section-title">
                <h3>2. 審核 &amp; 修改</h3>
                <p>AI 已填妥以下欄位，請確認無誤</p>
            </div>
            <form onSubmit={e => e.preventDefault()}>
                <div className="form-grid">
                    <div className="input-group">
                        <label>代碼 (UUID)</label>
                        <input type="text" id="f-code" value={code} readOnly className="readonly-input" />
                    </div>
                    <div className="input-group">
                        <label>標題 (Title)</label>
                        <input type="text" id="f-title" required value={title} onChange={e => setTitle(e.target.value)} />
                    </div>
                    <div className="input-group">
                        <label>網址 (Link)</label>
                        <input type="url" id="f-link" value={link} onChange={e => setLink(e.target.value)} />
                    </div>
                    <div className="input-group">
                        <label>衣珠類別 (Category)</label>
                        <input type="text" id="f-category" value={category} onChange={e => setCategory(e.target.value)} />
                    </div>
                    <div className="input-group">
                        <label>學制 (Education System)</label>
                        <Select isMulti options={toOptions(schema?.education_system)} value={eduSelected}
                            onChange={v => setEduSelected(v as OptionType[])} placeholder="選擇學制..."
                            styles={selectStyles} />
                    </div>
                    <div className="input-group">
                        <label>標籤 (Tags)</label>
                        <Select isMulti options={toOptions(schema?.tags)} value={tagsSelected}
                            onChange={v => setTagsSelected(v as OptionType[])} placeholder="選擇標籤..."
                            styles={selectStyles} />
                    </div>
                    <div className="input-group">
                        <label>適用身分 (Identity)</label>
                        <Select isMulti options={toOptions(schema?.identity)} value={identitySelected}
                            onChange={v => setIdentitySelected(v as OptionType[])} placeholder="選擇身分..."
                            styles={selectStyles} />
                    </div>
                    <div className="input-group">
                        <label>申請日期 (Date)</label>
                        <input type="text" id="f-date" value={date} onChange={e => setDate(e.target.value)} />
                    </div>
                </div>
                <div className="input-group full-width">
                    <label>金額說明 (Amount Summary)</label>
                    <input type="text" id="f-amount" value={amount} onChange={e => setAmount(e.target.value)} />
                </div>
                <div className="input-group full-width">
                    <label>聯絡人 (Contact)</label>
                    <input type="text" id="f-contact" value={contact} onChange={e => setContact(e.target.value)} />
                </div>
                <div className="input-group full-width">
                    <label>簡介 (Description)</label>
                    <textarea id="f-desc" rows={3} value={description} onChange={e => setDescription(e.target.value)} />
                </div>
                <div className="section-title mt-2">
                    <h3>3. 知識庫 Markdown 預覽</h3>
                    <p>這將是被切片存入 Milvus 向量資料庫的內容</p>
                </div>
                <div className="markdown-editor-container">
                    <textarea
                        id="f-markdown"
                        className="markdown-input"
                        spellCheck={false}
                        value={markdown}
                        onChange={e => setMarkdown(e.target.value)}
                    />
                    <div id="markdown-preview" className="markdown-preview" ref={previewRef} />
                </div>
                <div className="action-bar">
                    {mode === 'UPDATE' && (
                        <>
                            <button type="button" className="submit-btn btn-danger" id="btn-delete"
                                onClick={handleDelete} disabled={deleting}>
                                {deleting ? '刪除中...' : '刪除此筆資料'}
                            </button>
                            <button type="button" className="submit-btn btn-secondary" id="btn-clear"
                                onClick={onDeleted}>
                                清空並新增
                            </button>
                        </>
                    )}
                    <button type="button" className="submit-btn" id="btn-save"
                        onClick={handleSave} disabled={saving}>
                        {saving ? '處理中，正在進行向量切片與同步...' : mode === 'UPDATE' ? '更新資料庫與知識庫' : '確認無誤，存入關聯資料庫與知識庫'}
                    </button>
                </div>
            </form>
        </section>
    );
}