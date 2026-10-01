import { regimeBar } from '../regimeBar';

describe('regimeBar', () => {
  const reading = {
    probs: { REAL_YIELD_SHOCK: 0.284, RISK_ON: 0.237 },
    scores: { REAL_YIELD_SHOCK: 0.59, RISK_ON: 0.41 },
  };

  it('draws the absolute stress score and keeps the softmax weight for the tooltip', () => {
    expect(regimeBar(reading, 'REAL_YIELD_SHOCK')).toEqual({ value: 0.59, weight: 0.284, fromScores: true });
  });

  it('falls back to the probability for responses without scores', () => {
    expect(regimeBar({ probs: { RISK_ON: 0.3 } }, 'RISK_ON')).toEqual({ value: 0.3, weight: 0.3, fromScores: false });
    expect(regimeBar({ probs: { RISK_ON: 0.3 }, scores: null }, 'RISK_ON').fromScores).toBe(false);
  });

  it('reports a regime missing from the response as undefined, not zero', () => {
    expect(regimeBar(reading, 'RECESSION')).toEqual({ value: undefined, weight: undefined, fromScores: false });
    expect(regimeBar(null, 'RISK_ON')).toEqual({ value: undefined, weight: undefined, fromScores: false });
  });

  it('treats a genuine zero score as a score, not as missing', () => {
    expect(regimeBar({ probs: { RECESSION: 0.16 }, scores: { RECESSION: 0 } }, 'RECESSION')).toEqual({
      value: 0,
      weight: 0.16,
      fromScores: true,
    });
  });
});
