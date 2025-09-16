try:
    import bootstrap_flask
    print("Successfully imported bootstrap_flask")
    print(bootstrap_flask.__version__)
except ImportError as e:
    print(f"Failed to import bootstrap_flask: {e}")
import sys
print("sys.path:", sys.path)
