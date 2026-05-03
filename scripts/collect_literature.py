#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import feedparser
import requests

DAYS_BACK = int(os.getenv("DAYS_BACK", "7"))
MAX_PER_QUERY = int(os.getenv("MAX_PER_QUERY", "4"))
REPORTS_DIR = Path("reports")

SEARCH_TOPICS: Dict[str, List[str]] = {
    "ecological_modelling": [
        "ecological modelling pest management",
        "individual-based model invasive pest",
        "agent-based model pest spread",
        "species distribution model invasive pest",
        "risk mapping invasive species",
    ],
    "pest_management": [
        "integrated pest management invasive pest",
        "forest pest management outbreak",
        "plant disease management surveillance",
        "biological control invasive pest",
        "pest eradication containment",
    ],
    "outbreak_management": [
        "pest outbreak management",
        "plant disease outbreak response",
        "early detection rapid response invasive species",
        "surveillance network optimization pest",
        "outbreak prediction invasive pest",
    ],
    "pine_wood_nematode": [
        "pine wood nematode management",
        "Bursaphelenchus xylophilus surveillance",
        "Monochamus galloprovincialis dispersal",
        "pine wilt disease outbreak management",
    ],
}

RSS_FEEDS = [
    "https://www.sciencedaily.com/rss/plants_animals/invasive_species.xml",
    "https://www.sciencedaily.com/rss/plants_animals/agriculture_and_food.xml",
]


def today_utc() -> datetime:
    return datetime.now(timezone.utc)


def from_date_iso() -> str:
    return (today_utc().date() - timedelta(days=DAYS_BACK)).isoformat()


def clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(str(x) for x in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def abstract_from_openalex(inverted_index: object) -> str:
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""
    positions = []
    for word, idxs in inverted_index.items():
        if isinstance(idxs, list):
            for idx in idxs:
                if isinstance(idx, int):
                    positions.append((idx, word))
    return " ".join(word for _, word in sorted(positions))[:1200]


def doi_url(doi: str) -> str:
    doi = clean_text(doi).replace("https://doi.org/", "")
    return f"https://doi.org/{doi}" if doi else ""


def score_relevance(title: str, abstract: str) -> int:
    text = f"{title} {abstract}".lower()
    weighted_terms = {
        "invasive": 3, "invasion": 3, "pest": 3, "plant disease": 3,
        "surveillance": 4, "monitoring": 3, "outbreak": 4,
        "eradication": 4, "containment": 4, "management": 2, "risk": 2,
        "model": 3, "agent-based": 4, "individual-based": 4,
        "species distribution": 3, "pine wood nematode": 6,
        "bursaphelenchus": 6, "monochamus": 5, "forest": 2,
    }
    return sum(weight for term, weight in weighted_terms.items() if term in text)


def classify_paper(title: str, abstract: str) -> List[str]:
    text = f"{title} {abstract}".lower()
    labels = []
    rules = {
        "Ecological modelling": ["model", "simulation", "agent-based", "individual-based", "species distribution", "risk map"],
        "Pest management": ["pest management", "control", "eradication", "containment", "ipm", "integrated pest"],
        "Outbreak response": ["outbreak", "early detection", "rapid response", "emergency"],
        "Surveillance": ["surveillance", "monitoring", "survey", "trap", "network optimization"],
        "Biological invasion": ["invasive", "invasion", "alien species", "non-native"],
        "Pine wood nematode": ["pine wood nematode", "bursaphelenchus", "monochamus", "pine wilt"],
    }
    for label, terms in rules.items():
        if any(term in text for term in terms):
            labels.append(label)
    return labels or ["Other"]


def normalize_paper(title: str, authors: str = "", publication_date: str = "", doi: str = "",
                    url: str = "", source: str = "", abstract: str = "",
                    matched_query: str = "", topic: str = "") -> Optional[Dict[str, object]]:
    title = clean_text(title)
    if not title or title.lower() in {"n/a", "none"}:
        return None
    doi = clean_text(doi)
    url = clean_text(url) or doi_url(doi)
    abstract = clean_text(abstract)
    return {
        "title": title,
        "authors": clean_text(authors),
        "publication_date": clean_text(publication_date),
        "doi": doi.replace("https://doi.org/", ""),
        "url": url,
        "source": source,
        "abstract": abstract[:1200],
        "matched_query": matched_query,
        "topic": topic,
        "relevance_score": score_relevance(title, abstract),
        "labels": classify_paper(title, abstract),
    }


def fetch_openalex(query: str, topic: str) -> List[Dict[str, object]]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{from_date_iso()}",
        "sort": "publication_date:desc",
        "per-page": str(MAX_PER_QUERY),
    }
    email = os.getenv("OPENALEX_EMAIL", "")
    if email:
        params["mailto"] = email
    response = requests.get("https://api.openalex.org/works", params=params, timeout=30)
    response.raise_for_status()
    papers = []
    for work in response.json().get("results", []):
        authors = ", ".join(clean_text(auth.get("author", {}).get("display_name", ""))
                            for auth in work.get("authorships", [])[:5])
        source_name = clean_text((work.get("primary_location") or {}).get("source", {}).get("display_name", ""))
        paper = normalize_paper(
            title=work.get("title", ""),
            authors=authors,
            publication_date=work.get("publication_date", ""),
            doi=work.get("doi", ""),
            url=(work.get("primary_location") or {}).get("landing_page_url", ""),
            source="OpenAlex" + (f" / {source_name}" if source_name else ""),
            abstract=abstract_from_openalex(work.get("abstract_inverted_index")),
            matched_query=query,
            topic=topic,
        )
        if paper:
            papers.append(paper)
    return papers


