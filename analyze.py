#!/usr/bin/env python3
"""
Web Application Analyzer
Usage: python3 analyze.py <url> [--skip performance seo accessibility security links] [--json] [--pdf [FILE]]
"""

import argparse
import sys
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

SECTIONS = ["performance", "seo", "accessibility", "security", "links"]


def validate_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def run_analysis(url: str, skip: list, as_json: bool, pdf_path: str = None):
    from modules.performance import analyze_performance
    from modules.seo import analyze_seo
    from modules.accessibility import analyze_accessibility
    from modules.security import analyze_security
    from modules.links import analyze_links
    from reporter import generate_report

    module_map = {
        "performance":   (analyze_performance,  "Analyzing performance..."),
        "seo":           (analyze_seo,           "Analyzing SEO..."),
        "accessibility": (analyze_accessibility, "Analyzing accessibility..."),
        "security":      (analyze_security,      "Analyzing security..."),
        "links":         (analyze_links,         "Checking links & assets..."),
    }

    results = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        for section in SECTIONS:
            if section in skip:
                continue
            fn, desc = module_map[section]
            task = progress.add_task(desc, total=None)
            try:
                results[section] = fn(url)
            except Exception as e:
                results[section] = {"issues": [{"severity": "critical", "msg": f"Module crashed: {e}"}]}
            progress.remove_task(task)

    generate_report(url, results, as_json=as_json)

    # Save to history database
    try:
        import database as db
        analysis_id = db.save_analysis(url, results)
        if not as_json:
            console.print(f"  [dim]Saved to history (id={analysis_id}) — view at: python3 app.py[/dim]")
    except Exception as e:
        if not as_json:
            console.print(f"  [dim]History save failed: {e}[/dim]")

    if pdf_path is not False:
        from pdf_reporter import generate_pdf
        out = generate_pdf(url, results, output_path=pdf_path if isinstance(pdf_path, str) else None)
        console.print(f"\n  [bold green]PDF saved:[/bold green] {out}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a web application for performance, SEO, accessibility, security, and broken links.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("url", help="URL to analyze (e.g. https://example.com)")
    parser.add_argument(
        "--skip",
        nargs="+",
        choices=SECTIONS,
        default=[],
        metavar="MODULE",
        help="Skip specific modules: " + ", ".join(SECTIONS),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of terminal report",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=SECTIONS,
        default=[],
        metavar="MODULE",
        help="Run only specific modules",
    )
    parser.add_argument(
        "--pdf",
        nargs="?",
        const=True,
        default=False,
        metavar="FILE",
        help="Export report as PDF. Optionally specify output path (default: auto-named in current dir)",
    )

    args = parser.parse_args()
    url = validate_url(args.url)

    skip = args.skip
    if args.only:
        skip = [s for s in SECTIONS if s not in args.only]

    run_analysis(url, skip, args.json, pdf_path=args.pdf)


if __name__ == "__main__":
    main()
