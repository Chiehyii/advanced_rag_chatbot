import { useState, useEffect, useCallback } from 'react';
import Select from 'react-select';
import { Scholarship, MetadataSchema } from './types';
import { apiListScholarships, apiGetScholarship, apiGetMetadataSchema } from './api';
import './admin.css';
interface AdminSidebarProps {
    onSelect: (scholarship: Scholarship) => void;
    onUnauthorized: () => void;
    refreshTrigger: number;
}
type OptionType = { value: string; label: string };
export function AdminSidebar({ onSelect, onUnauthorized, refreshTrigger }: AdminSidebarProps) {
    const [allScholarships, setAllScholarships] = useState<Scholarship[]>([]);
    const [filtered, setFiltered] = useState<Scholarship[]>([]);
    const [schema, setSchema] = useState<MetadataSchema | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedEdu, setSelectedEdu] = useState<OptionType[]>([]);
    const [selectedTags, setSelectedTags] = useState<OptionType[]>([]);
    const [selectedIdentity, setSelectedIdentity] = useState<OptionType[]>([]);
    const [activeCode, setActiveCode] = useState<string | null>(null);
    const fetchData = useCallback(async () => {
        try {
            const [scholarships, meta] = await Promise.all([
                apiListScholarships(),
                apiGetMetadataSchema(),
            ]);
            setAllScholarships(scholarships);
            setSchema(meta);
        } catch (err: any) {
            if (err.message === 'UNAUTHORIZED') onUnauthorized();
        }
    }, [onUnauthorized]);
    useEffect(() => { fetchData(); }, [fetchData, refreshTrigger]);
    useEffect(() => {
        const search = searchTerm.toLowerCase();
        const eduVals = selectedEdu.map(o => o.value);
        const tagsVals = selectedTags.map(o => o.value);
        const identityVals = selectedIdentity.map(o => o.value);
        const hasOverlap = (source: string[] | undefined, filter: string[]) => {
            if (!filter.length) return true;
            if (!source?.length) return false;
            return filter.some(v => source.includes(v));
        };
        setFiltered(allScholarships.filter(item => {
            const textMatch = !search ||
                item.title?.toLowerCase().includes(search) ||
                item.scholarship_code?.toLowerCase().includes(search);
            return textMatch &&
                hasOverlap(item.education_system, eduVals) &&
                hasOverlap(item.tags, tagsVals) &&
                hasOverlap(item.identity, identityVals);
        }));
    }, [allScholarships, searchTerm, selectedEdu, selectedTags, selectedIdentity]);
    const handleClick = async (code: string) => {
        setActiveCode(code);
        try {
            const detail = await apiGetScholarship(code);
            onSelect(detail);
        } catch (err: any) {
            if (err.message === 'UNAUTHORIZED') onUnauthorized();
        }
    };
    const toOptions = (arr: string[] = []): OptionType[] => arr.map(s => ({ value: s, label: s }));
    const selectStyles = {
        control: (base: any) => ({
            ...base, borderRadius: 8, borderColor: '#cbd5e1', fontSize: '0.9rem', minHeight: 40,
        }),
        multiValue: (base: any) => ({ ...base, backgroundColor: '#6366f1', borderRadius: 6 }),
        multiValueLabel: (base: any) => ({ ...base, color: '#fff' }),
        multiValueRemove: (base: any) => ({ ...base, color: '#fff', ':hover': { backgroundColor: '#4f46e5' } }),
    };
    return (
        <aside className="sidebar glass-panel">
            <div className="sidebar-header">
                <div className="logo">✦</div>
                <h2>知識庫總覽</h2>
            </div>
            <div className="sidebar-content">
                <div className="filter-section">
                    <div className="search-box">
                        <input
                            type="text"
                            placeholder="🔍 搜尋標題或代碼..."
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                        />
                    </div>
                    {schema && (
                        <>
                            <Select isMulti options={toOptions(schema.education_system)} value={selectedEdu}
                                onChange={v => setSelectedEdu(v as OptionType[])} placeholder="過濾學制..."
                                styles={selectStyles} />
                            <Select isMulti options={toOptions(schema.tags)} value={selectedTags}
                                onChange={v => setSelectedTags(v as OptionType[])} placeholder="過濾標籤..."
                                styles={selectStyles} />
                            <Select isMulti options={toOptions(schema.identity)} value={selectedIdentity}
                                onChange={v => setSelectedIdentity(v as OptionType[])} placeholder="過濾身分..."
                                styles={selectStyles} />
                        </>
                    )}
                </div>
                <ul className="scholarship-list">
                    {filtered.length === 0 ? (
                        <li><div className="meta" style={{ textAlign: 'center', padding: '20px 0' }}>目前資料庫為空</div></li>
                    ) : filtered.map(item => (
                        <li key={item.scholarship_code}
                            className={`${activeCode === item.scholarship_code ? 'active' : ''} ${item.needs_review ? 'needs-review' : ''}`}
                            onClick={() => handleClick(item.scholarship_code)}>
                            <div className="title" style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                <span>{item.title}</span>
                                {item.needs_review && (
                                    <span className="pending-badge">待處理</span>
                                )}
                            </div>
                            <div className="meta">{item.category || '未分類'} | {item.scholarship_code.substring(0, 8)}</div>
                        </li>
                    ))}
                </ul>
            </div>
        </aside>
    );
}