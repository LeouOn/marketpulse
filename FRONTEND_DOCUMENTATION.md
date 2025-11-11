# MarketPulse Frontend Documentation

## Architecture Overview

The MarketPulse frontend is a Next.js 14+ React application with TypeScript, Tailwind CSS, and modern web technologies.

### Technology Stack
- **Framework:** Next.js 14+ (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **Charts:** Recharts
- **Icons:** Lucide React
- **State Management:** React Hooks
- **API Client:** Custom fetch wrapper
- **Testing:** Jest + React Testing Library

### Project Structure
```
marketpulse-client/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── layout.tsx         # Root layout
│   │   ├── page.tsx           # Home page
│   │   └── globals.css        # Global styles
│   ├── components/            # React components
│   │   ├── market-dashboard.tsx
│   │   └── __tests__/
│   ├── lib/                   # Utilities and API clients
│   │   └── api.ts
│   ├── types/                 # TypeScript type definitions
│   │   └── market.ts
│   └── ...
├── public/
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── next.config.js
```

## Key Components

### MarketDashboard Component (`src/components/market-dashboard.tsx`)

**Purpose:** Main dashboard displaying real-time market data and AI analysis

**Features:**
- Real-time market data updates (every 30 seconds)
- Symbol cards (SPY, QQQ, VIX) with price, change, volume
- Market bias indicator (BULLISH/BEARISH/MIXED)
- Volatility regime display
- Volume flow metrics
- AI analysis section

**State Management:**
```typescript
const [data, setData] = useState<DashboardData | null>(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
```

**Data Fetching:**
```typescript
const fetchData = async () => {
  try {
    const dashboardData = await marketPulseAPI.getDashboardData();
    setData(dashboardData);
    setLastUpdate(new Date());
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Failed to fetch data');
  }
};

useEffect(() => {
  fetchData();
  const interval = setInterval(fetchData, 30000);
  return () => clearInterval(interval);
}, []);
```

**Areas for Enhancement:**
- [ ] Add WebSocket support for real-time updates
- [ ] Implement auto-refresh toggle
- [ ] Add manual refresh button with loading state
- [ ] Implement error retry mechanism
- [ ] Add data timestamp display
- [ ] Implement responsive design improvements
- [ ] Add dark/light mode toggle
- [ ] Implement user preferences (update frequency, symbols)
- [ ] Add chart interactions (zoom, pan, tooltips)
- [ ] Implement data export functionality

### API Client (`src/lib/api.ts`)

**Purpose:** Centralized API client for all backend communication

**Current Methods:**
```typescript
class MarketPulseAPI {
  async getMarketInternals(): Promise<MarketInternals>
  async getDashboardData(): Promise<DashboardData>
  async getHistoricalData(symbol: string, timeframe?: string, limit?: number): Promise<PriceData[]>
  async getAIAnalysis(): Promise<string>
}
```

**Areas for Enhancement:**
- [ ] Add request/response interceptors for logging
- [ ] Implement request deduplication
- [ ] Add caching layer (React Query/SWR)
- [ ] Implement offline support
- [ ] Add request retry logic with exponential backoff
- [ ] Implement request cancellation
- [ ] Add type-safe error handling
- [ ] Implement API versioning support
- [ ] Add request/response transformers
- [ ] Implement WebSocket client methods

### Type Definitions (`src/types/market.ts`)

**Current Types:**
```typescript
interface MarketSymbol {
  price: number;
  change: number;
  changePct: number;
  volume: number;
}

interface DashboardData {
  timestamp: string;
  marketBias: string;
  volatilityRegime: string;
  symbols: {
    spy?: MarketSymbol;
    qqq?: MarketSymbol;
    vix?: MarketSymbol;
  };
  volumeFlow: {
    totalVolume60min: number;
    symbolsTracked: number;
  };
  aiAnalysis?: string;
}
```

**Areas for Enhancement:**
- [ ] Add stricter typing (branded types, discriminated unions)
- [ ] Implement runtime type validation (Zod/io-ts)
- [ ] Add API response validation
- [ ] Create type guards for runtime checking
- [ ] Add JSDoc comments for all types
- [ ] Implement type-safe API endpoints
- [ ] Add schema versioning
- [ ] Create type utilities (Pick, Omit, Partial variants)

## API Integration

### Current API Endpoints Used

1. **GET `/api/market/dashboard`**
   - Used in: `MarketDashboard` component
   - Frequency: Every 30 seconds
   - Data: Full dashboard data including AI analysis

2. **Future API Endpoints to Integrate:**
   - [ ] `POST /api/llm/comment` - Add user comments
   - [ ] `POST /api/llm/refine` - Refine AI analysis
   - [ ] `POST /api/llm/analyze-chart` - Chart analysis
   - [ ] `GET /api/llm/validation/sanity-check` - Data validation
   - [ ] `GET /api/llm/conversation-history` - Analysis history
   - [ ] `GET /api/market/historical` - Historical data for charts
   - [ ] `GET /api/market/internals` - Raw market internals
   - [ ] WebSocket `/ws/market` - Real-time updates

### Error Handling Strategy

**Current Implementation:**
```typescript
try {
  const data = await marketPulseAPI.getDashboardData();
  setData(data);
  setError(null);
} catch (err) {
  setError(err instanceof Error ? err.message : 'Failed to fetch data');
}
```

**Recommended Enhancements:**
- [ ] Implement global error boundary
- [ ] Add error recovery strategies
- [ ] Create user-friendly error messages
- [ ] Implement error logging service
- [ ] Add offline error queue
- [ ] Create error monitoring dashboard

## State Management Strategy

### Current Approach
- Local component state with `useState`
- Manual data fetching with `useEffect`
- Prop drilling for data sharing

### Recommended State Management Enhancements

**Option 1: React Context + Hooks**
```typescript
// Create context for market data
const MarketDataContext = createContext<MarketDataContextType>();

// Provide at app level
<MarketDataProvider>
  <App />
</MarketDataProvider>

// Consume in components
const { data, loading, error, refresh } = useMarketData();
```

**Option 2: Zustand (Lightweight State Management)**
```typescript
// Create store
interface MarketDataStore {
  data: DashboardData | null;
  loading: boolean;
  error: string | null;
  fetchData: () => Promise<void>;
  refresh: () => void;
}

const useMarketDataStore = create<MarketDataStore>((set, get) => ({
  // Store implementation
}));
```

**Option 3: React Query (Data Fetching & Caching)**
```typescript
// Automatic caching, refetching, and state management
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ['dashboardData'],
  queryFn: () => marketPulseAPI.getDashboardData(),
  refetchInterval: 30000,
});
```

**Areas for Enhancement:**
- [ ] Implement global state management solution
- [ ] Add data caching layer
- [ ] Implement optimistic updates
- [ ] Add state persistence (localStorage)
- [ ] Create state migration strategy
- [ ] Add state debugging tools

## Performance Optimization

### Current Performance Characteristics
- Initial load: ~1-2 seconds
- Data updates: ~100-300ms
- Re-render frequency: Every 30 seconds
- Bundle size: Not measured

### Optimization Opportunities

**1. Code Splitting**
```typescript
// Lazy load heavy components
const ChartComponent = dynamic(() => import('./ChartComponent'), {
  loading: () => <LoadingSpinner />,
  ssr: false,
});
```

**2. Memoization**
```typescript
// Prevent unnecessary re-renders
const MemoizedSymbolCard = React.memo(SymbolCard);

// Use useMemo for expensive calculations
const processedData = useMemo(() => 
  processMarketData(data), [data]
);
```

**3. Virtual Scrolling**
```typescript
// For large lists of data
<VirtualizedList
  items={historicalData}
  itemHeight={50}
  renderItem={renderHistoricalRow}
/>
```

**4. Image Optimization**
```typescript
// Optimize chart images
<Image
  src="/chart.png"
  alt="Market Chart"
  loading="lazy"
  placeholder="blur"
/>
```

**5. Bundle Optimization**
```typescript
// Analyze bundle size
// Remove unused dependencies
// Tree-shake libraries
```

**Areas for Enhancement:**
- [ ] Implement code splitting for routes
- [ ] Add component memoization
- [ ] Optimize re-render cycles
- [ ] Implement virtual scrolling for large datasets
- [ ] Add image optimization
- [ ] Implement bundle analyzer
- [ ] Add performance budgets
- [ ] Create performance monitoring

## Testing Strategy

### Current Test Setup
- Jest configured
- React Testing Library
- Basic component tests

### Recommended Test Coverage

**1. Unit Tests**
```typescript
// Test utility functions
describe('marketDataUtils', () => {
  it('should calculate change percentage correctly', () => {
    expect(calculateChangePct(100, 110)).toBe(10);
  });
});

// Test components
describe('MarketDashboard', () => {
  it('should render loading state', () => {
    render(<MarketDashboard />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });
});
```

**2. Integration Tests**
```typescript
// Test component + API interaction
describe('MarketDashboard Integration', () => {
  it('should fetch and display market data', async () => {
    render(<MarketDashboard />);
    
    await waitFor(() => {
      expect(screen.getByText('$450.25')).toBeInTheDocument();
    });
  });
});
```

**3. E2E Tests**
```typescript
// Test complete user flows
describe('User Journey', () => {
  it('should view market data and add comment', async () => {
    // Navigate to dashboard
    // Wait for data to load
    // Add comment
    // Verify comment appears
  });
});
```

**Areas for Enhancement:**
- [ ] Add unit tests for all utility functions
- [ ] Create integration tests for API interactions
- [ ] Implement E2E tests for critical user flows
- [ ] Add visual regression testing
- [ ] Implement performance testing
- [ ] Add accessibility testing
- [ ] Create test coverage reports
- [ ] Add continuous integration for tests

## Accessibility (A11y)

### Current State
- Basic semantic HTML
- Some ARIA labels
- Keyboard navigation partially supported

### Recommended Enhancements

**1. Semantic HTML**
```typescript
// Use semantic elements
<header>, <nav>, <main>, <section>, <article>, <aside>, <footer>

// Add proper headings hierarchy
<h1>MarketPulse Dashboard</h1>
<h2>Market Overview</h2>
<h3>SPY (Market)</h3>
```

**2. ARIA Labels**
```typescript
// Add descriptive ARIA labels
<div 
  aria-label="SPY Price: $450.25, up 2.15 (0.48%)"
  role="region"
>
  {/* Content */}
</div>

// Add live regions for dynamic content
<div aria-live="polite" aria-atomic="true">
  {lastUpdate && `Last updated: ${lastUpdate.toLocaleTimeString()}`}
</div>
```

**3. Keyboard Navigation**
```typescript
// Add keyboard shortcuts
useEffect(() => {
  const handleKeyPress = (e: KeyboardEvent) => {
    if (e.key === 'r') refreshData();
    if (e.key === '?') showHelp();
  };
  window.addEventListener('keydown', handleKeyPress);
  return () => window.removeEventListener('keydown', handleKeyPress);
}, []);
```

**4. Screen Reader Support**
```typescript
// Add screen reader only text
<span className="sr-only">Loading market data</span>

// Add status messages
<div role="status" aria-live="polite">
  {error && `Error: ${error}`}
</div>
```

**Areas for Enhancement:**
- [ ] Add comprehensive ARIA labels
- [ ] Implement keyboard navigation
- [ ] Add screen reader support
- [ ] Create high contrast mode
- [ ] Implement font size controls
- [ ] Add focus management
- [ ] Create accessibility documentation
- [ ] Conduct accessibility audit

## Mobile Responsiveness

### Current State
- Basic responsive design with Tailwind
- Mobile-first approach
- Some breakpoints implemented

### Recommended Enhancements

**1. Responsive Breakpoints**
```typescript
// Optimize for different screen sizes
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
  {/* Content */}
</div>
```

**2. Touch Interactions**
```typescript
// Add touch gestures
const handleTouch = useSwipeable({
  onSwipedLeft: () => nextChart(),
  onSwipedRight: () => previousChart(),
});

// Add touch-friendly buttons
<button className="min-h-[44px] min-w-[44px]">
  {/* Button content */}
</button>
```

**3. Mobile-First Design**
```typescript
// Design for mobile first
<div className="text-sm md:text-base lg:text-lg">
  {/* Responsive text */}
</div>
```

**Areas for Enhancement:**
- [ ] Optimize for tablet experience
- [ ] Add mobile-specific navigation
- [ ] Implement touch gestures
- [ ] Add responsive typography
- [ ] Optimize for landscape mode
- [ ] Add PWA features (offline, installable)
- [ ] Implement mobile app wrapper (Capacitor/React Native)

## Build and Deployment

### Current Build Process
```bash
# Development
npm run dev

# Production build
npm run build

# Start production server
npm start
```

### Recommended Build Optimizations

**1. Environment Configuration**
```typescript
// Different configs for dev/staging/prod
// .env.development
// .env.staging
// .env.production
```

**2. CI/CD Pipeline**
```yaml
# GitHub Actions
name: Deploy MarketPulse Frontend

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Node.js
        uses: actions/setup-node@v2
        with:
          node-version: '18'
      - run: npm ci
      - run: npm run build
      - run: npm run test
      - name: Deploy to Vercel/Netlify
        # Deployment steps
```

**3. Performance Monitoring**
```typescript
// Add performance metrics
useEffect(() => {
  const measurePerformance = () => {
    const navigation = performance.getEntriesByType('navigation')[0];
    console.log('Page load time:', navigation.loadEventEnd - navigation.loadEventStart);
  };
  window.addEventListener('load', measurePerformance);
}, []);
```

**Areas for Enhancement:**
- [ ] Implement CI/CD pipeline
- [ ] Add performance budgets
- [ ] Create staging environment
- [ ] Implement feature flags
- [ ] Add error tracking (Sentry)
- [ ] Create deployment documentation
- [ ] Implement rollback strategy
- [ ] Add monitoring and alerting

## Future Roadmap

### Phase 1: Core Features (Immediate)
- [ ] Add user comment system
- [ ] Implement chart analysis UI
- [ ] Add hypothesis testing interface
- [ ] Create settings/preferences page

### Phase 2: Advanced Features (Short-term)
- [ ] Add real-time WebSocket updates
- [ ] Implement advanced charting (TradingView integration)
- [ ] Create mobile app version
- [ ] Add social features (share analyses, follow traders)

### Phase 3: AI Integration (Medium-term)
- [ ] Add voice interface for queries
- [ ] Implement natural language to chart queries
- [ ] Create AI-powered trading journal
- [ ] Add predictive analytics visualization

### Phase 4: Ecosystem (Long-term)
- [ ] Create plugin system for custom indicators
- [ ] Implement marketplace for trading strategies
- [ ] Add educational content platform
- [ ] Create community features (forums, chat)

---

**Last Updated:** 2025-01-11
**Frontend Version:** 0.1.0
**Status:** Production Ready