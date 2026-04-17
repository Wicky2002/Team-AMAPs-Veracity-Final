// app/page.tsx — entry point: mounts <ChatWindow>
import type { Metadata } from 'next';
import ChatWindow from '@/components/ChatWindow';

export const metadata: Metadata = {
  title: 'Veracity — Signal to Action',
  description:
    'AI-powered multi-agent marketing intelligence: research signals, generate outreach, close the feedback loop — all in one chat.',
};

export default function Home() {
  return <ChatWindow />;
}
