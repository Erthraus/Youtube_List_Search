'use client';

import { signIn } from 'next-auth/react';
import { Youtube } from 'lucide-react';

export default function Login() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4">
      <div className="max-w-md w-full relative">
        <div className="absolute inset-0 bg-[#00ff41] blur-[100px] opacity-20 pointer-events-none rounded-full" />
        
        <div className="bg-[#111111] border border-[#333333] rounded-2xl p-8 relative z-10 shadow-2xl overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-[#00ff41] to-transparent" />
          
          <div className="flex flex-col items-center text-center space-y-6">
            <div className="h-16 w-16 bg-[#1a1a1a] rounded-xl flex items-center justify-center border border-[#333333] shadow-[0_0_15px_rgba(0,255,65,0.15)]">
              <Youtube className="w-8 h-8 text-[#00ff41]" />
            </div>
            
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">System Access Required</h1>
              <p className="text-[#a1a1aa] mt-2 text-sm">Secure connection to YouTube properties is not established.</p>
            </div>
            
            <div className="w-full pt-4">
              <button 
                onClick={() => signIn('google')}
                className="w-full relative group overflow-hidden bg-[#00ff41] text-black font-semibold py-3 px-4 rounded-lg transition-all hover:shadow-[0_0_20px_rgba(0,255,65,0.4)]"
              >
                <span className="relative z-10 flex items-center justify-center gap-2 tracking-wide uppercase text-sm">
                  [ Initiate Connection Sequence ]
                </span>
                <div className="absolute inset-0 h-full w-full scale-0 rounded-lg transition-all duration-300 group-hover:scale-100 group-hover:bg-white/20 z-0" />
              </button>
            </div>
            
            <div className="text-xs text-[#555555] mt-4">
              Requires OAuth 2.0 provisioning over isolated gateway protocols.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
