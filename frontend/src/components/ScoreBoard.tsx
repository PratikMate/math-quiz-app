import React from 'react';

interface UserScore {
  user_id: string;
  username: string;
  session_wins: number;
  session_problems_attempted: number;
  average_response_time_ms: number;
  fastest_response_time_ms?: number;
  rank: number;
}

interface SessionStats {
  total_players: number;
  total_wins: number;
  total_attempts: number;
  average_response_time_ms: number;
  fastest_response_time_ms?: number;
}

interface ScoreBoardProps {
  leaderboard: UserScore[];
  sessionStats?: SessionStats;
  currentUserId?: string;
  isVisible: boolean;
  onClose?: () => void;
}

const ScoreBoard: React.FC<ScoreBoardProps> = ({
  leaderboard,
  sessionStats,
  currentUserId,
  isVisible,
  onClose
}) => {
  if (!isVisible) return null;

  const formatTime = (timeMs?: number): string => {
    if (!timeMs) return 'N/A';
    if (timeMs < 1000) return `${timeMs}ms`;
    return `${(timeMs / 1000).toFixed(1)}s`;
  };

  const getRankIcon = (rank: number): string => {
    switch (rank) {
      case 1: return '🥇';
      case 2: return '🥈';
      case 3: return '🥉';
      default: return `#${rank}`;
    }
  };

  const getRankColor = (rank: number): string => {
    switch (rank) {
      case 1: return 'text-yellow-600 bg-yellow-50';
      case 2: return 'text-gray-600 bg-gray-50';
      case 3: return 'text-orange-600 bg-orange-50';
      default: return 'text-gray-700 bg-white';
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-2xl font-bold">🏆 Leaderboard</h2>
              <p className="text-blue-100 mt-1">Current Session Rankings</p>
            </div>
            {onClose && (
              <button
                onClick={onClose}
                className="text-white hover:text-gray-200 text-2xl font-bold"
                aria-label="Close leaderboard"
              >
                ×
              </button>
            )}
          </div>
        </div>

        <div className="overflow-y-auto max-h-[calc(90vh-200px)]">
          {/* Session Stats */}
          {sessionStats && (
            <div className="p-4 bg-gray-50 border-b">
              <h3 className="text-lg font-semibold text-gray-800 mb-3">Session Statistics</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div className="text-center">
                  <div className="text-2xl font-bold text-blue-600">{sessionStats.total_players}</div>
                  <div className="text-gray-600">Players</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-600">{sessionStats.total_wins}</div>
                  <div className="text-gray-600">Total Wins</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-600">{sessionStats.total_attempts}</div>
                  <div className="text-gray-600">Attempts</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-orange-600">
                    {formatTime(sessionStats.average_response_time_ms)}
                  </div>
                  <div className="text-gray-600">Avg Time</div>
                </div>
              </div>
            </div>
          )}

          {/* Leaderboard */}
          <div className="p-4">
            {leaderboard.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <div className="text-4xl mb-2">🎯</div>
                <p>No scores yet. Be the first to solve a problem!</p>
              </div>
            ) : (
              <div className="space-y-2">
                {leaderboard.map((user) => (
                  <div
                    key={user.user_id}
                    className={`
                      flex items-center justify-between p-4 rounded-lg border transition-all
                      ${user.user_id === currentUserId 
                        ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200' 
                        : 'border-gray-200 hover:border-gray-300'
                      }
                      ${getRankColor(user.rank)}
                    `}
                  >
                    {/* Rank and User Info */}
                    <div className="flex items-center space-x-4">
                      <div className="text-2xl font-bold min-w-[3rem] text-center">
                        {getRankIcon(user.rank)}
                      </div>
                      <div>
                        <div className="font-semibold text-gray-800">
                          {user.username}
                          {user.user_id === currentUserId && (
                            <span className="ml-2 text-xs bg-blue-500 text-white px-2 py-1 rounded-full">
                              You
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-600">
                          {user.session_problems_attempted} attempt{user.session_problems_attempted !== 1 ? 's' : ''}
                        </div>
                      </div>
                    </div>

                    {/* Stats */}
                    <div className="text-right">
                      <div className="flex items-center space-x-4">
                        {/* Wins */}
                        <div className="text-center">
                          <div className="text-lg font-bold text-green-600">
                            {user.session_wins}
                          </div>
                          <div className="text-xs text-gray-500">wins</div>
                        </div>

                        {/* Average Time */}
                        {user.session_wins > 0 && (
                          <div className="text-center">
                            <div className="text-sm font-semibold text-blue-600">
                              {formatTime(user.average_response_time_ms)}
                            </div>
                            <div className="text-xs text-gray-500">avg time</div>
                          </div>
                        )}

                        {/* Fastest Time */}
                        {user.fastest_response_time_ms && (
                          <div className="text-center">
                            <div className="text-sm font-semibold text-purple-600">
                              {formatTime(user.fastest_response_time_ms)}
                            </div>
                            <div className="text-xs text-gray-500">fastest</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-gray-50 border-t">
          <div className="flex justify-between items-center text-sm text-gray-600">
            <div>
              Showing top {Math.min(leaderboard.length, 10)} players
            </div>
            <div>
              Updated in real-time
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScoreBoard;