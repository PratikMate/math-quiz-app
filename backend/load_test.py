"""
Load testing script for competitive math quiz system.
Tests concurrent user submissions and system performance.
"""
import asyncio
import aiohttp
import socketio
import time
import random
import json
import statistics
from datetime import datetime
from typing import List, Dict, Any
import argparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LoadTestClient:
    """Individual client for load testing."""
    
    def __init__(self, client_id: int, server_url: str):
        """
        Initialize load test client.
        
        Args:
            client_id: Unique client identifier
            server_url: Server URL to connect to
        """
        self.client_id = client_id
        self.server_url = server_url
        self.username = f"LoadTestUser_{client_id}"
        self.sio = socketio.AsyncClient()
        self.connected = False
        self.current_problem = None
        self.metrics = {
            'connection_time': None,
            'join_time': None,
            'submissions': [],
            'errors': [],
            'messages_received': 0
        }
        
        # Setup event handlers
        self.setup_event_handlers()
    
    def setup_event_handlers(self):
        """Setup Socket.IO event handlers."""
        
        @self.sio.event
        async def connect():
            self.connected = True
            logger.debug(f"Client {self.client_id} connected")
        
        @self.sio.event
        async def disconnect():
            self.connected = False
            logger.debug(f"Client {self.client_id} disconnected")
        
        @self.sio.event
        async def connected(data):
            self.metrics['connection_time'] = time.time()
            logger.debug(f"Client {self.client_id} received connected event")
        
        @self.sio.event
        async def quiz_joined(data):
            self.metrics['join_time'] = time.time()
            logger.debug(f"Client {self.client_id} joined quiz")
        
        @self.sio.event
        async def new_problem(data):
            self.current_problem = data.get('problem')
            self.metrics['messages_received'] += 1
            logger.debug(f"Client {self.client_id} received new problem")
        
        @self.sio.event
        async def answer_received(data):
            self.metrics['messages_received'] += 1
            logger.debug(f"Client {self.client_id} answer acknowledged")
        
        @self.sio.event
        async def winner_announced(data):
            self.metrics['messages_received'] += 1
            logger.debug(f"Client {self.client_id} received winner announcement")
        
        @self.sio.event
        async def error(data):
            self.metrics['errors'].append({
                'timestamp': time.time(),
                'error': data.get('message', 'Unknown error')
            })
            logger.warning(f"Client {self.client_id} received error: {data}")
    
    async def connect_and_join(self):
        """Connect to server and join quiz."""
        try:
            start_time = time.time()
            
            # Connect to server
            await self.sio.connect(self.server_url)
            
            # Wait for connection confirmation
            await asyncio.sleep(0.1)
            
            # Join quiz
            await self.sio.emit('join_quiz', {'username': self.username})
            
            # Wait for join confirmation
            await asyncio.sleep(0.1)
            
            connection_duration = time.time() - start_time
            logger.info(f"Client {self.client_id} connected and joined in {connection_duration:.3f}s")
            
            return True
            
        except Exception as e:
            logger.error(f"Client {self.client_id} failed to connect: {e}")
            self.metrics['errors'].append({
                'timestamp': time.time(),
                'error': f"Connection failed: {e}"
            })
            return False
    
    async def submit_random_answer(self):
        """Submit a random answer to the current problem."""
        if not self.current_problem:
            return
        
        try:
            start_time = time.time()
            
            # Generate random answer (sometimes correct, sometimes not)
            if random.random() < 0.1:  # 10% chance of correct answer
                # Try to solve the problem (simplified)
                answer = self.attempt_solve_problem(self.current_problem['question'])
            else:
                # Random incorrect answer
                answer = random.randint(1, 1000)
            
            # Submit answer
            await self.sio.emit('submit_answer', {
                'answer': str(answer),
                'problem_id': self.current_problem['id']
            })
            
            submission_time = time.time() - start_time
            
            self.metrics['submissions'].append({
                'timestamp': start_time,
                'problem_id': self.current_problem['id'],
                'answer': answer,
                'submission_time_ms': submission_time * 1000
            })
            
            logger.debug(f"Client {self.client_id} submitted answer: {answer}")
            
        except Exception as e:
            logger.error(f"Client {self.client_id} failed to submit answer: {e}")
            self.metrics['errors'].append({
                'timestamp': time.time(),
                'error': f"Submission failed: {e}"
            })
    
    def attempt_solve_problem(self, question: str) -> int:
        """Attempt to solve a simple math problem."""
        try:
            # Very basic problem solving for common patterns
            question = question.lower().replace('what is', '').replace('?', '').strip()
            
            # Handle simple arithmetic
            if '+' in question:
                parts = question.split('+')
                return int(parts[0].strip()) + int(parts[1].strip())
            elif '-' in question:
                parts = question.split('-')
                return int(parts[0].strip()) - int(parts[1].strip())
            elif '*' in question or 'x' in question:
                parts = question.replace('*', 'x').split('x')
                return int(parts[0].strip()) * int(parts[1].strip())
            elif '/' in question:
                parts = question.split('/')
                return int(parts[0].strip()) // int(parts[1].strip())
            
            # Default random answer
            return random.randint(1, 100)
            
        except Exception:
            return random.randint(1, 100)
    
    async def disconnect(self):
        """Disconnect from server."""
        try:
            await self.sio.disconnect()
            logger.debug(f"Client {self.client_id} disconnected")
        except Exception as e:
            logger.error(f"Client {self.client_id} disconnect error: {e}")


