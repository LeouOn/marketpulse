'use client';

import { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

interface LayoutShellProps {
  children: React.ReactNode;
}

export function LayoutShell({ children }: LayoutShellProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="flex h-screen bg-gray-950 text-white">
      <div className="hidden lg:block">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        />
      </div>

      {mobileMenuOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-64">
            <Sidebar
              collapsed={false}
              onToggle={() => setMobileMenuOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar
          onMenuToggle={() => setMobileMenuOpen(!mobileMenuOpen)}
          isConnected={true}
          lastUpdate={null}
        />
        <main className="flex-1 overflow-auto p-4 lg:p-6">
          {children}
        </main>
        <footer className="h-8 bg-gray-900 border-t border-gray-800 px-4 flex items-center justify-between text-xs text-gray-500 shrink-0">
          <span>Data: Yahoo Finance</span>
          <span>v0.3.0</span>
        </footer>
      </div>
    </div>
  );
}
