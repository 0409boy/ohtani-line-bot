import os
import json
import requests
from datetime import datetime, timedelta, timezone

# =====================
# 設定
# =====================
JST = timezone(timedelta(hours=9))
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
DODGERS_TEAM_ID = 119
OHTANI_PLAYER_ID = 660271
NOTIFIED_FILE = "notified_games.json"

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")


# =====================
# 共通処理
# =====================
def get_json(url, params=None):
    res = requests.get(url, params=params, timeout=20)
    res.raise_for_status()
    return res.json()


def load_notified_games():
    if not os.path.exists(NOTIFIED_FILE):
        return {}
    try:
        with open(NOTIFIED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_notified_games(data):
    with open(NOTIFIED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_line_message(text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN または LINE_USER_ID が未設定です")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }

    res = requests.post(url, headers=headers, json=payload, timeout=20)
    if res.status_code >= 400:
        raise RuntimeError(f"LINE送信失敗: {res.status_code} {res.text}")


# =====================
# MLBデータ取得
# =====================
def get_today_dodgers_game():
    today_jst = datetime.now(JST).date()

    # アメリカ現地日付と日本日付がズレるので、前日〜翌日まで見る
    start_date = today_jst - timedelta(days=1)
    end_date = today_jst + timedelta(days=1)

    data = get_json(
        f"{MLB_API_BASE}/schedule",
        params={
            "sportId": 1,
            "teamId": DODGERS_TEAM_ID,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "hydrate": "probablePitcher,linescore",
        },
    )

    games = []
    for date_block in data.get("dates", []):
        games.extend(date_block.get("games", []))

    if not games:
        return None

    # 日本時間で今日9〜16時にチェックする想定なので、直近のドジャース戦を優先
    games.sort(key=lambda g: g.get("gameDate", ""), reverse=True)
    return games[0]


def get_boxscore(game_pk):
    return get_json(f"{MLB_API_BASE}/game/{game_pk}/boxscore")


def get_play_by_play(game_pk):
    return get_json(f"{MLB_API_BASE}/game/{game_pk}/playByPlay")


def get_ohtani_batting_average(boxscore):
    player_key = f"ID{OHTANI_PLAYER_ID}"
    for side in ["home", "away"]:
        players = boxscore.get("teams", {}).get(side, {}).get("players", {})
        player = players.get(player_key)
        if player:
            stats = player.get("seasonStats", {}).get("batting", {})
            avg = stats.get("avg")
            return avg if avg else "不明"
    return "不明"


def get_dodgers_starter(game, boxscore):
    teams = game.get("teams", {})
    dodgers_side = "home" if teams.get("home", {}).get("team", {}).get("id") == DODGERS_TEAM_ID else "away"

    probable = teams.get(dodgers_side, {}).get("probablePitcher", {}).get("fullName")
    if probable:
        return probable

    # probablePitcherが無い場合、boxscoreのpitchers先頭を先発として扱う
    team_box = boxscore.get("teams", {}).get(dodgers_side, {})
    pitcher_ids = team_box.get("pitchers", [])
    players = team_box.get("players", {})
    if pitcher_ids:
        first_pitcher = players.get(f"ID{pitcher_ids[0]}", {})
        return first_pitcher.get("person", {}).get("fullName", "不明")

    return "不明"


def get_ohtani_plate_appearances(play_by_play):
    results = []

    for play in play_by_play.get("allPlays", []):
        matchup = play.get("matchup", {})
        batter = matchup.get("batter", {})
        if batter.get("id") != OHTANI_PLAYER_ID:
            continue

        about = play.get("about", {})
        result = play.get("result", {})

        inning = about.get("inning")
        half = "表" if about.get("halfInning") == "top" else "裏"
        event = result.get("event") or result.get("description") or "不明"

        rbi = result.get("rbi")
        if rbi and rbi > 0:
            event += f"（{rbi}打点）"

        results.append(f"{len(results)+1}打席目：{inning}回{half} {event}")

    return results


def build_message(game, boxscore, play_by_play):
    teams = game.get("teams", {})
    home = teams.get("home", {})
    away = teams.get("away", {})

    home_name = home.get("team", {}).get("name", "ホーム")
    away_name = away.get("team", {}).get("name", "ビジター")
    home_score = home.get("score", 0)
    away_score = away.get("score", 0)

    dodgers_side = "home" if home.get("team", {}).get("id") == DODGERS_TEAM_ID else "away"
    dodgers_score = home_score if dodgers_side == "home" else away_score
    opponent_score = away_score if dodgers_side == "home" else home_score
    opponent_name = away_name if dodgers_side == "home" else home_name

    result_text = "勝利" if dodgers_score > opponent_score else "敗北" if dodgers_score < opponent_score else "引き分け"

    starter = get_dodgers_starter(game, boxscore)
    avg = get_ohtani_batting_average(boxscore)
    pa_results = get_ohtani_plate_appearances(play_by_play)

    if not pa_results:
        pa_text = "出場なし、または打席情報を取得できませんでした"
    else:
        pa_text = "\n".join(pa_results)

    game_date_jst = datetime.fromisoformat(game["gameDate"].replace("Z", "+00:00")).astimezone(JST)

    return f"""【ドジャース試合結果】
{game_date_jst.strftime('%Y/%m/%d')} 日本時間

ドジャース vs {opponent_name}

試合結果：
ドジャース {dodgers_score} - {opponent_score} {opponent_name}
ドジャース {result_text}

ドジャース先発：
{starter}

大谷翔平 全打席：
{pa_text}

試合終了時の大谷翔平 打率：
{avg}"""


# =====================
# メイン処理
# =====================
def main():
    game = get_today_dodgers_game()

    if not game:
        print("ドジャースの試合は見つかりませんでした")
        return

    game_pk = str(game.get("gamePk"))
    status = game.get("status", {}).get("detailedState", "")

    print(f"gamePk={game_pk}, status={status}")

    # 試合終了以外は通知しない
    if status not in ["Final", "Game Over", "Completed Early"]:
        print("まだ試合終了ではないため通知しません")
        return

    notified = load_notified_games()
    if notified.get(game_pk):
        print("この試合はすでに通知済みです")
        return

    boxscore = get_boxscore(game_pk)
    play_by_play = get_play_by_play(game_pk)
    message = build_message(game, boxscore, play_by_play)

    print(message)
    send_line_message(message)

    notified[game_pk] = {
        "notified_at_jst": datetime.now(JST).isoformat(),
        "status": status,
    }
    save_notified_games(notified)
    print("LINE通知完了")


if __name__ == "__main__":
    main()
