import { motion } from 'framer-motion';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  text?: string;
  className?: string;
}

export function LoadingSpinner({ size = 'md', text, className = '' }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  };

  return (
    <div className={`flex flex-col items-center justify-center ${className}`}>
      <motion.div
        className={`${sizeClasses[size]} border-2 border-blue-500 border-t-transparent rounded-full`}
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      />
      {text && (
        <motion.p
          className="mt-3 text-gray-400 text-sm"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          {text}
        </motion.p>
      )}
    </div>
  );
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-gray-900 rounded-lg p-6 border border-gray-800 ${className}`}>
      <div className="animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-3/4 mb-4"></div>
        <div className="h-8 bg-gray-700 rounded w-1/2 mb-2"></div>
        <div className="h-4 bg-gray-700 rounded w-1/4"></div>
      </div>
    </div>
  );
}

export function MarketDataSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}