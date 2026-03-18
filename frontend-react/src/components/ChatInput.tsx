import React, { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';
import { Language } from '../types';
import { translations } from '../App';

interface ChatInputProps {
  onSendMessage: (text: string) => void;
  onClearChat: () => void;
  onHelp: () => void;
  isLoading: boolean;
  language: Language;
  isInitial?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, onClearChat, onHelp, isLoading, language, isInitial }) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const t = translations[language];

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      // Max height set to 150px
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  const submitMessage = () => {
    if (input.trim() && !isLoading) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitMessage();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitMessage();
    }
  };

  return (
    <div id="input-area" className={isInitial ? 'initial' : ''}>
      <form id="input-form" onSubmit={handleSubmit}>
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            id="user-input"
            placeholder={t.input_placeholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
          <div className="input-bottom-row">
            <button type="submit" id="send-button" title={t.send_button_title} disabled={isLoading || !input.trim()}>
              <Send size={20} />
            </button>
          </div>
        </div>
        <div className="chat-notice">{t.chat_notice}</div>
        <div className="utility-buttons">
          <button type="button" id="clear-button" title={t.clear_chat_button_title || t.clear_chat_button} onClick={onClearChat}>
             {t.clear_chat_button}
          </button>
          <button type="button" id="help-button" title={t.help_button_title || t.help_button} onClick={() => {
            alert(t.help_alert);
            onHelp();
          }}>
             {t.help_button}
          </button>
        </div>
      </form>
    </div>
  );
};
