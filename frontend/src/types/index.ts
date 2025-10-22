export interface MathProblem {
  id: string;
  question: string;
  difficulty: 'easy' | 'medium' | 'hard';
  createdAt: string;
}

export interface Winner {
  userId: string;
  username: string;
  correctAnswer: number;
  responseTime: number;
}

export interface UserScore {
  user_id: string;
  username: string;
  session_wins: number;
  session_problems_attempted: number;
  average_response_time_ms: number;
  fastest_response_time_ms?: number;
  rank: number;
}

export interface SessionStats {
  total_players: number;
  total_wins: number;
  total_attempts: number;
  average_response_time_ms: number;
  fastest_response_time_ms?: number;
}

export interface QuizState {
  currentProblem: MathProblem | null;
  timeRemaining: number;
  userAnswer: string;
  isSubmitting: boolean;
  winner: Winner | null;
  leaderboard: UserScore[];
  sessionStats?: SessionStats;
}