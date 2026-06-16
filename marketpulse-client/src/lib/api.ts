import type { ScreenerResult, SymbolProfile, SymbolStats, FiftyTwoWeekRange, OHLCVBar, DashboardData, MarketSymbolData, MacroData } from '@/types/market';

const API_BASE = '/api';

export interface AIAnalysisData {
  analysis: string;
}

class MarketPulseAPIClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = API_BASE;
  }

  private async fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const json = await response.json();
    return json.data ?? json;
  }

  async getDashboardData(): Promise<DashboardData> {
    return this.fetchAPI<DashboardData>('/market/dashboard');
  }

  async getMacroData(): Promise<MacroData> {
    return this.fetchAPI<MacroData>('/market/macro');
  }

  async getAIAnalysis(): Promise<AIAnalysisData> {
    return this.fetchAPI<AIAnalysisData>('/market/ai-analysis');
  }

  async getMarketBreadth(): Promise<any> {
    return this.fetchAPI<any>('/market/breadth');
  }

  async getHistoricalData(symbol: string, timeframe: string = '1d', limit: number = 100): Promise<any> {
    return this.fetchAPI<any>(`/market/historical?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`);
  }

  async getOHLCAnalysis(symbol: string): Promise<any> {
    return this.fetchAPI<any>(`/market/ohlc-analysis/${encodeURIComponent(symbol)}`);
  }

  async getTrendAnalysis(symbol: string): Promise<any> {
    return this.fetchAPI<any>(`/market/trends/${encodeURIComponent(symbol)}`);
  }

  async chatWithLLM(message: string, context?: any, symbol?: string, conversationHistory?: Array<{role: string; content: string}>): Promise<string> {
    const response = await fetch(`${this.baseUrl}/llm/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        context,
        symbol,
        conversation_history: conversationHistory,
      }),
    });

    if (!response.ok) {
      throw new Error(`Chat API error: ${response.status}`);
    }

    const json = await response.json();
    return json.data?.response ?? json.data ?? '';
  }

  async getAvailableModels(): Promise<any> {
    return this.fetchAPI<any>('/llm/models');
  }

  async selectModel(modelId: string, provider: string = 'lm_studio'): Promise<any> {
    return this.fetchAPI<any>('/llm/select-model', {
      method: 'POST',
      body: JSON.stringify({ model_id: modelId, provider }),
    });
  }

  async getModelStatus(): Promise<any> {
    return this.fetchAPI<any>('/llm/model-status');
  }

  async getScreenerData(type: 'gainers' | 'losers' | 'most_active'): Promise<ScreenerResult[]> {
    return this.fetchAPI<ScreenerResult[]>(`/market/screeners/${type}`);
  }

  async getSymbols(): Promise<SymbolProfile[]> {
    return this.fetchAPI<SymbolProfile[]>('/market/symbols');
  }

  async getSymbolDetail(symbol: string): Promise<any> {
    return this.fetchAPI<any>(`/market/symbols/${encodeURIComponent(symbol)}`);
  }

  async getSymbolStats(symbol: string): Promise<SymbolStats> {
    return this.fetchAPI<SymbolStats>(`/market/symbols/${encodeURIComponent(symbol)}/stats`);
  }

  async get52WRange(symbol: string): Promise<FiftyTwoWeekRange> {
    return this.fetchAPI<FiftyTwoWeekRange>(`/market/symbols/${encodeURIComponent(symbol)}/52w-range`);
  }

  async searchSymbols(query: string): Promise<SymbolProfile[]> {
    return this.fetchAPI<SymbolProfile[]>(`/market/symbols/search?q=${encodeURIComponent(query)}`);
  }

  async getHistoricalFromDB(symbol: string, timeframe: string = '1d', period: string = '1mo'): Promise<{symbol: string, data: OHLCVBar[]}> {
    return this.fetchAPI(`/market/historical/${encodeURIComponent(symbol)}?timeframe=${timeframe}&period=${period}`);
  }

  // ----------------------- BTC Research Lab (B7) -----------------------

  async listResearchStrategies(): Promise<any[]> {
    return this.fetchAPI<any[]>('/research/strategies');
  }

  async describeResearchStrategy(name: string): Promise<any> {
    return this.fetchAPI<any>(`/research/strategies/${encodeURIComponent(name)}`);
  }

  async listResearchScaling(): Promise<any[]> {
    return this.fetchAPI<any[]>('/research/scaling');
  }

  async describeResearchScaling(name: string): Promise<any> {
    return this.fetchAPI<any>(`/research/scaling/${encodeURIComponent(name)}`);
  }

  async researchDataSummary(params: { start?: string; end?: string; timeframe?: string } = {}): Promise<any> {
    const qs = new URLSearchParams();
    if (params.start) qs.set('start', params.start);
    if (params.end) qs.set('end', params.end);
    if (params.timeframe) qs.set('timeframe', params.timeframe);
    const tail = qs.toString() ? `?${qs.toString()}` : '';
    return this.fetchAPI<any>(`/research/data/summary${tail}`);
  }

  async runResearchBacktest(req: {
    strategy: string;
    strategy_params?: Record<string, any>;
    scaling?: string;
    scaling_params?: Record<string, any>;
    start?: string;
    end?: string;
    timeframe?: string;
    starting_equity?: number;
    fee_bps?: number;
    slippage_bps?: number;
  }): Promise<any> {
    return this.fetchAPI<any>('/research/backtest', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async runResearchMonteCarlo(req: {
    method: 'gbm' | 'block_bootstrap' | 'regime_switching';
    n_paths?: number;
    n_steps?: number;
    starting_value?: number;
    mu?: number;
    sigma?: number;
    block_size?: number;
    start?: string;
    end?: string;
    seed?: number;
  }): Promise<any> {
    return this.fetchAPI<any>('/research/montecarlo', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async compareResearchStrategies(req: {
    strategies: (string | { name: string; params?: Record<string, any> })[];
    scaling?: string;
    start?: string;
    end?: string;
    timeframe?: string;
    starting_equity?: number;
  }): Promise<any> {
    return this.fetchAPI<any>('/research/compare', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async listResearchReports(params: { kind?: string; limit?: number } = {}): Promise<{ reports: any[] }> {
    const qs = new URLSearchParams();
    if (params.kind) qs.set('kind', params.kind);
    if (params.limit) qs.set('limit', String(params.limit));
    const tail = qs.toString() ? `?${qs.toString()}` : '';
    return this.fetchAPI<{ reports: any[] }>(`/research/reports${tail}`);
  }

  async getResearchReport(id: string): Promise<any> {
    return this.fetchAPI<any>(`/research/reports/${encodeURIComponent(id)}`);
  }

  getResearchReportImageUrl(id: string, kind: 'equity_png' | 'drawdown_png'): string {
    return `${API_BASE}/research/reports/${encodeURIComponent(id)}/image/${kind}`;
  }

  /**
   * Stream the research chat. Returns the raw Response so the caller can
   * read NDJSON line by line.
   */
  async streamResearchChat(messages: Array<{ role: string; content: string }>): Promise<Response> {
    return fetch(`${API_BASE}/research/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages, max_tool_calls: 5 }),
    });
  }
}

export async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  const json = await response.json();
  return (json.data ?? json) as T;
}

export const marketPulseAPI = new MarketPulseAPIClient();
