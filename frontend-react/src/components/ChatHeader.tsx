import React, { useState } from 'react';
import { Language } from '../types';
import { translations } from '../App';
import { Trash2, Menu, X, HelpCircle, Globe } from 'lucide-react';

interface ChatHeaderProps {
  language: Language;
  onLanguageChange: (lang: Language) => void;
  onClearChat: () => void;
  onHelp: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ language, onLanguageChange, onClearChat, onHelp }) => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const t = translations[language];

  return (
    <>
      <div className="chat-header">
        <div className="chat-header-content">
          {/* Mobile Menu Button — left side, mobile only */}
          <button type="button" className="header-icon-btn mobile-menu-btn" onClick={() => setIsMenuOpen(true)}>
            <Menu size={24} />
          </button>

          {/* Logo + Title — hidden on mobile */}
          <div className="header-logo-title-wrap">
            <img src="/school_logo.png" alt="School Logo" className="header-logo" />
            <h1 className="chat-title">{t.title}</h1>
          </div>

          {/* Right side actions */}
          <div className="header-actions">
            {/* Globe language switcher — desktop only */}
            <div className="header-lang-wrap desktop-actions">
              <button
                type="button"
                className="header-icon-btn"
                onClick={() => setLangOpen(prev => !prev)}
                title="Language"
              >
                <Globe size={20} />
              </button>
              {langOpen && (
                <div className="header-lang-dropdown">
                  {(['zh', 'en'] as Language[]).map(lang => (
                    <button
                      key={lang}
                      type="button"
                      className={`lang-option ${language === lang ? 'active' : ''}`}
                      onClick={() => { onLanguageChange(lang); setLangOpen(false); }}
                    >
                      {lang === 'zh' ? '繁體中文' : 'English'}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Help button — desktop only */}
            <button type="button" className="header-text-btn help-btn desktop-actions" onClick={onHelp} title={t.help_button_title || t.help_button}>
              {t.help_button}
            </button>

            {/* Clear Chat Icon - visible everywhere */}
            <button
              type="button"
              className="header-icon-btn clear-chat-btn"
              onClick={onClearChat}
              title={t.clear_chat_button_title || t.clear_chat_button}
            >
              <Trash2 size={20} strokeWidth={1.5} />
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Side Menu — slides from left */}
      {isMenuOpen && (
        <div className="mobile-side-menu-overlay" onClick={() => setIsMenuOpen(false)}>
          <div className="mobile-side-menu" onClick={e => e.stopPropagation()}>
            <div className="mobile-side-menu-header">
              <div className="menu-logo-title-wrap">
                <img src="/school_logo.png" alt="School Logo" className="menu-logo" />
                <span className="menu-title">{t.title}</span>
              </div>
              <button type="button" className="header-icon-btn close-menu-btn" onClick={() => setIsMenuOpen(false)}>
                <X size={24} />
              </button>
            </div>
            <div className="mobile-side-menu-content">
              <div className="menu-item language-switcher-menu">
                <Globe size={18} />
                <label htmlFor="mobile-language-switcher">Language</label>
                <select
                  id="mobile-language-switcher"
                  value={language}
                  onChange={(e) => {
                    onLanguageChange(e.target.value as Language);
                    setIsMenuOpen(false);
                  }}
                >
                  <option value="zh">繁體中文</option>
                  <option value="en">English</option>
                </select>
              </div>
              <button type="button" className="menu-item help-menu-btn" onClick={() => { onHelp(); setIsMenuOpen(false); }}>
                <HelpCircle size={18} />
                <span>{t.help_button}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
