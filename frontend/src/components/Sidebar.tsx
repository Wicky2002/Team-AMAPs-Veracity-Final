'use client';
// components/Sidebar.tsx — chat history sidebar
import { PlusIcon, MessageSquare, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';

export interface ChatSession {
  id: string;
  title: string;
  preview: string;
  timestamp: Date;
}

interface Props {
  sessions: ChatSession[];
  activeId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

function timeLabel(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function Sidebar({
  sessions,
  activeId,
  collapsed,
  onToggle,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  return (
    <aside
      className={`
        relative flex-shrink-0 flex flex-col h-full
        border-r border-white/5 bg-[#0D0D0D]
        transition-all duration-300 ease-in-out
        ${collapsed ? 'w-14' : 'w-60'}
      `}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between h-14 px-3 border-b border-white/5 flex-shrink-0">
        {!collapsed && (
          <span className="text-[11px] font-semibold tracking-widest text-neutral-500 uppercase">
            History
          </span>
        )}
        <button
          onClick={onNew}
          title="New session"
          className={`
            flex items-center justify-center rounded-lg
            w-8 h-8 border border-white/8 bg-white/[0.03]
            hover:bg-white/[0.07] hover:border-white/15
            text-neutral-400 hover:text-white transition-all
            ${collapsed ? 'mx-auto' : ''}
          `}
        >
          <PlusIcon size={15} strokeWidth={2} />
        </button>
      </div>

      {/* Session list */}
      <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-1">
        {sessions.length === 0 && !collapsed && (
          <div className="px-2 py-8 text-center">
            <MessageSquare size={20} className="mx-auto text-neutral-700 mb-2" />
            <p className="text-[11px] text-neutral-600">No sessions yet</p>
          </div>
        )}

        {sessions.map((s) => {
          const isActive = s.id === activeId;
          return (
            <div
              key={s.id}
              className={`
                group flex items-center gap-2 rounded-lg cursor-pointer
                transition-all duration-150 relative
                ${isActive
                  ? 'bg-white/[0.07] border border-white/10'
                  : 'hover:bg-white/[0.04] border border-transparent'}
                ${collapsed ? 'justify-center p-2' : 'px-3 py-2.5'}
              `}
              onClick={() => onSelect(s.id)}
              title={collapsed ? s.title : undefined}
            >
              {/* Icon */}
              <MessageSquare
                size={14}
                className={`flex-shrink-0 ${isActive ? 'text-white' : 'text-neutral-500 group-hover:text-neutral-300'}`}
              />

              {!collapsed && (
                <>
                  <div className="flex-1 min-w-0">
                    <p className={`text-[13px] font-medium truncate ${isActive ? 'text-white' : 'text-neutral-400 group-hover:text-neutral-200'}`}>
                      {s.title}
                    </p>
                    <p className="text-[11px] text-neutral-600 truncate mt-0.5">
                      {s.preview}
                    </p>
                  </div>

                  {/* Time + delete */}
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    <span className="text-[10px] text-neutral-600">
                      {timeLabel(s.timestamp)}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-neutral-600 hover:text-red-400"
                      title="Delete"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </nav>

      {/* Collapse toggle at bottom */}
      <div className="flex-shrink-0 border-t border-white/5 p-2">
        <button
          onClick={onToggle}
          className="w-full flex items-center justify-center h-8 rounded-lg text-neutral-600 hover:text-neutral-300 hover:bg-white/[0.04] transition-all"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
    </aside>
  );
}
