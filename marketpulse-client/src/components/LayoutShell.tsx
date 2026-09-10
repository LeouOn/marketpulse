'use client';

import { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { CommandPalette } from './CommandPalette';
import { KbdHelp } from './KbdHelp';

interface LayoutShellProps {
  children: React.ReactNode;
}

export function LayoutShell({ children }: LayoutShellProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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
    <div className="flex h-screen bg-canvas text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[200] focus:top-2 focus:left-2 focus:bg-surface focus:text-ink focus:px-3 focus:py-1.5 focus:border focus:border-line-focus"
      >
        Skip to content
      </a>
      <div className="hidden lg:block">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        />
      </div>

      {mobileMenuOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-canvas/80"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-[180px] z-10">
            <Sidebar
              collapsed={false}
              onToggle={() => setMobileMenuOpen(false)}
              mobile={true}
              onClose={() => setMobileMenuOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
        <TopBar
          onMenuToggle={() => setMobileMenuOpen(!mobileMenuOpen)}
        />
        <main id="main" className="flex-1 min-h-0 overflow-y-auto bg-canvas">
          {children}
        </main>
        <footer className="h-6 text-[10px] font-mono text-ink-muted border-t border-line-subtle flex items-center px-3 gap-2 shrink-0">
          <span>DATA YAHOO FINANCE · MARKETPULSE v0.3.0</span>
        </footer>
      </div>
      <CommandPalette />
      <KbdHelp />
    </div>
  );
}
