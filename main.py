import os
import json
import requests
from datetime import datetime, timedelta, timezone

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

TEAM_ID = 119
OHTANI_ID = 660271
STATE_FILE = "notified_state.json"

JST = timezone(timedelta(hours=9))

TEAM_JP = {
    "Arizona Diamondbacks": "アリゾナ・ダイヤモンドバックス",
    "Atlanta Braves": "アトランタ・ブレーブス",
    "Baltimore Orioles": "ボルチモア・オリオールズ",
    "Boston Red Sox": "ボストン・レッドソックス",
    "Chicago Cubs": "シカゴ・カブス",
    "Chicago White Sox": "シカゴ・ホワイトソックス",
    "Cincinnati Reds": "シンシナティ・レッズ",
    "Cleveland Guardians": "クリーブランド・ガーディアンズ",
    "Colorado Rockies": "コロラド・ロッキーズ",
    "Detroit Tigers": "デトロイト・タイガース",
    "Houston Astros": "ヒューストン・アストロズ",
    "Kansas City Royals": "カンザスシティ・ロイヤルズ",
    "Los Angeles Angels": "ロサンゼルス・エンゼルス",
    "Los Angeles Dodgers": "ロサンゼルス・ドジャース",
    "Miami Marlins": "マイアミ・マーリンズ",
    "Milwaukee Brewers": "ミルウォーキー・ブルワーズ",
    "Minnesota Twins": "ミネソタ・ツインズ",
    "New York Mets": "ニューヨーク・メッツ",
    "New York Yankees": "ニューヨーク・ヤンキース",
    "Athletics": "アスレチックス",
    "Philadelphia Phillies": "フィラデルフィア・フィリーズ",
    "Pittsburgh Pirates": "ピッツバーグ・パイレーツ",
    "San Diego Padres": "サンディエゴ・パドレス",
    "San Francisco Giants": "サンフランシスコ・ジャイアンツ",
    "Seattle Mariners": "シアトル・マリナーズ",
    "St. Louis Cardinals": "セントルイス・カージナルス",
    "Tampa Bay Rays": "タンパベイ・レイズ",
    "Texas Rangers": "テキサス・レンジャーズ",
    "Toronto Blue Jays": "トロント・ブルージェイズ",
    "Washington Nationals": "ワシントン・ナショナルズ",
}

PITCHER_JP = {
    "Paul Gervase": "ポール・ジャーベイス",
    "Edgardo Henriquez": "エドガルド・エンリケス",
    "Jonathan Hernández": "ジョナサン・ヘルナンデス",
    "Kyle Hurt": "カイル・ハート",
    "Will Klein": "ウィル・クライン",
    "Eric Lauer": "エリック・ラウアー",
    "Roki Sasaki": "佐々木朗希",
    "Tanner Scott": "タナー・スコット",
    "Emmet Sheehan": "エメット・シーハン",
    "Blake Treinen": "ブレイク・トライネン",
    "Alex Vesia": "アレックス・ベシア",
    "Justin Wrobleski": "ジャスティン・ロブレスキー",
    "Yoshinobu Yamamoto": "山本由伸",
    "Shohei Ohtani": "大谷翔平",
    "Tyler Glasnow": "タイラー・グラスノー",
    "Blake Snell": "ブレイク・スネル",
    "Dustin May": "ダスティン・メイ",
    "Clayton Kershaw": "クレイトン・カーショウ",
}


def jp_team(name):
    return TEAM_JP.get(name, name)


