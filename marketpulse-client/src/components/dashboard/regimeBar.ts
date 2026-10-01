/**
 * Which number a regime bar should show.
 *
 * The macro regime API returns both per-regime stress `scores` (absolute strength, 0-1) and `probs`
 * (a softmax of those scores). The softmax compresses everything: one fully fired regime against
 * four quiet ones can never exceed ~40%, so a bar drawn from `probs` makes a real shock look
 * minor. Draw the score when the API provides it and keep the relative weight for the tooltip;
 * fall back to `probs` for older responses.
 */
export interface RegimeReading {
  probs?: Record<string, number> | null;
  scores?: Record<string, number> | null;
}

export interface RegimeBar {
  /** 0-1 value to draw, or undefined when the regime is missing from the response. */
  value: number | undefined;
  /** Relative softmax weight (0-1), shown in the tooltip. */
  weight: number | undefined;
  /** True when `value` is the raw stress score rather than the softmax probability. */
  fromScores: boolean;
}

export function regimeBar(reading: RegimeReading | null | undefined, regime: string): RegimeBar {
  const score = reading?.scores?.[regime];
  const weight = reading?.probs?.[regime];
  if (score != null) {
    return { value: score, weight, fromScores: true };
  }
  return { value: weight, weight, fromScores: false };
}
