import { getChartTheme, SERIES_PALETTE } from '@/lib/chart-theme';

describe('chart-theme', () => {
  it('exposes a 6-color series palette led by teal', () => {
    expect(SERIES_PALETTE).toHaveLength(6);
    expect(SERIES_PALETTE[0]).toMatch(/#3b9da0/i);
  });

  it('reads CSS variables from the document root', () => {
    document.documentElement.style.setProperty('--surface', '#123456');
    const t = getChartTheme();
    expect(t.layout.background.color.toLowerCase()).toBe('#123456');
  });

  it('falls back to SERIES_PALETTE colors for up/down candles', () => {
    const t = getChartTheme();
    expect(typeof t.upColor).toBe('string');
    expect(typeof t.downColor).toBe('string');
  });
});
