import React from 'react';
import { Language } from '../types';
import { translations } from '../App';

interface ChatHeaderProps {
  language: Language;
  onLanguageChange: (lang: Language) => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ language, onLanguageChange }) => {
  const t = translations[language];

  return (
    <div className="chat-header">
      <div className="chat-header-content">
        <div className="header-logo-title-wrap">
          <img src="/school_logo.png" alt="School Logo" className="header-logo" />
          <h1 className="chat-title">{t.title}</h1>
        </div>
        <div className="language-switcher-container">
          <label htmlFor="language-switcher">Language:</label>
          <select 
            id="language-switcher" 
            value={language} 
            onChange={(e) => onLanguageChange(e.target.value as Language)}
          >
            <option value="zh">繁體中文</option>
            <option value="en">English</option>
          </select>
        </div>
      </div>
    </div>
  );
};
