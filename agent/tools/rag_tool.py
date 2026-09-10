"""Track A — RAG 検索ツール (Vertex AI Search)。

ハンドブックのコーパスをインジェストした Vertex AI Search データストアに対して
セマンティック検索を実行し、グラウンディング用のコンテキストと引用情報を返却します。
"""
from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as discoveryengine

from .. import config


def search_policy_docs(query: str) -> dict:
    """Vertex AI Search 上の HR ポリシーコーパスに対するセマンティック検索。

    Args:
        query: 従業員からの自然言語のポリシー質問または検索フレーズ。

    Returns:
        {"grounded_context": str, "citations": list[str], "resource": str}
    """
    location = config.VERTEX_AI_SEARCH_LOCATION
    project_id = config.GOOGLE_CLOUD_PROJECT
    engine_id = config.VERTEX_AI_SEARCH_ENGINE_ID

    client_options = (
        ClientOptions(api_endpoint=f"{location}-discoveryengine.googleapis.com")
        if location != "global"
        else None
    )
    client = discoveryengine.SearchServiceClient(client_options=client_options)
    serving_config = (
        f"projects/{project_id}/locations/{location}/collections/default_collection"
        f"/engines/{engine_id}/servingConfigs/default_search"
    )

    content_spec = discoveryengine.SearchRequest.ContentSearchSpec(
        extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
            max_extractive_answer_count=3,
            max_extractive_segment_count=5,
        ),
        snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
            return_snippet=True,
        ),
    )

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=5,
        content_search_spec=content_spec,
    )

    try:
        response = client.search(request)
    except Exception as e:
        return {
            "grounded_context": f"Error querying policy search engine: {e}",
            "citations": [],
            "resource": "Vertex AI Search",
        }

    contexts = []
    citations = []

    for result in response.results:
        d = result.document.derived_struct_data
        title = d.get("title") or ""
        link = d.get("link") or ""

        if link and link not in citations:
            citations.append(link)
        elif title and title not in citations:
            citations.append(title)

        header = f"### {title}" if title else "### Policy Document"
        found_content = False

        # 抽出セグメント
        segments = d.get("extractive_segments", [])
        for seg in segments:
            snippet = ""
            if hasattr(seg, "get"):
                snippet = str(seg.get("content", "")).strip()
            elif hasattr(seg, "content"):
                snippet = str(getattr(seg, "content", "")).strip()
            if snippet:
                contexts.append(f"{header}\n{snippet}")
                found_content = True

        # 抽出回答
        answers = d.get("extractive_answers", [])
        for ans in answers:
            snippet = ""
            if hasattr(ans, "get"):
                snippet = str(ans.get("content", "")).strip()
            elif hasattr(ans, "content"):
                snippet = str(getattr(ans, "content", "")).strip()
            if snippet:
                contexts.append(f"{header} (Key Answer)\n{snippet}")
                found_content = True

        # スニペットフォールバック
        if not found_content:
            for snip in d.get("snippets", []):
                snippet = ""
                if hasattr(snip, "get"):
                    snippet = str(snip.get("snippet", "")).strip()
                elif hasattr(snip, "snippet"):
                    snippet = str(getattr(snip, "snippet", "")).strip()
                if snippet:
                    contexts.append(f"{header}\n{snippet}")
                    found_content = True

    if not contexts:
        return {
            "grounded_context": "No relevant policy documents found.",
            "citations": [],
            "resource": "Vertex AI Search",
        }

    return {
        "grounded_context": "\n\n---\n\n".join(contexts),
        "citations": citations,
        "resource": citations[0] if citations else "Altostrat HR Policy Handbook",
    }

