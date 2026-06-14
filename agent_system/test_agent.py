"""
agent_system/test_agent.py
Runs tests, parses failures, collects coverage, and reports test outcomes.
"""
import subprocess
import re
from typing import List, Dict, Any, Tuple


class TestAgent:
    """
    TestAgent is responsible for executing the test suite,
    parsing output, and extracting detailed failure information.
    """

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir

    def run_tests(self) -> Dict[str, Any]:
        """
        Executes pytest and captures failures and coverage.
        """
        cmd = ["pytest", "tests/", "--tb=short", "-v"]
        
        # Run pytest inside the virtualenv
        try:
            result = subprocess.run(
                ["bash", "-c", f"source venv/bin/activate && {' '.join(cmd)}"],
                cwd=self.workspace_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120
            )
            stdout = result.stdout
            stderr = result.stderr
            returncode = result.returncode
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "timeout": True,
                "summary": "Test execution timed out.",
                "failures": []
            }

        failures = self._parse_failures(stdout)
        
        # Determine success
        success = returncode == 0

        # Create summary
        passed_match = re.search(r"(\d+) passed", stdout)
        failed_match = re.search(r"(\d+) failed", stdout)
        error_match = re.search(r"(\d+) error", stdout)
        
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(error_match.group(1)) if error_match else 0

        summary = f"{passed} passed, {failed} failed, {errors} errors"

        return {
            "success": success,
            "timeout": False,
            "stdout": stdout,
            "stderr": stderr,
            "summary": summary,
            "failures": failures,
            "metrics": {
                "passed": passed,
                "failed": failed,
                "errors": errors
            }
        }

    def _parse_failures(self, stdout: str) -> List[Dict[str, Any]]:
        """
        Parses pytest short traceback output to extract failing test files,
        lines, tracebacks, and error messages.
        """
        failures = []
        
        # Split by the pytest failure section indicator
        if "FAILURES" in stdout or "ERRORS" in stdout:
            # Simple regex parser for failures
            # Pytest outputs failures like:
            # ________________ TestSystemHealth.test_health_endpoint_returns_operational _________________
            # or
            # __________________________ ERROR at setup of ... ___________________________
            
            sections = re.split(r"_{3,}\s+([^\n]+)\s+_{3,}", stdout)
            
            # sections[0] is the pre-failure header
            # Afterwards, we have pairs of (section_name, section_body)
            for i in range(1, len(sections), 2):
                header = sections[i]
                body = sections[i+1] if i+1 < len(sections) else ""
                
                # Clean up body to get traceback and error message
                lines = body.split("\n")
                tb_lines = []
                error_msg = ""
                file_info = ""
                
                for line in lines:
                    if line.strip().startswith("E   ") or line.strip().startswith("E "):
                        error_msg += line.strip()[2:] + "\n"
                    elif line.strip().startswith("tests/"):
                        file_info = line.strip()
                        tb_lines.append(line)
                    else:
                        if line.strip() and not line.startswith("===") and not line.startswith("---"):
                            tb_lines.append(line)
                
                # Try to extract file and line number
                file_path = None
                line_no = None
                file_match = re.search(r"(tests/[a-zA-Z0-9_\-\./]+):(\d+)", file_info or body)
                if file_match:
                    file_path = file_match.group(1)
                    line_no = int(file_match.group(2))
                
                failures.append({
                    "name": header.strip(),
                    "file_path": file_path,
                    "line_number": line_no,
                    "error_message": error_msg.strip(),
                    "traceback": "\n".join(tb_lines[:15]).strip() # Limit traceback size
                })
                
        return failures
