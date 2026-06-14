"""
agent_system/cli.py
Command Line Interface to execute and display the Agent System loop beautifully.
"""
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.status import Status
from rich.markdown import Markdown

# Add current workspace directory to sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent_system.orchestrator import Orchestrator

console = Console()


def run_cli():
    """
    Main CLI function to run the multi-agent system.
    """
    console.print(
        Panel.fit(
            "🤖 [bold green]Enterprise Accounting API[/bold green] - [bold blue]Multi-Agent Test & Repair System[/bold blue]\n"
            "Collaborating Agents: Orchestrator, TestAgent, CodingAgent, ReporterAgent",
            border_style="green"
        )
    )

    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    report_path = os.path.join(workspace_dir, "agent_run_report.md")

    # Instantiate Orchestrator
    orchestrator = Orchestrator(
        workspace_dir=workspace_dir,
        report_path=report_path,
        max_iterations=5
    )

    # Start loop
    with console.status("[bold yellow]Initializing agent loop...", spinner="dots") as status:
        status.update("[bold yellow]Running Orchestrator...")
        final_state = orchestrator.start_loop()

    # Print results summary
    success = final_state.get("success")
    total_iter = final_state.get("total_iterations")

    if success:
        console.print(
            Panel(
                f"🎉 [bold green]SUCCESS[/bold green]: All tests passed after {total_iter} iterations!\n"
                f"Detailed markdown report generated at: [underline]{report_path}[/underline]",
                title="Status Summary",
                border_style="green"
            )
        )
    else:
        console.print(
            Panel(
                f"❌ [bold red]FAILED[/bold red]: Some tests are still failing or unresolved after {total_iter} iterations.\n"
                f"Please review the detailed report at: [underline]{report_path}[/underline] to fix remaining issues manually.",
                title="Status Summary",
                border_style="red"
            )
        )

    # Print final iteration table
    if orchestrator.history:
        table = Table(title="Iteration Summary", show_header=True, header_style="bold magenta")
        table.add_column("Iter #", style="dim", width=8)
        table.add_column("Test Status", width=30)
        table.add_column("Actions taken", width=40)

        for iter_data in orchestrator.history:
            iter_no = str(iter_data["iteration"])
            summary = iter_data["test_results"].get("summary", "N/A")
            
            fixes = iter_data.get("fixes_attempted", [])
            actions = []
            for f in fixes:
                status_str = "[green]Auto-Fixed[/green]" if f.get("fixed") else "[red]Manual Action Required[/red]"
                actions.append(f"{f.get('source_file') or 'Infra'}: {status_str}")
            
            table.add_row(
                iter_no,
                summary,
                "\n".join(actions) if actions else "None"
            )

        console.print(table)


if __name__ == "__main__":
    run_cli()
