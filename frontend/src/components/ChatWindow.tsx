'use client';
// components/ChatWindow.tsx — main shell with sidebar + session management
import { useState, useRef, useEffect, useCallback } from 'react';
import { Message, AgentResponse, postMessage } from '@/lib/api';
import MessageBubble from './MessageBubble';
import LoadingSpinner from './LoadingSpinner';
import Sidebar, { ChatSession } from './Sidebar';
import { Send, Sparkles } from 'lucide-react';

function makeId() {
  return Math.random().toString(36).slice(2);
}

const SUGGESTED_PROMPTS = [
  'Research market signals for Vector Agents',
  'Generate outreach emails for Lilian AI SDR',
  'Compare channels for outbound campaign',
];

function firstLine(text: string) {
  return text.split('\n')[0].slice(0, 60) || 'New session';
}

// ─── Types ──────────────────────────────────────────────────────────────────

interface Session {
  id: string;
  title: string;
  preview: string;
  timestamp: Date;
  messages: Message[];
}

function emptySession(): Session {
  return {
    id: makeId(),
    title: 'New session',
    preview: '',
    timestamp: new Date(),
    messages: [
      {
        id: 'welcome',
        role: 'assistant',
        text: 'Intelligence system online. Waiting for command...',
        timestamp: new Date(),
      },
    ],
  };
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function ChatWindow() {
  const [sessions, setSessions] = useState<Session[]>([emptySession()]);
  const [activeId, setActiveId] = useState<string>(sessions[0].id);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Current session derived state
  const activeSession = sessions.find((s) => s.id === activeId) ?? sessions[0];
  const messages = activeSession.messages;

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, scrollToBottom]);

  // ── Session helpers ──────────────────────────────────────────────────────

  function updateSession(id: string, patch: Partial<Session>) {
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, ...patch } : s))
    );
  }

  function handleNewSession() {
    const s = emptySession();
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setInput('');
    setIsLoading(false);
  }

  function handleDeleteSession(id: string) {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      if (next.length === 0) {
        const fresh = emptySession();
        return [fresh];
      }
      return next;
    });
    // Switch to another session if we deleted the active one
    if (id === activeId) {
      setSessions((prev) => {
        const remaining = prev.filter((s) => s.id !== id);
        if (remaining.length > 0) setActiveId(remaining[0].id);
        return prev; // actual filtering already done above
      });
      // After the delete above, sessions will have been updated; pick first remaining
      setActiveId((prev) => {
        const remaining = sessions.filter((s) => s.id !== id);
        return remaining.length > 0 ? remaining[0].id : emptySession().id;
      });
    }
  }

  function handleSelectSession(id: string) {
    setActiveId(id);
    setInput('');
    setIsLoading(false);
  }

  // ── Send message ─────────────────────────────────────────────────────────

  async function sendMessage(text: string = input) {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    setInput('');

    const userMsg: Message = {
      id: makeId(),
      role: 'user',
      text: trimmed,
      timestamp: new Date(),
    };

    const currentMessages = activeSession.messages;
    const updatedMessages = [...currentMessages, userMsg];

    // Update title from first user message
    const isFirstUserMsg = !currentMessages.some((m) => m.role === 'user');

    updateSession(activeId, {
      messages: updatedMessages,
      title: isFirstUserMsg ? firstLine(trimmed) : activeSession.title,
      preview: trimmed.slice(0, 50),
      timestamp: new Date(),
    });

    setIsLoading(true);

    try {
      const response: AgentResponse = await postMessage(trimmed, updatedMessages);

      const assistantMsg: Message = {
        id: makeId(),
        role: 'assistant',
        text: response.type === 'text' ? response.content : undefined,
        component: response.type !== 'text' ? response : undefined,
        timestamp: new Date(),
      };

      updateSession(activeId, {
        messages: [...updatedMessages, assistantMsg],
      });
    } catch (err) {
      updateSession(activeId, {
        messages: [
          ...updatedMessages,
          {
            id: makeId(),
            role: 'assistant',
            text: `Error: ${err instanceof Error ? err.message : 'Communication failed.'}`,
            timestamp: new Date(),
          },
        ],
      });
    } finally {
      setIsLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }

  function handleKeyPress(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // Sidebar shape
  const sidebarSessions: ChatSession[] = sessions.map((s) => ({
    id: s.id,
    title: s.title,
    preview: s.preview,
    timestamp: s.timestamp,
  }));

  const showSuggestions = messages.length === 1 && !isLoading;

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen overflow-hidden">

      {/* ── Sidebar ── */}
      <Sidebar
        sessions={sidebarSessions}
        activeId={activeId}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
        onDelete={handleDeleteSession}
      />

      {/* ── Main area ── */}
      <div className="flex-1 flex flex-col min-w-0 relative">

        {/* Ambient glow */}
        <div className="absolute top-[-10%] left-[20%] w-[600px] h-[500px] bg-emerald-500/5 blur-[120px] rounded-full pointer-events-none" />

        {/* Header */}
        <header className="glass-header px-6 py-4 flex items-center justify-between z-10 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded bg-white flex items-center justify-center">
              <span className="text-black font-bold text-xs">Vx</span>
            </div>
            <h1 className="text-sm font-semibold tracking-wide text-white truncate max-w-[200px] sm:max-w-none">
              {activeSession.title === 'New session' ? 'Veracity Workspace' : activeSession.title}
            </h1>
          </div>

          <div className="hidden sm:flex gap-4 text-xs font-mono text-neutral-500 border border-white/5 rounded-md px-3 py-1.5 bg-neutral-900/50">
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" /> Connected
            </span>
            <span className="flex items-center gap-1.5 border-l border-white/10 pl-4">
              <span className="w-1.5 h-1.5 bg-blue-500 rounded-full" /> Signals Active
            </span>
          </div>
        </header>

        {/* Message feed */}
        <div className="flex-1 overflow-y-auto z-0 relative pb-36">
          <div className="max-w-3xl mx-auto px-6 pt-12 flex flex-col gap-8">

            {showSuggestions && (
              <div className="animate-in mb-8">
                <h2 className="text-2xl font-light text-gradient mb-8 tracking-tight">
                  What shall we orchestrate today?
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {SUGGESTED_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => sendMessage(prompt)}
                      className="panel panel-hover p-4 rounded-xl text-left flex flex-col gap-3 group transition-all duration-300"
                    >
                      <Sparkles size={16} className="text-neutral-500 group-hover:text-white transition-colors" />
                      <span className="text-sm text-neutral-400 group-hover:text-white leading-snug">
                        {prompt}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-col gap-6">
              {messages.map((msg, i) => (
                <MessageBubble key={msg.id || i} message={msg} />
              ))}
              {isLoading && <div className="pt-2"><LoadingSpinner /></div>}
            </div>
            <div ref={bottomRef} className="h-8" />
          </div>
        </div>

        {/* Floating input */}
        <div className="absolute bottom-6 left-0 right-0 z-20 px-6">
          <div className="max-w-3xl mx-auto">
            <div className="panel p-2 rounded-2xl flex items-end gap-2 focus-within:border-white/20 transition-all">
              <textarea
                ref={inputRef}
                rows={1}
                className="flex-1 bg-transparent border-none text-[15px] text-white placeholder-neutral-500 outline-none resize-none leading-relaxed px-4 py-3 max-h-[200px]"
                placeholder="Enter instructions or query signals..."
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = 'auto';
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
                }}
                onKeyDown={handleKeyPress}
                disabled={isLoading}
              />
              <button
                id="send-btn"
                onClick={() => sendMessage()}
                disabled={!input.trim() || isLoading}
                className="mb-1 mr-1 w-10 h-10 rounded-xl bg-white text-black flex items-center justify-center hover:bg-neutral-200 disabled:opacity-20 disabled:hover:bg-white transition-all shrink-0"
                aria-label="Send"
              >
                <Send size={16} strokeWidth={2.5} />
              </button>
            </div>
            <p className="text-center mt-2 text-[11px] font-mono text-neutral-600">
              Powered by Multi-Agent Operations
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
