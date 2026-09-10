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
      if (window.innerWidth >= 900) {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="mp-shell">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[200] focus:top-2 focus:left-2 focus:bg-surface focus:text-ink focus:px-3 focus:py-1.5 focus:border focus:border-line-focus"
      >
        Skip to content
      </a>
      <div className="mp-sidebar-slot">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        />
      </div>

      {mobileMenuOpen && (
        <div className="mp-mobile-nav">
          <div
            className="mp-mobile-nav-backdrop"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="mp-mobile-nav-panel">
            <Sidebar
              collapsed={false}
              onToggle={() => setMobileMenuOpen(false)}
              mobile={true}
              onClose={() => setMobileMenuOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="mp-col">
        <TopBar
          onMenuToggle={() => setMobileMenuOpen(!mobileMenuOpen)}
        />
        <main id="main" className="mp-main">
          {children}
        </main>
        <footer className="mp-footer">
          <span>DATA YAHOO FINANCE · MARKETPULSE v0.3.0</span>
        </footer>
      </div>
      <CommandPalette />
      <KbdHelp />
    </div>
  );
}
