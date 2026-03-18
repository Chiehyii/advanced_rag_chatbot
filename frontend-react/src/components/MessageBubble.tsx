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

  const createMarkup = (text: string) => {
    return { __html: DOMPurify.sanitize(marked.parse(text) as string) };
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
            <div
              className={`message bot-message ${isStreaming && !content ? 'thinking' : ''}`}
              dangerouslySetInnerHTML={content ? createMarkup(content) : { __html: 'Thinking...' }}
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
                    <a key={idx} href={url} target="_blank" rel="noopener noreferrer" className="context-card-link" title={ctx.source_file || 'Unknown'}>
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
