import sys
import os
import subprocess

# Add project root to Python path
project_root = os.getcwd()
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set FLASK_APP environment variable
os.environ['FLASK_APP'] = 'run.py'

print("--- Running Upgrade ---")
try:
    # Use sys.executable to ensure we're using the same python interpreter
    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "upgrade"],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ
    )
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("--- Upgrade successful! ---")
except subprocess.CalledProcessError as e:
    print("!!! Error during upgrade !!!")
    print("STDOUT:", e.stdout)
    print("STDERR:", e.stderr)
except FileNotFoundError:
    print("!!! Error: python -m flask command not found !!!")