def fetch_crossref(query: str, topic: str) -> List[Dict[str, object]]:
    params = {
        "query": query,
        "rows": str(MAX_PER_QUERY),
        "sort": "published",
        "order": "desc",
        "filter": f"from-pub-date:{from_date_iso()}",
    }
    email = os.getenv("CROSSREF_EMAIL", "")
    if email:
        params["mailto"] = email
    response = requests.get("https://api.crossref.org/works", params=params, timeout=30)
    response.raise_for_status()
    papers = []
    for item in response.json().get("message", {}).get("items", []):
        authors = ", ".join(clean_text(f"{a.get('given', '')} {a.get('family', '')}")
                            for a in item.get("author", [])[:5])
        date_parts = (item.get("published-print", {}).get("date-parts")
                      or item.get("published-online", {}).get("date-parts")
                      or item.get("created", {}).get("date-parts")
                      or [[]])
        date_text = "-".join(str(x) for x in date_parts[0]) if date_parts and date_parts[0] else ""
        paper = normalize_paper(
            title=(item.get("title") or [""])[0],
            authors=authors,
            publication_date=date_text,
            doi=item.get("DOI", ""),
            url=item.get("URL", ""),
            source=f"Crossref / {clean_text((item.get('container-title') or [''])[0])}",
            abstract=item.get("abstract", ""),
            matched_query=query,
            topic=topic,
        )
        if paper:
            papers.append(paper)
    return papers


def fetch_pubmed(query: str, topic: str) -> List[Dict[str, object]]:
    mindate = from_date_iso().replace("-", "/")
    maxdate = today_utc().date().isoformat().replace("-", "/")
    search = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "term": query, "retmode": "json", "retmax": str(MAX_PER_QUERY),
                "sort": "pub+date", "datetype": "pdat", "mindate": mindate, "maxdate": maxdate},
        timeout=30,
    )
    search.raise_for_status()
    ids = search.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    summary = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        timeout=30,
    )
    summary.raise_for_status()
    data = summary.json().get("result", {})
    papers = []
    for uid in ids:
        item = data.get(uid, {})
        authors = ", ".join(clean_text(a.get("name", "")) for a in item.get("authors", [])[:5])
        doi = ""
        for article_id in item.get("articleids", []):
            if article_id.get("idtype") == "doi":
                doi = article_id.get("value", "")
                break
        paper = normalize_paper(
            title=item.get("title", ""),
            authors=authors,
            publication_date=item.get("pubdate", ""),
            doi=doi,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
            source="PubMed",
            abstract="",
            matched_query=query,
            topic=topic,
        )
        if paper:
            papers.append(paper)
    return papers


def fetch_rss() -> List[Dict[str, object]]:
    papers = []
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:MAX_PER_QUERY]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            if score_relevance(title, summary) < 3:
                continue
            paper = normalize_paper(
                title=title,
                authors=entry.get("author", ""),
                publication_date=entry.get("published", ""),
                url=entry.get("link", ""),
                source=f"RSS / {feed.feed.get('title', feed_url)}",
                abstract=summary,
                matched_query="RSS relevance filter",
                topic="rss",
            )
            if paper:
                papers.append(paper)
    return papers


def deduplicate(papers: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    seen = set()
    unique = []
    for paper in papers:
        doi = clean_text(paper.get("doi", "")).lower()
        title_key = re.sub(r"[^a-z0-9]+", "", clean_text(paper.get("title", "")).lower())[:120]
        key = doi or title_key
        if key and key not in seen:
            seen.add(key)
            unique.append(paper)
    unique.sort(key=lambda p: (int(p.get("relevance_score", 0)), clean_text(p.get("publication_date", ""))), reverse=True)
    return unique


def main() -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    all_papers: List[Dict[str, object]] = []
    for topic, queries in SEARCH_TOPICS.items():
        for query in queries:
            print(f"Searching {topic}: {query}")
            for fetcher in (fetch_openalex, fetch_crossref, fetch_pubmed):
                try:
                    all_papers.extend(fetcher(query, topic))
                except Exception as exc:
                    print(f"Warning: {fetcher.__name__} failed for '{query}': {exc}")
                time.sleep(0.4)
    try:
        all_papers.extend(fetch_rss())
    except Exception as exc:
        print(f"Warning: RSS collection failed: {exc}")

    unique = deduplicate(all_papers)
    today = datetime.now().strftime("%Y-%m-%d")
    output = REPORTS_DIR / f"literature_data_{today}.json"
    with output.open("w", encoding="utf-8") as f:
        json.dump({"generated_at_utc": today_utc().isoformat(), "days_back": DAYS_BACK,
                   "paper_count": len(unique), "papers": unique},
                  f, indent=2, ensure_ascii=False)
    print(f"Saved {len(unique)} unique papers to {output}")


if __name__ == "__main__":
    main()
