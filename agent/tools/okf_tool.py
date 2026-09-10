"""Track B — OKF retrieval tools.

The agent uses these to *navigate* the Open Knowledge Format bundle in knowledge/:
first list what concepts exist, then read the most relevant one. No vector DB.

You implement two functions. Keep the return shapes exactly as documented — the
prompt and the agent rely on them.
"""
import os
import re
import yaml

from .. import config  # config.KNOWLEDGE_DIR points at the knowledge/ bundle

RESERVED_FILES = {"index.md", "log.md"}
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def list_concepts() -> dict:
    """List the policy concepts available in the OKF bundle.

    Returns:
        {"concepts": [{"id": str, "title": str, "description": str}, ...]}
        where `id` is the concept path without the .md suffix,
        e.g. "leave/bereavement-leave".
    """
    knowledge_dir = os.path.abspath(config.KNOWLEDGE_DIR)
    concepts = []

    for root, _, files in os.walk(knowledge_dir):
        for file in sorted(files):
            if not file.endswith(".md") or file in RESERVED_FILES:
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, knowledge_dir)
            concept_id = rel_path[:-3] if rel_path.endswith(".md") else rel_path

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                m = FRONTMATTER_RE.match(content)
                fm = yaml.safe_load(m.group(1)) if m else {}
                if not isinstance(fm, dict):
                    fm = {}
            except Exception:
                fm = {}

            concepts.append({
                "id": concept_id,
                "title": fm.get("title", concept_id),
                "description": fm.get("description", ""),
            })

    return {"concepts": concepts}


def read_concept(concept_id: str) -> dict:
    """Read one OKF concept's content and citation.

    Args:
        concept_id: e.g. "03-other-compassionate-unpaid-leaves/3.1-bereavement-leave-global" (no .md).

    Returns:
        {"content": str, "title": str, "resource": str | None}
        where `content` is the markdown body (after the frontmatter) and
        `resource` is the frontmatter `source` (or `resource`) reference if present.
    """
    knowledge_dir = os.path.abspath(config.KNOWLEDGE_DIR)
    normalized_id = os.path.normpath(concept_id.strip("/"))
    target_path = os.path.abspath(os.path.join(knowledge_dir, f"{normalized_id}.md"))

    # Guard against paths that escape knowledge_dir
    if not target_path.startswith(knowledge_dir + os.sep):
        return {
            "content": f"Error: Invalid concept_id {concept_id!r} (path traversal detected).",
            "title": "",
            "resource": None,
        }

    if not os.path.isfile(target_path):
        return {
            "content": f"Concept {concept_id!r} not found in knowledge bundle.",
            "title": "",
            "resource": None,
        }

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            text = f.read()

        m = FRONTMATTER_RE.match(text)
        if m:
            fm = yaml.safe_load(m.group(1)) or {}
            if not isinstance(fm, dict):
                fm = {}
            body = text[m.end():].strip()
        else:
            fm = {}
            body = text.strip()

        title = fm.get("title", "")
        resource = fm.get("source") or fm.get("resource")
        return {
            "content": body,
            "title": title,
            "resource": resource,
        }
    except Exception as e:
        return {
            "content": f"Error reading concept {concept_id!r}: {e}",
            "title": "",
            "resource": None,
        }
