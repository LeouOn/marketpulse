import { MACRO_LABELS, MACRO_SYMBOLS, macroUnavailableReason } from '../labels';

describe('macroUnavailableReason', () => {
  it('extracts the backend reason from a success:false envelope', () => {
    const envelope = {
      success: false,
      error:
        'Yahoo Finance returned no macro data and MARKETPULSE_ALLOW_MOCK is not set. Set MARKETPULSE_ALLOW_MOCK=1 to allow a labelled mock fallback.',
      timestamp: '2026-09-29T12:00:00',
    };
    expect(macroUnavailableReason(envelope)).toBe(envelope.error);
  });

  it('returns null for real macro data', () => {
    const macroData = {
      DXY: { price: 101.2, change: 0.1, change_pct: 0.1, volume: 0, timestamp: 't', symbol: 'DX-Y.NYB' },
      GC: { price: 3300, change: 5, change_pct: 0.15, volume: 1, timestamp: 't', symbol: 'GC=F' },
    };
    expect(macroUnavailableReason(macroData)).toBeNull();
  });

  it('returns null for null/undefined/loading states', () => {
    expect(macroUnavailableReason(null)).toBeNull();
    expect(macroUnavailableReason(undefined)).toBeNull();
  });

  it('returns null for a success:false envelope without an error message', () => {
    expect(macroUnavailableReason({ success: false })).toBeNull();
  });
});

describe('MACRO_LABELS', () => {
  it('labels every macro symbol the dashboard renders', () => {
    for (const key of MACRO_SYMBOLS) {
      expect(MACRO_LABELS[key]).toBeTruthy();
    }
  });

  it('names the real instruments for DXY and gold', () => {
    expect(MACRO_LABELS.DXY).toContain('ICE');
    expect(MACRO_LABELS.GC).toContain('GC=F');
  });
});
