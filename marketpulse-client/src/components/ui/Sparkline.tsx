'use client';

import React from 'react';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  showDots?: boolean;
  className?: string;
}

export function Sparkline({
  data,
  width = 80,
  height = 24,
  color,
  showDots = false,
  className = ''
}: SparklineProps) {
  if (!data || data.length < 2) {
    return <div className={`${className}`} style={{ width, height }} />;
  }

  // Calculate min and max for scaling
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1; // Prevent division by zero

  // Scale data points to fit in the SVG
  const scaleX = width / (data.length - 1);
  const scaleY = height / range;

  // Generate SVG path
  const pathData = data.map((value, index) => {
    const x = index * scaleX;
    const y = height - (value - min) * scaleY;
    return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');

  // Determine trend and color
  const isUp = data[data.length - 1] >= data[0];
  const strokeColor = color || (isUp ? '#10b981' : '#ef4444');

  return (
    <svg
      width={width}
      height={height}
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      {/* Line */}
      <path
        d={pathData}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />

      {/* Optional dots at data points */}
      {showDots && data.map((value, index) => {
        const x = index * scaleX;
        const y = height - (value - min) * scaleY;
        return (
          <circle
            key={index}
            cx={x}
            cy={y}
            r="1.5"
            fill={strokeColor}
          />
        );
      })}

      {/* Highlight last point */}
      <circle
        cx={(data.length - 1) * scaleX}
        cy={height - (data[data.length - 1] - min) * scaleY}
        r="2"
        fill={strokeColor}
        opacity="0.8"
      />
    </svg>
  );
}

export function SparklineArea({
  data,
  width = 80,
  height = 24,
  color,
  className = ''
}: SparklineProps) {
  if (!data || data.length < 2) {
    return <div className={`${className}`} style={{ width, height }} />;
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const scaleX = width / (data.length - 1);
  const scaleY = height / range;

  // Generate SVG path for line
  const linePath = data.map((value, index) => {
    const x = index * scaleX;
    const y = height - (value - min) * scaleY;
    return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');

  // Generate area path (close the path at the bottom)
  const areaPath = linePath + ` L ${width} ${height} L 0 ${height} Z`;

  const isUp = data[data.length - 1] >= data[0];
  const strokeColor = color || (isUp ? '#10b981' : '#ef4444');
  const fillColor = isUp ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';

  return (
    <svg
      width={width}
      height={height}
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      {/* Area fill */}
      <path
        d={areaPath}
        fill={fillColor}
        opacity="0.5"
      />

      {/* Line */}
      <path
        d={linePath}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
