import { useState, useEffect, useCallback } from 'react';
import { apiGetDashboardSummary, apiGetDashboardTrends, apiGetDashboardRecent } from './api';
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
    Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { MessageSquare, Users, Zap, Coins, ThumbsUp, Flame, ChevronDown, ChevronUp, Calendar } from 'lucide-react';

interface DashboardProps {
    onUnauthorized: () => void;
}

interface SummaryData {
    today_queries: number;
    unique_users: number;
    avg_latency_ms: number;
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    satisfaction_rate: number | null;
    peak_rpm: number;
    peak_rpm_time: string | null;
}

interface TrendsData {
    labels: string[];
    queries: number[];
    tokens: number[];
    unique_users: number[];
    avg_latency: number[];
}

interface RecentLog {
    id: number;
    timestamp: string;
    question: string;
    answer: string;
    latency_ms: number;
    total_tokens: number;
    feedback_type: string | null;
}

// Helper: get ISO date string for N days ago
const daysAgo = (n: number): string => {
    const d = new Date();
    d.setDate(d.getDate() - n);
    return d.toISOString().split('T')[0];
};
const todayStr = () => new Date().toISOString().split('T')[0];

export function Dashboard({ onUnauthorized }: DashboardProps) {
    const [summary, setSummary] = useState<SummaryData | null>(null);
    const [trends, setTrends] = useState<TrendsData | null>(null);
    const [recent, setRecent] = useState<RecentLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [expandedRow, setExpandedRow] = useState<number | null>(null);
    const [showTokenDetail, setShowTokenDetail] = useState(false);

    // Date range state
    const [startDate, setStartDate] = useState(daysAgo(6));
    const [endDate, setEndDate] = useState(todayStr());
    const [activePreset, setActivePreset] = useState<string>('7d');

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [s, t, r] = await Promise.all([
                apiGetDashboardSummary(),
                apiGetDashboardTrends(startDate, endDate),
                apiGetDashboardRecent(20),
            ]);
            setSummary(s);
            setTrends(t);
            setRecent(r);
        } catch (err: any) {
            if (err.message === 'UNAUTHORIZED') onUnauthorized();
        } finally {
            setLoading(false);
        }
    }, [onUnauthorized, startDate, endDate]);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    // Fetch only trends when date changes (avoid refetching summary & recent)
    const fetchTrends = useCallback(async (s: string, e: string) => {
        try {
            const t = await apiGetDashboardTrends(s, e);
            setTrends(t);
        } catch (err: any) {
            if (err.message === 'UNAUTHORIZED') onUnauthorized();
        }
    }, [onUnauthorized]);

    const handlePreset = (preset: string, days: number) => {
        const newStart = daysAgo(days - 1);
        const newEnd = todayStr();
        setStartDate(newStart);
        setEndDate(newEnd);
        setActivePreset(preset);
        fetchTrends(newStart, newEnd);
    };

    const handleDateChange = (type: 'start' | 'end', value: string) => {
        setActivePreset('');
        if (type === 'start') {
            setStartDate(value);
            fetchTrends(value, endDate);
        } else {
            setEndDate(value);
            fetchTrends(startDate, value);
        }
    };

    // Prepare chart data
    const trendChartData = trends
        ? trends.labels.map((label, i) => ({
            date: label,
            提問數: trends.queries[i],
            使用者: trends.unique_users[i],
            '延遲(s)': +(trends.avg_latency[i] / 1000).toFixed(2),
        }))
        : [];

    const tokenChartData = trends
        ? trends.labels.map((label, i) => ({
            date: label,
            Tokens: trends.tokens[i],
        }))
        : [];

    const formatTimestamp = (ts: string) => {
        try {
            const d = new Date(ts);
            return d.toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
        } catch { return ts; }
    };

    const feedbackIcon = (type: string | null) => {
        if (type === 'like') return '👍';
        if (type === 'dislike') return '👎';
        return '—';
    };

    if (loading) {
        return (
            <div className="dash-loading">
                <div className="dash-spinner" />
                <p>載入 Dashboard 數據中...</p>
            </div>
        );
    }

    return (
        <div className="dashboard-container">
            {/* KPI Cards */}
            <div className="dash-cards">
                <div className="dash-card">
                    <div className="dash-card-icon" style={{ background: 'linear-gradient(135deg, #b7b0f1, #d2e6f1)' }}>
                        <MessageSquare size={22} />
                    </div>
                    <div className="dash-card-body">
                        <span className="dash-card-label">今日提問數</span>
                        <span className="dash-card-value">{summary?.today_queries ?? 0}</span>
                    </div>
                </div>
                <div className="dash-card">
                    <div className="dash-card-icon" style={{ background: 'linear-gradient(135deg, #5ac2d4ff, #afe4ecff)' }}>
                        <Users size={22} />
                    </div>
                    <div className="dash-card-body">
                        <span className="dash-card-label">獨立使用者</span>
                        <span className="dash-card-value">{summary?.unique_users ?? 0}</span>
                    </div>
                </div>
                <div className="dash-card">
                    <div className="dash-card-icon" style={{ background: 'linear-gradient(135deg, #f0b44eff, #f3dca1ff)' }}>
                        <Zap size={22} />
                    </div>
                    <div className="dash-card-body">
                        <span className="dash-card-label">平均回應速度</span>
                        <span className="dash-card-value">{summary ? (summary.avg_latency_ms / 1000).toFixed(1) : '0'}s</span>
                    </div>
                </div>
                <div className="dash-card" onClick={() => setShowTokenDetail(!showTokenDetail)} style={{ cursor: 'pointer' }}>
                    <div className="dash-card-icon" style={{ background: 'linear-gradient(135deg, #51be96ff, #bfddd3ff)' }}>
                        <Coins size={22} />
                    </div>
                    <div className="dash-card-body">
                        <span className="dash-card-label">Token 消耗 {showTokenDetail ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>
                        <span className="dash-card-value">{summary ? summary.total_tokens.toLocaleString() : '0'}</span>
                        {showTokenDetail && summary && (
                            <div className="dash-card-detail">
                                <span>提問: {summary.prompt_tokens.toLocaleString()}</span>
                                <span>回答: {summary.completion_tokens.toLocaleString()}</span>
                            </div>
                        )}
                    </div>
                </div>
                <div className="dash-card">
                    <div className="dash-card-icon" style={{ background: 'linear-gradient(135deg, #d476a5ff, #e9d9e1ff)' }}>
                        <ThumbsUp size={22} />
                    </div>
                    <div className="dash-card-body">
                        <span className="dash-card-label">滿意度</span>
                        <span className="dash-card-value">
                            {summary?.satisfaction_rate != null ? `${Math.round(summary.satisfaction_rate * 100)}%` : 'N/A'}
                        </span>
                    </div>
                </div>
                <div className="dash-card">
                    <div className="dash-card-icon" style={{ background: 'linear-gradient(135deg, #e47676ff, #fac2c2ff)' }}>
                        <Flame size={22} />
                    </div>
                    <div className="dash-card-body">
                        <span className="dash-card-label">尖峰 RPM</span>
                        <span className="dash-card-value">{summary?.peak_rpm ?? 0}</span>
                        {summary?.peak_rpm_time && (
                            <span className="dash-card-sub">發生於 {summary.peak_rpm_time}</span>
                        )}
                    </div>
                </div>
            </div>

            {/* Date Range Picker + Trend Charts */}
            <div className="dash-date-bar glass-panel">
                <div className="dash-date-left">
                    <Calendar size={16} />
                    <span className="dash-date-label">趨勢範圍</span>
                    <div className="dash-presets">
                        {[['7d', 7], ['14d', 14], ['30d', 30], ['90d', 90]].map(([label, days]) => (
                            <button
                                key={label as string}
                                className={`dash-preset-btn ${activePreset === label ? 'active' : ''}`}
                                onClick={() => handlePreset(label as string, days as number)}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="dash-date-inputs">
                    <input
                        type="date"
                        value={startDate}
                        max={endDate}
                        onChange={e => handleDateChange('start', e.target.value)}
                        className="dash-date-input"
                    />
                    <span className="dash-date-sep">—</span>
                    <input
                        type="date"
                        value={endDate}
                        min={startDate}
                        max={todayStr()}
                        onChange={e => handleDateChange('end', e.target.value)}
                        className="dash-date-input"
                    />
                </div>
            </div>

            <div className="dash-charts">
                <div className="dash-chart-box glass-panel">
                    <h3>每日提問量、使用者與回應速度</h3>
                    <ResponsiveContainer width="100%" height={280}>
                        <LineChart data={trendChartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                            <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
                            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} unit="s" />
                            <Tooltip
                                contentStyle={{ borderRadius: 10, border: 'none', boxShadow: '0 4px 16px rgba(0,0,0,0.12)' }}
                            />
                            <Legend />
                            <Line yAxisId="left" type="monotone" dataKey="提問數" stroke="#6366f1" strokeWidth={2.5} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                            <Line yAxisId="left" type="monotone" dataKey="使用者" stroke="#06b6d4" strokeWidth={2.5} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                            <Line yAxisId="right" type="monotone" dataKey="延遲(s)" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 3" dot={{ r: 3 }} activeDot={{ r: 5 }} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
                <div className="dash-chart-box glass-panel">
                    <h3>每日 Token 消耗量</h3>
                    <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={tokenChartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                            <YAxis tick={{ fontSize: 12 }} />
                            <Tooltip
                                contentStyle={{ borderRadius: 10, border: 'none', boxShadow: '0 4px 16px rgba(0,0,0,0.12)' }}
                                formatter={(value: number) => [value.toLocaleString(), 'Tokens']}
                            />
                            <Bar dataKey="Tokens" fill="url(#tokenGradient)" radius={[6, 6, 0, 0]} />
                            <defs>
                                <linearGradient id="tokenGradient" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#10b981" />
                                    <stop offset="100%" stopColor="#34d399" />
                                </linearGradient>
                            </defs>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Recent Activity */}
            <div className="dash-recent glass-panel">
                <h3>近期對話紀錄</h3>
                <div className="dash-table-wrapper">
                    <table className="dash-table">
                        <thead>
                            <tr>
                                <th>時間</th>
                                <th>用戶提問</th>
                                <th>延遲</th>
                                <th>Token</th>
                                <th>回饋</th>
                            </tr>
                        </thead>
                        <tbody>
                            {recent.length === 0 ? (
                                <tr><td colSpan={5} style={{ textAlign: 'center', padding: 24, color: '#94a3b8' }}>尚無對話紀錄</td></tr>
                            ) : recent.map(log => (
                                <>
                                    <tr
                                        key={log.id}
                                        className={`dash-table-row ${expandedRow === log.id ? 'expanded' : ''}`}
                                        onClick={() => setExpandedRow(expandedRow === log.id ? null : log.id)}
                                    >
                                        <td className="dash-td-time">{formatTimestamp(log.timestamp)}</td>
                                        <td className="dash-td-question">{log.question.length > 50 ? log.question.slice(0, 50) + '…' : log.question}</td>
                                        <td>{(log.latency_ms / 1000).toFixed(1)}s</td>
                                        <td>{log.total_tokens.toLocaleString()}</td>
                                        <td>{feedbackIcon(log.feedback_type)}</td>
                                    </tr>
                                    {expandedRow === log.id && (
                                        <tr key={`${log.id}-detail`} className="dash-table-detail">
                                            <td colSpan={5}>
                                                <div className="dash-detail-content">
                                                    <strong>完整提問：</strong> {log.question}
                                                    <br /><br />
                                                    <strong>AI 回答（節錄）：</strong> {log.answer}
                                                </div>
                                            </td>
                                        </tr>
                                    )}
                                </>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
