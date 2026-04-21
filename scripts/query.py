"""
LLM Knowledge Base v2 — Graph-Traversal Query Engine
Finds relevant wiki pages using keyword + tag + alias matching,
then expands context via typed graph traversal with weighted edges.

Usage:
    python scripts/query.py "What is Agentic RAG?" --depth 2
    python scripts/query.py "RAG effectiveness" --depth 2 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    WIKI_DIR,
    GRAPH_PATH,
    list_wiki_pages,
    read_page,
    extract_wikilinks,
)

# Edge weights from schema relation types
EDGE_WEIGHTS = {
    "cites": 4.0,
    "contradicts": 3.0,
    "implements": 3.0,
    "extends": 2.0,
    "prerequisite_of": 2.0,
    "derived_from": 2.0,
    "trades_off": 1.0,
    "neutral": 1.0,
}


def expand_query(question: str, model: str | None = None) -> list[str]:
    """Expand a question into multiple search queries using LLM.

    Returns a list of query strings including the original question.
    Falls back to [question] if LLM is unavailable or returns invalid output.
    """
    if not question.strip():
        return [question]

    system_prompt = (
        "You are a search query expander for a knowledge base. Given a question, "
        "generate 3-4 alternative search queries that would find relevant pages "
        "even if they use different terminology.\n\n"
        "Rules:\n"
        "- Each query should be 2-6 words\n"
        "- Use synonyms, related terms, and different phrasings\n"
        "- Include the original question's key concepts\n"
        "- Return only the queries, one per line\n"
        "- Do not include numbers, explanations, or formatting"
    )
    prompt = f"Question: {question}"

    try:
        from llm_client import completion_with_retry
        response = completion_with_retry(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=0.7,
            max_tokens=256,
            timeout=30,
            max_retries=1,
        )
        lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
        if not lines:
            return [question]
        # Always include the original question
        queries = [question] + lines
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for q in queries:
            q_lower = q.lower()
            if q_lower not in seen:
                seen.add(q_lower)
                unique.append(q)
        return unique[:5]  # Cap at 5 queries total
    except Exception:
        return [question]


def index_boost(question: str, wiki_dir: Path | None = None) -> dict[str, float]:
    """Read _index.md and score each page by question-word overlap with its entry.

    The index contains one-line summaries per page. Matching question words
    against these summaries provides a content-aware boost before the more
    expensive per-page scoring.

    Returns {page_stem: boost_score}.
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    index_path = wiki_dir / "indexes" / "_index.md"
    if not index_path.exists():
        return {}

    try:
        text = index_path.read_text(encoding="utf-8")
    except Exception:
        return {}

    question_words = set(question.lower().split())
    boosts: dict[str, float] = {}

    # Parse lines like "- [[Page Name]]" or "- [[Page Name]] — summary text"
    import re
    link_pattern = re.compile(r"-\s*\[\[([^\]]+)\]\](?:\s*[—–-]\s*(.*))?")

    for line in text.splitlines():
        m = link_pattern.match(line.strip())
        if not m:
            continue
        page_stem = m.group(1)
        summary = (m.group(2) or "").lower()
        line_text = (page_stem + " " + summary).lower()

        overlap = sum(1 for w in question_words if len(w) > 2 and w in line_text)
        if overlap > 0:
            boosts[page_stem] = overlap * 5  # +5 per matching word in index

    return boosts


