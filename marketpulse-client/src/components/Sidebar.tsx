'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Flame, BarChart3, Bell, Settings, ChevronLeft, ChevronRight, Menu, X } from 'lucide-react';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { href: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/trending', icon: Flame, label: 'Trending' },
  { href: '/chart/SPY', icon: BarChart3, label: 'Charts' },
  { href: '/alerts', icon: Bell, label: 'Alerts', disabled: true },
  { href: '/settings', icon: Settings, label: 'Settings', disabled: true },
];

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <nav
      className={`bg-gray-900 border-r border-gray-800 h-full flex flex-col transition-all duration-200 ${
        collapsed ? 'w-16' : 'w-[200px]'
      }`}
    >
      <div className="flex-1 py-4 px-2">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = !item.disabled && (
              item.href === '/' ? pathname === '/' : pathname.startsWith(item.href)
            );
            const Icon = item.icon;

            const linkContent = (
              <div
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-blue-500/10 text-blue-400 border-l-2 border-blue-400'
                    : item.disabled
                    ? 'text-gray-600 cursor-not-allowed'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`}
              >
                <Icon size={20} className="shrink-0" />
                {!collapsed && (
                  <span className="truncate">{item.label}</span>
                )}
                {!collapsed && item.disabled && (
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

      <div className="p-2 border-t border-gray-800">
        <button
          onClick={onToggle}
          className="flex items-center justify-center w-full px-4 py-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-gray-200 transition-colors"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
    </nav>
  );
}
