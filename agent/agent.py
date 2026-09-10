"""HR Policy & Enterprise SaaS Agent — エントリーポイント.

規程検索 (OKF/RAG) に加え、WorkWeek (HCM) および ServiceImmediately (ITSM) を統合した
エンタープライズ対応のオーケストレーターです。
"""
import asyncio
import re
import sys
from typing import Any, Dict, List, Tuple

from google.adk.agents import LlmAgent

from . import config
from .prompt import POLICY_AGENT_PROMPT


# ---------------------------------------------------------------------------
# ツール選定ロジック: 規程検索 + WorkWeek + ServiceImmediately
# ---------------------------------------------------------------------------
def select_tools(mode: str):
    """指定された検索モードに応じた規程検索ツールおよび SaaS 連携ツールを返却します。"""
    tools = []
    if mode in ("okf", "hybrid"):
        from .tools.okf_tool import list_concepts, read_concept
        tools += [list_concepts, read_concept]
    if mode in ("rag", "hybrid"):
        from .tools.rag_tool import search_policy_docs
        tools += [search_policy_docs]
    if not tools:
        raise ValueError(f"未知の RETRIEVAL_MODE です: {mode!r} (okf | rag | hybrid を指定してください)")

    # WorkWeek (HCM) ツール群
    from .tools.workweek_tool import (
        cancel_leave_request,
        get_employee_profile,
        get_leave_balance,
        submit_leave_request,
        update_contact_info,
    )
    # ServiceImmediately (ITSM) ツール群
    from .tools.serviceimmediately_tool import (
        add_ticket_comment,
        create_incident_ticket,
        get_ticket_details,
        update_ticket_status,
        void_incident_ticket,
    )

    tools += [
        get_employee_profile,
        update_contact_info,
        get_leave_balance,
        submit_leave_request,
        cancel_leave_request,
        get_ticket_details,
        create_incident_ticket,
        add_ticket_comment,
        update_ticket_status,
        void_incident_ticket,
    ]
    return tools


# ---------------------------------------------------------------------------
# インプロセス・軽量多層防御ガードレール (SLA < 50ms)
# ---------------------------------------------------------------------------
_CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(prior|previous)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+leak", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?(system|developer)\s+prompt", re.IGNORECASE),
    re.compile(r"これまでの指示を(すべて|全部)?無視", re.IGNORECASE),
]


def apply_input_guardrail(query: str) -> Tuple[bool, str]:
    """入力に対するプロンプトインジェクション検知を行います。"""
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(query):
            return False, "セキュリティポリシーに基づき、システム命令の変更やプロンプトの開示を求めるリクエストは処理できません。"
    return True, query


def apply_output_guardrail(response_text: str) -> str:
    """出力に対する PII（クレジットカード番号等）マスキングを行います。"""
    masked = _CREDIT_CARD_REGEX.sub("[REDACTED_CARD_NUMBER]", response_text)
    return masked


# ===========================================================================
# root_agent の構築 (Gemini 3.8 Flash)
# ===========================================================================
root_agent = LlmAgent(
    name="hr_enterprise_agent",
    model=config.GEMINI_MODEL,
    description="Altostrat Enterprise HR Assistant for policies, WorkWeek HCM, and ServiceImmediately ITSM.",
    instruction=POLICY_AGENT_PROMPT,
    tools=select_tools(config.RETRIEVAL_MODE),
)


# ---------------------------------------------------------------------------
# CLI ランナー & セッション管理
# ---------------------------------------------------------------------------
_session_service = None


def _ensure_runner():
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    global _session_service
    if root_agent is None:
        raise SystemExit(
            "root_agent is None — agent/agent.py で root_agent を構築してください。"
        )
    if _session_service is None:
        _session_service = InMemorySessionService()
    return Runner(app_name=config.APP_NAME, agent=root_agent, session_service=_session_service)


async def _ensure_session_async(user_id: str, session_id: str):
    """非同期 API 経由でセッションを作成します。"""
    try:
        await _session_service.create_session(
            app_name=config.APP_NAME, user_id=user_id, session_id=session_id
        )
    except Exception:
        pass  # 既存セッション


async def _run_query_traced_async(query: str, user_id: str, session_id: str):
    from google.genai import types

    # 入力ガードレール検査
    is_safe, guarded_query = apply_input_guardrail(query)
    if not is_safe:
        return guarded_query, [{"tool": "input_guardrail", "payload": {"blocked": True}}]

    runner = _ensure_runner()
    await _ensure_session_async(user_id, session_id)
    message = types.Content(role="user", parts=[types.Part(text=guarded_query)])
    final = ""
    evidence = []
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            fr = getattr(part, "function_response", None)
            if fr is not None:
                evidence.append({"tool": getattr(fr, "name", "?"), "payload": fr.response})
        if event.is_final_response() and event.content.parts:
            texts = [p.text for p in event.content.parts if getattr(p, "text", None)]
            if texts:
                final = "\n".join(texts)

    # 出力ガードレール検査（PIIマスキング）
    final = apply_output_guardrail(final)
    return final, evidence


def run_query(query: str, user_id: str = "learner", session_id: str = "session-1") -> str:
    """エージェントにクエリを送信し、回答文字列を取得します。"""
    answer, _evidence = run_query_traced(query, user_id=user_id, session_id=session_id)
    return answer


def run_query_traced(query: str, user_id: str = "learner", session_id: str = "session-1"):
    """エージェントにクエリを送信し、(回答, 実行証跡evidence) を取得します。"""
    return asyncio.run(_run_query_traced_async(query, user_id, session_id))


def _interactive():
    print(f"Enterprise HR Agent [{config.RETRIEVAL_MODE} | {config.GEMINI_MODEL}] — 'exit' で終了。")
    while True:
        try:
            q = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit"}:
            break
        if q:
            print(f"\nagent > {run_query(q)}")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "--interactive":
        _interactive()
    elif argv:
        print(run_query(" ".join(argv)))
    else:
        print('使用法: uv run python -m agent.agent "<質問または指示>"  |  --interactive')


if __name__ == "__main__":
    main()
