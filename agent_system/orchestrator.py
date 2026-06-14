"""
agent_system/orchestrator.py
Coordinates the multi-agent test-analyze-fix loop.
"""
from typing import List, Dict, Any
from agent_system.test_agent import TestAgent
from agent_system.coding_agent import CodingAgent
from agent_system.reporter_agent import ReporterAgent


class Orchestrator:
    """
    Orchestrator manages the feedback loop between the TestAgent and CodingAgent.
    """

    def __init__(
        self,
        workspace_dir: str,
        report_path: str = "agent_run_report.md",
        max_iterations: int = 5
    ):
        self.workspace_dir = workspace_dir
        self.report_path = report_path
        self.max_iterations = max_iterations
        
        self.test_agent = TestAgent(workspace_dir)
        self.coding_agent = CodingAgent(workspace_dir)
        self.reporter_agent = ReporterAgent(report_path)
        
        self.history: List[Dict[str, Any]] = []

    def start_loop(self) -> Dict[str, Any]:
        """
        Runs the iterative test-and-repair loop.
        """
        iteration_count = 0
        success = False

        while iteration_count < self.max_iterations:
            iteration_count += 1
            print(f"\n[Orchestrator] Starting Iteration {iteration_count} of {self.max_iterations}...")
            
            # Step 1: Run tests
            print("[Orchestrator] Invoking TestAgent to run tests...")
            test_results = self.test_agent.run_tests()
            
            # Step 2: Record state
            iteration_data = {
                "iteration": iteration_count,
                "test_results": test_results,
                "fixes_attempted": []
            }
            
            # Check success condition
            if test_results.get("success"):
                print("[Orchestrator] ✅ All tests passed!")
                self.history.append(iteration_data)
                success = True
                break
                
            if test_results.get("timeout"):
                print("[Orchestrator] ❌ Test run timed out. Aborting.")
                self.history.append(iteration_data)
                break

            failures = test_results.get("failures", [])
            print(f"[Orchestrator] Test run completed: {test_results.get('summary')}")
            print(f"[Orchestrator] Found {len(failures)} test failures.")

            # Step 3: Analyze and fix each failure
            fixes_made = 0
            for idx, failure in enumerate(failures):
                print(f"[Orchestrator] Analyzing failure {idx + 1}/{len(failures)}: {failure.get('name')}")
                fix_proposal = self.coding_agent.analyze_and_fix(failure)
                iteration_data["fixes_attempted"].append(fix_proposal)
                
                if fix_proposal.get("fixed"):
                    fixes_made += 1

            self.history.append(iteration_data)
            
            if fixes_made == 0:
                print("[Orchestrator] ⚠️ No automatic fixes could be applied in this iteration. Stopping loop.")
                break
                
            print(f"[Orchestrator] Applied {fixes_made} code fixes. Proceeding to next iteration to re-test...")

        final_state = {
            "success": success,
            "total_iterations": iteration_count
        }

        # Step 4: Generate final execution report
        print(f"[Orchestrator] Generating final execution report to {self.report_path}...")
        self.reporter_agent.generate_report(self.history, final_state)
        
        return final_state
