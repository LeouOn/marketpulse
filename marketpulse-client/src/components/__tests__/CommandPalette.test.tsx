import { act, render, screen, fireEvent } from '@testing-library/react';
import { CommandPalette } from '@/components/CommandPalette';
import { ThemeProvider } from '@/components/theme-provider';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));

function renderPalette() {
  return render(
    <ThemeProvider>
      <CommandPalette />
    </ThemeProvider>
  );
}

describe('CommandPalette', () => {
  it('opens on mp:open-palette event and shows commands', () => {
    renderPalette();
    act(() => { window.dispatchEvent(new CustomEvent('mp:open-palette')); });
    expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
    expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
  });

  it('filters to symbol command for ticker-like input', () => {
    renderPalette();
    act(() => { window.dispatchEvent(new CustomEvent('mp:open-palette')); });
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'aapl' } });
    expect(screen.getByText(/go to aapl/i)).toBeInTheDocument();
  });
});
