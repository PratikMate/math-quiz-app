import { useState, useEffect, useCallback, useRef } from 'react';
import { websocketService, WebSocketEvents } from '../services/websocket';
import { MathProblem, Winner, UserScore, SessionStats } from '../types';

export interface ConnectionStatus {
  connected: boolean;
  connecting: boolean;
  error: string | null;
  reconnecting: boolean;
  reconnectAttempt: number;
  quality: 'excellent' | 'good' | 'poor' | 'disconnected';
  nextRetryIn?: number;
  latency?: number;
  pendingSubmissions: number;
}

export interface QuizData {
  currentProblem: MathProblem | null;
  winner: Winner | null;
  activeUsersCount: number;
  leaderboard: UserScore[];
  sessionStats?: SessionStats;
  userInfo: {
    userId: string | null;
    username: string | null;
  };
}

export interface SubmissionResult {
  isCorrect: boolean;
  submittedAnswer: number;
  feedback?: string;
  message: string;
}

export const useWebSocket = (username?: string) => {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    connected: false,
    connecting: false,
    error: null,
    reconnecting: false,
    reconnectAttempt: 0,
    quality: 'disconnected',
    pendingSubmissions: 0
  });

  const [quizData, setQuizData] = useState<QuizData>({
    currentProblem: null,
    winner: null,
    activeUsersCount: 0,
    leaderboard: [],
    sessionStats: undefined,
    userInfo: {
      userId: null,
      username: null
    }
  });

  const [submissionResult, setSubmissionResult] = useState<SubmissionResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Use refs to store latest values for event handlers
  const quizDataRef = useRef(quizData);
  const connectionStatusRef = useRef(connectionStatus);
  
  useEffect(() => {
    quizDataRef.current = quizData;
  }, [quizData]);

  useEffect(() => {
    connectionStatusRef.current = connectionStatus;
  }, [connectionStatus]);

  // Event handlers
  const handleConnected = useCallback((data: Parameters<WebSocketEvents['connected']>[0]) => {
    console.log('WebSocket connected:', data);
    setConnectionStatus(prev => ({
      ...prev,
      connected: true,
      connecting: false,
      error: null,
      reconnecting: false
    }));
  }, []);

  const handleQuizJoined = useCallback((data: Parameters<WebSocketEvents['quiz_joined']>[0]) => {
    console.log('Joined quiz:', data);
    setQuizData(prev => ({
      ...prev,
      activeUsersCount: data.active_users_count,
      userInfo: {
        userId: data.user_id,
        username: data.username
      }
    }));
  }, []);

  const handleNewProblem = useCallback((data: Parameters<WebSocketEvents['new_problem']>[0]) => {
    console.log('New problem received:', data);
    setQuizData(prev => ({
      ...prev,
      currentProblem: data.problem,
      winner: null // Clear previous winner
    }));
    setSubmissionResult(null); // Clear previous submission result
    setIsSubmitting(false); // Reset submitting state
    
    // Clear any pending submission tracking
    websocketService.clearSubmissionTracking();
  }, []);

  const handleWinnerAnnounced = useCallback((data: Parameters<WebSocketEvents['winner_announced']>[0]) => {
    console.log('Winner announced:', data);
    const winner: Winner = {
      userId: data.winner.user_id,
      username: data.winner.username,
      correctAnswer: data.winner.correct_answer,
      responseTime: 0 // Will be calculated on server side later
    };
    
    setQuizData(prev => ({
      ...prev,
      winner
    }));
  }, []);

  const handleAnswerReceived = useCallback((data: Parameters<WebSocketEvents['answer_received']>[0]) => {
    console.log('Answer received:', data);
    setSubmissionResult({
      isCorrect: data.is_correct,
      submittedAnswer: data.submitted_answer,
      feedback: data.feedback,
      message: data.message
    });
    setIsSubmitting(false);
  }, []);

  const handleUserJoined = useCallback((data: Parameters<WebSocketEvents['user_joined']>[0]) => {
    console.log('User joined:', data);
    setQuizData(prev => ({
      ...prev,
      activeUsersCount: data.active_users_count
    }));
  }, []);

  const handleUserLeft = useCallback((data: Parameters<WebSocketEvents['user_left']>[0]) => {
    console.log('User left:', data);
    setQuizData(prev => ({
      ...prev,
      activeUsersCount: data.active_users_count
    }));
  }, []);

  const handleLeaderboardUpdate = useCallback((data: Parameters<WebSocketEvents['leaderboard_update']>[0]) => {
    console.log('Leaderboard updated:', data);
    setQuizData(prev => ({
      ...prev,
      leaderboard: data.leaderboard,
      sessionStats: data.session_stats
    }));
  }, []);

  const handleLeaderboardData = useCallback((data: any) => {
    console.log('Leaderboard data received:', data);
    setQuizData(prev => ({
      ...prev,
      leaderboard: data.leaderboard,
      sessionStats: data.session_stats
    }));
  }, []);

  const handleError = useCallback((data: Parameters<WebSocketEvents['error']>[0]) => {
    console.error('WebSocket error:', data);
    setConnectionStatus(prev => ({
      ...prev,
      error: data.message
    }));
    setIsSubmitting(false);
  }, []);

  const handleConnectionStatus = useCallback((status: {
    connected: boolean;
    quality?: 'excellent' | 'good' | 'poor' | 'disconnected';
    reason?: string;
    reconnecting?: boolean;
    reconnected?: boolean;
    attempt?: number;
    reconnectFailed?: boolean;
    error?: string;
    nextRetryIn?: number;
    latency?: number;
  }) => {
    console.log('Connection status changed:', status);
    
    setConnectionStatus(prev => ({
      ...prev,
      connected: status.connected,
      reconnecting: status.reconnecting || false,
      reconnectAttempt: status.attempt || prev.reconnectAttempt,
      quality: status.quality || prev.quality,
      nextRetryIn: status.nextRetryIn,
      latency: status.latency,
      pendingSubmissions: websocketService.getPendingSubmissionsCount(),
      error: status.reconnectFailed 
        ? 'Failed to reconnect to server' 
        : status.error || (status.connected ? null : prev.error)
    }));

    // Clear quiz data if disconnected and not reconnecting
    if (!status.connected && !status.reconnecting) {
      setQuizData(prev => ({
        ...prev,
        currentProblem: null,
        winner: null,
        activeUsersCount: 0
      }));
    }
  }, []);

  // Connect to WebSocket
  const connect = useCallback(async (connectUsername?: string, difficulty?: string) => {
    const usernameToUse = connectUsername || username;
    
    setConnectionStatus(prev => ({
      ...prev,
      connecting: true,
      error: null
    }));

    try {
      await websocketService.connect(usernameToUse, difficulty);
    } catch (error) {
      console.error('Failed to connect:', error);
      setConnectionStatus(prev => ({
        ...prev,
        connecting: false,
        error: error instanceof Error ? error.message : 'Connection failed'
      }));
    }
  }, [username]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    websocketService.disconnect();
    setConnectionStatus({
      connected: false,
      connecting: false,
      error: null,
      reconnecting: false,
      reconnectAttempt: 0,
      quality: 'disconnected',
      pendingSubmissions: 0
    });
    setQuizData({
      currentProblem: null,
      winner: null,
      activeUsersCount: 0,
      leaderboard: [],
      sessionStats: undefined,
      userInfo: {
        userId: null,
        username: null
      }
    });
  }, []);

  // Submit answer with timeout and error handling
  const submitAnswer = useCallback(async (answer: string | number, problemId: string) => {
    setIsSubmitting(true);
    setSubmissionResult(null);
    
    try {
      await websocketService.submitAnswer(answer, problemId);
      // Success will be handled by answer_received event
    } catch (error) {
      console.error('Failed to submit answer:', error);
      setIsSubmitting(false);
      
      const errorMessage = error instanceof Error ? error.message : 'Failed to submit answer';
      
      // Update pending submissions count
      setConnectionStatus(prev => ({
        ...prev,
        pendingSubmissions: websocketService.getPendingSubmissionsCount()
      }));
      
      // Provide specific error messages based on error type
      let userMessage = errorMessage;
      let messageType: 'error' | 'info' = 'error';
      
      if (errorMessage.includes('already submitted')) {
        userMessage = 'You have already submitted an answer for this problem.';
      } else if (errorMessage.includes('already in progress')) {
        userMessage = 'Please wait, your previous submission is still being processed.';
      } else if (errorMessage.includes('queued for retry')) {
        userMessage = 'Connection lost. Your answer will be submitted when connection is restored.';
        messageType = 'info';
      } else if (errorMessage.includes('timed out')) {
        userMessage = 'Submission timed out. Your answer has been queued for retry.';
        messageType = 'info';
      } else if (!connectionStatus.connected) {
        userMessage = 'Not connected to server. Answer queued for when connection is restored.';
        messageType = 'info';
      }
      
      // Show user-friendly error message
      setSubmissionResult({
        isCorrect: false,
        submittedAnswer: typeof answer === 'number' ? answer : parseFloat(answer.toString()),
        message: userMessage,
        feedback: messageType === 'info' ? 'Your answer is saved and will be submitted automatically.' : undefined
      });
    }
  }, [connectionStatus.connected]);

  // Request current problem
  const requestCurrentProblem = useCallback(() => {
    if (!connectionStatus.connected) {
      throw new Error('Not connected to server');
    }

    try {
      websocketService.requestCurrentProblem();
    } catch (error) {
      console.error('Failed to request current problem:', error);
      setConnectionStatus(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to request problem'
      }));
    }
  }, [connectionStatus.connected]);

  // Request leaderboard
  const requestLeaderboard = useCallback(() => {
    if (!connectionStatus.connected) {
      throw new Error('Not connected to server');
    }

    try {
      websocketService.emit('get_leaderboard', {});
    } catch (error) {
      console.error('Failed to request leaderboard:', error);
      setConnectionStatus(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to request leaderboard'
      }));
    }
  }, [connectionStatus.connected]);

  // Set up event listeners
  useEffect(() => {
    // Add event listeners
    websocketService.addEventListener('connected', handleConnected);
    websocketService.addEventListener('quiz_joined', handleQuizJoined);
    websocketService.addEventListener('new_problem', handleNewProblem);
    websocketService.addEventListener('winner_announced', handleWinnerAnnounced);
    websocketService.addEventListener('answer_received', handleAnswerReceived);
    websocketService.addEventListener('user_joined', handleUserJoined);
    websocketService.addEventListener('user_left', handleUserLeft);
    websocketService.addEventListener('leaderboard_update', handleLeaderboardUpdate);
    websocketService.addEventListener('leaderboard_data', handleLeaderboardData);
    websocketService.addEventListener('error', handleError);
    websocketService.onConnectionStatus(handleConnectionStatus);

    // Cleanup function
    return () => {
      websocketService.removeEventListener('connected', handleConnected);
      websocketService.removeEventListener('quiz_joined', handleQuizJoined);
      websocketService.removeEventListener('new_problem', handleNewProblem);
      websocketService.removeEventListener('winner_announced', handleWinnerAnnounced);
      websocketService.removeEventListener('answer_received', handleAnswerReceived);
      websocketService.removeEventListener('user_joined', handleUserJoined);
      websocketService.removeEventListener('user_left', handleUserLeft);
      websocketService.removeEventListener('leaderboard_update', handleLeaderboardUpdate);
      websocketService.removeEventListener('leaderboard_data', handleLeaderboardData);
      websocketService.removeEventListener('error', handleError);
    };
  }, [
    handleConnected,
    handleQuizJoined,
    handleNewProblem,
    handleWinnerAnnounced,
    handleAnswerReceived,
    handleUserJoined,
    handleUserLeft,
    handleLeaderboardUpdate,
    handleLeaderboardData,
    handleError,
    handleConnectionStatus
  ]);

  // Auto-connect on mount if username is provided
  useEffect(() => {
    if (username && !connectionStatus.connected && !connectionStatus.connecting) {
      connect(username);
    }
  }, [username, connectionStatus.connected, connectionStatus.connecting, connect]);

  return {
    // Connection state
    connectionStatus,
    
    // Quiz data
    quizData,
    
    // Submission state
    submissionResult,
    isSubmitting,
    
    // Actions
    connect,
    disconnect,
    submitAnswer,
    requestCurrentProblem,
    requestLeaderboard,
    
    // Utilities
    isConnected: connectionStatus.connected,
    clearSubmissionResult: () => setSubmissionResult(null),
    clearError: () => setConnectionStatus(prev => ({ ...prev, error: null }))
  };
};