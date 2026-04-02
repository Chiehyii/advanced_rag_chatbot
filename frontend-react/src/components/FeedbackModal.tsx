import React, { useState } from 'react';
import { Language } from '../types';
import { translations } from '../App';

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (feedbackText: string) => void;
  language: Language;
}

export const FeedbackModal: React.FC<FeedbackModalProps> = ({ isOpen, onClose, onSubmit, language }) => {
  const [text, setText] = useState('');
  const t = translations[language];

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(text);
    setText('');
  };

  return (
    <>
      <div id="feedback-backdrop" style={{ display: 'block' }} onClick={onClose}></div>
      <div id="feedback-modal" style={{ display: 'block' }}>
        <h3>{t.feedback_title}</h3>
        <p>{t.feedback_prompt}</p>
        <form id="feedback-form" onSubmit={handleSubmit}>
          <textarea
            id="feedback-textarea"
            placeholder={t.feedback_placeholder}
            required
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div style={{ textAlign: 'right' }}>
            <button type="button" id="feedback-text-btn" onClick={onClose}>{t.cancel_button}</button>
            <button type="submit" id="feedback-text-btn">{t.submit_button}</button>
          </div>
        </form>
      </div>
    </>
  );
};
