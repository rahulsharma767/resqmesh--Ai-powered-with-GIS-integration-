"""
Runs all offline unit tests (no LLM_API_KEY required — uses FakeLLMClient).
    python run_tests.py
"""
import subprocess
import sys
import os

TEST_FILES = [
    "tests/test_schema.py",
    "tests/test_extractor.py",
    "tests/test_ambiguity.py",
    "tests/test_reviewer.py",
    "tests/test_injection.py",
    "tests/test_explainer_and_clarification.py",
]

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    failures = 0
    for tf in TEST_FILES:
        print(f"--- Running {tf} ---")
        result = subprocess.run([sys.executable, tf], cwd=root)
        if result.returncode != 0:
            failures += 1
    if failures:
        print(f"\n{failures} test file(s) FAILED")
        sys.exit(1)
    print("\nAll test files passed.")
