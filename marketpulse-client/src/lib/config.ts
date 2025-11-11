/**
 * Frontend configuration management
 * Centralizes all environment variables with type safety and defaults
 */

export const config = {
  // API Configuration
  api: {
    baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    wsUrl: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000',
  },

  // Polling Configuration
  polling: {
    interval: parseInt(process.env.NEXT_PUBLIC_POLL_INTERVAL || '30000', 10),
  },

  // Feature Flags
  features: {
    websocket: process.env.NEXT_PUBLIC_ENABLE_WEBSOCKET === 'true',
    charts: process.env.NEXT_PUBLIC_ENABLE_CHARTS === 'true',
    aiAnalysis: process.env.NEXT_PUBLIC_ENABLE_AI_ANALYSIS === 'true',
  },

  // Development
  debug: process.env.NEXT_PUBLIC_DEBUG === 'true',
} as const;

// Type-safe config access
export type Config = typeof config;

// Export individual configs for convenience
export const { api, polling, features, debug } = config;
