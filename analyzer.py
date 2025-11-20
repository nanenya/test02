import json
import subprocess
import sys

def run_command(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        return result.stdout.strip()
    except FileNotFoundError:
        return f"Error: Command '{command[0]}' not found. Please ensure it's installed."
    except Exception as e:
        return f"An unexpected error occurred: {e}"

def analyze_files(file_list):
    analysis_results = {}
    for file_path in file_list:
        print(f"Analyzing {file_path}...")
        try:
            # Linting with flake8
            lint_result = run_command(['flake8', file_path])
            
            # Complexity with radon
            complexity_result = run_command(['radon', 'cc', '-s', file_path])
            
            analysis_results[file_path] = {
                'lint': lint_result or 'No issues found.',
                'complexity': complexity_result or 'Could not calculate.'
            }
        except Exception as e:
            analysis_results[file_path] = {'error': str(e)}
    return analysis_results

if __name__ == "__main__":
    files_to_analyze = sys.argv[1:]
    if not files_to_analyze:
        print("No files provided for analysis.", file=sys.stderr)
        sys.exit(1)

    report = analyze_files(files_to_analyze)
    
    with open('analysis_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print("Analysis complete. Report saved to analysis_report.json")
