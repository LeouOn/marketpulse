'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Flame, BarChart3, Bell, Settings, ChevronLeft, ChevronRight, X, TrendingUp, FlaskConical } from 'lucide-react';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  mobile?: boolean;
  onClose?: () => void;
}

const navItems = [
  { href: '/', icon: LayoutDashboard, label: 'Dashboard', matchExact: true },
  { href: '/trending', icon: Flame, label: 'Trending' },
  { href: '/chart/SPY', icon: BarChart3, label: 'Charts', matchPrefix: '/chart' },
  { href: '/symbol/SPY', icon: TrendingUp, label: 'Symbol', matchPrefix: '/symbol' },
  { href: '/research', icon: FlaskConical, label: 'Research', matchPrefix: '/research' },
  { href: '/alerts', icon: Bell, label: 'Alerts', disabled: true },
  { href: '/settings', icon: Settings, label: 'Settings', disabled: true },
];

export function Sidebar({ collapsed, onToggle, mobile, onClose }: SidebarProps) {
  const pathname = usePathname();

  function isActive(item: typeof navItems[0]): boolean {
    if (item.disabled) return false;
    if (item.matchExact) return pathname === item.href;
    if (item.matchPrefix) return pathname.startsWith(item.matchPrefix);
    return pathname === item.href || pathname.startsWith(item.href + '/');
  }

  return (
    <nav
      className={`bg-surface border-r border-line-subtle h-full flex flex-col transition-all duration-200 ${
        collapsed && !mobile ? 'w-12' : 'w-[180px]'
      }`}
    >
      {mobile && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-line-subtle">
          <span className="panel-title">Menu</span>
          <button
            onClick={onClose}
            className="p-1 text-ink-secondary hover:text-ink"
            aria-label="Close menu"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <div className="flex-1 py-2 px-0">
        <ul className="space-y-0.5">
          {navItems.map((item) => {
            const active = isActive(item);
            const Icon = item.icon;

            const linkContent = (
              <div
                className={`h-7 px-2 text-[12px] flex items-center gap-2 border-l-2 ${
                  active
                    ? 'bg-teal-dim text-teal border-teal'
                    : item.disabled
                    ? 'text-ink-muted cursor-not-allowed border-transparent'
                    : 'text-ink-secondary hover:bg-surface-hover hover:text-ink border-transparent'
                }`}
                title={collapsed && !mobile ? item.label : undefined}
              >
                <Icon size={14} className="shrink-0" />
                {(!collapsed || mobile) && (
                  <span className="truncate">{item.label}</span>
                )}
                {(!collapsed || mobile) && item.disabled && (
                  <span className="ml-auto text-[10px] font-mono tracking-[0.08em] text-ink-muted">
                    SOON
                  </span>
                )}
              </div>
            );

            if (item.disabled) {
              return (
                <li key={item.href}>
                  <div className="cursor-not-allowed">{linkContent}</div>
                </li>
              );
            }

            return (
              <li key={item.href}>
                <Link href={item.href}>{linkContent}</Link>
              </li>
            );
          })}
        </ul>
      </div>

      {!mobile && (
        <div className="p-2 border-t border-line-subtle">
          <button
            onClick={onToggle}
            className="flex items-center justify-center w-full h-7 text-ink-secondary hover:bg-surface-hover hover:text-ink rounded-[3px]"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>
      )}
    </nav>
  );
}
