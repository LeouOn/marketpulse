import { DashboardData, MarketInternals, PriceData } from '@/types/market';

export interface HistoricalParams {
  symbol: string;
  timeframe?: '1Min' | '5Min' | '15Min' | '1Hour' | '1Day';
  limit?: number;
  start?: string;
  end?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: string;
}

export class MarketPulseAPIError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public response?: any
  ) {
    super(message);
    this.name = 'MarketPulseAPIError';
  }
}

export class MarketPulseAPI {
  private baseUrl: string;
  private defaultHeaders: HeadersInit;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
  }

  /**
   * Generic fetch wrapper with error handling
   */
  private async fetchWithErrorHandling<T>(
    endpoint: string,
    options?: RequestInit
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...this.defaultHeaders,
          ...options?.headers,
        },
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new MarketPulseAPIError(
          `API request failed: ${response.statusText}`,
          response.status,
          errorText
        );
      }

      const data = await response.json();
      return data;
    } catch (error) {
      if (error instanceof MarketPulseAPIError) {
        throw error;
      }

      throw new MarketPulseAPIError(
        `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        undefined,
        error
      );
    }
  }

  /**
   * Get dashboard data with market bias, symbols, and AI analysis
   */
  async getDashboardData(): Promise<ApiResponse<DashboardData>> {
    return this.fetchWithErrorHandling<DashboardData>('/api/market/dashboard');
  }

  /**
   * Get market internals for all symbols or a specific symbol
   */
  async getMarketInternals(symbol?: string): Promise<ApiResponse<MarketInternals>> {
    const endpoint = symbol
      ? `/api/market/internals?symbol=${encodeURIComponent(symbol)}`
      : '/api/market/internals';

    return this.fetchWithErrorHandling<MarketInternals>(endpoint);
  }

  /**
   * Get historical price data for a symbol
   */
  async getHistoricalData(params: HistoricalParams): Promise<ApiResponse<PriceData[]>> {
    const queryParams = new URLSearchParams();
    queryParams.append('symbol', params.symbol);

    if (params.timeframe) {
      queryParams.append('timeframe', params.timeframe);
    }
    if (params.limit) {
      queryParams.append('limit', params.limit.toString());
    }
    if (params.start) {
      queryParams.append('start', params.start);
    }
    if (params.end) {
      queryParams.append('end', params.end);
    }

    return this.fetchWithErrorHandling<PriceData[]>(
      `/api/market/historical?${queryParams.toString()}`
    );
  }

  /**
   * Request AI analysis for current market conditions
   */
  async requestAnalysis(
    analysisType: 'quick' | 'deep' | 'trade_setup' = 'quick'
  ): Promise<ApiResponse<{ analysis: string; model: string; confidence?: number }>> {
    return this.fetchWithErrorHandling(
      `/api/llm/analyze?type=${analysisType}`,
      { method: 'POST' }
    );
  }

  /**
   * Get WebSocket URL for real-time updates
   */
  getWebSocketUrl(): string {
    const wsProtocol = this.baseUrl.startsWith('https') ? 'wss' : 'ws';
    const wsBaseUrl = this.baseUrl.replace(/^https?/, wsProtocol);
    return `${wsBaseUrl}/api/market/stream`;
  }

  /**
   * Health check endpoint
   */
  async healthCheck(): Promise<ApiResponse<{ status: string }>> {
    return this.fetchWithErrorHandling('/health');
  }
}

// Export singleton instance
export const marketPulseAPI = new MarketPulseAPI();

// Export class for testing with custom base URL
export default MarketPulseAPI;
