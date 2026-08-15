import { render, screen, fireEvent } from '@testing-library/react';
import { useTheme, ThemeProvider } from '@/components/theme-provider';

function Probe() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button onClick={toggleTheme} data-testid="probe">
      {theme}
    </button>
  );
}

describe('ThemeProvider', () => {
  it('defaults to dark and toggles to light, persisting choice', () => {
    localStorage.removeItem('mp-theme');
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    );
    const probe = screen.getByTestId('probe');
    expect(probe.textContent).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    fireEvent.click(probe);
    expect(probe.textContent).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem('mp-theme')).toBe('light');
  });
});