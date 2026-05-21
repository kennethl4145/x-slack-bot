import requests
import time
import os
import re

# --- CONFIG ---
X_USERNAME = "underdogmlb"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
POLL_INTERVAL = 60  # seconds
LAST_POST_FILE = "last_post_id.txt"


def get_latest_tweet():
    """Fetch latest tweet via RapidAPI Twitter135."""
    url = "https://twitter135.p.rapidapi.com/v2/UserTweets/"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "twitter135.p.rapidapi.com"
    }
    params = {"username": X_USERNAME, "count": "1"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Navigate the response structure
        instructions = (
            data.get("data", {})
                .get("user", {})
                .get("result", {})
                .get("timeline_v2", {})
                .get("timeline", {})
                .get("instructions", [])
        )

        for instruction in instructions:
            entries = instruction.get("entries", [])
            for entry in entries:
                content = entry.get("content", {})
                item_content = content.get("itemContent", {})
                tweet_results = item_content.get("tweet_results", {}).get("result", {})

                if not tweet_results:
                    continue

                legacy = tweet_results.get("legacy", {})
                tweet_id = legacy.get("id_str", "")
                tweet_text = legacy.get("full_text", "")

                # Skip retweets
                if tweet_text.startswith("RT @"):
                    continue

                if tweet_id:
                    return {
                        "id": tweet_id,
                        "text": tweet_text,
                        "url": f"https://x.com/{X_USERNAME}/status/{tweet_id}",
                        "date": legacy.get("created_at", ""),
                    }
    except Exception as e:
        print(f"RapidAPI error: {e}")

    return None


def load_last_post_id():
    if os.path.exists(LAST_POST_FILE):
        with open(LAST_POST_FILE, "r") as f:
            return f.read().strip()
    return None


def save_last_post_id(post_id):
    with open(LAST_POST_FILE, "w") as f:
        f.write(post_id)


def send_to_slack(tweet):
    message = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*New post from <https://x.com/{X_USERNAME}|@{X_USERNAME}>*\n\n{tweet['text']}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{tweet['url']}|View on X> • {tweet['date']}"
                    }
                ]
            }
        ]
    }

    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        if resp.status_code == 200:
            print(f"✅ Sent to Slack: {tweet['text'][:80]}...")
        else:
            print(f"❌ Slack error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"❌ Slack send error: {e}")


def main():
    if not SLACK_WEBHOOK_URL:
        print("❌ SLACK_WEBHOOK_URL environment variable not set!")
        return
    if not RAPIDAPI_KEY:
        print("❌ RAPIDAPI_KEY environment variable not set!")
        return

    print(f"🚀 Monitoring @{X_USERNAME} every {POLL_INTERVAL} seconds...")
    last_id = load_last_post_id()
    print(f"Last known post ID: {last_id or 'None (first run)'}")

    while True:
        try:
            tweet = get_latest_tweet()

            if tweet is None:
                print("⚠️  Could not fetch tweet. Retrying next cycle...")
            elif tweet["id"] != last_id:
                if last_id is not None:
                    send_to_slack(tweet)
                else:
                    print(f"📌 First run — storing post ID: {tweet['id']}")

                save_last_post_id(tweet["id"])
                last_id = tweet["id"]
            else:
                print(f"No new posts. Last ID: {last_id}")

        except Exception as e:
            print(f"❌ Error in main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
