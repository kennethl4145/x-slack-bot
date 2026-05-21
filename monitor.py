import requests
import time
import os

# --- CONFIG ---
X_USERNAME = "underdogmlb"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
POLL_INTERVAL = 60  # seconds
LAST_POST_FILE = "last_post_id.txt"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "twitter-aio.p.rapidapi.com",
    "Content-Type": "application/json",
}


def get_user_id():
    """Convert @underdogmlb username to userId."""
    url = f"https://twitter-aio.p.rapidapi.com/user/details/username/{X_USERNAME}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        user_id = data.get("data", {}).get("user", {}).get("result", {}).get("rest_id")
        if user_id:
            print(f"✅ Resolved @{X_USERNAME} to userId: {user_id}")
            return user_id
    except Exception as e:
        print(f"❌ Error resolving userId: {e}")
    return None


def get_latest_tweet(user_id):
    """Fetch the latest tweet for a given userId."""
    url = f"https://twitter-aio.p.rapidapi.com/user/{user_id}/tweets"
    params = {"count": "5"}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        entries = (
            data.get("data", {})
                .get("user", {})
                .get("result", {})
                .get("timeline_v2", {})
                .get("timeline", {})
                .get("instructions", [])
        )

        for instruction in entries:
            for entry in instruction.get("entries", []):
                tweet_result = (
                    entry.get("content", {})
                         .get("itemContent", {})
                         .get("tweet_results", {})
                         .get("result", {})
                )
                if not tweet_result:
                    continue

                legacy = tweet_result.get("legacy", {})
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
        print(f"❌ Error fetching tweets: {e}")

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

    # Resolve userId once at startup
    user_id = get_user_id()
    if not user_id:
        print("❌ Could not resolve userId. Check your API key and username.")
        return

    last_id = load_last_post_id()
    print(f"Last known post ID: {last_id or 'None (first run)'}")

    while True:
        try:
            tweet = get_latest_tweet(user_id)

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
