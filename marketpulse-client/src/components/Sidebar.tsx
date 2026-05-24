'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Flame, BarChart3, Bell, Settings, ChevronLeft, ChevronRight, X, TrendingUp } from 'lucide-react';

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
      className={`bg-gray-900 border-r border-gray-800 h-full flex flex-col transition-all duration-200 ${
        collapsed && !mobile ? 'w-16' : 'w-[200px]'
      }`}
    >
      {mobile && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
          <span className="text-sm font-semibold text-gray-300">Menu</span>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white transition-colors"
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>
      )}

      <div className="flex-1 py-4 px-2">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const active = isActive(item);
            const Icon = item.icon;

            const linkContent = (
              <div
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  active
                    ? 'bg-blue-500/10 text-blue-400 border-l-2 border-blue-400'
                    : item.disabled
                    ? 'text-gray-600 cursor-not-allowed'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`}
                title={collapsed && !mobile ? item.label : undefined}
              >
                <Icon size={20} className="shrink-0" />
                {(!collapsed || mobile) && (
                  <span className="truncate">{item.label}</span>
                )}
                {(!collapsed || mobile) && item.disabled && (
                  <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">
                    Soon
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
        <div className="p-2 border-t border-gray-800">
          <button
            onClick={onToggle}
            className="flex items-center justify-center w-full px-4 py-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-gray-200 transition-colors"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>
      )}
    </nav>
  );
}
