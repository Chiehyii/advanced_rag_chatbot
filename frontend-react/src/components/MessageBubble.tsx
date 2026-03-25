import React, { useState } from 'react';
import { Message, Language } from '../types';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { ThumbsUp, ThumbsDown, Globe } from 'lucide-react';
import { translations } from '../App';

interface MessageBubbleProps {
  message: Message;
  onFeedback: (logId: string, type: 'like' | 'dislike' | null) => void;
  onChipClick: (text: string) => void;
  language?: Language;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, onFeedback, onChipClick, language = 'zh' }) => {
  const { role, content, contexts, logId, chips, isStreaming } = message;
  const t = translations[language];
  const [feedbackState, setFeedbackState] = useState<'like' | 'dislike' | null>(null);

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
      let url = ctx.source_url || '#';
      if (url !== '#' && !url.startsWith('http')) {
        url = 'https://' + url;
      }
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

    // 3. 確保 DOMPurify 允許我們新增的屬性 (target, rel, class)
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
            {/* 3. 記得把 onClick={handleMessageClick} 移除，並且把 contexts 傳給 createMarkup */}
            <div
              className={`message bot-message ${isStreaming && !content ? 'thinking' : ''}`}
              dangerouslySetInnerHTML={content ? createMarkup(content, contexts || []) : { __html: 'Thinking...' }}
            />
            {logId && !isStreaming && (
              <div className="feedback-buttons">
                <button
                  className={`feedback-btn like-btn ${feedbackState === 'like' ? 'active' : ''}`}
                  onClick={() => {
                    const newState = feedbackState === 'like' ? null : 'like';
                    setFeedbackState(newState);
                    onFeedback(logId, newState);
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
                    onFeedback(logId, newState);
                  }}
                  title="Dissatisfied"
                >
                  <ThumbsDown size={16} color={feedbackState === 'dislike' ? '#ea4335' : '#adb1b9'} fill={feedbackState === 'dislike' ? '#ea4335' : 'none'} />
                </button>
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
          {contexts && contexts.length > 0 && !isStreaming && (
            <div className="contexts">
              <h4>{t.reference_title}</h4>
              <div className="context-cards-list">
                {contexts.map((ctx, idx) => {
                  let url = ctx.source_url || '#';
                  if (url !== '#' && !url.startsWith('http')) {
                    url = 'https://' + url;
                  }
                  const domain = url !== '#' ? new URL(url).hostname : '';
                  const displaySnippet = (ctx.text || '').replace(/<[^>]*>?/gm, '');

                  return (
                    // 4. 在 <a> 標籤上加入動態 id，注意這裡的 index 是 idx + 1，因為標籤是從 [1] 開始
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
                        <div className="context-card-text">{displaySnippet}</div>
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
};