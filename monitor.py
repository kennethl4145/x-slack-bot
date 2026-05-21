import requests
import time
import json
import os
import re

# --- CONFIG ---
X_USERNAME = "underdogmlb"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/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")
POLL_INTERVAL = 60  # seconds
LAST_POST_FILE = "last_post_id.txt"

# --- HEADERS to mimic a browser ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_latest_tweet():
    """Fetch the latest tweet from the public Nitter instance."""
    # Try multiple public nitter instances as fallbacks
    nitter_instances = [
        "https://nitter.privacydev.net",
        "https://nitter.poast.org",
        "https://nitter.1d4.us",
    ]

    for instance in nitter_instances:
        try:
            url = f"{instance}/{X_USERNAME}/rss"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                return parse_rss(resp.text)
        except Exception:
            continue

    # Fallback: scrape x.com directly
    return scrape_x_directly()


def parse_rss(rss_text):
    """Parse RSS feed to extract latest tweet."""
    try:
        # Extract first item from RSS
        item_match = re.search(r'<item>(.*?)</item>', rss_text, re.DOTALL)
        if not item_match:
            return None

        item = item_match.group(1)

        # Extract fields
        title = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item, re.DOTALL)
        link = re.search(r'<link>(.*?)</link>', item)
        pub_date = re.search(r'<pubDate>(.*?)</pubDate>', item)
        description = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item, re.DOTALL)

        if not link:
            return None

        tweet_url = link.group(1).strip()
        tweet_id = tweet_url.split("/")[-1]

        # Clean up description (strip HTML tags)
        desc_text = ""
        if description:
            desc_text = re.sub(r'<[^>]+>', '', description.group(1)).strip()

        tweet_text = desc_text if desc_text else (title.group(1).strip() if title else "")

        return {
            "id": tweet_id,
            "text": tweet_text,
            "url": tweet_url.replace("nitter.privacydev.net", "x.com")
                            .replace("nitter.poast.org", "x.com")
                            .replace("nitter.1d4.us", "x.com"),
            "date": pub_date.group(1).strip() if pub_date else "",
        }
    except Exception as e:
        print(f"RSS parse error: {e}")
        return None


def scrape_x_directly():
    """Fallback: attempt to get tweet from syndication API."""
    try:
        url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{X_USERNAME}?count=1"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        tweets = data.get("timeline", {}).get("entries", [])
        if not tweets:
            return None

        tweet = tweets[0].get("content", {}).get("tweet", {})
        tweet_id = tweet.get("id_str", "")
        tweet_text = tweet.get("full_text", tweet.get("text", ""))

        return {
            "id": tweet_id,
            "text": tweet_text,
            "url": f"https://x.com/{X_USERNAME}/status/{tweet_id}",
            "date": "",
        }
    except Exception as e:
        print(f"Fallback scrape error: {e}")
        return None


def load_last_post_id():
    """Load the last seen tweet ID from file."""
    if os.path.exists(LAST_POST_FILE):
        with open(LAST_POST_FILE, "r") as f:
            return f.read().strip()
    return None


def save_last_post_id(post_id):
    """Save the latest tweet ID to file."""
    with open(LAST_POST_FILE, "w") as f:
        f.write(post_id)


def send_to_slack(tweet):
    """Send tweet to Slack channel via webhook."""
    message = {
        "text": f"*New post from @{X_USERNAME}*",
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
                        "text": f"<{tweet['url']}|View on X>"
                        + (f" • {tweet['date']}" if tweet['date'] else "")
                    }
                ]
            }
        ]
    }

    resp = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
    if resp.status_code == 200:
        print(f"✅ Sent to Slack: {tweet['text'][:80]}...")
    else:
        print(f"❌ Slack error {resp.status_code}: {resp.text}")


def main():
    print(f"🚀 Monitoring @{X_USERNAME} every {POLL_INTERVAL} seconds...")
    last_id = load_last_post_id()
    print(f"Last known post ID: {last_id or 'None (first run)'}")

    while True:
        try:
            tweet = get_latest_tweet()

            if tweet is None:
                print("⚠️  Could not fetch tweet. Retrying next cycle...")
            elif tweet["id"] != last_id:
                if last_id is not None:  # Don't alert on very first run
                    send_to_slack(tweet)
                else:
                    print(f"📌 First run — storing post ID: {tweet['id']}")

                save_last_post_id(tweet["id"])
                last_id = tweet["id"]
            else:
                print(f"No new posts. Last ID: {last_id}")

        except Exception as e:
            print(f"❌ Error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
