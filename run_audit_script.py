from pathlib import Path
from pip_audit._audit import Auditor
from pip_audit._dependency_source import RequirementSource
from pip_audit._service import PyPIService

def main():
    req_file = Path("requirements.txt")
    source = RequirementSource([req_file])

    service = PyPIService()
    auditor = Auditor(service)

    print("Starting audit (synchronous)...")
    results_found = False
    processed_specs_count = 0
    vulnerabilities_detected = False

    # The auditor.audit() method seems to be a generator
    for spec_and_vulns_tuple in auditor.audit(source):
        processed_specs_count +=1
        spec, vulns = spec_and_vulns_tuple
        results_found = True # Set to true if we process at least one spec
        if vulns:
            vulnerabilities_detected = True
            print(f"Package: {spec.name}, Version: {spec.version}")
            for v in vulns:
                print(f"  ID: {v.id}")
                fix_versions_str = ', '.join(str(fv) for fv in v.fix_versions)
                print(f"  Fix Versions: {fix_versions_str if fix_versions_str else 'No fix versions available'}")
                print(f"  Description: {v.description}")
                print("-" * 20)
        # else:
        #    print(f"No vulnerabilities found for {spec.name} ({spec.version})")

    if not results_found:
        # This means the loop "for spec_and_vulns_tuple in auditor.audit(source):" didn't run even once.
        # This could be due to an issue with RequirementSource or the audit process itself before yielding results.
        # The earlier venv error is a prime suspect for this path.
        print("No dependencies were processed by the audit. This might indicate an issue with parsing requirements.txt or an underlying problem with the environment setup (e.g., venv creation if still attempted by the library internally).")
    elif not vulnerabilities_detected:
        print(f"Audit finished. Processed {processed_specs_count} dependencies. No vulnerabilities found.")
    else:
        print(f"Audit finished. Processed {processed_specs_count} dependencies. Vulnerabilities listed above.")

if __name__ == "__main__":
    main()
