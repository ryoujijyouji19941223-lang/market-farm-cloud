from market_farm.news import sentiment


def filter_like_fetch(items, asset):
    required = [x.lower() for x in asset.get("news_required_any", [])]
    excluded = [x.lower() for x in asset.get("news_exclude_terms", [])]
    out = []
    for item in items:
        title = item.get("title", "").lower()
        if excluded and any(term in title for term in excluded):
            continue
        if required and not any(term in title for term in required):
            continue
        out.append(item)
    return out


def test_asterisk_anime_is_rejected_but_company_news_passes():
    asset = {
        "news_required_any": ["株式会社アスタリスク", "AsReader", "RFID", "AsCode", "6522"],
        "news_exclude_terms": ["学戦都市アスタリスク", "アニメ", "ABEMA"],
    }
    items = [
        {"title": "学戦都市アスタリスク (アニメ) 無料動画 - ABEMA", "link": "anime"},
        {"title": "株式会社アスタリスク、AsReader RFID新製品を発表", "link": "company"},
    ]
    filtered = filter_like_fetch(items, asset)
    assert [x["link"] for x in filtered] == ["company"]
