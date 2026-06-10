"""
Scrape Oleg's blog and upsert all posts into Pinecone as chunked documents.

Each H2 section becomes its own document so similarity search can pinpoint
the exact part of a post that answers a question.

Usage:
    python -m backend.scripts.scrape_blog

Or trigger via the admin API:
    POST /admin/knowledge-base/scrape-blog
"""
import asyncio
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import httpx
from bs4 import BeautifulSoup

BLOG_BASE = "https://ai-agents-blog-snowy.vercel.app"

POST_SLUGS = [
    # Agents
    "/posts/codex-vs-claude-code-token-limits",
    "/posts/i-replaced-my-n8n-workflows-and-langchain-scripts-with-a-markdown-file",
    "/posts/skills-are-the-npm-of-ai-agents",
    "/posts/why-ai-agents-need-skills",
    "/posts/what-kiro-is-and-how-it-compares",
    "/posts/mcp-agent-architecture",
    # Messaging Systems
    "/posts/queues-vs-logs-in-trading-systems",
    "/posts/messaging-systems-for-trading-uis",
    "/posts/kafka-cdc-basics",
    # Health Tech
    "/posts/why-health-plus-tech-might-be-the-new-computer-science",
    "/posts/a-health-tech-project-roadmap-by-year",
    "/posts/a-concrete-health-tech-curriculum-roadmap",
    # AI Engineering
    "/posts/llm-determinism-temperature-explained",
    # Data Engineering
    "/posts/spark-for-full-stack-engineers",
]

# Max characters per Pinecone chunk — keeps embedding quality high
_MAX_CHUNK_CHARS = 1500


def _extract_sections(html: str, url: str) -> list[dict]:
    """
    Parse one post's HTML into section-level chunks.
    Returns list of {"id", "text", "metadata"} ready for Pinecone upsert.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Locate the article body — try semantic tags then class hints
    container = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"prose|content|post|article", re.I))
        or soup.body
    )

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else url.split("/")[-1].replace("-", " ").title()
    slug_id = url.rstrip("/").split("/")[-1]

    # Walk top-level block elements and split on H2 boundaries
    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = [f"Post: {title}"]

    block_tags = {"h2", "h3", "p", "ul", "ol", "li", "pre", "blockquote", "table", "td", "th"}

    for tag in container.find_all(block_tags):
        # Skip deeply nested duplicates (e.g. li inside ul already captured)
        if tag.name in ("li", "td", "th") and tag.find_parent(["ul", "ol", "table"]):
            continue

        if tag.name == "h2":
            if len("\n".join(current_lines)) > 80:  # skip near-empty sections
                sections.append((current_heading, current_lines))
            current_heading = tag.get_text(strip=True)
            current_lines = [f"Post: {title}", f"Section: {current_heading}"]
        elif tag.name == "h3":
            heading_text = tag.get_text(strip=True)
            if heading_text:
                current_lines.append(f"\n### {heading_text}")
        else:
            text = tag.get_text(separator=" ", strip=True)
            if text and len(text) > 10:
                current_lines.append(text)

    # Flush last section
    if len("\n".join(current_lines)) > 80:
        sections.append((current_heading, current_lines))

    # If the page gave us nothing useful (likely CSR), return empty
    if not sections:
        return []

    docs = []
    for i, (heading, lines) in enumerate(sections):
        text = "\n".join(lines)
        # Hard-cap chunk size to keep embedding quality high
        if len(text) > _MAX_CHUNK_CHARS:
            text = text[:_MAX_CHUNK_CHARS] + "…"
        docs.append({
            "id": f"blog-{slug_id}-{i}",
            "text": text,
            "metadata": {
                "source": "blog",
                "post_title": title,
                "section": heading or "intro",
                "url": url,
            },
        })

    return docs


async def scrape_all(verbose: bool = True) -> list[dict]:
    """Fetch all posts and return the full list of chunk documents."""
    all_docs: list[dict] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for slug in POST_SLUGS:
            url = f"{BLOG_BASE}{slug}"
            if verbose:
                print(f"  Fetching {slug}…", end=" ", flush=True)
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                docs = _extract_sections(resp.text, url)
                all_docs.extend(docs)
                if verbose:
                    print(f"{len(docs)} chunks")
            except Exception as exc:
                if verbose:
                    print(f"FAILED ({exc})")

    return all_docs


async def main():
    from backend.services.pinecone_service import ensure_index, upsert_documents

    print("Ensuring Pinecone index exists…")
    ensure_index()

    print(f"Scraping {len(POST_SLUGS)} posts…")
    docs = await scrape_all(verbose=True)

    if not docs:
        print("No documents extracted — the blog may be client-side rendered.")
        return

    print(f"\nUpserting {len(docs)} chunks to Pinecone…")
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        await upsert_documents(batch)
        print(f"  Batch {i // batch_size + 1}: {len(batch)} docs")

    print(f"\nDone — {len(docs)} chunks from {len(POST_SLUGS)} posts in Pinecone.")


if __name__ == "__main__":
    asyncio.run(main())
