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
import './index.css';

const AdminApp = React.lazy(() => import('./admin/AdminApp').then(module => ({ default: module.AdminApp })));
const CHAT_STORAGE_KEY = 'tcu_scholarship_chat_history';
const SESSION_ID_KEY = 'tcu_session_id';
const USER_ID_KEY = 'tcu_user_id';
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/** 從指定的 Storage 中取得或產生一個新的 UUID */
function getOrCreateId(storage: Storage, key: string): string {
  let id = storage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    storage.setItem(key, id);
  }
  return id;
}
// --- i18n Dictionaries ---
export const translations = {
  zh: {
    welcome_title: "你好！想了解哪些獎助學金？",
    title: "獎助學金問答",
    input_placeholder: "請在這裡輸入您的問題...",
    send_button_title: "Send",
    clear_chat_button: "清除對話",
    help_button: "幫助",
    feedback_title: "提供你的意見",
    feedback_prompt: "請告訴我們這個回答哪裡不符合你的預期，以幫助我們提升服務品質！",
    feedback_placeholder: "例如：答案不正確、資訊不完整、與問題無關...",
    cancel_button: "取消",
    submit_button: "送出",
    initial_bot_message: "你好！我是慈濟大學獎助學金問答助理，請問有什麼可以幫助您的嗎？",
    error_message: "抱歉，連線時發生錯誤，請稍後再試。",
    example_question_1: "提供給五專生原住民的獎助學金有哪些?",
    example_question_2: "申請校內工讀需要具備甚麼條件?",
    example_question_3: "家庭意外補助",
    example_question_4: "低收入可以申請甚麼?",
    example_question_5: "大三下要到海外交流和志工服務, 學校有提供甚麼補助嗎?",
    example_question_6: "學校有提供證照獎勵補助嗎?",
    example_question_7: "就學貸款辦理資訊",
    example_question_8: "碩士班外籍生可以申請獎助學金嗎？",
    example_question_9: "學術論文/期刊發表有甚麼補助?",
    example_question_10: "校外競賽獎勵",
    example_question_11: "大學部原住民可以申請甚麼獎助學金?",
    example_question_12: "弱勢助學",
    reference_title: "來源：",
    unknown_source: "未知來源",
    chat_notice: "AI回答可能會出錯，請查證回覆內容。",
    clear_chat_button_title: "Clear Chat",
    help_button_title: "Help",
    help_alert: "系統問題請聯絡: \n\n校務研究中心 資料庫組\n電話: (03)856-5301 ext.11148\n信箱: chiehyi@gms.tcu.edu.tw",
    homepage_button: "首頁",
    show_more: "顯示全部",
    show_less: "收起",
    filter_title: "獎學金篩選",
    filter_category: "類別",
    filter_tags: "條件",
    filter_all: "全部",
    filter_results: "篩選結果",
    filter_results_unit: "筆",
    filter_max_hint: "已達上限 3 個",
    filter_loading: "載入中...",
    filter_empty: "沒有符合的結果",
    filter_remove_tag: "移除",
    tour_button: "使用說明",
    tour_step_sidebar_title: "📌 側邊選單",
    tour_step_sidebar_desc: "這裡可以前往學務處首頁、切換語言（中/英），以及聯繫系統管理員取得技術支援。",
    tour_step_input_title: "💬 提問輸入框",
    tour_step_input_desc: "在這裡輸入您的問題，按 Enter 或點右側送出按鈕即可發送。支援 Shift + Enter 換行。",
    tour_step_filter_title: "🎯 獎學金篩選",
    tour_step_filter_desc: "點擊 ＋ 按鈕可開啟獎學金篩選器，選擇特定獎學金後系統會更精準地回答相關問題（最多選 3 個）。",
    tour_step_examples_title: "💡 範例問題",
    tour_step_examples_desc: "不知道怎麼問？直接點擊這些預設問題，即可快速開始對話！",
    tour_step_clear_title: "🗑️ 清除對話",
    tour_step_clear_desc: "點擊此按鈕可清除所有聊天記錄，重新開始一段新的對話。",
    tour_step_response_title: "🤖 AI 回答",
    tour_step_response_desc: "AI 回答會顯示在這裡。回答中的 [1][2] 標記可點擊查看引用來源；右側會顯示來源卡片，下方可對回答按讚或回報問題。",
    settings_button: "設定",
    theme_title: "主題",
    theme_system: "預設",
    theme_light: "亮色",
    theme_dark: "暗色"
  },
  en: {
    welcome_title: "Hi! Ask me about scholarships!",
    title: "Scholarship Chat",
    input_placeholder: "Please enter your question here...",
    send_button_title: "Send",
    clear_chat_button: "Clear Chat",
    help_button: "Help",
    feedback_title: "Provide your feedback",
    feedback_prompt: "Please let us know where this answer did not meet your expectations to help us improve our service quality!",
    feedback_placeholder: "For example: The answer is incorrect, the information is incomplete, it is not relevant to the question...",
    cancel_button: "Cancel",
    submit_button: "Submit",
    initial_bot_message: "Hello! I am the Tzu Chi University Scholarship Q&A Assistant. How can I help you?",
    error_message: "Sorry, an error occurred while connecting. Please try again later.",
    example_question_1: "What scholarships are available for aboriginal students in the five-year junior college program?",
    example_question_2: "What are the eligibility requirements for TCU work-study?",
    example_question_3: "Family accident subsidy",
    example_question_4: "What subsidies can low-income households apply for?",
    example_question_5: "I am going on an overseas exchange and volunteer service in the second semester of my junior year. Does the school offer any subsidies?",
    example_question_6: "Does the school offer certification or license incentives?",
    example_question_7: "Student loan application information",
    example_question_8: "Can international students in master's programs apply for scholarships?",
    example_question_9: "What subsidies are available for academic paper/journal publication?",
    example_question_10: "Scholarships for participating in external competitions",
    example_question_11: "What scholarships are available for aboriginal students in the undergraduate level?",
    example_question_12: "Grants for Disadvantaged Students",
    reference_title: "References:",
    unknown_source: "Unknown source",
    chat_notice: "AI chat may produce errors, please verify the responses.",
    clear_chat_button_title: "Clear Chat",
    help_button_title: "Help",
    help_alert: "For system issues, please contact:\n\nInstitutional Research Office, Database Division\nTel: (03)856-5301 ext.11148\nEmail: chiehyi@gms.tcu.edu.tw",
    homepage_button: "Homepage",
    show_more: "Show all",
    show_less: "Show less",
    filter_title: "Scholarship Filter",
    filter_category: "Category",
    filter_tags: "Category",
    filter_all: "All",
    filter_results: "Results",
    filter_results_unit: "items",
    filter_max_hint: "Max 3 reached",
    filter_loading: "Loading...",
    filter_empty: "No matching results",
    filter_remove_tag: "Remove",
    tour_button: "User Guide",
    tour_step_sidebar_title: "📌 Sidebar Menu",
    tour_step_sidebar_desc: "Navigate to the Student Affairs homepage, switch between Chinese and English, or contact the system administrator for support.",
    tour_step_input_title: "💬 Chat Input",
    tour_step_input_desc: "Type your question here and press Enter or click the send button. Use Shift + Enter for a new line.",
    tour_step_filter_title: "🎯 Scholarship Filter",
    tour_step_filter_desc: "Click the + button to open the scholarship filter. Select specific scholarships so the system can answer related questions more accurately (max 3).",
    tour_step_examples_title: "💡 Example Questions",
    tour_step_examples_desc: "Not sure what to ask? Click one of these preset questions to start a conversation right away!",
    tour_step_clear_title: "🗑️ Clear Chat",
    tour_step_clear_desc: "Click this button to clear all chat history and start a fresh conversation.",
    tour_step_response_title: "🤖 AI Response",
    tour_step_response_desc: "AI responses appear here. Inline [1][2] markers are clickable to view citation sources; source cards are shown on the right side. You can also like or report answers below each response.",
    settings_button: "Settings",
    theme_title: "Theme",
    theme_system: "System",
    theme_light: "Light",
    theme_dark: "Dark"
  }
};
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
  const sessionId = useRef(getOrCreateId(sessionStorage, SESSION_ID_KEY)).current;
  const userId = useRef(getOrCreateId(localStorage, USER_ID_KEY)).current;
  // [PERF-4] RAF handle 用於批次更新串流內容，避免每個 token 就觸發一次 re-render
  const rafRef = useRef<number | null>(null);
  const fullAnswerRef = useRef<string>(''); // 持綌最新的 fullAnswer，供 RAF closure 使用
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
    const newMessage = { role: 'user', content: text } as Message;
    setMessages(prev => [...prev, newMessage]);
    setIsLoading(true);
    // Prepare history payload for API
    const history = messages.map(msg => ({ role: msg.role, content: msg.content }));
    history.push({ role: 'user', content: text });
    // Add empty placeholder for bot streaming
    setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: text,
          history,
          lang: language,
          title_filter: selectedTags.length > 0 ? selectedTags.map(t => t.title) : null,
          session_id: sessionId,
          user_id: userId,
        })
      });
      if (!response.ok) {
        throw new Error('Network response was not ok');
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
                // [PERF-4] 尾區到達前先沖溅剩餘的 RAF
                if (rafRef.current !== null) {
                  cancelAnimationFrame(rafRef.current);
                  rafRef.current = null;
                }
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
                  }
                } catch (e) {
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
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      setIsLoading(false);
    }
  };
  const handleClearChat = () => {
    setMessages([]);
    setSelectedTags([]);  // Clear tags when clearing chat
    try {
      sessionStorage.removeItem(CHAT_STORAGE_KEY);
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
  const handleFeedback = async (logId: string, type: 'like' | 'dislike' | null) => {
    // Send feedback to backend
    await fetch(`${API_BASE_URL}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log_id: logId, feedback_type: type })
    }).catch(err => console.error("Error sending feedback:", err));
    if (type === 'dislike') {
      setCurrentFeedbackLogId(logId);
      setIsFeedbackOpen(true);
    }
  };
  const handleFeedbackSubmit = async (feedbackText: string) => {
    if (!currentFeedbackLogId) return;
    await fetch(`${API_BASE_URL}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        log_id: currentFeedbackLogId,
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