from app import db
from app.core.models import Hashtag, HashtagUsage
from sqlalchemy import func
from datetime import datetime, timedelta

def calculate_trending_scores():
    """
    Calculates a trending score for each hashtag based on its usage
    over different time periods.
    """
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)
    one_week_ago = now - timedelta(weeks=1)

    hashtags = Hashtag.query.all()
    trending_scores = {}

    for hashtag in hashtags:
        # Get usage counts for different time periods
        recent_usage = HashtagUsage.query.filter(
            HashtagUsage.hashtag_id == hashtag.id,
            HashtagUsage.timestamp >= one_hour_ago
        ).count()

        daily_usage = HashtagUsage.query.filter(
            HashtagUsage.hashtag_id == hashtag.id,
            HashtagUsage.timestamp >= one_day_ago
        ).count()

        weekly_usage = HashtagUsage.query.filter(
            HashtagUsage.hashtag_id == hashtag.id,
            HashtagUsage.timestamp >= one_week_ago
        ).count()

        # Calculate score with different weights
        score = (recent_usage * 0.6) + (daily_usage * 0.3) + (weekly_usage * 0.1)
        trending_scores[hashtag.tag_text] = score

    # Sort hashtags by score in descending order
    sorted_hashtags = sorted(trending_scores.items(), key=lambda item: item[1], reverse=True)
    return sorted_hashtags
