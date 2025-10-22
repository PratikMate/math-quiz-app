import React, { useState, useEffect } from 'react';
import { MathProblem, Winner } from '../types';
import SubmissionTimer from './SubmissionTimer';

interface QuizInterfaceProps {
  currentProblem: MathProblem | null;
  winner: Winner | null;
  isSubmitting: boolean;
  onSubmitAnswer: (answer: number) => void;
  onRequestNewProblem?: () => void;
  submissionResult?: {
    isCorrect: boolean;
    submittedAnswer: number;
    message: string;
    feedback?: string;
  } | null;
}

const QuizInterface: React.FC<QuizInterfaceProps> = ({
  currentProblem,
  winner,
  isSubmitting,
  onSubmitAnswer,
  onRequestNewProblem,
  submissionResult
}) => {
  const [userAnswer, setUserAnswer] = useState<string>('');
  const [inputError, setInputError] = useState<string>('');
  const [countdown, setCountdown] = useState<number | null>(null);

  // Countdown timer for next question
  useEffect(() => {
    console.log('Timer effect triggered:', { winner: !!winner, currentProblem: !!currentProblem });
    if (winner && !currentProblem) {
      console.log('Starting countdown timer');
      setCountdown(3);
      const timer = setInterval(() => {
        setCountdown(prev => {
          console.log('Countdown tick:', prev);
          if (prev === null || prev <= 1) {
            clearInterval(timer);
            console.log('Countdown finished, requesting new problem');
            onRequestNewProblem?.();
            return null;
          }
          return prev - 1;
        });
      }, 1000);

      return () => {
        console.log('Cleaning up countdown timer');
        clearInterval(timer);
      };
    } else {
      setCountdown(null);
    }
  }, [winner, currentProblem, onRequestNewProblem]);

  const validateNumericInput = (value: string): boolean => {
    // Allow empty string, integers, and decimals (including negative numbers)
    const numericRegex = /^-?\d*\.?\d*$/;
    return numericRegex.test(value);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    
    if (validateNumericInput(value)) {
      setUserAnswer(value);
      setInputError('');
    } else {
      setInputError('Please enter a valid number');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!userAnswer.trim()) {
      setInputError('Please enter an answer');
      return;
    }

    const numericAnswer = parseFloat(userAnswer);
    if (isNaN(numericAnswer)) {
      setInputError('Please enter a valid number');
      return;
    }

    onSubmitAnswer(numericAnswer);
    setUserAnswer('');
    setInputError('');
  };

  // Show winner announcement
  if (winner) {
    return (
      <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl mx-auto">
        <div className="text-center">
          <div className="text-6xl mb-4">🎉</div>
          <h2 className="text-2xl font-bold text-green-600 mb-2">
            Winner: {winner.username}
          </h2>
          <p className="text-lg text-gray-700 mb-2">
            Correct Answer: {winner.correctAnswer}
          </p>
          <p className="text-sm text-gray-500">
            Response Time: {winner.responseTime}ms
          </p>
          <p className="text-sm text-gray-400 mt-4">
            {countdown !== null ? (
              <>Next question in {countdown} seconds...</>
            ) : (
              <>Next question coming up...</>
            )}
          </p>
          
          {/* Manual trigger for testing */}
          <button
            onClick={() => onRequestNewProblem?.()}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Get Next Question
          </button>
        </div>
      </div>
    );
  }

  // Show problem interface
  if (currentProblem) {
    return (
      <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl mx-auto">
        <div className="text-center mb-6">
          <div className="inline-block px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium mb-4">
            {currentProblem.difficulty.charAt(0).toUpperCase() + currentProblem.difficulty.slice(1)}
          </div>
          <h2 className="text-3xl font-bold text-gray-800 mb-6">
            {currentProblem.question}
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="answer" className="block text-sm font-medium text-gray-700 mb-2">
              Your Answer:
            </label>
            <input
              id="answer"
              type="text"
              value={userAnswer}
              onChange={handleInputChange}
              disabled={isSubmitting}
              className={`w-full px-4 py-3 text-lg border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-center ${
                inputError ? 'border-red-500' : 'border-gray-300'
              } ${isSubmitting ? 'bg-gray-100 cursor-not-allowed' : ''}`}
              placeholder="Enter your answer..."
              autoComplete="off"
            />
            {inputError && (
              <p className="mt-1 text-sm text-red-600">{inputError}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting || !!inputError || !userAnswer.trim()}
            className={`w-full py-3 px-6 text-lg font-semibold rounded-lg transition-colors ${
              isSubmitting || !!inputError || !userAnswer.trim()
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-2 focus:ring-blue-500'
            }`}
          >
            {isSubmitting ? (
              <div className="flex items-center justify-center">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                Submitting... (30s timeout)
              </div>
            ) : (
              'Submit Answer'
            )}
          </button>

          {/* Submission Timer */}
          <SubmissionTimer
            isActive={isSubmitting}
            duration={30000} // 30 seconds
            onTimeout={() => {
              // Timer will show timeout, actual timeout is handled by WebSocket service
            }}
          />
        </form>

        {/* Submission Result Feedback */}
        {submissionResult && (
          <div className={`mt-4 p-4 rounded-lg ${
            submissionResult.isCorrect 
              ? 'bg-green-100 border border-green-200 text-green-800'
              : submissionResult.message.includes('queued') || submissionResult.message.includes('timeout')
              ? 'bg-yellow-100 border border-yellow-200 text-yellow-800'
              : 'bg-red-100 border border-red-200 text-red-800'
          }`}>
            <p className="font-medium">{submissionResult.message}</p>
            {submissionResult.feedback && (
              <p className="text-sm mt-1">{submissionResult.feedback}</p>
            )}
            <p className="text-sm mt-1">
              Your answer: {submissionResult.submittedAnswer}
            </p>
          </div>
        )}

        <div className="mt-4 text-center text-sm text-gray-500">
          Problem ID: {currentProblem.id}
        </div>
      </div>
    );
  }

  // No problem available
  return (
    <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl mx-auto">
      <div className="text-center">
        <div className="text-4xl mb-4">⏳</div>
        <h2 className="text-xl font-semibold text-gray-700 mb-2">
          Waiting for next problem...
        </h2>
        <p className="text-gray-500">
          Get ready to compete!
        </p>
      </div>
    </div>
  );
};

export default QuizInterface;