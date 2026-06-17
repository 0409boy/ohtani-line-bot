import os
import json
import requests
from datetime import datetime, timedelta, timezone

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

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
    "Shohei Ohtani": "大谷翔平",
    "Yoshinobu Yamamoto": "山本由伸",
    "Roki Sasaki": "佐々木朗希",
    "Tyler Glasnow": "タイラー・グラスノー",
    "Blake Snell": "ブレイク・スネル",
    "Dustin May": "ダスティン・メイ",
    "Clayton Kershaw": "クレイトン・カーショウ",
    "Tanner Scott": "タナー・スコット",
    "Blake Treinen": "ブレイク・トライネン",
    "Alex Vesia": "アレックス・ベシア",
    "Emmet Sheehan": "エメット・シーハン",
    "Eric Lauer": "エリック・ラウアー",
    "Justin Wrobleski": "ジャスティン・ロブレスキー",
    "Will Klein": "ウィル・クライン",
    "Kyle Hurt": "カイル・ハート",
    "Edgardo Henriquez": "エドガルド・エンリケス",
    "Jonathan Hernández": "ジョナサン・ヘルナンデス",
    "Paul Gervase": "ポール・ジャーベイス",
}


def valid(value):
    return value not in [None, "", "取得不可", ".---", "---"]


def jp_team(name):
    return TEAM_JP.get(name, name)


def jp_pitcher(name):
    return PITCHER_JP.get(name, name)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"game_results": [], "home_runs": []}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "game_results": data.get("game_results", data.get("ゲーム結果", [])),
        "home_runs": data.get("home_runs", data.get("ホームラン", [])),
    }


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

            return f"""次回試合
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

                    if valid(wins) and valid(losses):
                        return f"{wins}勝{losses}敗"

        return ""

    except Exception as e:
        print("Team record fetch error:", e)
        return ""


def get_ohtani_stats(boxscore):
    players = boxscore.get("teams", {}).get("away", {}).get("players", {})
    players.update(boxscore.get("teams", {}).get("home", {}).get("players", {}))

    player = players.get(f"ID{OHTANI_ID}")

    if not player:
        return {}, {}

    batting = player.get("seasonStats", {}).get("batting", {})
    pitching = player.get("seasonStats", {}).get("pitching", {})

    batting_stats = {
        "打率": batting.get("avg"),
        "本塁打": batting.get("homeRuns"),
    }

    pitching_stats = {
        "勝利": pitching.get("wins"),
        "敗戦": pitching.get("losses"),
        "防御率": pitching.get("era"),
        "投球回": pitching.get("inningsPitched"),
        "奪三振": pitching.get("strikeOuts"),
        "WHIP": pitching.get("whip"),
        "被打率": pitching.get("avg"),
    }

    return batting_stats, pitching_stats


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
        "Single": "ヒット",
        "Double": "ツーベース",
        "Triple": "スリーベース",
        "Strikeout": "空振り三振",
        "Groundout": "ゴロアウト",
        "Flyout": "フライアウト",
        "Lineout": "ライナーアウト",
        "Pop Out": "内野フライアウト",
        "Hit By Pitch": "死球",
        "Intent Walk": "申告敬遠",
        "Sac Fly": "犠牲フライ",
        "Sac Bunt": "送りバント",
        "Field Error": "エラーで出塁",
        "Forceout": "ランナーがアウト",
        "Double Play": "ダブルプレー",
        "Grounded Into DP": "ダブルプレー",
        "Fielders Choice": "相手がランナーをアウトにして出塁",
        "Catcher Interference": "守備妨害",
        "Reached on Error": "エラーで出塁",
        "Bunt Groundout": "バントアウト",
        "Bunt Pop Out": "バントフライアウト",
        "Field Out": "アウト",
        "Runner Out": "ランナーアウト",
        "Sacrifice Fly Double Play": "犠牲フライダブルプレー",
        "Strikeout Double Play": "三振ダブルプレー",
        "Pickoff": "けん制アウト",
        "Caught Stealing": "盗塁失敗",
        "Stolen Base": "盗塁成功"
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


def build_batting_text(batting_stats):
    lines = []

    if valid(batting_stats.get("打率")):
        lines.append(f"打率 {batting_stats['打率']}")

    if valid(batting_stats.get("本塁打")):
        lines.append(f"本塁打 第{batting_stats['本塁打']}号")

    if not lines:
        return ""

    return "大谷翔平 打撃成績\n" + "\n".join(lines)


def build_pitching_text(pitching_stats):
    lines = []

    wins = pitching_stats.get("勝利")
    losses = pitching_stats.get("敗戦")

    if valid(wins) and valid(losses):
        lines.append(f"{wins}勝{losses}敗")

    if valid(pitching_stats.get("防御率")):
        lines.append(f"防御率 {pitching_stats['防御率']}")

    if valid(pitching_stats.get("投球回")):
        lines.append(f"投球回 {pitching_stats['投球回']}回")

    if valid(pitching_stats.get("奪三振")):
        lines.append(f"奪三振 {pitching_stats['奪三振']}")

    if valid(pitching_stats.get("WHIP")):
        lines.append(f"WHIP {pitching_stats['WHIP']}")

    if valid(pitching_stats.get("被打率")):
        lines.append(f"被打率 {pitching_stats['被打率']}")

    if not lines:
        return ""

    return "大谷翔平 投手成績\n" + "\n".join(lines)


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
    date_text = f"{now.month}/{now.day}日({weekdays[now.weekday()]})"

    starter = get_dodgers_starting_pitcher(boxscore)

    batting_stats, pitching_stats = get_ohtani_stats(boxscore)

    at_bats, _ = get_ohtani_at_bats_and_homers(pbp)

    at_bat_lines = []

    if at_bats:
        for i, event in enumerate(at_bats, start=1):
            at_bat_lines.append(f"{i}打席目　【{event}】")
    else:
        at_bat_lines.append("出場なし、または打席情報なし")

    sections = []

    sections.append(f"""【試合結果】

