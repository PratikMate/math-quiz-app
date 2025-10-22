import React, { useState, useEffect } from 'react';

interface SubmissionTimerProps {
  isActive: boolean;
  duration: number; // in milliseconds
  onTimeout?: () => void;
}

const SubmissionTimer: React.FC<SubmissionTimerProps> = ({
  isActive,
  duration,
  onTimeout
}) => {
  const [timeLeft, setTimeLeft] = useState(duration);

  useEffect(() => {
    if (!isActive) {
      setTimeLeft(duration);
      return;
    }

    const startTime = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, duration - elapsed);
      
      setTimeLeft(remaining);
      
      if (remaining === 0) {
        clearInterval(interval);
        onTimeout?.();
      }
    }, 100);

    return () => clearInterval(interval);
  }, [isActive, duration]); // Remove onTimeout from dependencies

  if (!isActive) return null;

  const seconds = Math.ceil(timeLeft / 1000);
  const percentage = (timeLeft / duration) * 100;

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between text-sm text-gray-600 mb-1">
        <span>Submission timeout:</span>
        <span className={`font-medium ${seconds <= 5 ? 'text-red-600' : seconds <= 10 ? 'text-yellow-600' : 'text-gray-600'}`}>
          {seconds}s
        </span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all duration-100 ${
            percentage > 50 ? 'bg-green-500' : 
            percentage > 25 ? 'bg-yellow-500' : 'bg-red-500'
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

export default SubmissionTimer;