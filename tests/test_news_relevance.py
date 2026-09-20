from market_farm.news import is_relevant_item


def check(asset, title, source="", source_url=""):
    ok, reason = is_relevant_item(
        asset,
        {"title": title, "source": source, "source_url": source_url},
    )
    return ok, reason


def test_asterisk_rejects_anime_and_generic_rfid_but_accepts_company_identity():
    asset = {
        "news_required_any": ["株式会社アスタリスク", "AsReader", "AsCode", "6522"],
        "news_trusted_sources": ["asx.co.jp", "asreader.jp"],
        "news_exclude_terms": ["学戦都市アスタリスク", "アニメ", "ABEMA"],
    }
    assert check(asset, "学戦都市アスタリスク (アニメ) 無料動画 - ABEMA")[0] is False
    assert check(asset, "データセンター用RFIDの世界市場が拡大")[0] is False
    assert check(asset, "株式会社アスタリスク、AsReader新製品を発表")[0] is True
    assert check(asset, "RFIDの課題について", source_url="https://asreader.jp/news/x")[0] is True


def test_otec_requires_ticker_specific_identity_or_official_source():
    asset = {
        "news_required_any": ["1736", "オーテック---", "オーテック[1736]", "オーテック（1736）"],
        "news_trusted_sources": ["o-tec.co.jp"],
        "news_exclude_terms": ["自動車部品のオーテック", "e-autec"],
    }
    assert check(asset, "自動車部品のオーテック DX戦略を発表")[0] is False
    assert check(asset, "オーテック(1736) 27年3月期1Qは減益")[0] is True
    assert check(asset, "北海道支店のZEB化を推進", source_url="https://www.o-tec.co.jp/news")[0] is True


def test_generic_sector_articles_do_not_become_company_news():
    smfg = {
        "news_required_any": ["三井住友フィナンシャルグループ", "SMFG", "SMBCグループ", "8316"],
        "news_trusted_sources": ["smfg.co.jp"],
    }
    kioxia = {
        "news_required_any": ["キオクシア", "Kioxia", "285A"],
        "news_trusted_sources": ["kioxia-holdings.com"],
    }
    klab = {
        "news_required_any": ["KLab", "KLab株式会社", "3656", "KLab HOMMA"],
        "news_trusted_sources": ["klab.com"],
    }
    nippon = {
        "news_required_any": ["日本製鉄", "Nippon Steel", "U.S. Steel", "US Steel", "5401"],
        "news_trusted_sources": ["nipponsteel.com"],
    }

    assert check(smfg, "日銀が追加利上げを決定")[0] is False
    assert check(kioxia, "NAND価格が世界的に上昇")[0] is False
    assert check(klab, "今週発売の注目新作ゲーム10選")[0] is False
    assert check(nippon, "世界の鉄鋼需要見通しを発表")[0] is False

    assert check(smfg, "SMFG、個人投資家向け説明会を開催")[0] is True
    assert check(kioxia, "キオクシア、北上工場に新製造棟")[0] is True
    assert check(klab, "KLab HOMMA Middle East UAEにオフィス開設")[0] is True
    assert check(nippon, "日本製鉄、欧州拠点に9億ユーロ投資")[0] is True


def test_distinctive_company_names_pass():
    nintendo = {
        "news_required_any": ["任天堂", "Nintendo", "7974", "Nintendo Switch 2"],
        "news_trusted_sources": ["nintendo.co.jp"],
    }
    sanrio = {
        "news_required_any": ["サンリオ", "Sanrio", "8136"],
        "news_trusted_sources": ["corporate.sanrio.co.jp"],
    }
    assert check(nintendo, "任天堂、Nintendo Switch 2特別モデルを発売")[0] is True
    assert check(sanrio, "サンリオ、グローバルYouTubeチャンネル開設")[0] is True
