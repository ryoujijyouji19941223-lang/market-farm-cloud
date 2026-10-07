from __future__ import annotations


def news_quality(*, error=None, capped=False, article_count=0):
    """Describe collection quality without treating an outage as neutral news."""
    if error:
        status = "ERROR"
    elif capped:
        status = "PARTIAL"
    else:
        status = "OK" if article_count else "EMPTY"
    return {
        "status": status,
        "error": error,
        "article_count": article_count,
        "usable": status in {"OK", "EMPTY"},
    }


def historical_news_status(asset, snapshot=None):
    snapshot = snapshot or {}
    if snapshot.get("news_status"):
        return snapshot["news_status"]
    if asset.get("news_error"):
        return "ERROR"
    if asset.get("archive_capped") or asset.get("capped_chunks"):
        return "PARTIAL"
    if "archive_articles" in asset:
        return "OK" if asset["archive_articles"] else "EMPTY"
    return "UNKNOWN"


def news_status_label(status):
    return {
        "OK": "取得済み",
        "EMPTY": "取得済み・該当記事なし",
        "ERROR": "取得失敗",
        "PARTIAL": "一部のみ取得",
        "UNKNOWN": "取得状況不明",
    }.get(status, "取得状況不明")
