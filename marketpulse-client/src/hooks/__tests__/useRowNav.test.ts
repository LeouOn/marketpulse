import { act, renderHook } from '@testing-library/react';
import { useRowNav } from '@/hooks/useRowNav';

function key(k: string): React.KeyboardEvent {
  return { key: k, preventDefault: () => {} } as unknown as React.KeyboardEvent;
}

describe('useRowNav', () => {
  it('moves down with j and up with k, clamped', () => {
    const { result } = renderHook(() => useRowNav(3));
    act(() => { result.current.handleKeyDown(key('j')); });
    act(() => { result.current.handleKeyDown(key('j')); });
    act(() => { result.current.handleKeyDown(key('j')); }); // clamp at 2
    expect(result.current.focusedIndex).toBe(2);
    act(() => { result.current.handleKeyDown(key('k')); });
    expect(result.current.focusedIndex).toBe(1);
  });

  it('fires onEnter with focused index', () => {
    const onEnter = jest.fn();
    const { result } = renderHook(() => useRowNav(3, { onEnter }));
    act(() => { result.current.handleKeyDown(key('j')); });
    act(() => { result.current.handleKeyDown(key('Enter')); });
    expect(onEnter).toHaveBeenCalledWith(1);
  });

  it('is a no-op when disabled', () => {
    const { result } = renderHook(() => useRowNav(3, { enabled: false }));
    act(() => { result.current.handleKeyDown(key('j')); });
    expect(result.current.focusedIndex).toBe(0);
  });
});
