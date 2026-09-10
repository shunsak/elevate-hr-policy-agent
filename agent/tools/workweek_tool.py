"""WorkWeek (HCM: 人事管理システム) 連携ツール

従業員プロフィール照会、有給・病気休暇残高確認、休暇申請の提出、および
Saga補償トランザクション（申請取消）機能を提供します。
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
_MOCK_EMPLOYEES: Dict[str, Dict[str, Any]] = {
    "EMP001": {
        "employee_id": "EMP001",
        "name": "Alex Chen",
        "email": "alex.chen@altostrat.com",
        "department": "Engineering",
        "job_title": "Senior Cloud Software Engineer",
        "manager": "Sarah Jenkins",
        "hire_date": "2018-04-15",
        "address": "12 Marina Boulevard, Singapore 018982",
        "phone": "+65 9123 4567",
        "remote_work_eligible": True,
        "location": "Singapore",
    },
    "learner": {
        "employee_id": "learner",
        "name": "Taro Yamada",
        "email": "taro.yamada@altostrat.com",
        "department": "Customer Engineering",
        "job_title": "Cloud Architect",
        "manager": "Kenji Sato",
        "hire_date": "2020-01-10",
        "address": "1-1-1 Otemachi, Chiyoda-ku, Tokyo, Japan",
        "phone": "+81 90 1234 5678",
        "remote_work_eligible": True,
        "location": "Tokyo",
    },
}

_MOCK_LEAVE_BALANCES: Dict[str, Dict[str, Any]] = {
    "EMP001": {
        "employee_id": "EMP001",
        "vacation": {"accrued": 21.0, "used": 5.0, "remaining": 16.0},
        "sick": {"accrued": 14.0, "used": 2.0, "remaining": 12.0},
    },
    "learner": {
        "employee_id": "learner",
        "vacation": {"accrued": 20.0, "used": 4.0, "remaining": 16.0},
        "sick": {"accrued": 14.0, "used": 0.0, "remaining": 14.0},
    },
}

_MOCK_LEAVE_REQUESTS: Dict[str, Dict[str, Any]] = {}
_REQUEST_COUNTER = 1000


def get_employee_profile(employee_id: str) -> Dict[str, Any]:
    """指定された従業員IDのプロフィール情報（業務・連絡先メタデータ）を取得します。

    Args:
        employee_id: 従業員ID（例: 'EMP001', 'learner'）

    Returns:
        従業員情報（氏名、メール、部署、役職、上司、住所、電話番号等）を含む辞書
    """
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/workweek/employees/{employee_id}"
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
            logger.warning(f"外部 WorkWeek API 呼出失敗。ローカルモックにフォールバック: {e}")

    profile = _MOCK_EMPLOYEES.get(employee_id)
    if profile:
        return {"status": "success", "profile": profile}
    return {
        "status": "error",
        "message": f"従業員ID '{employee_id}' が見つかりませんでした。",
    }


def update_contact_info(
    employee_id: str, address: str = "", phone: str = ""
) -> Dict[str, Any]:
    """従業員の自宅住所および電話番号を更新します。

    Args:
        employee_id: 従業員ID
        address: 新しい自宅住所（省略時は更新なし）
        phone: 新しい電話番号（省略時は更新なし）

    Returns:
        更新結果および最新の連絡先情報
    """
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/workweek/employees/{employee_id}/contact"
            data = json.dumps({"address": address, "phone": phone}).encode("utf-8")
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
            logger.warning(f"外部 WorkWeek API 呼出失敗。ローカルモックにフォールバック: {e}")

    profile = _MOCK_EMPLOYEES.get(employee_id)
    if not profile:
        return {
            "status": "error",
            "message": f"従業員ID '{employee_id}' が見つかりません。",
        }

    if address:
        profile["address"] = address
    if phone:
        profile["phone"] = phone

    return {
        "status": "success",
        "message": "連絡先情報が正常に更新されました。",
        "employee_id": employee_id,
        "updated_address": profile["address"],
        "updated_phone": profile["phone"],
    }


def get_leave_balance(employee_id: str) -> Dict[str, Any]:
    """従業員の有給休暇（Vacation）および病気休暇（Sick）の残日数を照会します。

    Args:
        employee_id: 従業員ID

    Returns:
        発生日数、消化日数、残日数を含む辞書
    """
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/workweek/employees/{employee_id}/leave-balance"
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
            logger.warning(f"外部 WorkWeek API 呼出失敗。ローカルモックにフォールバック: {e}")

    balance = _MOCK_LEAVE_BALANCES.get(employee_id)
    if balance:
        return {"status": "success", "balances": balance}
    return {
        "status": "error",
        "message": f"従業員ID '{employee_id}' の休暇データが存在しません。",
    }


def submit_leave_request(
    employee_id: str,
    start_date: str,
    end_date: str,
    leave_type: str,
    days: float,
    idempotency_key: str = "",
) -> Dict[str, Any]:
    """WorkWeek で休暇（有給または病気休暇）を申請します。

    Args:
        employee_id: 従業員ID
        start_date: 休暇開始日（YYYY-MM-DD）
        end_date: 休暇終了日（YYYY-MM-DD）
        leave_type: 休暇種別 ('vacation' または 'sick')
        days: 申請日数（例: 1.0, 2.0）
        idempotency_key: 冪等性キー（重複防止用UUID）

    Returns:
        申請ステータス、リクエストID、残日数
    """
    global _REQUEST_COUNTER

    # ガードレール: 休暇種別の検証
    norm_type = leave_type.lower()
    if norm_type not in ("vacation", "sick"):
        return {
            "status": "error",
            "message": f"無効な休暇種別です: '{leave_type}'. 'vacation' または 'sick' を指定してください。",
        }

    # ガードレール: 日程の時系列妥当性検証
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")
        if dt_start > dt_end:
            return {
                "status": "error",
                "message": f"開始日 ({start_date}) は終了日 ({end_date}) より前である必要があります。",
            }
    except ValueError:
        return {
            "status": "error",
            "message": "日付フォーマットは YYYY-MM-DD である必要があります。",
        }

    # ガードレール: 残高制限の検証
    balance = _MOCK_LEAVE_BALANCES.get(employee_id)
    if not balance:
        return {
            "status": "error",
            "message": f"従業員ID '{employee_id}' の休暇残高が確認できません。",
        }

    remaining = balance[norm_type]["remaining"]
    if days > remaining:
        return {
            "status": "error",
            "message": f"残日数不足エラー: 申請日数 ({days}日) が現在の残日数 ({remaining}日) を超過しています。",
        }

    # 外部 API 呼出試行
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/workweek/leave-requests"
            payload = {
                "employee_id": employee_id,
                "start_date": start_date,
                "end_date": end_date,
                "leave_type": norm_type,
                "days": days,
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
            logger.warning(f"外部 WorkWeek API 呼出失敗。ローカルモックにフォールバック: {e}")

    # ローカル処理
    _REQUEST_COUNTER += 1
    req_id = f"LR-{_REQUEST_COUNTER}"
    balance[norm_type]["used"] += days
    balance[norm_type]["remaining"] -= days

    _MOCK_LEAVE_REQUESTS[req_id] = {
        "request_id": req_id,
        "employee_id": employee_id,
        "start_date": start_date,
        "end_date": end_date,
        "leave_type": norm_type,
        "days": days,
        "status": "APPROVED",
        "created_at": datetime.now().isoformat(),
    }

    return {
        "status": "success",
        "message": f"{norm_type.capitalize()} 休暇申請が承認されました。",
        "request_id": req_id,
        "employee_id": employee_id,
        "days_deducted": days,
        "remaining_balance": balance[norm_type]["remaining"],
    }


def cancel_leave_request(employee_id: str, request_id: str) -> Dict[str, Any]:
    """【Saga補償トランザクション】提出済みの休暇申請を取り消し、残高をロールバックします。

    Args:
        employee_id: 従業員ID
        request_id: 取り消す休暇申請のリクエストID

    Returns:
        取り消しステータスおよび復元後の休暇残高
    """
    if not config.USE_LOCAL_MOCK_SAAS and config.MCP_TOKEN:
        try:
            url = f"{config.MOCK_SAAS_URL}/api/workweek/leave-requests/{request_id}/cancel"
            data = json.dumps({"employee_id": employee_id}).encode("utf-8")
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
            logger.warning(f"外部 WorkWeek API 呼出失敗。ローカルモックにフォールバック: {e}")

    req = _MOCK_LEAVE_REQUESTS.get(request_id)
    if not req or req.get("employee_id") != employee_id:
        return {
            "status": "error",
            "message": f"リクエストID '{request_id}' が見つからないか、権限がありません。",
        }

    if req.get("status") == "CANCELLED":
        return {"status": "success", "message": "既にキャンセルされています。"}

    norm_type = req["leave_type"]
    days = req["days"]
    balance = _MOCK_LEAVE_BALANCES[employee_id]
    balance[norm_type]["used"] -= days
    balance[norm_type]["remaining"] += days
    req["status"] = "CANCELLED"

    return {
        "status": "success",
        "message": f"休暇申請 '{request_id}' は正常に取り消され、{days} 日の残高が復元されました。",
        "remaining_balance": balance[norm_type]["remaining"],
    }
