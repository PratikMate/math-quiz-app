import { io, Socket } from 'socket.io-client';
import { MathProblem, UserScore } from '../types';

export interface WebSocketEvents {
  // Server to client events
  connected: (data: { message: string; timestamp: string }) => void;
  quiz_joined: (data: { 
    message: string; 
    user_id: string; 
    username: string; 
    active_users_count: number 
  }) => void;
  new_problem: (data: { problem: MathProblem }) => void;
  winner_announced: (data: { 
    winner: {
      user_id: string;
      username: string;
      answer: number;
      correct_answer: number;
    };
    problem: {
      id: string;
      question: string;
    };
  }) => void;
  answer_received: (data: { 
    message: string; 
    is_correct: boolean; 
    submitted_answer: number;
    feedback?: string;
  }) => void;
  user_joined: (data: { 
    user_id: string; 
    username: string; 
    active_users_count: number 
  }) => void;
  user_left: (data: { 
    user_id: string; 
    username: string; 
    active_users_count: number 
  }) => void;
  leaderboard_update: (data: { leaderboard: UserScore[]; session_stats?: any }) => void;
  leaderboard_data: (data: { leaderboard: UserScore[]; session_stats?: any }) => void;
  quiz_stats: (data: { 
    active_users_count: number; 
    current_problem_id: string | null;
    users: Array<{
      user_id: string;
      username: string;
      score: number;
      wins: number;
    }>;
  }) => void;
  error: (data: { message: string; error?: string }) => void;
}

export interface WebSocketEmitEvents {
  // Client to server events
  join_quiz: (data: { username?: string; preferred_difficulty?: string }) => void;
  submit_answer: (data: { answer: string | number; problem_id: string }) => void;
  request_current_problem: (data?: any) => void;
  get_quiz_stats: (data?: any) => void;
  get_leaderboard: (data?: any) => void;
}

export class WebSocketService {
  private socket: Socket<WebSocketEvents, WebSocketEmitEvents> | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseReconnectDelay = 1000; // Start with 1 second
  private maxReconnectDelay = 30000; // Max 30 seconds
  private isConnecting = false;
  private eventListeners: Map<string, Function[]> = new Map();
  private pendingSubmissions: Map<string, { answer: string | number; problemId: string; timestamp: number; retries: number }> = new Map();
  private activeSubmissions: Map<string, { timeoutId: number; timestamp: number }> = new Map();
  private submittedProblems: Set<string> = new Set();
  private maxSubmissionRetries = 3;
  private submissionTimeout = 30000; // 30 seconds
  private connectionQuality: 'excellent' | 'good' | 'poor' | 'disconnected' = 'disconnected';
  private pingInterval: number | null = null;

  constructor(private serverUrl: string = 'http://localhost:8000') {}

  /**
   * Connect to the WebSocket server with automatic reconnection and exponential backoff
   */
  connect(username?: string, difficulty?: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.socket?.connected) {
        resolve();
        return;
      }

      if (this.isConnecting) {
        reject(new Error('Connection already in progress'));
        return;
      }

      this.isConnecting = true;
      this.connectionQuality = 'disconnected';

      try {
        // Calculate exponential backoff delay
        const currentDelay = Math.min(
          this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
          this.maxReconnectDelay
        );

        this.socket = io(this.serverUrl, {
          transports: ['websocket', 'polling'],
          timeout: 10000,
          reconnection: true,
          reconnectionAttempts: this.maxReconnectAttempts,
          reconnectionDelay: currentDelay,
          reconnectionDelayMax: this.maxReconnectDelay,
          randomizationFactor: 0.5 // Add jitter to prevent thundering herd
        });

        // Connection successful
        this.socket.on('connect', () => {
          console.log('Connected to quiz server');
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          this.connectionQuality = 'excellent';
          
          // Start connection quality monitoring
          this.startConnectionMonitoring();
          
          // Retry any pending submissions
          this.retryPendingSubmissions();
          
          // Auto-join quiz after connection
          if (username) {
            this.joinQuiz(username);
          }
          
          this.emitToListeners('connection_status', { 
            connected: true, 
            quality: this.connectionQuality,
            reconnected: this.reconnectAttempts > 0 
          });
          
          resolve();
        });

        // Connection error with exponential backoff
        this.socket.on('connect_error', (error) => {
          console.error('Connection error:', error);
          this.isConnecting = false;
          this.connectionQuality = 'disconnected';
          this.reconnectAttempts++;
          
          this.emitToListeners('connection_status', { 
            connected: false, 
            quality: this.connectionQuality,
            error: error.message,
            nextRetryIn: currentDelay
          });
          
          if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            reject(new Error(`Failed to connect after ${this.maxReconnectAttempts} attempts`));
          }
        });

