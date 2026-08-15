// lightweight-charts v5 is ESM-only and ships no CJS build. Jest's CJS runtime
// cannot resolve or load the .mjs files, so we provide a minimal stub here.
// chart-theme.ts only references the ColorType enum value; chart tests that
// need a real chart should be rendered with Playwright, not jsdom.
export const ColorType = { Solid: 'solid', VerticalGradient: 'gradient' };
