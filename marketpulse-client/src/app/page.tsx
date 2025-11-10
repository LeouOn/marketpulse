import { MarketDashboard } from "@/components/market-dashboard";

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="container mx-auto px-4 py-8">
        <header className="mb-8">
          <h1 className="text-4xl font-bold text-blue-400 mb-2">MarketPulse</h1>
          <p className="text-gray-400">Real-time Market Internals Analysis</p>
        </header>
        
        <MarketDashboard />
      </div>
    </main>
  );
}