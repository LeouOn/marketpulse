'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { DashboardData } from '@/types/market';
import { config } from '@/lib/config';

export interface WebSocketState {
  data: DashboardData | null;
  connected: boolean;
  error: string | null;
  reconnecting: boolean;
}

export interface UseMarketWebSocketOptions {
  autoConnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  onData?: (data: DashboardData) => void;
}

/**
 * Custom hook for WebSocket connection to MarketPulse API
 * Provides automatic reconnection and state management
 */
export function useMarketWebSocket(options: UseMarketWebSocketOptions = {}) {
  const {
    autoConnect = true,
    reconnectInterval = 5000,
    maxReconnectAttempts = 10,
    onConnect,
    onDisconnect,
    onError,
    onData,
  } = options;

  const [state, setState] = useState<WebSocketState>({
    data: null,
    connected: false,
    error: null,
    reconnecting: false,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    // Don't connect if WebSocket is disabled
    if (!config.features.websocket) {
      console.log('WebSocket is disabled in config');
      return;
    }

    // Don't create a new connection if one already exists
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const wsUrl = `${config.api.wsUrl}/api/market/stream`;
      console.log('Connecting to WebSocket:', wsUrl);

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        reconnectCountRef.current = 0;
        setState((prev) => ({
          ...prev,
          connected: true,
          error: null,
          reconnecting: false,
        }));
        onConnect?.();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as DashboardData;
          setState((prev) => ({
            ...prev,
            data,
            error: null,
          }));
          onData?.(data);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
          setState((prev) => ({
            ...prev,
            error: 'Failed to parse server message',
          }));
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setState((prev) => ({
          ...prev,
          error: 'WebSocket connection error',
        }));
        onError?.(error);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setState((prev) => ({
          ...prev,
          connected: false,
        }));
        onDisconnect?.();

        // Attempt to reconnect
        if (reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current += 1;
          setState((prev) => ({
            ...prev,
            reconnecting: true,
          }));

          console.log(
            `Reconnecting... (attempt ${reconnectCountRef.current}/${maxReconnectAttempts})`
          );

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        } else {
          console.error('Max reconnection attempts reached');
          setState((prev) => ({
            ...prev,
            reconnecting: false,
            error: 'Failed to reconnect to server',
          }));
        }
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setState((prev) => ({
        ...prev,
        error: 'Failed to create WebSocket connection',
      }));
    }
  }, [reconnectInterval, maxReconnectAttempts, onConnect, onDisconnect, onError, onData]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setState({
      data: null,
      connected: false,
      error: null,
      reconnecting: false,
    });
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    reconnectCountRef.current = 0;
    connect();
  }, [connect, disconnect]);

  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return {
    ...state,
    connect,
    disconnect,
    reconnect,
  };
}
