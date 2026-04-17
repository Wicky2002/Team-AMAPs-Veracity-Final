'use client';
// components/LoadingSpinner.tsx
import { Loader2 } from 'lucide-react';

export default function LoadingSpinner() {
  return (
    <div className="flex items-center gap-3 text-neutral-500 py-2 border-l-2 border-white/5 pl-5 ml-[7px]">
      <Loader2 size={16} className="animate-spin" />
      <span className="text-sm font-medium tracking-wide">Agents analyzing...</span>
    </div>
  );
}
