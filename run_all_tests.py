import sys
import time
import unittest


def run_all_tests():
    #runs all test cases in the current directory and subdirectories, providing a summary of results at the end
    print("=" * 70)
    print("TM113 SCHEDULING SYSTEM - TESTING")
    print("=" * 70)
    print()

    #discover all test cases
    loader = unittest.TestLoader()
    start_dir = '.'
    suite = loader.discover(start_dir, pattern='test_*.py')

    #run tests and measure time taken
    runner = unittest.TextTestRunner(verbosity=2)
    start_time = time.time()
    result = runner.run(suite)
    end_time = time.time()

    #print summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print("=" * 70)
    print()

    #return exit code
    if result.wasSuccessful():
        print("ALL TESTS PASSED")
        return 0
    else:
        print("SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
