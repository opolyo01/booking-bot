"""
Run once to seed Pinecone with your about-me knowledge base.

Usage:
  cd backend
  python -m scripts.seed_knowledge_base

Edit the DOCUMENTS list below with your own content.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.pinecone_service import ensure_index, upsert_documents

DOCUMENTS = [
    {
        "id": "about-1",
        "text": (
            "Oleg Polyakov is a seasoned software engineer with deep experience building "
            "high-performance developer platforms, trading systems, and full-stack applications "
            "across fintech and SaaS environments. He specializes in architecting complex systems "
            "that bridge product, infrastructure, and engineering workflows."
        ),
        "metadata": {"category": "about"},
    },
    {
        "id": "about-2",
        "text": (
            "Oleg's technical background spans modern web and desktop architectures using "
            "TypeScript and JavaScript frameworks such as React and Angular, with backend services "
            "built in Node.js, Python, and Java (FastAPI, Express, Spring). He has extensive "
            "experience designing distributed systems, CI/CD pipelines, and cloud-native deployments "
            "using Kubernetes and modern developer tooling."
        ),
        "metadata": {"category": "skills"},
    },
    {
        "id": "about-3",
        "text": (
            "Recently Oleg's focus has shifted toward AI-driven developer platforms and agent systems. "
            "He is actively building tools that integrate large language models into real engineering "
            "workflows — including AI-powered release pipelines, developer assistants, and internal "
            "agent frameworks using technologies such as OpenAI APIs, MCP-based integrations, and "
            "modern coding agents including LangChain and LangGraph."
        ),
        "metadata": {"category": "skills"},
    },
    {
        "id": "about-4",
        "text": (
            "Oleg is particularly interested in the emerging field of AI agents for software "
            "development, where systems combine LLM reasoning, structured context, and tools to "
            "automate complex engineering tasks. He also develops mobile applications using "
            "React Native and native Java/Swift stacks."
        ),
        "metadata": {"category": "skills"},
    },
    {
        "id": "about-5",
        "text": (
            "Oleg writes about AI agent architectures, developer tooling, and LLM-based systems. "
            "His blog is at https://ai-agents-blog-snowy.vercel.app/ — covering experiments and "
            "insights at the intersection of AI, developer tooling, and modern software infrastructure."
        ),
        "metadata": {"category": "about"},
    },
    {
        "id": "consulting",
        "text": (
            "Oleg is open to consulting engagements in AI engineering, distributed systems architecture, "
            "developer platform design, fintech infrastructure, and LLM/agent integrations. Typical "
            "projects range from architecture reviews to hands-on implementation of complex systems."
        ),
        "metadata": {"category": "consulting"},
    },
    {
        "id": "job-offer",
        "text": (
            "For job opportunities, Oleg is interested in senior or staff engineering roles at companies "
            "building AI products, developer platforms, or high-performance fintech systems. He prefers "
            "roles where he can bridge infrastructure, AI, and product engineering."
        ),
        "metadata": {"category": "job_offer"},
    },
    {
        "id": "training",
        "text": (
            "Oleg offers technical training and workshops on LangGraph, LangChain, AI agent architectures, "
            "FastAPI, distributed systems design, and modern full-stack engineering for teams."
        ),
        "metadata": {"category": "training"},
    },
    {
        "id": "meetup",
        "text": (
            "Oleg enjoys speaking at meetups and hackathons about AI agent systems, developer tooling, "
            "and LLM-based engineering workflows. He is happy to collaborate on community events and "
            "technical talks."
        ),
        "metadata": {"category": "meetup_hackathon"},
    },
    {
        "id": "meeting-types",
        "text": (
            "Available meeting types with Oleg: job_offer (30 min) for career and role discussions, "
            "consulting (30 min) for project scoping and architecture, training (30 min) for workshops "
            "and team upskilling, meetup_hackathon (15 min) for events and community collaboration."
        ),
        "metadata": {"category": "meta"},
    },
]


async def main():
    print("Ensuring Pinecone index exists...")
    ensure_index()
    print("Upserting documents...")
    await upsert_documents(DOCUMENTS)
    print(f"Done — seeded {len(DOCUMENTS)} documents.")


if __name__ == "__main__":
    asyncio.run(main())
