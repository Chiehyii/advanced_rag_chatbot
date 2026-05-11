import React, { useState } from 'react';
import { Message, Language } from '../types';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { ThumbsUp, ThumbsDown, Globe, ChevronDown, ChevronRight, BookOpen, Loader2 } from 'lucide-react';
import { translations } from '../App';

interface MessageBubbleProps {
  message: Message;
  onFeedback: (logId: string, feedbackToken: string, type: 'like' | 'dislike' | null) => void;
  onChipClick: (text: string) => void;
  language?: Language;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, onFeedback, onChipClick, language = 'zh' }) => {
  const { role, content, contexts, logId, feedbackToken, chips, isStreaming, thinkingSteps } = message;
  const t = translations[language];
  const [feedbackState, setFeedbackState] = useState<'like' | 'dislike' | null>(null);
  const [isMobileExpanded, setIsMobileExpanded] = useState(false);
  const [isThinkingCollapsed, setIsThinkingCollapsed] = useState(true);

  // [SEC-5] 使用 URL 建構子驗證協議，防止 javascript: / data: 等惡意 URL
  const sanitizeUrl = (raw: string | undefined | null): string => {
    if (!raw || raw === '#') return '#';
    try {
      const normalized = raw.startsWith('http') ? raw : 'https://' + raw;
      const parsed = new URL(normalized);
      // 只允許 https 和 http 協議，其他一律顯示安全的佔位符
      return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : '#';
    } catch {
      return '#'; // URL 格式錯誤時也安全降級
    }
  };

  // 修改 createMarkup，讓它接收 contexts 陣列
  const createMarkup = (text: string, ctxs: any[]) => {
    // 1. 先把 Markdown 轉成 HTML，避免 marked 把之後注入的 HTML 標籤當文字跳脫
    const rawHtml = marked.parse(text) as string;

    // 2. 再對 HTML 字串做引用標籤替換 [1] → Tooltip 結構
    const processedHtml = rawHtml.replace(/\[(\d+)\]/g, (match, num) => {
      const idx = parseInt(num) - 1;
      const ctx = ctxs && ctxs[idx] ? ctxs[idx] : null;

      // 如果找不到對應的文件，就保持原樣
      if (!ctx) return `<sup class="inline-citation">${match}</sup>`;

      // 取得網址、標題與內容片段
      const url = sanitizeUrl(ctx.source_url);  // [SEC-5]
      const title = ctx.source_file || t.unknown_source;
      const domain = url !== '#' ? new URL(url).hostname : '';
      // 產生 Tooltip 結構 (<a> 標籤負責點擊前往，後面的 span 是 Hover 卡片)
      return `
        <span class="citation-wrapper">
          <a href="${url}" target="_blank" rel="noopener noreferrer" class="inline-citation">
            <sup>[${num}]</sup>
          </a>
          <span class="citation-tooltip">
            <span class="tooltip-title">${title}</span>
            ${domain ? `<span class="tooltip-url">${domain}</span>` : ''}
          </span>
        </span>
      `;
    });

    return {
      __html: DOMPurify.sanitize(processedHtml, { ADD_ATTR: ['target', 'rel', 'class'] })
    };
  };

  if (role === 'user') {
    return (
      <div className="message user-message">
        {content}
      </div>
    );
  }

  return (
    <div className="bot-message-container">
      <div className="bot-message-content">
        <div className="message-body">
          <div className="bot-left-col">
            {/* Thinking steps or content */}
            <div
              className="message bot-message"
            >
              {/* Thinking steps section — auto-collapsed when content starts */}
              {thinkingSteps && thinkingSteps.length > 0 && (
                <div className={`thinking-steps ${content ? 'collapsed' : 'expanded'}`}>
                  {content ? (
                    <button
                      className="thinking-toggle"
                      onClick={() => setIsThinkingCollapsed(!isThinkingCollapsed)}
                    >
                      {isThinkingCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                      <span className="thinking-toggle-text">
                        {thinkingSteps.filter(s => s.status === 'done').length} steps completed
                      </span>
                    </button>
                  ) : null}
                  {/* Show list when: no content yet (still thinking), OR content exists but user expanded */}
                  {(!content || (content && !isThinkingCollapsed)) && (
                    <div className="thinking-list">
                      {thinkingSteps.map((step, idx) => (
                        <div key={idx} className={`thinking-item thinking-${step.status}`}>
                          {step.status === 'running' && (
                            <span className="thinking-icon">
                              <Loader2 size={14} className="spin" />
                            </span>
                          )}
                          <span className="thinking-text">{step.step}</span>
                          {step.detail && <span className="thinking-detail">{step.detail}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {/* Main content */}
              {content && (
                <div dangerouslySetInnerHTML={createMarkup(content, contexts || [])} />
              )}
            </div>
            {logId && feedbackToken && !isStreaming && (
              <div className="feedback-buttons">
                <button
                  className={`feedback-btn like-btn ${feedbackState === 'like' ? 'active' : ''}`}
                  onClick={() => {
                    const newState = feedbackState === 'like' ? null : 'like';
                    setFeedbackState(newState);
                    onFeedback(logId, feedbackToken, newState);
                  }}
                  title="Satisfied"
                >
                  <ThumbsUp size={16} color={feedbackState === 'like' ? 'var(--link-color)' : '#adb1b9'} fill={feedbackState === 'like' ? 'var(--link-color)' : 'none'} />
                </button>
                <button
                  className={`feedback-btn dislike-btn ${feedbackState === 'dislike' ? 'active' : ''}`}
                  onClick={() => {
                    const newState = feedbackState === 'dislike' ? null : 'dislike';
                    setFeedbackState(newState);
                    onFeedback(logId, feedbackToken, newState);
                  }}
                  title="Dissatisfied"
                >
                  <ThumbsDown size={16} color={feedbackState === 'dislike' ? '#ea4335' : '#adb1b9'} fill={feedbackState === 'dislike' ? '#ea4335' : 'none'} />
                </button>
                {contexts && contexts.length > 0 && (
                  <button
                    className={`feedback-btn source-toggle-btn ${isMobileExpanded ? 'active' : ''}`}
                    onClick={() => setIsMobileExpanded(!isMobileExpanded)}
                    title={t.reference_title}
                  >
                    <BookOpen size={16} color={isMobileExpanded ? 'var(--link-color)' : '#adb1b9'} strokeWidth={1.5} />
                  </button>
                )}
              </div>
            )}
            {/* Inline source cards — toggled by BookOpen icon */}
            {isMobileExpanded && contexts && contexts.length > 0 && !isStreaming && (
              <div className="inline-contexts">
                {contexts.map((ctx, idx) => {
                  const url = sanitizeUrl(ctx.source_url);
                  const domain = url !== '#' ? new URL(url).hostname : '';
                  return (
                    <a
                      key={idx}
                      id={`context-card-${logId || 'temp'}-${idx + 1}`}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="context-card-link"
                      title={ctx.source_file || 'Unknown'}
                    >
                      <div className="context-card">
                        <div className="context-card-title">{ctx.source_file || t.unknown_source}</div>
                        <div className="context-card-url" style={{ color: '#666', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          {domain ? (
                            <img src={`https://www.google.com/s2/favicons?sz=64&domain=${encodeURIComponent(domain)}`} alt="icon" style={{ width: 16, height: 16, borderRadius: 2 }} />
                          ) : <Globe size={16} color="#888" />}
                          <span className="url-text">{url}</span>
                        </div>
                      </div>
                    </a>
                  );
                })}
              </div>
            )}
            {chips && chips.length > 0 && !isStreaming && (
              <div className="chips-container">
                {chips.map((chip, idx) => (
                  <button key={idx} className="chip" onClick={() => onChipClick(chip)}>
                    {chip}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
