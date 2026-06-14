"""
agent_system/reporter_agent.py
Generates Markdown summaries and execution reports of the agent system runs.
"""
import datetime
from typing import List, Dict, Any


class ReporterAgent:
    """
    ReporterAgent generates clean reports of the test-and-repair sessions.
    """

    def __init__(self, report_path: str):
        self.report_path = report_path

    def generate_report(
        self,
        iterations: List[Dict[str, Any]],
        final_state: Dict[str, Any]
    ) -> str:
        """
        Generates a markdown report summarizing the iterations.
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        md = []
        md.append("# 🤖 Accounting Agent System Run Report")
        md.append(f"*Generated on: {now}*")
        md.append("\n## 📊 Run Summary")
        
        # Calculate totals
        total_iterations = len(iterations)
        initial_run = iterations[0] if total_iterations > 0 else {}
        final_run = iterations[-1] if total_iterations > 0 else {}
        
        init_metrics = initial_run.get("test_results", {}).get("metrics", {})
        final_metrics = final_run.get("test_results", {}).get("metrics", {})
        
        status_emoji = "✅" if final_state.get("success") else "❌"
        md.append(f"- **Final Status**: {status_emoji} {'All Tests Passed!' if final_state.get('success') else 'Tests Failing/Incomplete'}")
        md.append(f"- **Total Iterations**: {total_iterations}")
        md.append(f"- **Initial Test State**: {initial_run.get('test_results', {}).get('summary', 'Unknown')}")
        md.append(f"- **Final Test State**: {final_run.get('test_results', {}).get('summary', 'Unknown')}")
        
        md.append("\n## 🔄 Execution History")
        for idx, iter_data in enumerate(iterations):
            iter_no = idx + 1
            test_res = iter_data.get("test_results", {})
            fixed_issues = iter_data.get("fixes_attempted", [])
            
            md.append(f"\n### 🔹 Iteration {iter_no}")
            md.append(f"- **Test Results**: `{test_res.get('summary')}`")
            
            if fixed_issues:
                md.append("- **Fixes Attempted**:")
                for fix in fixed_issues:
                    source_file = fix.get("source_file") or "Infrastructure"
                    strategy = fix.get("strategy")
                    explanation = fix.get("explanation")
                    fixed_status = "✅ Fixed" if fix.get("fixed") else "⚠️ Warning"
                    
                    md.append(f"  - **[{fixed_status}]** `{source_file}` via `{strategy}`")
                    md.append(f"    * {explanation}")
            else:
                md.append("- *No failures to fix in this iteration.*")

        # Detailed breakdown of final failures if not successful
        if not final_state.get("success"):
            md.append("\n## 🚨 Outstanding Failures")
            failures = final_run.get("test_results", {}).get("failures", [])
            if failures:
                for f in failures:
                    md.append(f"\n### ❌ {f.get('name')}")
                    md.append(f"- **File**: `{f.get('file_path')}:{f.get('line_number')}`")
                    md.append(f"- **Error Message**:\n```\n{f.get('error_message')}\n```")
                    md.append(f"- **Traceback Snippet**:\n```\n{f.get('traceback')}\n```")
            else:
                md.append("No specific test failures, check standard error/infrastructure logs.")

        report_content = "\n".join(md)
        
        # Write to report path
        try:
            with open(self.report_path, "w") as f:
                f.write(report_content)
        except Exception as e:
            print(f"Failed to write markdown report to {self.report_path}: {e}")
            
        return report_content
