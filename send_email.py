#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import smtplib
from collections import Counter, defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List

REPORTS_DIR = Path("reports")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_data() -> Dict:
    path = REPORTS_DIR / f"literature_data_{today()}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing literature data file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def paper_link(paper: Dict) -> str:
    if paper.get("doi"):
        return f"https://doi.org/{paper['doi']}"
    return paper.get("url", "")


def relevance_reason(paper: Dict) -> str:
    labels = paper.get("labels", [])
    label_text = ", ".join(labels) if labels else "General relevance"
    query = paper.get("matched_query", "")
    return f"{label_text}. Matched query: {query}"


def one_sentence_summary(paper: Dict) -> str:
    abstract = str(paper.get("abstract", "")).strip()
    if abstract:
        first = abstract.split(". ")[0].strip()
        if len(first) > 280:
            first = first[:277] + "..."
        return first
    return "No abstract was available from the metadata source; assess relevance from the title, source, and link."


def section_title(label: str) -> str:
    icons = {
        "Ecological modelling": "🔬",
        "Pest management": "🐛",
        "Outbreak response": "🚨",
        "Surveillance": "📡",
        "Biological invasion": "🌍",
        "Pine wood nematode": "🌲",
        "Other": "📚",
    }
    return f"{icons.get(label, '📚')} {label}"


def generate_markdown(data: Dict) -> str:
    papers: List[Dict] = data.get("papers", [])
    label_counts = Counter(label for p in papers for label in p.get("labels", []))
    grouped = defaultdict(list)
    for p in papers:
        grouped[p.get("labels", ["Other"])[0]].append(p)

    preferred_order = ["Pine wood nematode", "Outbreak response", "Surveillance",
                       "Ecological modelling", "Pest management", "Biological invasion", "Other"]

    lines = [
        f"# Daily Literature Report — {today()}",
        "",
        "Topic: pest management, invasive pest outbreak management, ecological modelling, surveillance optimization, biological invasion, and pine wood nematode.",
        "",
        "## Summary",
        f"- Total records collected: **{len(papers)}**",
        f"- Search window: last **{data.get('days_back', 'N/A')}** days",
        f"- Generated at UTC: `{data.get('generated_at_utc', '')}`",
        "",
        "### Category counts",
    ]

    if label_counts:
        for label, count in label_counts.most_common():
            lines.append(f"- {section_title(label)}: {count}")
    else:
        lines.append("- No category labels were assigned.")

    lines.extend(["", "---", ""])

    if not papers:
        lines.append("No papers were found today. Consider broadening keywords or increasing DAYS_BACK.")
        return "\n".join(lines)

    for label in preferred_order:
        items = grouped.get(label, [])
        if not items:
            continue
        lines.extend([f"## {section_title(label)}", ""])
        for idx, paper in enumerate(items[:12], 1):
            link = paper_link(paper)
            lines.append(f"### {idx}. {paper.get('title', 'Untitled')}")
            if paper.get("authors"):
                lines.append(f"- **Authors**: {paper['authors']}")
            if paper.get("publication_date"):
                lines.append(f"- **Date**: {paper['publication_date']}")
            lines.append(f"- **Source**: {paper.get('source', 'Unknown')}")
            if paper.get("doi"):
                lines.append(f"- **DOI**: `{paper['doi']}`")
            if link:
                lines.append(f"- **Link**: {link}")
            lines.append(f"- **One-sentence summary**: {one_sentence_summary(paper)}")
            lines.append(f"- **Why relevant**: {relevance_reason(paper)}")
            lines.append("")
        lines.extend(["---", ""])

    lines.append("*This report was generated automatically by GitHub Actions.*")
    return "\n".join(lines)


def markdown_to_html(markdown_text: str) -> str:
    body_lines = []
    for raw in markdown_text.splitlines():
        line = html.escape(raw)
        if line.startswith("# "):
            body_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("- "):
            body_lines.append(f"<li>{line[2:]}</li>")
        elif line.startswith("---"):
            body_lines.append("<hr>")
        elif line.strip():
            body_lines.append(f"<p>{line}</p>")
        else:
            body_lines.append("<br>")
    return f"""<!doctype html>
<html><head><meta charset="UTF-8">
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.55; color: #222; max-width: 920px; }}
h1 {{ color: #1f4e3d; }}
h2 {{ color: #2c6b4f; margin-top: 28px; }}
h3 {{ color: #333; }}
li {{ margin: 4px 0; }}
code {{ background: #f3f3f3; padding: 2px 4px; }}
hr {{ border: none; border-top: 1px solid #ddd; margin: 24px 0; }}
</style></head><body>
{chr(10).join(body_lines)}
</body></html>"""


def send_gmail(markdown_text: str, html_text: str) -> bool:
    sender = os.getenv("SENDER_EMAIL", "").strip()
    password = os.getenv("SENDER_PASSWORD", "").strip()
    recipient = os.getenv("RECIPIENT_EMAIL", "").strip()
    if not sender or not password or not recipient:
        print("Email skipped: SENDER_EMAIL, SENDER_PASSWORD, or RECIPIENT_EMAIL is missing.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Daily Literature Report — {today()}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(markdown_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_text, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)
    print(f"Email sent to {recipient}")
    return True


def main() -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    data = load_data()
    markdown_text = generate_markdown(data)
    report_path = REPORTS_DIR / f"daily_report_{today()}.md"
    report_path.write_text(markdown_text, encoding="utf-8")
    print(f"Report saved to {report_path}")

    service = os.getenv("EMAIL_SERVICE", "").strip().lower()
    if service in {"", "none", "off", "false"}:
        print("Email not sent because EMAIL_SERVICE is not set to 'gmail'.")
        return
    if service != "gmail":
        raise ValueError("This minimal version supports EMAIL_SERVICE=gmail only.")

    html_text = markdown_to_html(markdown_text)
    sent = send_gmail(markdown_text, html_text)
    if not sent:
        raise RuntimeError("Email was not sent. Check GitHub Secrets.")


if __name__ == "__main__":
    main()
