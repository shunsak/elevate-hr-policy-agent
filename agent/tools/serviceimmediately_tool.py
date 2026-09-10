"""ServiceImmediately (ITSM: ITサービス管理・人事サービス配信) 連携ツール

インシデントチケットの照会、新規作成、コメント追記、ステータス更新、
および Saga 補償トランザクション（チケット無効化）機能を提供します。
"""

from datetime import datetime
import json
import logging
from typing import Any, Dict
import urllib.error
import urllib.request

from .. import config

logger = logging.getLogger(__name__)

# ローカルインメモリデータストア（決定論的テストおよびオフラインフォールバック用）
_MOCK_TICKETS: Dict[str, Dict[str, Any]] = {
    "INC123456": {
        "ticket_id": "INC123456",
        "employee_id": "EMP001",
        "category": "Network",
        "summary": "VPN connection drops frequently",
        "description": "User experiences intermittent VPN disconnections when connecting from Singapore home network.",
        "priority": "3 - Medium",
        "status": "In Progress",
        "assignee": "IT Network Operations",
        "comments": [
            {
                "author": "IT Support Bot",
                "timestamp": "2026-09-08T09:00:00",
                "text": "Ticket created automatically via user request.",
            },
            {
                "author": "John Doe (Network Eng)",
                "timestamp": "2026-09-08T10:30:00",
                "text": "Investigating gateway traffic. Requested log upload from user.",
            },
        ],
        "created_at": "2026-09-08T09:00:00",
        "updated_at": "2026-09-08T10:30:00",
    }
}

_TICKET_COUNTER = 200000


def get_ticket_details(ticket_id: str) -> Dict[str, Any]:
    """指定されたチケットIDの詳細（ステータス、要約、担当者、コメント履歴）を照会します。

    Args:
        ticket_id: インシデントチケットID（例: 'INC123456'）

    Returns:
        チケットの詳細情報辞書
    """
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/serviceimmediately/tickets/{ticket_id}"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {config.MCP_TOKEN}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"外部 ServiceImmediately API 呼出失敗。ローカルモックにフォールバック: {e}")

    ticket = _MOCK_TICKETS.get(ticket_id)
    if ticket:
        return {"status": "success", "ticket": ticket}
    return {
        "status": "error",
        "message": f"チケットID '{ticket_id}' が見つかりませんでした。",
    }


def create_incident_ticket(
    employee_id: str,
    category: str,
    summary: str,
    description: str,
    priority: str = "3 - Medium",
    idempotency_key: str = "",
) -> Dict[str, Any]:
    """ServiceImmediately で新規サポート・インシデントチケットを作成します。

    Args:
        employee_id: 申請者の従業員ID
        category: カテゴリ（例: 'Hardware', 'Software', 'Facilities', 'Access'）
        summary: チケット要約・件名
        description: インシデントの詳細な説明
        priority: 優先度 ('1 - Critical', '2 - High', '3 - Medium', '4 - Low')
        idempotency_key: 冪等性キー（重複防止用UUID）

    Returns:
        作成されたチケットIDおよびステータス情報
    """
    global _TICKET_COUNTER

    # ガードレール: 優先度フォーマット検証
    valid_priorities = ("1 - Critical", "2 - High", "3 - Medium", "4 - Low")
    if priority not in valid_priorities:
        # 表記揺れ吸収
        matched = [p for p in valid_priorities if priority.lower() in p.lower()]
        if matched:
            priority = matched[0]
        else:
            priority = "3 - Medium"

    # 外部 API 呼出試行
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/serviceimmediately/tickets"
            payload = {
                "employee_id": employee_id,
                "category": category,
                "summary": summary,
                "description": description,
                "priority": priority,
                "idempotency_key": idempotency_key,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {config.MCP_TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"外部 ServiceImmediately API 呼出失敗。ローカルモックにフォールバック: {e}")

    # ローカル処理
    _TICKET_COUNTER += 1
    ticket_id = f"INC{_TICKET_COUNTER}"
    now_iso = datetime.now().isoformat()

    new_ticket = {
        "ticket_id": ticket_id,
        "employee_id": employee_id,
        "category": category,
        "summary": summary,
        "description": description,
        "priority": priority,
        "status": "New",
        "assignee": "ServiceDesk Triage",
        "comments": [
            {
                "author": "HR Agent Orchestrator",
                "timestamp": now_iso,
                "text": f"自動起票: {summary}",
            }
        ],
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    _MOCK_TICKETS[ticket_id] = new_ticket

    return {
        "status": "success",
        "message": f"インシデントチケット '{ticket_id}' が正常に作成されました。",
        "ticket_id": ticket_id,
        "priority": priority,
        "ticket_status": "New",
    }


def add_ticket_comment(ticket_id: str, comment: str) -> Dict[str, Any]:
    """既存のインシデントチケットにコメントまたは更新ノートを追記します。

    Args:
        ticket_id: チケットID
        comment: 追記するコメント本文

    Returns:
        更新ステータス
    """
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/serviceimmediately/tickets/{ticket_id}/comments"
            data = json.dumps({"comment": comment}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {config.MCP_TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"外部 ServiceImmediately API 呼出失敗。ローカルモックにフォールバック: {e}")

    ticket = _MOCK_TICKETS.get(ticket_id)
    if not ticket:
        return {
            "status": "error",
            "message": f"チケットID '{ticket_id}' が存在しません。",
        }

    ticket["comments"].append({
        "author": "Employee / Agent",
        "timestamp": datetime.now().isoformat(),
        "text": comment,
    })
    ticket["updated_at"] = datetime.now().isoformat()

    return {
        "status": "success",
        "message": f"チケット '{ticket_id}' にコメントが追記されました。",
    }


def update_ticket_status(
    ticket_id: str, status: str, resolution_notes: str = ""
) -> Dict[str, Any]:
    """チケットのステータス（ライフサイクル状態）を更新します。

    Args:
        ticket_id: チケットID
        status: 新しいステータス ('In Progress', 'Resolved', 'Closed', 'Cancelled')
        resolution_notes: 解決・変更メモ

    Returns:
        更新ステータス
    """
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/serviceimmediately/tickets/{ticket_id}/status"
            data = json.dumps({
                "status": status,
                "resolution_notes": resolution_notes,
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {config.MCP_TOKEN}",
                    "Content-Type": "application/json",
                },
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"外部 ServiceImmediately API 呼出失敗。ローカルモックにフォールバック: {e}")

    ticket = _MOCK_TICKETS.get(ticket_id)
    if not ticket:
        return {
            "status": "error",
            "message": f"チケットID '{ticket_id}' が存在しません。",
        }

    ticket["status"] = status
    ticket["updated_at"] = datetime.now().isoformat()
    if resolution_notes:
        ticket["comments"].append({
            "author": "System Resolver",
            "timestamp": datetime.now().isoformat(),
            "text": f"ステータス変更 ({status}): {resolution_notes}",
        })

    return {
        "status": "success",
        "message": f"チケット '{ticket_id}' のステータスが '{status}' に変更されました。",
        "current_status": status,
    }


def void_incident_ticket(ticket_id: str, reason: str = "") -> Dict[str, Any]:
    """【Saga補償トランザクション】複数システム連携失敗時に、起票済みチケットを無効化（Cancelled）します。

    Args:
        ticket_id: 無効化するチケットID
        reason: 無効化理由（例: 'WorkWeek連携失敗に伴う補償ロールバック'）

    Returns:
        無効化結果ステータス
    """
    return update_ticket_status(
        ticket_id,
        status="Cancelled",
        resolution_notes=f"【Saga補償ロールバック】{reason}",
    )
