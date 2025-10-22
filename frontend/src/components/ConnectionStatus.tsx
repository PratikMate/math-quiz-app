import React from 'react';
import { ConnectionStatus as ConnectionStatusType } from '../hooks/useWebSocket';

interface ConnectionStatusProps {
  connectionStatus: ConnectionStatusType;
  onRetry?: () => void;
}

const ConnectionStatus: React.FC<ConnectionStatusProps> = ({ 
  connectionStatus, 
  onRetry 
}) => {
  const getStatusColor = () => {
    if (!connectionStatus.connected) return 'text-red-500';
    
    switch (connectionStatus.quality) {
      case 'excellent': return 'text-green-500';
      case 'good': return 'text-yellow-500';
      case 'poor': return 'text-orange-500';
      default: return 'text-gray-500';
    }
  };

  const getStatusIcon = () => {
    if (connectionStatus.connecting || connectionStatus.reconnecting) {
      return (
        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
      );
    }
    
    if (!connectionStatus.connected) {
      return <span className="text-lg">⚠️</span>;
    }
    
    switch (connectionStatus.quality) {
      case 'excellent': return <span className="text-lg">🟢</span>;
      case 'good': return <span className="text-lg">🟡</span>;
      case 'poor': return <span className="text-lg">🟠</span>;
      default: return <span className="text-lg">⚪</span>;
    }
  };

  const getStatusText = () => {
    if (connectionStatus.connecting) {
      return 'Connecting...';
    }
    
    if (connectionStatus.reconnecting) {
      return `Reconnecting... (${connectionStatus.reconnectAttempt}/10)`;
    }
    
    if (!connectionStatus.connected) {
      return 'Disconnected';
    }
    
    let text = `Connected (${connectionStatus.quality})`;
    if (connectionStatus.latency) {
      text += ` - ${connectionStatus.latency}ms`;
    }
    
    return text;
  };

  const formatRetryTime = (ms: number) => {
    const seconds = Math.ceil(ms / 1000);
    return `${seconds}s`;
  };

  return (
    <div className="flex items-center justify-between bg-white border rounded-lg p-3 shadow-sm">
      <div className="flex items-center space-x-2">
        {getStatusIcon()}
        <span className={`text-sm font-medium ${getStatusColor()}`}>
          {getStatusText()}
        </span>
        
        {connectionStatus.nextRetryIn && (
          <span className="text-xs text-gray-500">
            (retry in {formatRetryTime(connectionStatus.nextRetryIn)})
          </span>
        )}
      </div>
      
      <div className="flex items-center space-x-3">
        {connectionStatus.pendingSubmissions > 0 && (
          <div className="flex items-center space-x-1">
            <span className="text-xs text-orange-600">
              📤 {connectionStatus.pendingSubmissions} pending
            </span>
          </div>
        )}
        
        {connectionStatus.error && (
          <div className="text-xs text-red-600 max-w-xs truncate" title={connectionStatus.error}>
            {connectionStatus.error}
          </div>
        )}
        
        {!connectionStatus.connected && !connectionStatus.connecting && !connectionStatus.reconnecting && onRetry && (
          <button
            onClick={onRetry}
            className="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
};

export default ConnectionStatus;