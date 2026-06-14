"""
agent_system/coding_agent.py
Analyzes test failures, locates code, and generates fixes (using rules or LLMs).
"""
import os
import re
from typing import Dict, Any, List, Optional, Tuple
import google.generativeai as genai


class CodingAgent:
    """
    CodingAgent takes failures from the TestAgent, locates the source files,
    and applies/proposes corrections.
    """

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)

    def analyze_and_fix(self, failure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes a single test failure and generates a fix proposal.
        """
        test_file = failure.get("file_path")
        error_msg = failure.get("error_message")
        traceback = failure.get("traceback")
        test_name = failure.get("name")

        # Map test file to source file
        source_file = self._map_test_to_source(test_file, test_name, error_msg)
        
        analysis = {
            "test_file": test_file,
            "test_name": test_name,
            "source_file": source_file,
            "error_msg": error_msg,
            "fixed": False,
            "strategy": None,
            "explanation": ""
        }

        # 1. Check for database/infra connection errors (standard/common rule-based check)
        if "Connection refused" in error_msg or "docker.sock" in error_msg:
            analysis["strategy"] = "infrastructure_check"
            analysis["explanation"] = (
                "PostgreSQL database connection refused. The database is likely not running. "
                "Instructions: Start PostgreSQL using docker compose (e.g., 'sudo docker compose up -d')."
            )
            return analysis

        # 2. Try LLM fix if API key is present
        if self.api_key and source_file:
            success, explanation, diff = self._attempt_llm_fix(source_file, test_file, test_name, error_msg, traceback)
            if success:
                analysis["fixed"] = True
                analysis["strategy"] = "llm_auto_fix"
                analysis["explanation"] = explanation
                analysis["diff"] = diff
                return analysis

        # 3. Fallback to heuristic/rule-based analysis
        analysis["strategy"] = "human_guided"
        analysis["explanation"] = self._generate_heuristic_explanation(source_file, error_msg, traceback)
        return analysis

    def _map_test_to_source(self, test_file: Optional[str], test_name: str, error_msg: str) -> Optional[str]:
        """
        Heuristically maps a test file and name to the likely source code file.
        """
        if not test_file:
            return None
        
        # Mapping test_plugins.py -> plugins
        if "test_plugins" in test_file:
            if "us_gaap" in test_name or "gaap" in error_msg.lower():
                return "app/plugins/us_gaap.py"
            elif "eu_ifrs" in test_name or "ifrs" in error_msg.lower():
                return "app/plugins/eu_ifrs.py"
            elif "in_gst" in test_name or "gst" in error_msg.lower():
                return "app/plugins/in_gst.py"
            return "app/plugins/base.py"
            
        # Mapping test_ledger.py -> ledger_service or models
        if "test_ledger" in test_file:
            if "trial_balance" in test_name or "balance_sheet" in test_name:
                return "app/services/reporting_service.py"
            elif "post" in test_name or "reverse" in test_name:
                return "app/services/ledger_service.py"
            elif "account" in test_name:
                return "app/models/ledger.py"
            return "app/services/ledger_service.py"

        return None

    def _attempt_llm_fix(
        self, source_file: str, test_file: str, test_name: str, error_msg: str, traceback: str
    ) -> Tuple[bool, str, str]:
        """
        Calls the Gemini API to fix the bug in the source file.
        """
        source_path = os.path.join(self.workspace_dir, source_file)
        test_path = os.path.join(self.workspace_dir, test_file)

        if not os.path.exists(source_path) or not os.path.exists(test_path):
            return False, "Files not found for editing.", ""

        with open(source_path, "r") as f:
            source_content = f.read()

        with open(test_path, "r") as f:
            test_content = f.read()

        prompt = f"""
You are an expert developer. You are part of an autonomous coding agent loop.
Your task is to fix a bug in the file `{source_file}` that causes the test `{test_name}` in `{test_file}` to fail.

Here is the failure information:
Error Message:
{error_msg}

Traceback:
{traceback}

---
Here is the contents of `{test_file}`:
{test_content}

---
Here is the contents of `{source_file}`:
{source_content}

---
Generate a fix for `{source_file}`.
Your output must be the complete updated code of `{source_file}` wrapped in a single ```python code block.
Before the code block, provide a short explanation of what was wrong and how you fixed it.
"""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            text = response.text

            # Parse explanation and code
            explanation = ""
            code_block_match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
            if code_block_match:
                new_code = code_block_match.group(1)
                explanation_match = re.search(r"(.*?)```python", text, re.DOTALL)
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                
                # Write fixed code back to file
                with open(source_path, "w") as f:
                    f.write(new_code)
                
                # Generate simple line diff representation
                diff = f"Updated {source_file} successfully."
                return True, explanation, diff
            
            return False, "Failed to parse code block from LLM response.", ""
        except Exception as e:
            return False, f"LLM API Call failed: {str(e)}", ""

    def _generate_heuristic_explanation(self, source_file: Optional[str], error_msg: str, traceback: str) -> str:
        """
        Generates general heuristic explanations when no LLM is available.
        """
        if not source_file:
            return f"Heuristic Analysis: Could not match this failure to a specific source file. Error message: {error_msg}"
        
        explanation = f"Heuristic Analysis for target file `{source_file}`:\n"
        if "404" in error_msg:
            explanation += "- A resource was not found. Check if the entity (Tenant or Account) is being seeded correctly in the test setup.\n"
        if "422" in error_msg:
            explanation += "- Validation failed. The Pydantic schema is rejecting the inputs. Check if fields align with the constraints (e.g. non-zero amounts, multi-line entries).\n"
        if "409" in error_msg:
            explanation += "- Integrity conflict. Likely trying to insert a duplicate account code or double-reverse an entry.\n"
        if "ForeignKeyViolation" in error_msg or "FOREIGN KEY" in error_msg:
            explanation += "- Database constraint violation. Verify the ordering of inserts or the relation IDs used.\n"
            
        explanation += f"\nPlease inspect the traceback in `{source_file}` to identify the exact line causing the crash."
        return explanation
