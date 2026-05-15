import React, { useState } from 'react';
import { marked } from 'marked';
import type { Token, Tokens } from 'marked';
import { BookOpen, ChevronDown, ChevronRight, Globe, Loader2, ThumbsDown, ThumbsUp } from 'lucide-react';
import { Language, Message } from '../types';
import { translations } from '../App';

interface MessageBubbleProps {
  message: Message;
  onFeedback: (logId: string, feedbackToken: string, type: 'like' | 'dislike' | null) => void;
  onChipClick: (text: string) => void;
  language?: Language;
}

type ContextLike = {
  source_file?: string;
  source_url?: string;
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, onFeedback, onChipClick, language = 'zh' }) => {
  const { role, content, contexts, logId, feedbackToken, chips, isStreaming, thinkingSteps } = message;
  const t = translations[language];
  const [feedbackState, setFeedbackState] = useState<'like' | 'dislike' | null>(null);
  const [isMobileExpanded, setIsMobileExpanded] = useState(false);
  const [isThinkingCollapsed, setIsThinkingCollapsed] = useState(true);

  const sanitizeUrl = (raw: string | undefined | null): string => {
    if (!raw || raw === '#') return '#';
    try {
      const normalized = raw.startsWith('http') ? raw : 'https://' + raw;
      const parsed = new URL(normalized);
      return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : '#';
    } catch {
      return '#';
    }
  };

  const renderCitation = (num: string, key: string, ctxs: ContextLike[], showTooltip = true) => {
    const idx = parseInt(num, 10) - 1;
    const ctx = ctxs && ctxs[idx] ? ctxs[idx] : null;
    if (!ctx) return <sup key={key} className="inline-citation">[{num}]</sup>;

    const url = sanitizeUrl(ctx.source_url);
    const title = ctx.source_file || t.unknown_source;
    const domain = url !== '#' ? new URL(url).hostname : '';

    if (!showTooltip) {
      return (
        <a key={key} href={url} target="_blank" rel="noopener noreferrer" className="inline-citation">
          <sup>[{num}]</sup>
        </a>
      );
    }

    return (
      <span key={key} className="citation-wrapper">
        <a href={url} target="_blank" rel="noopener noreferrer" className="inline-citation">
          <sup>[{num}]</sup>
        </a>
        <span className="citation-tooltip">
          <span className="tooltip-title">{title}</span>
          {domain ? <span className="tooltip-url">{domain}</span> : null}
        </span>
      </span>
    );
  };

  const renderInline = (text: string, keyPrefix: string, ctxs: ContextLike[], options: { showCitationTooltip?: boolean } = {}): React.ReactNode[] => {
    const nodes: React.ReactNode[] = [];
    const pattern = /(\[(\d+)\]|\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|<br\s*\/?>)/gi;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = pattern.exec(text)) !== null) {
      if (match.index > lastIndex) {
        nodes.push(text.slice(lastIndex, match.index));
      }

      const key = `${keyPrefix}-${match.index}`;
      if (match[2]) {
        nodes.push(renderCitation(match[2], key, ctxs, options.showCitationTooltip !== false));
      } else if (match[3] && match[4]) {
        const url = sanitizeUrl(match[4]);
        nodes.push(
          <a key={key} href={url} target="_blank" rel="noopener noreferrer">
            {match[3]}
          </a>
        );
      } else if (match[5]) {
        nodes.push(<code key={key}>{match[5]}</code>);
      } else if (match[6]) {
        nodes.push(<strong key={key}>{match[6]}</strong>);
      } else if (match[0].toLowerCase().startsWith('<br')) {
        nodes.push(<br key={key} />);
      }

      lastIndex = pattern.lastIndex;
    }

    if (lastIndex < text.length) {
      nodes.push(text.slice(lastIndex));
    }

    return nodes;
  };

  const normalizeMarkdownTables = (value: string): string => {
    const separatorPattern = /\|(?:\s*:?-{3,}:?\s*\|)+/g;
    const countCells = (row: string) => row.split('|').slice(1, -1).length;
    const readRow = (line: string, start: number, cellCount: number) => {
      let pipes = 0;
      for (let i = start; i < line.length; i++) {
        if (line[i] === '|') {
          pipes += 1;
          if (pipes === cellCount + 1) {
            return { row: line.slice(start, i + 1).trim(), end: i + 1 };
          }
        }
      }
      return null;
    };

    return value.split('\n').map((line) => {
      separatorPattern.lastIndex = 0;
      const separatorMatch = separatorPattern.exec(line);
      if (!separatorMatch) return line;

      const separator = separatorMatch[0].trim();
      const cellCount = countCells(separator);
      if (cellCount < 2) return line;

      const separatorStart = separatorMatch.index;
      const headerCandidates: number[] = [];
      for (let i = 0; i < separatorStart; i++) {
        if (line[i] === '|') headerCandidates.push(i);
      }

      let headerStart: number | undefined;
      for (let i = headerCandidates.length - 1; i >= 0; i--) {
        const start = headerCandidates[i];
        const candidate = readRow(line, start, cellCount);
        if (candidate && candidate.end <= separatorStart && line.slice(candidate.end, separatorStart).trim() === '') {
          headerStart = start;
          break;
        }
      }
      if (headerStart === undefined) return line;

      const header = readRow(line, headerStart, cellCount);
      const separatorRow = readRow(line, separatorStart, cellCount);
      if (!header || !separatorRow) return line;

      const rows: string[] = [];
      let cursor = separatorRow.end;
      while (cursor < line.length) {
        while (line[cursor] === ' ' || line[cursor] === '\t') cursor += 1;
        if (line[cursor] !== '|') break;

        const row = readRow(line, cursor, cellCount);
        if (!row) break;
        rows.push(row.row);
        cursor = row.end;
      }

      if (rows.length === 0) return line;

      const before = line.slice(0, headerStart);
      const after = line.slice(cursor);
      const trailingText = after.trim() ? `\n\n${after.trimStart()}` : after;
      return `${before}${header.row}\n${separator}\n${rows.join('\n')}${trailingText}`;
    }).join('\n');
  };

  const getTableCellText = (cell: Tokens.TableCell | string): string => {
    if (typeof cell === 'string') return cell;
    return cell.text || '';
  };

  const getTableTextAlign = (
    align: Tokens.Table['align'][number] | undefined
  ): React.CSSProperties['textAlign'] => {
    return align || undefined;
  };

  const renderMarkdown = (text: string, ctxs: ContextLike[]) => {
    const tokens = marked.lexer(normalizeMarkdownTables(text), { gfm: true, breaks: true });

    return tokens.map((token: Token, idx: number) => {
      const key = `md-${idx}`;

      if (token.type === 'heading') {
        const HeadingTag = `h${Math.min(token.depth || 3, 4)}` as keyof JSX.IntrinsicElements;
        return <HeadingTag key={key}>{renderInline(token.text || '', key, ctxs)}</HeadingTag>;
      }

      if (token.type === 'paragraph') {
        return <p key={key}>{renderInline(token.text || '', key, ctxs)}</p>;
      }

      if (token.type === 'list') {
        const ListTag = token.ordered ? 'ol' : 'ul';
        return (
          <ListTag key={key}>
            {token.items.map((item: Tokens.ListItem, itemIdx: number) => (
              <li key={`${key}-item-${itemIdx}`}>{renderInline(item.text, `${key}-item-${itemIdx}`, ctxs)}</li>
            ))}
          </ListTag>
        );
      }

      if (token.type === 'table') {
        return (
          <div key={key} className="markdown-table-wrapper">
            <table>
              <thead>
                <tr>
                  {token.header.map((cell: Tokens.TableCell, cellIdx: number) => (
                    <th key={`${key}-head-${cellIdx}`} style={{ textAlign: getTableTextAlign(token.align[cellIdx]) }}>
                      {renderInline(getTableCellText(cell), `${key}-head-${cellIdx}`, ctxs, { showCitationTooltip: false })}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {token.rows.map((row: Tokens.TableCell[], rowIdx: number) => (
                  <tr key={`${key}-row-${rowIdx}`}>
                    {row.map((cell: Tokens.TableCell, cellIdx: number) => (
                      <td key={`${key}-cell-${rowIdx}-${cellIdx}`} style={{ textAlign: getTableTextAlign(token.align[cellIdx]) }}>
                        {renderInline(getTableCellText(cell), `${key}-cell-${rowIdx}-${cellIdx}`, ctxs, { showCitationTooltip: false })}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }

      if (token.type === 'code') {
        return (
          <pre key={key}>
            <code>{token.text || ''}</code>
          </pre>
        );
      }

      if (token.type === 'blockquote') {
        return <blockquote key={key}>{renderInline(token.text || '', key, ctxs)}</blockquote>;
      }

      if (token.type === 'space') return null;

      return <p key={key}>{renderInline(token.raw || '', key, ctxs)}</p>;
    });
  };

  if (role === 'user') {
    return <div className="message user-message">{content}</div>;
  }

  return (
    <div className="bot-message-container">
      <div className="bot-message-content">
        <div className="message-body">
          <div className="bot-left-col">
            <div className="message bot-message">
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
              {content && <div>{renderMarkdown(content, contexts || [])}</div>}
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