def jp_pitcher(name):
    return PITCHER_JP.get(name, name)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"game_results": [], "home_runs": []}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_line(text):
    url = "https://api.line.me/v2/bot/message/broadcast"

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {
        "messages": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    response = requests.post(url, headers=headers, json=data)

    print("LINE status:", response.status_code)
    print("LINE response:", response.text)


def mlb_get(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def get_today_jst():
    return datetime.now(JST).strftime("%Y-%m-%d")


def get_dodgers_game():
    now_jst = datetime.now(JST)

    dates_to_check = [
        (now_jst - timedelta(days=1)).strftime("%Y-%m-%d"),
        now_jst.strftime("%Y-%m-%d")
    ]

    for target_date in dates_to_check:
        url = (
            f"https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&teamId={TEAM_ID}&date={target_date}"
            f"&hydrate=team,linescore"
        )

        data = mlb_get(url)
        dates = data.get("dates", [])

        if not dates:
            continue

        games = dates[0].get("games", [])

        if not games:
            continue

        return games[0]

    return None


def get_next_game():
    today = get_today_jst()

    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={TEAM_ID}"
        f"&startDate={today}&endDate=2100-01-01"
    )

    data = mlb_get(url)
    dates = data.get("dates", [])

    for date_block in dates:
        for game in date_block.get("games", []):
            status = game.get("status", {}).get("abstractGameState")

            if status == "Final":
                continue

            game_date = game.get("gameDate")

            dt_utc = datetime.strptime(
                game_date,
                "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)

            dt_jst = dt_utc.astimezone(JST)
            weekdays = ["月", "火", "水", "木", "金", "土", "日"]

            date_text = (
                f"{dt_jst.month}/{dt_jst.day}"
                f"({weekdays[dt_jst.weekday()]}) "
                f"{dt_jst.strftime('%H:%M')}〜"
            )

            teams = game["teams"]
            home = teams["home"]["team"]["name"]
            away = teams["away"]["team"]["name"]

            opponent = away if home == "Los Angeles Dodgers" else home

            return f"""\n次回試合
{date_text}
ドジャース vs {jp_team(opponent)}"""

    return ""


def get_boxscore(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    return mlb_get(url)


def get_play_by_play(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/playByPlay"
    return mlb_get(url)


def get_team_record():
    try:
        today = get_today_jst()

        url = (
            f"https://statsapi.mlb.com/api/v1/standings"
            f"?leagueId=104&date={today}&hydrate=team"
        )

        data = mlb_get(url)

        for record_group in data.get("records", []):
            for team_record in record_group.get("teamRecords", []):
                if team_record.get("team", {}).get("id") == TEAM_ID:
                    wins = team_record.get("wins")
                    losses = team_record.get("losses")
                    return f"{wins}勝{losses}敗"

        return "取得不可"

    except Exception as e:
        print("Team record fetch error:", e)
        return "取得不可"


def get_ohtani_batting_stats(boxscore):
    players = boxscore.get("teams", {}).get("away", {}).get("players", {})
    players.update(boxscore.get("teams", {}).get("home", {}).get("players", {}))

    player = players.get(f"ID{OHTANI_ID}")

    if not player:
        return {
            "avg": "取得不可",
            "home_runs": "取得不可"
        }

    batting = player.get("seasonStats", {}).get("batting", {})

    return {
        "avg": batting.get("avg", "取得不可"),
        "home_runs": batting.get("homeRuns", "取得不可")
    }


def get_ohtani_pitching_stats(boxscore):
    players = boxscore.get("teams", {}).get("away", {}).get("players", {})
    players.update(boxscore.get("teams", {}).get("home", {}).get("players", {}))

    player = players.get(f"ID{OHTANI_ID}")

    if not player:
        return {
            "wins": "取得不可",
            "losses": "取得不可",
            "era": "取得不可",
            "innings": "取得不可",
            "strikeouts": "取得不可",
            "whip": "取得不可",
            "avg": "取得不可"
        }

    pitching = player.get("seasonStats", {}).get("pitching", {})

    return {
        "wins": pitching.get("wins", "取得不可"),
        "losses": pitching.get("losses", "取得不可"),
        "era": pitching.get("era", "取得不可"),
        "innings": pitching.get("inningsPitched", "取得不可"),
        "strikeouts": pitching.get("strikeOuts", "取得不可"),
        "whip": pitching.get("whip", "取得不可"),
        "avg": pitching.get("avg", "取得不可")
    }


def get_dodgers_starting_pitcher(boxscore):
    for side in ["home", "away"]:
        team = boxscore.get("teams", {}).get(side, {})

        if team.get("team", {}).get("id") == TEAM_ID:
            pitcher_id = team.get("pitchers", [None])[0]

            if pitcher_id:
                player = team.get("players", {}).get(f"ID{pitcher_id}", {})
                name = player.get("person", {}).get("fullName", "取得不可")
                return jp_pitcher(name)

    return "取得不可"


def convert_event(event):
    mapping = {
        "Home Run": "HR",
        "Walk": "四球",
        "Single": "安打",
        "Double": "二塁打",
        "Triple": "三塁打",
        "Strikeout": "空振り三振",
        "Groundout": "ゴロ",
        "Flyout": "飛",
        "Lineout": "直",
        "Pop Out": "邪飛",
        "Hit By Pitch": "死球",
        "Intent Walk": "申告敬遠",
        "Sac Fly": "犠飛",
        "Sac Bunt": "犠打",
        "Field Error": "失策出塁",
        "Forceout": "フォースアウト",
        "Double Play": "併殺打",
    }

    return mapping.get(event, event)


def get_ohtani_at_bats_and_homers(pbp):
    at_bats = []
    homers = []

    for play in pbp.get("allPlays", []):
        matchup = play.get("matchup", {})
        batter = matchup.get("batter", {})

        if batter.get("id") != OHTANI_ID:
            continue

        result = play.get("result", {})
        event = result.get("event", "不明")

        at_bats.append(convert_event(event))

        if "Home Run" in event:
            unique_id = play.get("playEvents", [{}])[-1].get(
                "playId",
                str(play.get("about", {}).get("atBatIndex"))
            )

            homers.append(unique_id)

    return at_bats, homers


def build_game_result_message(game, boxscore, pbp):
    teams = game["teams"]

    home = teams["home"]
    away = teams["away"]

    home_score = home.get("score", 0)
    away_score = away.get("score", 0)

    dodgers_home = home["team"]["id"] == TEAM_ID

    dodgers_score = home_score if dodgers_home else away_score
    opponent_score = away_score if dodgers_home else home_score

    opponent_name = away["team"]["name"] if dodgers_home else home["team"]["name"]
    opponent_name_jp = jp_team(opponent_name)

    result_text = (
        "ドジャース勝利"
        if dodgers_score > opponent_score
        else "ドジャース敗北"
    )

    now = datetime.now(JST)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    date_text = f"{now.month}/{now.day}日({weekdays[now.weekday()]}