class LoadTester:
    """Main load testing coordinator."""
    
    def __init__(self, server_url: str, num_clients: int, test_duration: int):
        """
        Initialize load tester.
        
        Args:
            server_url: Server URL to test
            num_clients: Number of concurrent clients
            test_duration: Test duration in seconds
        """
        self.server_url = server_url
        self.num_clients = num_clients
        self.test_duration = test_duration
        self.clients: List[LoadTestClient] = []
        self.test_results = {
            'start_time': None,
            'end_time': None,
            'total_clients': num_clients,
            'successful_connections': 0,
            'total_submissions': 0,
            'total_errors': 0,
            'response_times': [],
            'connection_times': []
        }
    
    async def run_load_test(self):
        """Run the complete load test."""
        logger.info(f"Starting load test with {self.num_clients} clients for {self.test_duration}s")
        
        self.test_results['start_time'] = time.time()
        
        # Create clients
        self.clients = [
            LoadTestClient(i, self.server_url) 
            for i in range(self.num_clients)
        ]
        
        # Connect all clients
        await self.connect_all_clients()
        
        # Run test for specified duration
        await self.run_test_scenario()
        
        # Disconnect all clients
        await self.disconnect_all_clients()
        
        self.test_results['end_time'] = time.time()
        
        # Analyze results
        self.analyze_results()
        
        return self.test_results
    
    async def connect_all_clients(self):
        """Connect all clients concurrently."""
        logger.info(f"Connecting {self.num_clients} clients...")
        
        # Connect clients in batches to avoid overwhelming the server
        batch_size = 10
        for i in range(0, len(self.clients), batch_size):
            batch = self.clients[i:i + batch_size]
            
            # Connect batch concurrently
            tasks = [client.connect_and_join() for client in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successful connections
            for result in results:
                if result is True:
                    self.test_results['successful_connections'] += 1
            
            # Small delay between batches
            await asyncio.sleep(0.5)
        
        logger.info(f"Connected {self.test_results['successful_connections']}/{self.num_clients} clients")
    
    async def run_test_scenario(self):
        """Run the main test scenario."""
        logger.info(f"Running test scenario for {self.test_duration} seconds...")
        
        end_time = time.time() + self.test_duration
        
        while time.time() < end_time:
            # Simulate random answer submissions
            active_clients = [c for c in self.clients if c.connected]
            
            if active_clients:
                # Select random subset of clients to submit answers
                num_submitters = min(len(active_clients), random.randint(1, 20))
                submitters = random.sample(active_clients, num_submitters)
                
                # Submit answers concurrently
                tasks = [client.submit_random_answer() for client in submitters]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait before next round
            await asyncio.sleep(random.uniform(0.5, 2.0))
    
    async def disconnect_all_clients(self):
        """Disconnect all clients."""
        logger.info("Disconnecting all clients...")
        
        tasks = [client.disconnect() for client in self.clients]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def analyze_results(self):
        """Analyze test results and generate summary."""
        logger.info("Analyzing test results...")
        
        # Collect metrics from all clients
        all_submissions = []
        all_errors = []
        connection_times = []
        
        for client in self.clients:
            all_submissions.extend(client.metrics['submissions'])
            all_errors.extend(client.metrics['errors'])
            
            if client.metrics['connection_time'] and client.metrics['join_time']:
                connection_time = client.metrics['join_time'] - client.metrics['connection_time']
                connection_times.append(connection_time)
        
        # Calculate statistics
        self.test_results.update({
            'total_submissions': len(all_submissions),
            'total_errors': len(all_errors),
            'connection_times': connection_times,
            'avg_connection_time': statistics.mean(connection_times) if connection_times else 0,
            'submission_rate': len(all_submissions) / self.test_duration if self.test_duration > 0 else 0
        })
        
        if all_submissions:
            submission_times = [s['submission_time_ms'] for s in all_submissions]
            self.test_results.update({
                'avg_submission_time_ms': statistics.mean(submission_times),
                'median_submission_time_ms': statistics.median(submission_times),
                'max_submission_time_ms': max(submission_times),
                'min_submission_time_ms': min(submission_times)
            })
    
    def print_results(self):
        """Print test results summary."""
        results = self.test_results
        
        print("\n" + "="*60)
        print("LOAD TEST RESULTS")
        print("="*60)
        print(f"Test Duration: {results['end_time'] - results['start_time']:.2f} seconds")
        print(f"Total Clients: {results['total_clients']}")
        print(f"Successful Connections: {results['successful_connections']}")
        print(f"Connection Success Rate: {(results['successful_connections'] / results['total_clients']) * 100:.1f}%")
        
        if results.get('avg_connection_time'):
            print(f"Average Connection Time: {results['avg_connection_time']:.3f} seconds")
        
        print(f"\nSubmissions:")
        print(f"  Total Submissions: {results['total_submissions']}")
        print(f"  Submission Rate: {results.get('submission_rate', 0):.2f} submissions/second")
        
        if results.get('avg_submission_time_ms'):
            print(f"  Average Response Time: {results['avg_submission_time_ms']:.2f} ms")
            print(f"  Median Response Time: {results['median_submission_time_ms']:.2f} ms")
            print(f"  Min Response Time: {results['min_submission_time_ms']:.2f} ms")
            print(f"  Max Response Time: {results['max_submission_time_ms']:.2f} ms")
        
        print(f"\nErrors:")
        print(f"  Total Errors: {results['total_errors']}")
        print(f"  Error Rate: {(results['total_errors'] / max(results['total_submissions'], 1)) * 100:.2f}%")
        
        print("="*60)


async def main():
    """Main function to run load test."""
    parser = argparse.ArgumentParser(description='Load test the competitive math quiz system')
    parser.add_argument('--url', default='http://localhost:8000', help='Server URL')
    parser.add_argument('--clients', type=int, default=50, help='Number of concurrent clients')
    parser.add_argument('--duration', type=int, default=60, help='Test duration in seconds')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run load tester
    tester = LoadTester(args.url, args.clients, args.duration)
    
    try:
        results = await tester.run_load_test()
        tester.print_results()
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"load_test_results_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\nDetailed results saved to: {filename}")
        
    except KeyboardInterrupt:
        print("\nLoad test interrupted by user")
    except Exception as e:
        logger.error(f"Load test failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())