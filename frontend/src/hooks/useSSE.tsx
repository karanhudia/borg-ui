import { useEffect, useRef, useState, useCallback } from 'react';
import { eventsAPI } from '../services/api';

interface SSEEvent {
  type: string;
  data: any;
  timestamp: string;
}

interface UseSSEReturn {
  isConnected: boolean;
  lastEvent: SSEEvent | null;
  events: SSEEvent[];
  connect: () => void;
  disconnect: () => void;
  clearEvents: () => void;
}

export const useSSE = (): UseSSEReturn => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const eventSource = eventsAPI.streamEvents();
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        // Only log once on initial connection, not on every reconnect
        console.log('[SSE] Connected');
      };

      eventSource.onmessage = (event) => {
        try {
          const sseEvent: SSEEvent = JSON.parse(event.data);
          setLastEvent(sseEvent);
          setEvents(prev => {
            const newEvents = [...prev, sseEvent];
            // Keep only last 100 events to prevent memory issues
            return newEvents.length > 100 ? newEvents.slice(-100) : newEvents;
          });
        } catch (error) {
          console.error('[SSE] Failed to parse event:', error);
        }
      };

      eventSource.onerror = () => {
        console.warn('[SSE] Connection lost, will retry...');
        setIsConnected(false);
      };

    } catch (error) {
      console.error('[SSE] Failed to create connection:', error);
      setIsConnected(false);
    }
  }, []); // Remove events.length dependency - this was causing reconnects!

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLastEvent(null);
  }, []);

  useEffect(() => {
    // Auto-connect on mount
    connect();

    // Cleanup on unmount
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected,
    lastEvent,
    events,
    connect,
    disconnect,
    clearEvents,
  };
};

// Hook for specific event types
export const useSSEEvent = (eventType: string) => {
  const { events, isConnected } = useSSE();
  
  const filteredEvents = events.filter(event => event.type === eventType);
  const lastEvent = filteredEvents[filteredEvents.length - 1] || null;
  
  return {
    events: filteredEvents,
    lastEvent,
    isConnected,
  };
};

// Hook for backup progress
export const useBackupProgress = (jobId?: string) => {
  const { events, isConnected } = useSSE();
  
  const backupEvents = events.filter(event => 
    event.type === 'backup_progress' && 
    (!jobId || event.data.job_id === jobId)
  );
  
  const lastProgress = backupEvents[backupEvents.length - 1] || null;
  
  return {
    progress: lastProgress?.data || null,
    isConnected,
    allProgress: backupEvents,
  };
};

// Hook for system status
export const useSystemStatus = () => {
  const { lastEvent, isConnected } = useSSE();
  
  const systemStatus = lastEvent?.type === 'system_status' ? lastEvent.data : null;
  
  return {
    systemStatus,
    isConnected,
  };
};
