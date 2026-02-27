"""
Twitter/X Poster — Upload PNG + post tweet
Uses OAuth 1.0a (User Context) with HMAC-SHA1
"""
import os
import sys
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
import uuid
import requests

# --- Credentials from environment ---
API_KEY = os.environ.get("X_API_KEY", "")
API_SECRET = os.environ.get("X_API_SECRET", "")
ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN", "")
ACCESS_SECRET = os.environ.get("X_ACCESS_SECRET", "")


def _percent_encode(s):
    return urllib.parse.quote(str(s), safe="")


def _oauth_signature(method, url, params, consumer_secret, token_secret):
    """Generate OAuth 1.0a HMAC-SHA1 signature."""
    sorted_params = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted(params.items())
    )
    base_string = "&".join([
        method.upper(),
        _percent_encode(url),
        _percent_encode(sorted_params),
    ])
    signing_key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    return signature


def _oauth_header(method, url, extra_params=None):
    """Build OAuth 1.0a Authorization header."""
    oauth_params = {
        "oauth_consumer_key": API_KEY,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": ACCESS_TOKEN,
        "oauth_version": "1.0",
    }
    all_params = {**oauth_params}
    if extra_params:
        all_params.update(extra_params)

    signature = _oauth_signature(method, url, all_params, API_SECRET, ACCESS_SECRET)
    oauth_params["oauth_signature"] = signature

    auth_str = ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {auth_str}"


def upload_media(image_path):
    """Upload image to Twitter using multipart form upload and return media_id."""
    url = "https://upload.twitter.com/1.1/media/upload.json"

    with open(image_path, "rb") as f:
        files = {"media": f}
        header = _oauth_header("POST", url)
        resp = requests.post(
            url,
            files=files,
            headers={"Authorization": header},
        )

    if resp.status_code not in (200, 201, 202):
        print(f"Media upload failed ({resp.status_code}): {resp.text}")
        return None

    media_id = resp.json().get("media_id_string")
    print(f"Media uploaded: {media_id}")
    return media_id


def post_tweet(text, media_id=None, reply_to_id=None):
    """Post a tweet, optionally with media and as a reply."""
    url = "https://api.x.com/2/tweets"

    payload = {"text": text}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    header = _oauth_header("POST", url)
    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": header,
            "Content-Type": "application/json",
        },
    )

    if resp.status_code not in (200, 201):
        print(f"Tweet failed ({resp.status_code}): {resp.text}")
        return None

    tweet_data = resp.json().get("data", {})
    tweet_id = tweet_data.get("id")
    print(f"Tweet posted: {tweet_id}")
    return tweet_id


def post_with_image(tweet_text, image_path, reply_text=None, reply_tweets=None):
    """
    Post a tweet with an image. Optionally post reply tweet(s).
    reply_text: single reply string (legacy)
    reply_tweets: list of reply strings (thread)
    Returns (main_tweet_id, [reply_ids]).
    """
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET]):
        print("ERROR: Twitter credentials not set. Skipping post.")
        return None, []

    # Upload image
    media_id = upload_media(image_path)
    if not media_id:
        return None, []

    # Post main tweet with image
    main_id = post_tweet(tweet_text, media_id=media_id)
    if not main_id:
        return None, []

    # Build list of replies
    replies = []
    if reply_tweets and isinstance(reply_tweets, list):
        replies = reply_tweets
    elif reply_text:
        replies = [reply_text]

    # Post reply thread
    reply_ids = []
    last_id = main_id
    for rt in replies:
        time.sleep(2)
        rid = post_tweet(rt, reply_to_id=last_id)
        if rid:
            reply_ids.append(rid)
            last_id = rid  # chain replies

    return main_id, reply_ids


# --- CLI interface ---
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python twitter_poster.py <json_path> <type>")
        print("Types: gauge, ranking, countries, headlines, anomaly")
        sys.exit(1)

    json_path = sys.argv[1]
    post_type = sys.argv[2]

    # Load the JSON output
    with open(json_path) as f:
        data = json.load(f)

    tweet_text = data.get("tweet_text", "")
    image_path = data.get("png_path", "")
    reply_text = data.get("reply_text", "")
    reply_tweets = data.get("reply_tweets", [])

    if not tweet_text or not image_path:
        print(f"No tweet_text or png_path in {json_path}. Skipping.")
        sys.exit(0)

    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}. Skipping.")
        sys.exit(1)

    print(f"Posting {post_type}...")
    print(f"  Text: {tweet_text[:100]}...")
    print(f"  Image: {image_path}")
    if reply_tweets:
        print(f"  Reply tweets: {len(reply_tweets)}")
    elif reply_text:
        print(f"  Reply: {reply_text[:100]}...")

    main_id, reply_ids = post_with_image(
        tweet_text, image_path,
        reply_text=reply_text or None,
        reply_tweets=reply_tweets or None,
    )

    if main_id:
        print(f"SUCCESS — Tweet ID: {main_id}")
        for i, rid in enumerate(reply_ids):
            print(f"Reply {i+1} ID: {rid}")
    else:
        print("FAILED to post tweet")
        sys.exit(1)
