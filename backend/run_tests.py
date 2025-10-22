#!/usr/bin/env python3
"""
Test runner script for the competitive math quiz backend.
"""
import subprocess
import sys
import os


def run_tests():
    """Run all tests and display results."""
    print("🧪 Running Competitive Math Quiz Tests")
    print("=" * 50)
    
    # Change to backend directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Test categories to run
    test_categories = [
        ("Unit Tests - Models", "tests/test_models.py"),
        ("Unit Tests - Gemini Service", "tests/test_gemini_service.py"),
        ("Unit Tests - Quiz Engine", "tests/test_quiz_engine.py"),
        ("Unit Tests - Submission Processor", "tests/test_submission_processor.py"),
        ("Unit Tests - Score Tracker", "tests/test_score_tracker.py"),
        ("Integration Tests", "tests/test_integration.py"),
    ]
    
    results = {}
    
    for category, test_path in test_categories:
        print(f"\n📋 Running {category}...")
        print("-" * 30)
        
        try:
            # Run pytest with minimal output
            result = subprocess.run([
                sys.executable, "-m", "pytest", 
                test_path, 
                "-v", 
                "--tb=short",
                "--disable-warnings"
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Count passed tests
                passed_count = result.stdout.count(" PASSED")
                results[category] = ("✅ PASSED", passed_count, 0)
                print(f"✅ {category}: {passed_count} tests passed")
            else:
                # Count failed tests
                failed_count = result.stdout.count(" FAILED")
                passed_count = result.stdout.count(" PASSED")
                results[category] = ("❌ FAILED", passed_count, failed_count)
                print(f"❌ {category}: {passed_count} passed, {failed_count} failed")
                
        except subprocess.TimeoutExpired:
            results[category] = ("⏰ TIMEOUT", 0, 0)
            print(f"⏰ {category}: Timed out")
        except Exception as e:
            results[category] = ("💥 ERROR", 0, 0)
            print(f"💥 {category}: Error - {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    total_passed = 0
    total_failed = 0
    
    for category, (status, passed, failed) in results.items():
        print(f"{status} {category}: {passed} passed, {failed} failed")
        total_passed += passed
        total_failed += failed
    
    print("-" * 50)
    print(f"🎯 TOTAL: {total_passed} passed, {total_failed} failed")
    
    if total_failed == 0:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())