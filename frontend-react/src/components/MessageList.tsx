import React, { useEffect, useRef } from 'react';
import { Message, Language } from '../types';
import { MessageBubble } from './MessageBubble';

interface MessageListProps {
  messages: Message[];
  onFeedback: (logId: string, type: 'like' | 'dislike' | null) => void;
  onChipClick: (text: string) => void;
  language: Language;
}

export const MessageList: React.FC<MessageListProps> = ({ messages, onFeedback, onChipClick, language }) => {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div id="chat-popup" ref={listRef}>
      <div id="chat-container">
        <div id="message-window">
          {messages.map((msg, index) => (
            <MessageBubble 
              key={index} 
              message={msg} 
              onFeedback={onFeedback} 
              onChipClick={onChipClick}
              language={language}
            />
          ))}
        </div>
      </div>
    </div>
  );
};
