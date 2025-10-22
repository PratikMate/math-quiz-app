import React, { useState, useCallback, useEffect } from 'react';
import QuizInterface from './components/QuizInterface';
import ScoreBoard from './components/ScoreBoard';
import ConnectionStatus from './components/ConnectionStatus';
import { useWebSocket } from './hooks/useWebSocket';

function App() {
  const [username, setUsername] = useState<string>('');
  const [isJoined, setIsJoined] = useState<boolean>(false);
  const [showScoreBoard, setShowScoreBoard] = useState<boolean>(false);
  const [preferredDifficulty, setPreferredDifficulty] = useState<string>('medium');
  
  const {
    connectionStatus,
    quizData,
    submissionResult,
    isSubmitting,
    connect,
    disconnect,
    submitAnswer,
    requestCurrentProblem,
    requestLeaderboard,
    isConnected,
    clearSubmissionResult,
    clearError
  } = useWebSocket();

  const [submissionFeedback, setSubmissionFeedback] = useState<{
    message: string;
    type: 'success' | 'error' | 'info';
  } | null>(null);

  // Handle submission result changes
  useEffect(() => {
    if (submissionResult) {
      setSubmissionFeedback({
        message: submissionResult.message,
        type: submissionResult.isCorrect ? 'success' : 'error'
      });

      // Clear feedback after 3 seconds if not a winner
      if (!submissionResult.isCorrect) {
        const timer = setTimeout(() => {
          setSubmissionFeedback(null);
          clearSubmissionResult();
        }, 3000);
        return () => clearTimeout(timer);
      }
    }
  }, [submissionResult]); // Remove clearSubmissionResult from dependencies

  // Clear winner display after 2 seconds
  useEffect(() => {
    if (quizData.winner) {
      const timer = setTimeout(() => {
        setSubmissionFeedback(null);
        clearSubmissionResult();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [quizData.winner]); // Remove clearSubmissionResult from dependencies

  // Clear error state when successfully connected and joined
  useEffect(() => {
    if (isConnected && isJoined && connectionStatus.error) {
      clearError();
    }
  }, [isConnected, isJoined, connectionStatus.error, clearError]);

  // Save state to localStorage
  useEffect(() => {
    if (isJoined && quizData.userInfo.userId) {
      localStorage.setItem('quizState', JSON.stringify({
        username,
        isJoined,
        userId: quizData.userInfo.userId,
        preferredDifficulty
      }));
    }
  }, [isJoined, username, quizData.userInfo.userId, preferredDifficulty]);

  // Restore state on page load
  useEffect(() => {
    const saved = localStorage.getItem('quizState');
    if (saved) {
      try {
        const state = JSON.parse(saved);
        if (state.username && state.isJoined) {
          setUsername(state.username);
          setPreferredDifficulty(state.preferredDifficulty || 'medium');
          // Auto-reconnect
          connect(state.username).then(() => {
            setIsJoined(true);
          }).catch(() => {
            // Clear invalid state if reconnection fails
            localStorage.removeItem('quizState');
          });
        }
      } catch (error) {
        localStorage.removeItem('quizState');
      }
    }
  }, [connect]);

  const handleJoinQuiz = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) return;

    try {
      await connect(username.trim(), preferredDifficulty);
      setIsJoined(true);
      clearError(); // Clear any previous errors when successfully joining
    } catch (error) {
      console.error('Failed to join quiz:', error);
    }
  }, [username, preferredDifficulty, connect, clearError]);

  const handleLeaveQuiz = useCallback(() => {
    disconnect();
    setIsJoined(false);
    setSubmissionFeedback(null);
    localStorage.removeItem('quizState');
  }, [disconnect]);

  const handleRetryConnection = useCallback(async () => {
    if (username) {
      try {
        await connect(username);
      } catch (error) {
        console.error('Failed to retry connection:', error);
      }
    }
  }, [username, connect]);

  const handleSubmitAnswer = useCallback(async (answer: number) => {
    if (!quizData.currentProblem) {
      setSubmissionFeedback({
        message: 'No active problem to answer',
        type: 'error'
      });
      return;
    }

    try {
      submitAnswer(answer, quizData.currentProblem.id);
    } catch (error) {
      setSubmissionFeedback({
        message: error instanceof Error ? error.message : 'Failed to submit answer',
        type: 'error'
      });
    }
  }, [quizData.currentProblem, submitAnswer]);

  const handleRequestProblem = useCallback(() => {
    try {
      requestCurrentProblem();
    } catch (error) {
      setSubmissionFeedback({
        message: error instanceof Error ? error.message : 'Failed to request problem',
        type: 'error'
      });
    }
  }, [requestCurrentProblem]);

  const handleShowScoreBoard = useCallback(() => {
    setShowScoreBoard(true);
    try {
      requestLeaderboard();
    } catch (error) {
      console.error('Failed to request leaderboard:', error);
    }
  }, [requestLeaderboard]);

  const handleCloseScoreBoard = useCallback(() => {
    setShowScoreBoard(false);
  }, []);

  // Show join form if not connected or joined
  if (!isJoined || !isConnected) {
    return (
      <div className="min-h-screen bg-gray-100 py-8 px-4">
        <div className="max-w-md mx-auto">
          <header className="text-center mb-8">
            <h1 className="text-4xl font-bold text-gray-800 mb-2">
              Competitive Math Quiz
            </h1>
            <p className="text-gray-600">
              Compete with others to solve math problems first!
            </p>
          </header>

          <div className="bg-white p-8 rounded-lg shadow-md">
            {connectionStatus.connecting && (
              <div className="text-center mb-4">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
                <p className="text-gray-600">Connecting to server...</p>
              </div>
            )}

            {connectionStatus.reconnecting && (
              <div className="text-center mb-4">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600 mx-auto mb-2"></div>
                <p className="text-yellow-600">
                  Reconnecting... (Attempt {connectionStatus.reconnectAttempt})
                </p>
              </div>
            )}

            {connectionStatus.error && (
              <div className="bg-red-100 border border-red-200 text-red-800 p-4 rounded-lg mb-4">
                <p className="font-semibold">Connection Error</p>
                <p className="text-sm">{connectionStatus.error}</p>
                <button
                  onClick={clearError}
                  className="mt-2 text-sm underline hover:no-underline"
                >
                  Dismiss
                </button>
              </div>
            )}

            <form onSubmit={handleJoinQuiz} className="space-y-4">
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-2">
                  Enter your username:
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={connectionStatus.connecting}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Your username..."
                  maxLength={20}
                  required
                />
              </div>

              <div>
                <label htmlFor="difficulty" className="block text-sm font-medium text-gray-700 mb-2">
                  Preferred difficulty:
                </label>
                <select
                  id="difficulty"
                  value={preferredDifficulty}
                  onChange={(e) => setPreferredDifficulty(e.target.value)}
                  disabled={connectionStatus.connecting}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="easy">Easy - Basic arithmetic</option>
                  <option value="medium">Medium - Algebra & fractions</option>
                  <option value="hard">Hard - Advanced math</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={connectionStatus.connecting || !username.trim()}
                className={`w-full py-3 px-6 text-lg font-semibold rounded-lg transition-colors ${
                  connectionStatus.connecting || !username.trim()
                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-2 focus:ring-blue-500'
                }`}
              >
                {connectionStatus.connecting ? 'Connecting...' : 'Join Quiz'}
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <header className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">
            Competitive Math Quiz
          </h1>
          <p className="text-gray-600">
            Welcome, {quizData.userInfo.username}! Compete with others to solve math problems first!
          </p>
          <div className="mt-4 flex justify-center items-center space-x-4 text-sm text-gray-500">
            <span>Active Users: {quizData.activeUsersCount}</span>
            <span>•</span>
            <span className={`flex items-center ${isConnected ? 'text-green-600' : 'text-red-600'}`}>
              <div className={`w-2 h-2 rounded-full mr-1 ${isConnected ? 'bg-green-600' : 'bg-red-600'}`}></div>
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
            <span>•</span>
            <button
              onClick={handleShowScoreBoard}
              className="text-blue-600 hover:text-blue-800 underline"
            >
              Leaderboard
            </button>
            <span>•</span>
            <button
              onClick={handleLeaveQuiz}
              className="text-red-600 hover:text-red-800 underline"
            >
              Leave Quiz
            </button>
          </div>
        </header>

        {/* Connection Status Indicator */}
        <div className="mb-6">
          <ConnectionStatus 
            connectionStatus={connectionStatus}
            onRetry={handleRetryConnection}
          />
        </div>

        <main className="mb-8">
          <QuizInterface
            currentProblem={quizData.currentProblem}
            winner={quizData.winner}
            isSubmitting={isSubmitting}
            onSubmitAnswer={handleSubmitAnswer}
            onRequestNewProblem={handleRequestProblem}
            submissionResult={submissionResult}
          />
        </main>

        {!quizData.currentProblem && !quizData.winner && (
          <div className="max-w-2xl mx-auto text-center mb-4">
            <div className="flex items-center justify-center gap-4">
              <select
                value={preferredDifficulty}
                onChange={(e) => setPreferredDifficulty(e.target.value)}
                disabled={!isConnected}
                className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
              <button
                onClick={handleRequestProblem}
                disabled={!isConnected}
                className={`px-6 py-2 rounded-lg font-medium ${
                  isConnected
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                }`}
              >
                Request New Problem
              </button>
            </div>
          </div>
        )}

        {submissionFeedback && (
          <div className={`max-w-2xl mx-auto p-4 rounded-lg text-center ${
            submissionFeedback.type === 'success' 
              ? 'bg-green-100 text-green-800 border border-green-200'
              : submissionFeedback.type === 'error'
              ? 'bg-red-100 text-red-800 border border-red-200'
              : 'bg-blue-100 text-blue-800 border border-blue-200'
          }`}>
            {submissionFeedback.message}
          </div>
        )}

        <footer className="text-center text-sm text-gray-500 mt-8">
          <p>
            Status: {isSubmitting ? 'Submitting...' : isConnected ? 'Ready' : 'Disconnected'}
            {connectionStatus.reconnecting && ` • Reconnecting (${connectionStatus.reconnectAttempt})`}
          </p>
        </footer>

        {/* ScoreBoard Modal */}
        <ScoreBoard
          leaderboard={quizData.leaderboard}
          sessionStats={quizData.sessionStats}
          currentUserId={quizData.userInfo.userId || undefined}
          isVisible={showScoreBoard}
          onClose={handleCloseScoreBoard}
        />
      </div>
    </div>
  );
}

export default App;