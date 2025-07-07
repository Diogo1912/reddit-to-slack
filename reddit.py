import praw
import requests
import logging
import os
from datetime import datetime
from tqdm import tqdm
import openai

# -------------------------------
# Configuration
# -------------------------------

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

SUBREDDITS = [
    "Netherlands", "Belgium", "France", "Sweden", "Denmark", "Europe",
    "germany", "Amsterdam", "thehague", "Rotterdam", "Utrecht", "Brussels",
    "Paris", "London", "Antwerpen", "luxembourg", "milano", "rome",
    "ZeroWaste", "ThriftStoreHauls", "BuyItForLife", "Frugal", "Minimalism",
    "SustainableLiving", "SecondHand", "InteriorDesign", "interiordecorating",
    "DesignMyRoom", "MaleLivingSpace", "FemaleLivingSpace", "HomeDecorating",
    "CozyPlaces", "RoomPorn", "amateurroomporn", "HomeImprovement", "DIY",
    "ApartmentHacks", "ScandinavianInterior", "furniture", "Mid_Century", "WhatIsThisThing"
]

KEYWORDS = [
    "secondhand", "second-hand", "thrift", "thrifted", "vintage", "used", "pre-owned",
    "preloved", "pre-loved", "reclaimed", "upcycled", "repurposed", "handmade", "antique",
    "restored", "retro", "sustainable", "eco-friendly", "eco friendly", "zero waste",
    "minimalist", "minimalism", "buy it for life", "durable", "timeless", "reuse", "resale",
    "interior", "interior design", "home decor", "furniture", "sofa", "table", "chair",
    "cabinet", "dresser", "sideboard", "dining set", "lamp", "rug", "mirror", "art", "poster",
    "wall decor", "shelving", "bookshelf", "tv stand", "bed", "bed frame", "nightstand",
    "storage", "cozy", "scandinavian", "mid-century", "boho", "eclectic", "apartment",
    "renovation", "remodel", "decorating"
]

POST_LIMIT = 20
MAX_POSTS_PER_DAY = 10


# -------------------------------
# Logging
# -------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# -------------------------------
# Reddit Setup
# -------------------------------

def create_reddit_instance():
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )

# -------------------------------
# Fetch & Filter by Keyword
# -------------------------------

def fetch_matching_posts(reddit, subreddit_name, keywords):
    matches = []
    try:
        subreddit = reddit.subreddit(subreddit_name)
        for post in subreddit.hot(limit=POST_LIMIT):
            text = f"{post.title} {post.selftext}".lower()
            if any(keyword in text for keyword in keywords):
                matches.append({
                    'title': post.title,
                    'subreddit': subreddit_name,
                    'url': post.url,
                    'permalink': f"https://reddit.com{post.permalink}",
                    'text': text
                })
    except Exception as e:
        logging.error(f"Error fetching from r/{subreddit_name}: {e}")
    return matches

# -------------------------------
# AI Filtering
# -------------------------------

def score_post_with_ai(post):
    prompt = (
        f"You are a social media manager for Whoppah, a secondhand design marketplace. "
        f"Rate this Reddit post's relevance to Whoppah on a scale from 1 (not relevant) to 10 (highly relevant). "
        f"Only respond with a number.\n\n"
        f"Title: {post['title']}\n"
        f"Body: {post['text']}"
    )
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5
        )
        score_text = response.choices[0].message.content.strip()
        score = int(''.join(filter(str.isdigit, score_text)))
        return score
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        return 0

def filter_with_ai(posts, max_results=MAX_POSTS_PER_DAY):
    scored = []
    for post in tqdm(posts, desc="Filtering posts with AI"):
        score = score_post_with_ai(post)
        if score > 0:
            scored.append((score, post))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in scored[:max_results]]

# -------------------------------
# Slack Integration
# -------------------------------

def send_to_slack(posts):
    for post in posts:
        message = (
            f"*{post['title']}*\n"
            f"Subreddit: r/{post['subreddit']}\n"
            f"<{post['permalink']}|View on Reddit>"
        )
        try:
            res = requests.post(SLACK_WEBHOOK_URL, json={"text": message})
            if res.status_code != 200:
                logging.error(f"Slack error: {res.status_code} - {res.text}")
        except Exception as e:
            logging.error(f"Slack send failed: {e}")

# -------------------------------
# Main Logic
# -------------------------------

def main():
    logging.info("Starting Reddit to Slack job")
    reddit = create_reddit_instance()
    all_matches = []

    for sub in SUBREDDITS:
        logging.info(f"Scanning r/{sub}")
        matches = fetch_matching_posts(reddit, sub, KEYWORDS)
        all_matches.extend(matches)

    if not all_matches:
        logging.info("No keyword matches found today.")
        return

    filtered_posts = filter_with_ai(all_matches)

    if filtered_posts:
        send_to_slack(filtered_posts)
        logging.info(f"Sent {len(filtered_posts)} filtered post(s) to Slack.")
    else:
        logging.info("No posts passed AI filtering.")

if __name__ == "__main__":
    main()