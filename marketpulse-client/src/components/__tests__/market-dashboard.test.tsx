import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MarketDashboard } from '../market-dashboard'
import { marketPulseAPI } from '@/lib/api'

// Mock the API
jest.mock('@/lib/api', () => ({
  marketPulseAPI: {
    getDashboardData: jest.fn(),
  },
}))

describe('MarketDashboard', () => {
  const mockDashboardData = {
    timestamp: '2024-01-01T12:00:00Z',
    marketBias: 'BULLISH' as const,
    volatilityRegime: 'NORMAL' as const,
    symbols: {
      spy: {
        symbol: 'SPY',
        price: 450.00,
        change: 2.50,
        changePct: 0.56,
        volume: 1000000,
        timestamp: '2024-01-01T12:00:00Z',
      },
      qqq: {
        symbol: 'QQQ',
        price: 380.00,
        change: 3.20,
        changePct: 0.85,
        volume: 800000,
        timestamp: '2024-01-01T12:00:00Z',
      },
      vix: {
        symbol: 'VIX',
        price: 15.50,
        change: -0.30,
        changePct: -1.90,
        volume: 500000,
        timestamp: '2024-01-01T12:00:00Z',
      },
    },
    volumeFlow: {
      totalVolume60min: 2500000,
      symbolsTracked: 3,
    },
    aiAnalysis: 'Market shows bullish momentum with strong volume support.',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders loading state initially', () => {
    ;(marketPulseAPI.getDashboardData as jest.Mock).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    )

    render(<MarketDashboard />)
    
    expect(screen.getByText('Loading market data...')).toBeInTheDocument()
  })

  it('renders error state when API fails', async () => {
    ;(marketPulseAPI.getDashboardData as jest.Mock).mockRejectedValue(
      new Error('Network error')
    )

    render(<MarketDashboard />)
    
    await waitFor(() => {
      expect(screen.getByText(/Error: Network error/)).toBeInTheDocument()
    })
  })

  it('renders dashboard data successfully', async () => {
    ;(marketPulseAPI.getDashboardData as jest.Mock).mockResolvedValue(mockDashboardData)

    render(<MarketDashboard />)
    
    await waitFor(() => {
      // Check header
      expect(screen.getByText('MarketPulse')).toBeInTheDocument()
      
      // Check symbol cards
      expect(screen.getByText('SPY (Market)')).toBeInTheDocument()
      expect(screen.getByText('QQQ (Tech)')).toBeInTheDocument()
      expect(screen.getByText('VIX (Volatility)')).toBeInTheDocument()
      
      // Check prices
      expect(screen.getByText('$450.00')).toBeInTheDocument()
      expect(screen.getByText('$380.00')).toBeInTheDocument()
      expect(screen.getByText('15.50')).toBeInTheDocument()
      
      // Check market bias
      expect(screen.getByText('BULLISH')).toBeInTheDocument()
      
      // Check volatility regime
      expect(screen.getByText('NORMAL')).toBeInTheDocument()
      
      // Check volume flow
      expect(screen.getByText('2,500,000')).toBeInTheDocument()
      
      // Check AI analysis
      expect(screen.getByText(/Market shows bullish momentum/)).toBeInTheDocument()
    })
  })

  it('displays correct trend indicators', async () => {
    ;(marketPulseAPI.getDashboardData as jest.Mock).mockResolvedValue(mockDashboardData)

    render(<MarketDashboard />)
    
    await waitFor(() => {
      // SPY and QQQ should show upward trends
      const trendingUpIcons = screen.getAllByTestId('trending-up')
      expect(trendingUpIcons.length).toBeGreaterThan(0)
      
      // VIX should show downward trend
      const trendingDownIcons = screen.getAllByTestId('trending-down')
      expect(trendingDownIcons.length).toBeGreaterThan(0)
    })
  })

  it('shows refresh button and updates data on click', async () => {
    ;(marketPulseAPI.getDashboardData as jest.Mock)
      .mockResolvedValueOnce(mockDashboardData)
      .mockResolvedValueOnce({
        ...mockDashboardData,
        marketBias: 'BEARISH' as const,
      })

    render(<MarketDashboard />)
    
    await waitFor(() => {
      expect(screen.getByText('BULLISH')).toBeInTheDocument()
    })

    const refreshButton = screen.getByText('Refresh')
    fireEvent.click(refreshButton)

    await waitFor(() => {
      expect(screen.getByText('BEARISH')).toBeInTheDocument()
    })
    
    expect(marketPulseAPI.getDashboardData).toHaveBeenCalledTimes(2)
  })

  it('auto-refreshes data every 30 seconds', async () => {
    jest.useFakeTimers()
    
    ;(marketPulseAPI.getDashboardData as jest.Mock)
      .mockResolvedValue(mockDashboardData)

    render(<MarketDashboard />)
    
    await waitFor(() => {
      expect(marketPulseAPI.getDashboardData).toHaveBeenCalledTimes(1)
    })

    // Fast-forward 30 seconds
    jest.advanceTimersByTime(30000)

    await waitFor(() => {
      expect(marketPulseAPI.getDashboardData).toHaveBeenCalledTimes(2)
    })

    jest.useRealTimers()
  })

  it('displays last update time', async () => {
    ;(marketPulseAPI.getDashboardData as jest.Mock).mockResolvedValue(mockDashboardData)

    render(<MarketDashboard />)
    
    await waitFor(() => {
      expect(screen.getByText(/Last updated:/)).toBeInTheDocument()
    })
  })

  it('handles missing symbol data gracefully', async () => {
    const incompleteData = {
      ...mockDashboardData,
      symbols: {
        spy: mockDashboardData.symbols.spy,
        // qqq and vix are missing
      },
    }

    ;(marketPulseAPI.getDashboardData as jest.Mock).mockResolvedValue(incompleteData)

    render(<MarketDashboard />)
    
    await waitFor(() => {
      // Should still render SPY
      expect(screen.getByText('SPY (Market)')).toBeInTheDocument()
      expect(screen.getByText('$450.00')).toBeInTheDocument()
      
      // Should not render missing symbols
      expect(screen.queryByText('QQQ (Tech)')).not.toBeInTheDocument()
      expect(screen.queryByText('VIX (Volatility)')).not.toBeInTheDocument()
    })
  })

  it('displays correct colors for different market conditions', async () => {
    const bearishData = {
      ...mockDashboardData,
      marketBias: 'BEARISH' as const,
      volatilityRegime: 'HIGH' as const,
    }

    ;(marketPulseAPI.getDashboardData as jest.Mock).mockResolvedValue(bearishData)

    render(<MarketDashboard />)
    
    await waitFor(() => {
      // Bearish should be red
      const bearishElement = screen.getByText('BEARISH')
      expect(bearishElement).toHaveClass('text-red-400')
      
      // High volatility should be orange
      const volatilityElement = screen.getByText('HIGH')
      expect(volatilityElement).toHaveClass('text-orange-400')
    })
  })
})