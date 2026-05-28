import os
import json
import requests
from datetime import datetime, timedelta, timezone

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

TEAM_ID = 119  # Dodgers
OHTANI_ID = 660271
STATE_FILE = "notified_state.json"

JST = timezone(timedelta(hours=9))


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"game_results": [], "home_runs": []}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {
        "to": LINE_USER_ID,
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


def get_today_jst():
    return datetime.now(JST).strftime("%Y-%m-%d")


def mlb_get(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()
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



def get_boxscore(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    return mlb_get(url)


def get_play_by_play(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/playByPlay"
    return mlb_get(url)


def get_team_record():
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


def get_ohtani_batting_average(boxscore):

    players = boxscore.get("teams", {}).get("away", {}).get("players", {})
    players.update(boxscore.get("teams", {}).get("home", {}).get("players", {}))

    player = players.get(f"ID{OHTANI_ID}")

    if not player:
        return "取得不可"

    avg = (
        player.get("seasonStats", {})
        .get("batting", {})
        .get("avg", "取得不可")
    )

    return avg


def get_dodgers_starting_pitcher(boxscore):

    for side in ["home", "away"]:

        team = boxscore.get("teams", {}).get(side, {})

        if team.get("team", {}).get("id") == TEAM_ID:

            pitcher_id = team.get("pitchers", [None])[0]

            if pitcher_id:

                player = team.get("players", {}).get(f"ID{pitcher_id}", {})

                return player.get("person", {}).get(
                    "fullName",
                    "取得不可"
                )

    return "取得不可"


def convert_event(event):

    mapping = {
        "Home Run": "HR",
        "Walk": "四球",
        "Single": "右安打",
        "Double": "二塁打",
        "Triple": "三塁打",
        "Strikeout": "空振り三振",
        "Groundout": "ゴロ",
        "Flyout": "飛",
        "Lineout": "直",
        "Pop Out": "邪飛",
        "Hit By Pitch": "死球",
        "Intent Walk": "申告敬遠",
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

            unique_id = play.get(
                "playEvents",
                [{}]
            )[-1].get(
                "playId",
                str(play.get("about", {}).get("atBatIndex"))
            )

            homers.append(unique_id)

    return at_bats, homers


def build_game_result_message(game, boxscore, pbp):

    teams = game["teams"]

    home = teams["home"]
    away = teams["away"]

    home_name = home["team"]["name"]
    away_name = away["team"]["name"]

    home_score = home.get("score", 0)
    away_score = away.get("score", 0)

    dodgers_home = home["team"]["id"] == TEAM_ID

    dodgers_score = home_score if dodgers_home else away_score
    opponent_score = away_score if dodgers_home else home_score

    opponent_name = away_name if dodgers_home else home_name

    result_text = (
        "ドジャース勝利"
        if dodgers_score > opponent_score
        else "ドジャース敗北"
    )

    now = datetime.now(JST)

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]

    date_text = (
        f"{now.month}/{now.day}日"
        f"({weekdays[now.weekday()]})"
    )

    starter = get_dodgers_starting_pitcher(boxscore)

    avg = get_ohtani_batting_average(boxscore)

    record = get_team_record()

    at_bats, _ = get_ohtani_at_bats_and_homers(pbp)

    at_bat_lines = []

    if at_bats:

        for i, event in enumerate(at_bats, start=1):

            at_bat_lines.append(
                f"{i}打席目　【{event}】"
            )

    else:

        at_bat_lines.append(
            "出場なし、または打席情報なし"
        )

    message = f"""【試合結果】

{date_text}
ドジャース vs {opponent_name}
{dodgers_score}-{opponent_score} {result_text}

先発ドジャースピッチャー
{starter}

大谷翔平 全打席
{chr(10).join(at_bat_lines)}

大谷翔平 打率
{avg}

ドジャース成績
{record}"""

    return message


def check_home_run(game, state):

    game_pk = game["gamePk"]

    status = game.get("status", {}).get("abstractGameState")

    if status not in ["Live", "Final"]:

        print("Game is not live/final.")
        return

    pbp = get_play_by_play(game_pk)

    _, homers = get_ohtani_at_bats_and_homers(pbp)

    for homer_id in homers:

        unique_id = f"{game_pk}_{homer_id}"

        if unique_id in state["home_runs"]:

            print("Already notified HR:", unique_id)
            continue

        text = """【速報】
大谷翔平 ホームラン‼"""

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

    message = build_game_result_message(
        game,
        boxscore,
        pbp
    )

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
