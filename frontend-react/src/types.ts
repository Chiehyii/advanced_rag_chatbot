export interface Context {
  source_file?: string;
  source_url?: string;
  text?: string;
  score?: number;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  contexts?: Context[];
  logId?: string;
  chips?: string[];
  isStreaming?: boolean;
}

export type Language = 'zh' | 'en';