        // Disconnection handling
        this.socket.on('disconnect', (reason) => {
          console.log('Disconnected from server:', reason);
          this.isConnecting = false;
          this.connectionQuality = 'disconnected';
          this.stopConnectionMonitoring();
          
          // Emit custom disconnect event for UI updates
          this.emitToListeners('connection_status', { 
            connected: false, 
            quality: this.connectionQuality,
            reason 
          });
        });

        // Enhanced reconnection handling
        this.socket.io.on('reconnect', (attemptNumber: number) => {
          console.log(`Reconnected after ${attemptNumber} attempts`);
          this.reconnectAttempts = 0;
          this.connectionQuality = 'good';
          
          // Restart connection monitoring
          this.startConnectionMonitoring();
          
          // Retry pending submissions
          this.retryPendingSubmissions();
          
          this.emitToListeners('connection_status', { 
            connected: true, 
            quality: this.connectionQuality,
            reconnected: true,
            attemptNumber 
          });
        });

        this.socket.io.on('reconnect_attempt', (attemptNumber: number) => {
          console.log(`Reconnection attempt ${attemptNumber}`);
          this.reconnectAttempts = attemptNumber;
          
          // Calculate next delay for UI display
          const nextDelay = Math.min(
            this.baseReconnectDelay * Math.pow(2, attemptNumber),
            this.maxReconnectDelay
          );
          
          this.emitToListeners('connection_status', { 
            connected: false, 
            quality: this.connectionQuality,
            reconnecting: true, 
            attempt: attemptNumber,
            nextRetryIn: nextDelay
          });
        });

        this.socket.io.on('reconnect_failed', () => {
          console.error('Failed to reconnect to server');
          this.connectionQuality = 'disconnected';
          this.emitToListeners('connection_status', { 
            connected: false, 
            quality: this.connectionQuality,
            reconnectFailed: true 
          });
        });

