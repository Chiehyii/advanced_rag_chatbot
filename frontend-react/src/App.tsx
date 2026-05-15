import React, { useState, useEffect, useRef, useMemo, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import { MessageList } from './components/MessageList';
import { ChatInput } from './components/ChatInput';
import { FeedbackModal } from './components/FeedbackModal';
import { ScholarshipFilterModal } from './components/ScholarshipFilterModal';
import { DesktopSidebar } from './components/DesktopSidebar';
import { OnboardingTour, TourStep } from './components/OnboardingTour';
import { Trash2 } from 'lucide-react';
import { Message, Language, ScholarshipTag, Theme } from './types';
import { translations } from './translations';
import './index.css';

const AdminApp = React.lazy(() => import('./admin/AdminApp').then(module => ({ default: module.AdminApp })));
const CHAT_STORAGE_KEY = 'tcu_scholarship_chat_history';
const CHAT_SESSION_TOKEN_KEY = 'tcu_chat_session_token';
const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const MAX_HISTORY_MESSAGES = 20;
const MAX_HISTORY_CONTENT_LENGTH = 2000;

function App() {
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const saved = sessionStorage.getItem(CHAT_STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [language, setLanguage] = useState<Language>('zh');
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem('tcu_theme') as Theme) || 'system';
  });
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    localStorage.setItem('tcu_theme', theme);
    if (theme === 'system') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
  }, [theme]);
  // --- 追蹤 ID ---
  const chatSessionTokenRef = useRef(sessionStorage.getItem(CHAT_SESSION_TOKEN_KEY) || '');
  const resetServerSessionRef = useRef(false);
  // [PERF-4] RAF handle 用於批次更新串流內容，避免每個 token 就觸發一次 re-render
  const rafRef = useRef<number | null>(null);
  const fullAnswerRef = useRef<string>(''); // 持綌最新的 fullAnswer，供 RAF closure 使用
  const flushStreamingContent = () => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const latest = fullAnswerRef.current;
    setMessages(prev => {
      const newMessages = [...prev];
      const lastIdx = newMessages.length - 1;
      if (lastIdx >= 0 && newMessages[lastIdx].role === 'assistant') {
        newMessages[lastIdx] = { ...newMessages[lastIdx], content: latest };
      }
      return newMessages;
    });
  };
  // Feedback state
  const [isFeedbackOpen, setIsFeedbackOpen] = useState(false);
  const [currentFeedbackLogId, setCurrentFeedbackLogId] = useState<string | null>(null);
  // Scholarship filter & tag state
  const [selectedTags, setSelectedTags] = useState<ScholarshipTag[]>([]);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  // Onboarding tour state
  const [isTourOpen, setIsTourOpen] = useState(false);
  // Persist messages to sessionStorage whenever they change
  useEffect(() => {
    // Only save completed (non-streaming) messages
    const messagesToSave = messages.filter(m => !m.isStreaming);
    try {
      sessionStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messagesToSave));
    } catch (e) {
      console.warn('Failed to save chat history to sessionStorage:', e);
    }
  }, [messages]);
  const handleSendMessage = async (text: string) => {
    const query = text.trim();
    if (!query || isLoading) {
      return;
    }

    // Hide prediction chips from the last bot message before responding
    setMessages(prev => {
      const updatedMessages = [...prev];
      for (let i = updatedMessages.length - 1; i >= 0; i--) {
        if (updatedMessages[i].role === 'assistant' && updatedMessages[i].chips) {
          updatedMessages[i] = { ...updatedMessages[i], chips: [] };
          break;
        }
      }
      return updatedMessages;
    });
    // Add user message
    const newMessage = { role: 'user', content: query } as Message;
    setMessages(prev => [...prev, newMessage]);
    setIsLoading(true);
    // Prepare a bounded history payload for API validation and request-size limits.
    const previousHistory = messages
      .filter(msg => !msg.isStreaming && (msg.role === 'user' || msg.role === 'assistant'))
      .map(msg => ({
        role: msg.role,
        content: msg.content.trim().slice(0, MAX_HISTORY_CONTENT_LENGTH),
      }))
      .filter(msg => msg.content.length > 0);
    const history = [
      ...previousHistory.slice(-(MAX_HISTORY_MESSAGES - 1)),
      { role: 'user' as const, content: query.slice(0, MAX_HISTORY_CONTENT_LENGTH) },
    ];
    // Add empty placeholder for bot streaming
    setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query,
          history,
          lang: language,
          title_filter: selectedTags.length > 0 ? selectedTags.map(t => t.title) : null,
          chat_session_token: chatSessionTokenRef.current || null,
          reset_session: resetServerSessionRef.current,
        })
      });
      resetServerSessionRef.current = false;
      const nextChatSessionToken = response.headers.get('X-Chat-Session-Token');
      if (nextChatSessionToken) {
        chatSessionTokenRef.current = nextChatSessionToken;
        sessionStorage.setItem(CHAT_SESSION_TOKEN_KEY, nextChatSessionToken);
      }
      if (!response.ok) {
        const errorText = await response.text().catch(() => '');
        throw new Error(`Network response was not ok (${response.status}): ${errorText}`);
      }
      if (response.body) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let done = false;
        let buffer = '';
        let fullAnswer = '';
        fullAnswerRef.current = ''; // [PERF-4] 重置 ref
        while (!done) {
          const { value, done: readerDone } = await reader.read();
          done = readerDone;
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || ''; // keep incomplete line
            for (const line of lines) {
              if (line.startsWith('event: end_stream')) {
                // Flush coalesced chunks before the final event marks streaming complete.
                flushStreamingContent();
                const dataLine = line.substring(line.indexOf('data: ') + 6);
                if (dataLine.trim()) {
                  try {
                    const finalPayload = JSON.parse(dataLine);
                    const finalData = finalPayload.data || {};
                    // Update the last message with contexts, logId, chips, and remove streaming flag
                    setMessages(prev => {
                      const newMessages = [...prev];
                      const lastIdx = newMessages.length - 1;
                      if (newMessages[lastIdx].role === 'assistant') {
                        newMessages[lastIdx] = {
                          ...newMessages[lastIdx],
                          isStreaming: false,
                          contexts: finalData.contexts || [],
                          logId: finalData.log_id,
                          feedbackToken: finalData.feedback_token,
                          chips: finalData.chips || []
                        };
                      }
                      return newMessages;
                    });
                  } catch (e) {
                    console.error('Error parsing final JSON:', e, dataLine);
                  }
                }
              } else if (line.startsWith('data: ')) {
                const chunk = line.substring(6);
                try {
                  const parsed = JSON.parse(chunk);
                  if (parsed.type === 'content') {
                    fullAnswer += parsed.data;
                  } else if (parsed.type === 'thinking_step') {
                    const stepData = parsed.data;
                    setMessages(prev => {
                      const newMessages = [...prev];
                      const lastIdx = newMessages.length - 1;
                      if (newMessages[lastIdx].role === 'assistant') {
                        const existing = newMessages[lastIdx].thinkingSteps || [];
                        // Replace last step if it was 'running' and this is a 'done' for same concept
                        const updated = [...existing];
                        if (stepData.status === 'done' && updated.length > 0 && updated[updated.length - 1].status === 'running') {
                          updated[updated.length - 1] = stepData;
                        } else {
                          updated.push(stepData);
                        }
                        newMessages[lastIdx] = { ...newMessages[lastIdx], thinkingSteps: updated };
                      }
                      return newMessages;
                    });
                  }
                } catch {
                  // Fallback for raw text
                  fullAnswer += chunk;
                }
                fullAnswerRef.current = fullAnswer; // [PERF-4] 每個 token 都同步更新 ref
                // [PERF-4] 用 RAF 批次更新，同一幀(約 16ms)內收到多個 token 時合並為一次 re-render
                if (rafRef.current === null) {
                  rafRef.current = requestAnimationFrame(() => {
                    rafRef.current = null;
                    const latest = fullAnswerRef.current; // 讀取最新內容
                    setMessages(prev => {
                      const newMessages = [...prev];
                      const lastIdx = newMessages.length - 1;
                      if (newMessages[lastIdx].role === 'assistant') {
                        newMessages[lastIdx] = { ...newMessages[lastIdx], content: latest };
                      }
                      return newMessages;
                    });
                  });
                }
              } else if (line.startsWith('event: error')) {
                throw new Error('Server-side error during streaming.');
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('API Error:', error);
      setMessages(prev => {
        const newMessages = [...prev];
        const lastIdx = newMessages.length - 1;
        if (newMessages[lastIdx].role === 'assistant') {
          newMessages[lastIdx] = {
            ...newMessages[lastIdx],
            content: 'Sorry, an error occurred while connecting. Please try again later.',
            isStreaming: false
          };
        }
        return newMessages;
      });
    } finally {
      // [PERF-4] 確保离開時清除殘餘的 RAF
      flushStreamingContent();
      setIsLoading(false);
    }
  };
  const handleClearChat = () => {
    setMessages([]);
    setSelectedTags([]);
    try {
      sessionStorage.removeItem(CHAT_STORAGE_KEY);
      sessionStorage.removeItem(CHAT_SESSION_TOKEN_KEY);
      chatSessionTokenRef.current = '';
      resetServerSessionRef.current = true;
    } catch (e) {
      console.warn('Failed to clear chat history from sessionStorage:', e);
    }
  };
  const handleAddTag = (tag: ScholarshipTag) => {
    setSelectedTags(prev => {
      if (prev.length >= 3) return prev;
      if (prev.some(t => t.scholarship_code === tag.scholarship_code)) return prev;
      return [...prev, tag];
    });
  };
  const handleRemoveTag = (scholarshipCode: string) => {
    setSelectedTags(prev => prev.filter(t => t.scholarship_code !== scholarshipCode));
  };
  const handleFeedback = async (logId: string, feedbackToken: string, type: 'like' | 'dislike' | null) => {
    // Send feedback to backend
    await fetch(`${API_BASE_URL}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log_id: logId, feedback_token: feedbackToken, feedback_type: type })
    }).catch(err => console.error("Error sending feedback:", err));
    if (type === 'dislike') {
      setCurrentFeedbackLogId(logId);
      sessionStorage.setItem(`feedback_token_${logId}`, feedbackToken);
      setIsFeedbackOpen(true);
    }
  };
  const handleFeedbackSubmit = async (feedbackText: string) => {
    if (!currentFeedbackLogId) return;
    const feedbackToken = sessionStorage.getItem(`feedback_token_${currentFeedbackLogId}`);
    if (!feedbackToken) return;
    await fetch(`${API_BASE_URL}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        log_id: currentFeedbackLogId,
        feedback_token: feedbackToken,
        feedback_type: 'dislike',
        feedback_text: feedbackText
      })
    });
    setIsFeedbackOpen(false);
    setCurrentFeedbackLogId(null);
  };
  const isInitialState = messages.length === 0;
  const t = translations[language];

  // Define tour steps — some steps only apply on initial state or chat state
  const tourSteps = useMemo<TourStep[]>(() => {
    const base: TourStep[] = [
      { targetSelector: '.sidebar-nav', i18nKey: 'tour_step_sidebar', position: 'right' },
      { targetSelector: '.input-wrapper', i18nKey: 'tour_step_input', position: 'top' },
      { targetSelector: '.filter-trigger-btn', i18nKey: 'tour_step_filter', position: 'top' },
    ];
    if (isInitialState) {
      base.push({ targetSelector: '.example-questions-container', i18nKey: 'tour_step_examples', position: 'top' });
    }
    base.push({ targetSelector: '.clear-chat-btn', i18nKey: 'tour_step_clear', position: 'bottom' });
    if (!isInitialState) {
      base.push({ targetSelector: '.bot-message-container', i18nKey: 'tour_step_response', position: 'bottom' });
    }
    return base;
  }, [isInitialState]);
  return (
    <Routes>
      <Route path="/admin/*" element={
        <Suspense fallback={<div style={{ padding: '20px', textAlign: 'center', color: '#fff' }}>Loading Admin Panel...</div>}>
          <AdminApp />
        </Suspense>
      } />
      <Route path="*" element={
        <>
          <div id="main-layout" style={{ display: 'flex', height: '100%', width: '100%', overflow: 'hidden' }}>
            <DesktopSidebar
              language={language}
              onLanguageChange={setLanguage}
              theme={theme}
              onThemeChange={setTheme}
              onHelp={() => alert(t.help_alert)}
              onTour={() => setIsTourOpen(true)}
            />
            <div id="chat-side" style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
              {/* Minimal top bar — only trash icon */}
              <div className="top-action-bar">
                <button
                  type="button"
                  className="header-icon-btn clear-chat-btn"
                  onClick={handleClearChat}
                  title={t.clear_chat_button_title || t.clear_chat_button}
                >
                  <Trash2 size={20} strokeWidth={1.5} />
                </button>
              </div>
              {isInitialState ? (
                <div className="hero-container">
                  <div className="hero-title">{t.welcome_title}</div>
                  <ChatInput
                    isLoading={isLoading}
                    onSendMessage={handleSendMessage}
                    language={language}
                    isInitial={true}
                    selectedTags={selectedTags}
                    onRemoveTag={handleRemoveTag}
                    onOpenFilter={() => setIsFilterOpen(true)}
                  />
                  <div className="example-questions-container initial-chips">
                    {[
                      t.example_question_1,
                      // t.example_question_2,
                      t.example_question_3,
                      t.example_question_4,
                      // t.example_question_5,
                      // t.example_question_6,
                      t.example_question_7,
                      t.example_question_8,
                      t.example_question_9,
                      // t.example_question_10,
                      // t.example_question_11,
                      // t.example_question_12
                    ].map((q, idx) => (
                      <div key={idx} className="example-question" onClick={() => handleSendMessage(q)}>
                        {q}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  <MessageList
                    messages={messages}
                    onFeedback={handleFeedback}
                    onChipClick={handleSendMessage}
                    language={language}
                  />
                  <ChatInput
                    isLoading={isLoading}
                    onSendMessage={handleSendMessage}
                    language={language}
                    selectedTags={selectedTags}
                    onRemoveTag={handleRemoveTag}
                    onOpenFilter={() => setIsFilterOpen(true)}
                  />
                </>
              )}
            </div>
          </div>
          <FeedbackModal
            isOpen={isFeedbackOpen}
            onClose={() => setIsFeedbackOpen(false)}
            onSubmit={handleFeedbackSubmit}
            language={language}
          />
          <ScholarshipFilterModal
            isOpen={isFilterOpen}
            onClose={() => setIsFilterOpen(false)}
            onSelectScholarship={handleAddTag}
            selectedTags={selectedTags}
            language={language}
          />
          <OnboardingTour
            isOpen={isTourOpen}
            onClose={() => setIsTourOpen(false)}
            language={language}
            steps={tourSteps}
            translations={t}
          />
        </>
      } />
    </Routes>
  );
}
export default App;