def find_seed_pages(
    question: str | list[str],
    wiki_dir: Path | None = None,
    top_k: int = 5,
) -> list[Path]:
    """Find seed pages relevant to a question using keyword + tag + alias matching.

    Accepts either a single query string or a list of query strings.
    When given a list, scores pages against each query and merges by
    taking the maximum score per page across all variants.

    Scoring:
    - Index boost: +5 per question-word match in _index.md summary
    - Title word overlap: +10 per matching word
    - Alias match: +8 per matching alias
    - Tag word overlap: +3 per matching tag word
    - Content keyword match (first 500 chars): +1 per matching word (>3 chars)

    Returns top_k pages sorted by score descending.
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    # Normalize to list of queries
    if isinstance(question, str):
        queries = [question]
    else:
        queries = list(question)

    if not queries:
        return []

    # Collect pages from concepts and entities directories
    pages = []
    for subdir in ["concepts", "entities"]:
        d = wiki_dir / subdir
        if d.exists():
            pages.extend(sorted(d.glob("*.md")))

    if not pages:
        return []

    # Score pages against all query variants, taking max score per page
    best_scores: dict[Path, float] = {}

    for q in queries:
        question_words = set(q.lower().split())

        # Get index boost for this query
        boosts = index_boost(q, wiki_dir)

        for page in pages:
            if page.stem.startswith("_"):
                continue

            try:
                post = read_page(page)
            except Exception:
                continue

            score = 0.0

            # Index boost (from _index.md summary matching)
            score += boosts.get(page.stem, 0.0)

            # Title match
            title = post.metadata.get("title", page.stem).lower()
            title_words = set(title.split())
            title_overlap = len(question_words & title_words)
            score += title_overlap * 10

            # Alias match
            for alias in post.metadata.get("aliases", []):
                if alias.lower() in q.lower():
                    score += 8

            # Tag match
            for tag in post.metadata.get("tags", []):
                tag_words = set(tag.replace("/", " ").replace("-", " ").split())
                tag_overlap = len(question_words & tag_words)
                score += tag_overlap * 3

            # Content keyword match (first 500 chars)
            content_sample = post.content[:500].lower()
            for word in question_words:
                if len(word) > 3 and word in content_sample:
                    score += 1

            if score > 0:
                # Keep the best score across all query variants
                if page not in best_scores or score > best_scores[page]:
                    best_scores[page] = score

    # Sort by best score descending
    sorted_pages = sorted(best_scores.items(), key=lambda x: x[1], reverse=True)
    return [page for page, _ in sorted_pages[:top_k]]


def traverse_typed_graph(seed_pages: list[Path], graph: dict, depth: int = 2) -> list[dict]:
    """Traverse typed edges from seed pages to expand context.

    For each seed page, follow its edges in the graph.
    At each depth level, expand to connected pages.
    Score pages by cumulative edge weights from seed pages.

    Returns list of dicts: [{"page": Path, "score": float, "path": list[str]}]
    sorted by score descending.
    """
    if not seed_pages or not graph.get("edges"):
        return [{"page": p, "score": 10.0, "path": [p.stem]} for p in seed_pages]

    # Build adjacency map from graph
    node_stems = {n["id"].lower(): n["id"] for n in graph.get("nodes", [])}
    adjacency: dict[str, list[tuple[str, str, float]]] = {}  # source -> [(target, type, weight)]

    for edge in graph.get("edges", []):
        source = edge.get("source", "")
        target = edge.get("target", "")
        edge_type = edge.get("type", "neutral")
        weight = edge.get("weight", EDGE_WEIGHTS.get(edge_type, 1.0))
        if source not in adjacency:
            adjacency[source] = []
        adjacency[source].append((target, edge_type, weight))

    # BFS with weighted scoring
    visited: dict[str, float] = {}  # page_stem -> best score
    paths: dict[str, list[str]] = {}  # page_stem -> path from seed
    current_layer: list[tuple[str, float, list[str]]] = []

    # Initialize with seed pages
    for seed_page in seed_pages:
        stem = seed_page.stem
        if stem not in visited:
            visited[stem] = 10.0
            paths[stem] = [stem]
            current_layer.append((stem, 10.0, [stem]))

    for d in range(depth):
        next_layer: list[tuple[str, float, list[str]]] = []
        for node_stem, node_score, node_path in current_layer:
            edges = adjacency.get(node_stem, [])
            # Also try lowercase match
            edges += adjacency.get(node_stem.lower(), [])
            for target, edge_type, weight in edges:
                # Normalize target to match file stems
                target_stem = node_stems.get(target.lower(), target)
                new_score = node_score * weight / (d + 1)  # Decay with depth
                if target_stem not in visited or new_score > visited.get(target_stem, 0):
                    visited[target_stem] = visited.get(target_stem, 0) + new_score
                    new_path = node_path + [target_stem]
                    paths[target_stem] = new_path
                    next_layer.append((target_stem, new_score, new_path))
        current_layer = next_layer

    # Find actual page files for visited stems by searching near seed pages
    all_pages = {}
    if seed_pages:
        # Determine wiki_dir from the seed page paths
        for seed in seed_pages:
            wiki_dir_guess = seed.parent.parent  # concepts/ or entities/ -> wiki/
            for subdir in ["concepts", "entities"]:
                d = wiki_dir_guess / subdir
                if d.exists():
                    for p in d.glob("*.md"):
                        all_pages[p.stem] = p
            break
    if not all_pages:
        all_pages = {p.stem: p for p in list_wiki_pages()}
    results = []
    for stem, score in sorted(visited.items(), key=lambda x: x[1], reverse=True):
        if stem in all_pages:
            results.append({
                "page": all_pages[stem],
                "score": round(score, 2),
                "path": paths.get(stem, [stem]),
            })

    return results


def build_context(pages: list[dict], max_chars: int = 50_000) -> str:
    """Build a context string from traversed pages.

    For each page, format as:
    ## [Page Title] (type: concept, confidence: HIGH)

    [page content]

    ---

    Stop if max_chars would be exceeded.
    """
    context_parts = []
    char_count = 0

    for page_info in pages:
        page = page_info["page"]
        try:
            post = read_page(page)
            header = f"## [{post.metadata.get('title', page.stem)}] (type: {post.metadata.get('type', '?')}, confidence: {post.metadata.get('confidence', '?')})"
            section = f"{header}\n\n{post.content}\n\n---\n"

            if char_count + len(section) > max_chars:
                break

            context_parts.append(section)
            char_count += len(section)
        except Exception:
            continue

    return "\n".join(context_parts)


def synthesize_answer(question: str, context: str, model: str | None = None) -> str:
    """Call LLM to synthesize an answer from wiki context."""
    from llm_client import completion_with_retry

    system_prompt = (
        "You are a knowledge base query engine. Answer the user's question using ONLY "
        "the provided wiki context. Cite sources using [source: filename, §section] format. "
        "If the context doesn't contain enough information, say so explicitly. "
        "Be concise, factual, and structured. Use markdown headers and bullet points."
    )
    prompt = f"## Question\n{question}\n\n## Wiki Context\n{context}\n\n## Answer\n"

    return completion_with_retry(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=0.3,
        max_tokens=4096,
        timeout=180,
    )


def main():
    parser = argparse.ArgumentParser(
        description="LLM Knowledge Base v2 — Graph-Traversal Query Engine",
    )
    parser.add_argument("question", help="Question to find context for")
    parser.add_argument("--depth", type=int, default=2, help="Link traversal depth (default: 2)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of seed pages (default: 5)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--context-only", action="store_true", help="Output raw context without LLM synthesis")

    args = parser.parse_args()

    pages = list_wiki_pages()
    if not pages:
        print("Wiki is empty. Ingest some sources first.")
        sys.exit(0)

    seed_pages = find_seed_pages(args.question, top_k=args.top_k)

    if not seed_pages:
        print("No relevant wiki pages found.")
        sys.exit(0)

    # Load graph
    graph = {}
    if GRAPH_PATH.exists():
        graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))

    traversed = traverse_typed_graph(seed_pages, graph, args.depth)
    context = build_context(traversed)

    if args.context_only:
        print(context)
        sys.exit(0)

    print(f"\n🔍 Question: {args.question}")
    print(f"📄 Seed pages: {', '.join(p.stem for p in seed_pages)}")
    print(f"🔗 Traversed: {len(traversed)} pages (depth={args.depth})")
    print(f"📝 Context: {len(context):,} chars")
    print(f"🧠 Synthesizing answer...\n")

    try:
        answer = synthesize_answer(args.question, context)
        print(answer)
    except Exception as e:
        print(f"⚠️  LLM synthesis failed: {e}")
        print("Falling back to raw context:\n")
        print(context)

    if args.json:
        output = {
            "question": args.question,
            "seed_pages": [p.stem for p in seed_pages],
            "traversed_pages": [{"page": r["page"].stem, "score": r["score"], "path": r["path"]} for r in traversed],
            "context_chars": len(context),
            "context": context,
            "answer": answer,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()