        // Set up event forwarding
        this.setupEventForwarding();

      } catch (error) {
        this.isConnecting = false;
        this.connectionQuality = 'disconnected';
        reject(error);
      }
    });
  }

  /**
   * Disconnect from the WebSocket server
   */
  disconnect(): void {
    this.stopConnectionMonitoring();
    this.clearAllSubmissions();
    
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
    
    this.connectionQuality = 'disconnected';
    this.reconnectAttempts = 0;
    this.eventListeners.clear();
  }

  /**
   * Clear submission tracking for new problem
   */
  clearSubmissionTracking(problemId?: string): void {
    if (problemId) {
      this.submittedProblems.delete(problemId);
      
      const activeSubmission = this.activeSubmissions.get(problemId);
      if (activeSubmission) {
        clearTimeout(activeSubmission.timeoutId);
        this.activeSubmissions.delete(problemId);
      }
    } else {
      // Clear all submission tracking (for new problem)
      this.submittedProblems.clear();
      
      // Clear all active submissions
      for (const [, submission] of this.activeSubmissions.entries()) {
        clearTimeout(submission.timeoutId);
      }
      this.activeSubmissions.clear();
    }
  }

  /**
   * Clear all submissions and timeouts
   */
  private clearAllSubmissions(): void {
    this.pendingSubmissions.clear();
    this.submittedProblems.clear();
    
    // Clear all active submission timeouts
    for (const [, submission] of this.activeSubmissions.entries()) {
      clearTimeout(submission.timeoutId);
    }
    this.activeSubmissions.clear();
  }

  /**
   * Check if connected to server
   */
  isConnected(): boolean {
    return this.socket?.connected ?? false;
  }

  /**
   * Join the quiz with optional username and difficulty
   */
  joinQuiz(username?: string, difficulty?: string): void {
    if (!this.socket?.connected) {
      throw new Error('Not connected to server');
    }
    
    this.socket.emit('join_quiz', { username, preferred_difficulty: difficulty || 'medium' });
  }

  /**
   * Submit an answer for the current problem with timeout and duplicate prevention
   */
  submitAnswer(answer: string | number, problemId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      // Check for duplicate submission
      if (this.submittedProblems.has(problemId)) {
        reject(new Error('You have already submitted an answer for this problem.'));
        return;
      }

      // Check if there's already an active submission for this problem
      if (this.activeSubmissions.has(problemId)) {
        reject(new Error('Submission already in progress for this problem.'));
        return;
      }

      if (!this.socket?.connected) {
        // Store submission for retry when reconnected
        const submissionId = `${problemId}_${Date.now()}`;
        this.pendingSubmissions.set(submissionId, {
          answer,
          problemId,
          timestamp: Date.now(),
          retries: 0
        });
        
        reject(new Error('Not connected to server. Submission queued for retry when connection is restored.'));
        return;
      }

      try {
        // Mark problem as submitted to prevent duplicates
        this.submittedProblems.add(problemId);
        
        // Set up timeout for submission
        const timeoutId = setTimeout(() => {
          // Clean up active submission
          this.activeSubmissions.delete(problemId);
          
          // Move to pending submissions for retry
          const submissionId = `${problemId}_${Date.now()}`;
          this.pendingSubmissions.set(submissionId, {
            answer,
            problemId,
            timestamp: Date.now(),
            retries: 0
          });
          
          // Remove from submitted problems to allow retry
          this.submittedProblems.delete(problemId);
          
          reject(new Error('Submission timed out after 30 seconds. Will retry when connection is stable.'));
        }, this.submissionTimeout);

        // Track active submission
        this.activeSubmissions.set(problemId, {
          timeoutId,
          timestamp: Date.now()
        });

        // Listen for answer received confirmation
        const handleAnswerReceived = (data: any) => {
          if (data.problem_id === problemId || !data.problem_id) {
            // Clean up
            const activeSubmission = this.activeSubmissions.get(problemId);
            if (activeSubmission) {
              clearTimeout(activeSubmission.timeoutId);
              this.activeSubmissions.delete(problemId);
            }
            
            this.socket?.off('answer_received', handleAnswerReceived);
            resolve();
          }
        };

        // Listen for error responses
        const handleError = (data: any) => {
          if (data.problem_id === problemId || data.message?.includes('duplicate')) {
            // Clean up
            const activeSubmission = this.activeSubmissions.get(problemId);
            if (activeSubmission) {
              clearTimeout(activeSubmission.timeoutId);
              this.activeSubmissions.delete(problemId);
            }
            
            this.socket?.off('error', handleError);
            this.socket?.off('answer_received', handleAnswerReceived);
            
            reject(new Error(data.message || 'Submission failed'));
          }
        };

        this.socket.on('answer_received', handleAnswerReceived);
        this.socket.on('error', handleError);
        this.socket.emit('submit_answer', { answer, problem_id: problemId });
        
      } catch (error) {
        // Clean up on immediate error
        this.submittedProblems.delete(problemId);
        this.activeSubmissions.delete(problemId);
        
        // Store for retry
        const submissionId = `${problemId}_${Date.now()}`;
        this.pendingSubmissions.set(submissionId, {
          answer,
          problemId,
          timestamp: Date.now(),
          retries: 0
        });
        
        reject(error);
      }
    });
  }

  /**
   * Request the current active problem
   */
  requestCurrentProblem(): void {
    if (!this.socket?.connected) {
      throw new Error('Not connected to server');
    }
    
    this.socket.emit('request_current_problem');
  }

  /**
   * Get quiz statistics
   */
  getQuizStats(): void {
    if (!this.socket?.connected) {
      throw new Error('Not connected to server');
    }
    
    this.socket.emit('get_quiz_stats');
  }

  /**
   * Emit a generic event (for flexibility)
   */
  emit(event: string, data?: any): void {
    if (!this.socket?.connected) {
      throw new Error('Not connected to server');
    }
    
    this.socket.emit(event as any, data);
  }

  /**
   * Add event listener for WebSocket events
   */
  addEventListener<K extends keyof WebSocketEvents>(
    event: K, 
    listener: WebSocketEvents[K]
  ): void {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, []);
    }
    this.eventListeners.get(event)!.push(listener);
  }

  /**
   * Remove event listener
   */
  removeEventListener<K extends keyof WebSocketEvents>(
    event: K, 
    listener: WebSocketEvents[K]
  ): void {
    const listeners = this.eventListeners.get(event);
    if (listeners) {
      const index = listeners.indexOf(listener);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }

  /**
   * Add listener for connection status changes
   */
  onConnectionStatus(listener: (status: {
    connected: boolean;
    quality?: 'excellent' | 'good' | 'poor' | 'disconnected';
    reason?: string;
    reconnecting?: boolean;
    reconnected?: boolean;
    attempt?: number;
    reconnectFailed?: boolean;
    error?: string;
    nextRetryIn?: number;
    attemptNumber?: number;
  }) => void): void {
    this.addEventListener('connection_status' as any, listener as any);
  }

  /**
   * Get current connection quality
   */
  getConnectionQuality(): 'excellent' | 'good' | 'poor' | 'disconnected' {
    return this.connectionQuality;
  }

  /**
   * Get pending submissions count
   */
  getPendingSubmissionsCount(): number {
    return this.pendingSubmissions.size;
  }

  /**
   * Start connection quality monitoring with ping/pong
   */
  private startConnectionMonitoring(): void {
    this.stopConnectionMonitoring();
    
    this.pingInterval = setInterval(() => {
      if (this.socket?.connected) {
        const pingStart = Date.now();
        
        this.socket.emit('ping' as any, { timestamp: pingStart });
        
        // Listen for pong response
        const handlePong = () => {
          const latency = Date.now() - pingStart;
          this.updateConnectionQuality(latency);
          this.socket?.off('pong' as any, handlePong);
        };
        
        this.socket.on('pong' as any, handlePong);
        
        // Timeout for pong response
        setTimeout(() => {
          this.socket?.off('pong' as any, handlePong);
          this.updateConnectionQuality(5000); // Assume poor connection if no pong
        }, 3000);
      }
    }, 5000); // Ping every 5 seconds
  }

  /**
   * Stop connection monitoring
   */
  private stopConnectionMonitoring(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  /**
   * Update connection quality based on latency
   */
  private updateConnectionQuality(latency: number): void {
    const previousQuality = this.connectionQuality;
    
    if (latency < 100) {
      this.connectionQuality = 'excellent';
    } else if (latency < 300) {
      this.connectionQuality = 'good';
    } else {
      this.connectionQuality = 'poor';
    }
    
    // Emit status update if quality changed
    if (previousQuality !== this.connectionQuality) {
      this.emitToListeners('connection_status', {
        connected: true,
        quality: this.connectionQuality,
        latency
      });
    }
  }

  /**
   * Retry pending submissions when connection is restored
   */
  private retryPendingSubmissions(): void {
    if (!this.socket?.connected || this.pendingSubmissions.size === 0) {
      return;
    }

    console.log(`Retrying ${this.pendingSubmissions.size} pending submissions`);
    
    const submissions = Array.from(this.pendingSubmissions.entries());
    
    submissions.forEach(([submissionId, submission]) => {
      // Check if submission is too old (older than 2 minutes)
      if (Date.now() - submission.timestamp > 120000) {
        this.pendingSubmissions.delete(submissionId);
        console.log(`Discarded old submission: ${submissionId}`);
        return;
      }
      
      // Check retry limit
      if (submission.retries >= this.maxSubmissionRetries) {
        this.pendingSubmissions.delete(submissionId);
        console.log(`Max retries reached for submission: ${submissionId}`);
        this.emitToListeners('error', {
          message: 'Failed to submit answer after multiple retries',
          error: 'SUBMISSION_RETRY_FAILED'
        });
        return;
      }
      
      // Retry submission
      submission.retries++;
      
      try {
        this.socket!.emit('submit_answer', { 
          answer: submission.answer, 
          problem_id: submission.problemId 
        });
        
        console.log(`Retried submission ${submissionId} (attempt ${submission.retries})`);
        
        // Remove from pending after successful emit
        // Note: We'll remove it when we get confirmation or on next cleanup
        
      } catch (error) {
        console.error(`Failed to retry submission ${submissionId}:`, error);
      }
    });
  }



  /**
   * Set up event forwarding from socket to listeners
   */
  private setupEventForwarding(): void {
    if (!this.socket) return;

    // Forward all relevant events to listeners
    const events: (keyof WebSocketEvents)[] = [
      'connected',
      'quiz_joined', 
      'new_problem',
      'winner_announced',
      'answer_received',
      'user_joined',
      'user_left',
      'leaderboard_update',
      'leaderboard_data',
      'quiz_stats',
      'error'
    ];

    events.forEach(event => {
      this.socket!.on(event, (data: any) => {
        // Clear submission tracking when new problem arrives
        if (event === 'new_problem') {
          this.clearSubmissionTracking();
        }
        
        this.emitToListeners(event, data);
      });
    });
  }

  /**
   * Emit event to all registered listeners
   */
  private emitToListeners(event: string, data: any): void {
    const listeners = this.eventListeners.get(event);
    if (listeners) {
      listeners.forEach(listener => {
        try {
          listener(data);
        } catch (error) {
          console.error(`Error in event listener for ${event}:`, error);
        }
      });
    }
  }
}

// Create singleton instance
export const websocketService = new WebSocketService(
  import.meta.env.VITE_WEBSOCKET_URL || 'http://localhost:8000'
);