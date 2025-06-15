from pathlib import Path
import pip_audit

def main():
    print("Starting audit...")
    try:
        # Use pip_audit's main entry point to perform the audit
        pip_audit.main(["--requirement", "requirements.txt"])
    except SystemExit as e:
        # pip_audit.main may call sys.exit, so we catch SystemExit to handle it gracefully
        if e.code == 0:
            print("Audit finished successfully. No vulnerabilities found.")
        else:
            print("Audit finished with vulnerabilities or errors.")
if __name__ == "__main__":
    main()