{date_text}
ドジャース vs {opponent_name_jp}
{dodgers_score}-{opponent_score} {result_text}

先発ドジャースピッチャー
{starter}

大谷翔平 全打席
{chr(10).join(at_bat_lines)}""")

    batting_text = build_batting_text(batting_stats)
    if batting_text:
        sections.append(batting_text)

    pitching_text = build_pitching_text(pitching_stats)
    if pitching_text:
        sections.append(pitching_text)

    record = get_team_record()
    if record:
        sections.append(f"ドジャース成績\n{record}")

    next_game = get_next_game()
    if next_game:
        sections.append(next_game)

    return "\n\n".join(sections)


def check_home_run(game, state):
    game_pk = game["gamePk"]

    status = game.get("status", {}).get("abstractGameState")

    if status not in ["Live", "Final"]:
        print("Game is not live/final.")
        return

    pbp = get_play_by_play(game_pk)
    _, homers = get_ohtani_at_bats_and_homers(pbp)

    print("HOME RUN IDS:", homers)

    for homer_id in homers:
        unique_id = f"{game_pk}_{homer_id}"

        if unique_id in state["home_runs"]:
            print("Already notified HR:", unique_id)
            continue

        boxscore = get_boxscore(game_pk)
        batting_stats, _ = get_ohtani_stats(boxscore)
        hr_total = batting_stats.get("本塁打", "")

        text = f"""【速報】
大谷翔平 第{hr_total}号ホームラン‼"""

        send_line(text)
        state["home_runs"].append(unique_id)


def check_game_result(game, state):
    game_pk = game["gamePk"]
    status = game.get("status", {}).get("abstractGameState")

    if status != "Final":
        print("Game not final.")
        return

    if game_pk in state["game_results"]:
        print("Already notified game result.")
        return

    boxscore = get_boxscore(game_pk)
    pbp = get_play_by_play(game_pk)

    message = build_game_result_message(game, boxscore, pbp)

    send_line(message)

    state["game_results"].append(game_pk)


def main():
    state = load_state()

    game = get_dodgers_game()

    if not game:
        print("No Dodgers game today.")
        save_state(state)
        return

    check_home_run(game, state)
    check_game_result(game, state)

    save_state(state)


if __name__ == "__main__":
    main()
