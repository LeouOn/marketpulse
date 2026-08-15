import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-jbmono)', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      colors: {
        canvas: 'var(--canvas)',
        surface: {
          DEFAULT: 'var(--surface)',
          raised: 'var(--surface-raised)',
          hover: 'var(--surface-hover)',
        },
        line: {
          DEFAULT: 'var(--border-default)',
          subtle: 'var(--border-subtle)',
          strong: 'var(--border-strong)',
          focus: 'var(--border-focus)',
        },
        ink: {
          DEFAULT: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        pos: { DEFAULT: 'var(--green)', dim: 'var(--green-dim)' },
        neg: { DEFAULT: 'var(--red)', dim: 'var(--red-dim)' },
        warn: { DEFAULT: 'var(--amber)', dim: 'var(--amber-dim)' },
        sel: { DEFAULT: 'var(--blue)', dim: 'var(--blue-dim)' },
        teal: { DEFAULT: 'var(--teal)', dim: 'var(--teal-dim)' },
      },
    },
  },
  plugins: [],
}
export default config