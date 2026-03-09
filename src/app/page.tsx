'use client';

import { useSession } from 'next-auth/react';
import Login from '@/components/Login';
import Dashboard from '@/components/Dashboard';

export default function Home() {
  const { status } = useSession();

  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <div className="h-12 w-12 border-4 border-[#333] border-t-[#00ff41] rounded-full animate-spin" />
          <p className="text-[#00ff41] text-sm tracking-widest uppercase font-mono">Initializing...</p>
        </div>
      </div>
    );
  }

  if (status === 'authenticated') {
    return <Dashboard />;
  }

  return <Login />;
}
