import React, { useState } from 'react';
import { Globe, HelpCircle, ChevronRight, Menu, X, ExternalLink } from 'lucide-react';
import { Language } from '../types';
import { translations } from '../App';

interface DesktopSidebarProps {
  language: Language;
  onLanguageChange: (lang: Language) => void;
  onHelp: () => void;
}

const SidebarContent: React.FC<DesktopSidebarProps & { onClose?: () => void }> = ({
  language, onLanguageChange, onHelp, onClose
}) => {
  const [langOpen, setLangOpen] = useState(false);
  const t = translations[language];

  return (
    <>
      {/* Logo + Title */}
      <div className="sidebar-logo-wrap">
        <img src="/school_logo.png" alt="School Logo" className="sidebar-logo" />
        <span className="sidebar-app-title">{t.title}</span>
      </div>

      <nav className="sidebar-nav">
        {/* Source Link */}
        <button
          type="button"
          className="sidebar-nav-item"
          onClick={() => { window.open('https://yizhu.tcu.edu.tw/', '_blank'); if (onClose) onClose(); }}
          title={(t as any).homepage_button || '首頁'}
        >
          <ExternalLink size={20} strokeWidth={1.5} />
          <span className="sidebar-nav-label">{(t as any).homepage_button || '首頁'}</span>
        </button>

        {/* Language switcher */}
        <div className="sidebar-nav-item-wrap">
          <button
            type="button"
            className="sidebar-nav-item"
            onClick={() => setLangOpen(prev => !prev)}
            title="Language"
          >
            <Globe size={20} strokeWidth={1.5} />
            <span className="sidebar-nav-label">Language</span>
            <ChevronRight size={14} strokeWidth={1.5} className={`sidebar-chevron ${langOpen ? 'open' : ''}`} />
          </button>
          {langOpen && (
            <div className="sidebar-sub-menu">
              {(['zh', 'en'] as Language[]).map(lang => (
                <button
                  key={lang}
                  type="button"
                  className={`sidebar-sub-item ${language === lang ? 'active' : ''}`}
                  onClick={() => { onLanguageChange(lang); setLangOpen(false); if (onClose) onClose(); }}
                >
                  {lang === 'zh' ? '繁體中文' : 'English'}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Help */}
        <button
          type="button"
          className="sidebar-nav-item"
          onClick={() => { onHelp(); if (onClose) onClose(); }}
          title={t.help_button}
        >
          <HelpCircle size={20} strokeWidth={1.5} />
          <span className="sidebar-nav-label">{t.help_button}</span>
        </button>
      </nav>
    </>
  );
};

export const DesktopSidebar: React.FC<DesktopSidebarProps> = (props) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="desktop-sidebar">
        <SidebarContent {...props} />
      </aside>

      {/* Mobile hamburger button (top-left floating) */}
      <button
        type="button"
        className="mobile-hamburger-btn"
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <Menu size={22} strokeWidth={1.5} />
      </button>

      {/* Mobile side menu overlay */}
      {mobileOpen && (
        <div className="mobile-side-menu-overlay" onClick={() => setMobileOpen(false)}>
          <div className="mobile-side-menu" onClick={e => e.stopPropagation()}>
            <div className="mobile-side-menu-close-row">
              <button
                type="button"
                className="header-icon-btn close-menu-btn"
                onClick={() => setMobileOpen(false)}
              >
                <X size={24} strokeWidth={1.5} />
              </button>
            </div>
            <SidebarContent {...props} onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
};
