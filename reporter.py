import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich import box
from rich.columns import Columns
from rich.padding import Padding

console = Console()

SEVERITY_STYLE = {
    "critical": ("red", "✗"),
    "warning":  ("yellow", "⚠"),
    "ok":       ("green", "✓"),
    "info":     ("cyan", "ℹ"),
}


def score_color(score):
    if score is None:
        return "dim"
    if score >= 90:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def score_label(score):
    if score is None:
        return "N/A"
    if score >= 90:
        return f"{score} Good"
    if score >= 50:
        return f"{score} Needs Work"
    return f"{score} Poor"


def render_issues(issues: list, title: str, score=None):
    color = score_color(score)
    score_str = f"  [{color}]{score_label(score)}[/{color}]" if score is not None else ""
    console.print(f"\n[bold white]{title}[/bold white]{score_str}")
    console.print(Rule(style="dim"))

    for issue in issues:
        sev = issue.get("severity", "info")
        msg = issue.get("msg", "")
        style, icon = SEVERITY_STYLE.get(sev, ("dim", "·"))
        console.print(f"  [{style}]{icon}[/{style}] {msg}")


def render_metrics(metrics: dict):
    if not metrics:
        return
    console.print("\n  [bold]Core Web Vitals[/bold]")
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Metric", style="white")
    table.add_column("Value", justify="right")
    table.add_column("Status", justify="center")

    for label, data in metrics.items():
        value = data.get("value", "N/A")
        sev = data.get("severity", "info")
        style, icon = SEVERITY_STYLE.get(sev, ("dim", "·"))
        table.add_row(label, value, f"[{style}]{icon}[/{style}]")

    console.print(Padding(table, (0, 4)))


def render_opportunities(opportunities: list):
    if not opportunities:
        return
    console.print("\n  [bold]Performance Opportunities[/bold]")
    for opp in sorted(opportunities, key=lambda x: -x.get("savings_ms", 0))[:5]:
        ms = opp.get("savings_ms", 0)
        console.print(f"    [yellow]→[/yellow] {opp['title']} [dim](save ~{ms}ms)[/dim]")


def overall_score(results: dict) -> int:
    scores = []
    weights = {"performance": 0.3, "seo": 0.25, "accessibility": 0.25, "security": 0.2}
    for key, weight in weights.items():
        s = results.get(key, {}).get("score")
        if s is not None:
            scores.append(s * weight)
    if not scores:
        return None
    return round(sum(scores) / sum(weights[k] for k in weights if results.get(k, {}).get("score") is not None))


def generate_report(url: str, results: dict, as_json: bool = False):
    if as_json:
        print(json.dumps({"url": url, "results": results}, indent=2, default=str))
        return

    # Header
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Web Application Analyzer[/bold cyan]\n[dim]{url}[/dim]",
        border_style="cyan",
        padding=(1, 4),
    ))

    # Overall score summary
    score = overall_score(results)
    color = score_color(score)
    scores_row = []
    for section in ["performance", "seo", "accessibility", "security"]:
        s = results.get(section, {}).get("score")
        c = score_color(s)
        label = score_label(s)
        scores_row.append(f"[bold]{section.title()}[/bold]\n[{c}]{label}[/{c}]")

    console.print()
    console.print(Columns([
        Panel(t, expand=True, border_style="dim", padding=(0, 1)) for t in scores_row
    ]))

    if score is not None:
        console.print(f"\n  [bold]Overall Health Score:[/bold] [{color}][bold]{score}/100[/bold][/{color}]")

    # Performance
    if "performance" in results:
        perf = results["performance"]
        render_issues(perf.get("issues", []), "Performance", perf.get("score"))
        render_metrics(perf.get("metrics", {}))
        render_opportunities(perf.get("opportunities", []))

    # SEO
    if "seo" in results:
        seo = results["seo"]
        render_issues(seo.get("issues", []), "SEO", seo.get("score"))

    # Accessibility
    if "accessibility" in results:
        a11y = results["accessibility"]
        render_issues(a11y.get("issues", []), "Accessibility", a11y.get("score"))

    # Security
    if "security" in results:
        sec = results["security"]
        render_issues(sec.get("issues", []), "Security", sec.get("score"))
        ssl_info = sec.get("details", {})
        if ssl_info.get("tls_version"):
            console.print(f"    [dim]TLS: {ssl_info['tls_version']} | SSL expires: {ssl_info.get('ssl_expires','N/A')} ({ssl_info.get('ssl_days_left','?')} days)[/dim]")

    # Links
    if "links" in results:
        links = results["links"]
        render_issues(links.get("issues", []), "Links & Assets")
        d = links.get("details", {})
        if d.get("total_links"):
            console.print(f"    [dim]Total links: {d['total_links']} | Internal: {d['internal']} | External: {d['external']}[/dim]")

    # Summary of all critical issues
    all_critical = []
    for section, data in results.items():
        for issue in data.get("issues", []):
            if issue.get("severity") == "critical" and not issue["msg"].startswith("  "):
                all_critical.append(f"[{section.upper()}] {issue['msg']}")

    if all_critical:
        console.print()
        console.print(Panel(
            "\n".join(f"[red]✗[/red] {c}" for c in all_critical),
            title="[bold red]Critical Issues to Fix First[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))

    console.print()
