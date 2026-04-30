import React, { useState } from 'react';
import { Globe, HelpCircle, ChevronRight, Menu, X, ExternalLink, BookOpen, Settings, Moon, Sun, Monitor } from 'lucide-react';
import { Language, Theme } from '../types';
import { translations } from '../App';

interface DesktopSidebarProps {
  language: Language;
  onLanguageChange: (lang: Language) => void;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  onHelp: () => void;
  onTour: () => void;
}

const SidebarContent: React.FC<DesktopSidebarProps & { onClose?: () => void }> = ({
  language, onLanguageChange, theme, onThemeChange, onHelp, onTour, onClose
}) => {
  const [settingsOpen, setSettingsOpen] = useState(false);
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

        {/* Settings switcher */}
        <div className="sidebar-nav-item-wrap">
          <button
            type="button"
            className="sidebar-nav-item"
            onClick={() => setSettingsOpen(prev => !prev)}
            title={(t as any).settings_button || 'Settings'}
          >
            <Settings size={20} strokeWidth={1.5} />
            <span className="sidebar-nav-label">{(t as any).settings_button || 'Settings'}</span>
            <ChevronRight size={14} strokeWidth={1.5} className={`sidebar-chevron ${settingsOpen ? 'open' : ''}`} />
          </button>
          {settingsOpen && (
            <div className="sidebar-sub-menu">
              {/* Language Section */}
              <div className="sidebar-sub-menu-section">
                <div className="sidebar-sub-menu-title">
                  <Globe size={14} /> <span>Language</span>
                </div>
                {(['zh', 'en'] as Language[]).map(lang => (
                  <button
                    key={lang}
                    type="button"
                    className={`sidebar-sub-item ${language === lang ? 'active' : ''}`}
                    onClick={() => { onLanguageChange(lang); setSettingsOpen(false); if (onClose) onClose(); }}
                  >
                    {lang === 'zh' ? '繁體中文' : 'English'}
                  </button>
                ))}
              </div>
              
              {/* Theme Section */}
              <div className="sidebar-sub-menu-section">
                <div className="sidebar-sub-menu-title">
                  <Monitor size={14} /> <span>{(t as any).theme_title || 'Theme'}</span>
                </div>
                {(['system', 'light', 'dark'] as Theme[]).map(th => {
                  const Icon = th === 'dark' ? Moon : (th === 'light' ? Sun : Monitor);
                  const label = th === 'dark' ? ((t as any).theme_dark || 'Dark') : 
                                th === 'light' ? ((t as any).theme_light || 'Light') : 
                                ((t as any).theme_system || 'System');
                  return (
                    <button
                      key={th}
                      type="button"
                      className={`sidebar-sub-item ${theme === th ? 'active' : ''}`}
                      onClick={() => { onThemeChange(th); setSettingsOpen(false); if (onClose) onClose(); }}
                    >
                      <Icon size={14} style={{ marginRight: '6px' }} />
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* User Guide / Tour */}
        <button
          type="button"
          className="sidebar-nav-item"
          onClick={() => { onTour(); if (onClose) onClose(); }}
          title={(t as any).tour_button || '使用說明'}
        >
          <BookOpen size={20} strokeWidth={1.5} />
          <span className="sidebar-nav-label">{(t as any).tour_button || '使用說明'}</span>
        </button>

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
