'use client';
// components/MessageBubble.tsx
import { Message } from '@/lib/api';
import ResearchCard from './ResearchCard';
import VariantGrid from './VariantGrid';
import ChannelSelector from './ChannelSelector';
import FeedbackPanel from './FeedbackPanel';
import { Terminal, Bot } from 'lucide-react';

interface Props {
  message: Message;
}

function renderComponent(message: Message) {
  if (!message.component) return null;

  switch (message.component.type) {
    case 'research':
      return <ResearchCard data={message.component} />;
    case 'variants':
      return <VariantGrid data={message.component} />;
    case 'channel_select':
      return <ChannelSelector data={message.component} />;
    case 'feedback':
      return <FeedbackPanel data={message.component} />;
    default:
      return null;
  }
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex flex-col gap-2 animate-in-fast py-2">
        <div className="flex items-center gap-3 text-neutral-400">
          <Terminal size={14} className="text-emerald-400" />
          <span className="text-xs uppercase tracking-widest font-semibold text-emerald-400/80">Command executed</span>
          <span className="text-xs ml-auto opacity-50 font-mono">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        <div className="text-[15px] font-medium text-white pl-6">
          {message.text}
        </div>
      </div>
    );
  }

  // Assistant response
  const comp = renderComponent(message);
  const hasText = !!message.text;

  return (
    <div className="flex flex-col gap-4 py-4 animate-in-fast border-l-2 border-white/5 pl-5 ml-[7px]">
      <div className="flex items-center gap-2">
        <Bot size={16} className="text-neutral-500" />
        <span className="text-xs font-semibold tracking-wide text-neutral-500 uppercase">System Output</span>
      </div>
      
      {hasText && (
        <div className="text-[15px] text-neutral-200 leading-relaxed font-sans">
          {message.text}
        </div>
      )}

      {comp && <div className="mt-1">{comp}</div>}
    </div>
  );
}
