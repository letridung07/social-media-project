# Privacy Level Constants
PRIVACY_PUBLIC = "PUBLIC"
PRIVACY_FOLLOWERS = "FOLLOWERS"
PRIVACY_CUSTOM_LIST = "CUSTOM_LIST"
PRIVACY_PRIVATE = "PRIVATE"

from app import db, cache # Import cache
from flask_login import UserMixin
from passlib.hash import sha256_crypt
from datetime import datetime, timezone, timedelta
import secrets # For generating secure tokens
try:
    from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
except ImportError:
    from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app
from sqlalchemy.ext.associationproxy import association_proxy


# Add this class definition at an appropriate place, e.g., in app/models.py or a utils file.
# If in a utils file, ensure it's imported in app/models.py.
# For this subtask, placing it in app/models.py before the User class is fine.

class ManualPagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = (total + per_page - 1) // per_page if total > 0 else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1 if self.has_prev else None
        self.next_num = page + 1 if self.has_next else None

    @property
    def prev(self):
        # Compatibility with Flask-SQLAlchemy pagination's prev property
        if not self.has_prev:
            return None
        # This should ideally return a new Pagination object for the prev page
        # For template usage of prev_num, this simplified version is okay.
        return {'page': self.prev_num}


    @property
    def next(self):
        # Compatibility with Flask-SQLAlchemy pagination's next property
        if not self.has_next:
            return None
        return {'page': self.next_num}

    def iter_pages(self, left_edge=1, left_current=1, right_current=2, right_edge=1):
        # Simplified iter_pages logic, good enough for most cases
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

# Define the association table for followers
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

# Define the association table for conversation participants
conversation_participants = db.Table('conversation_participants',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('conversation_id', db.Integer, db.ForeignKey('conversations.id'), primary_key=True)
)

# Define the association table for post_hashtags
post_hashtags = db.Table('post_hashtags',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True),
    db.Column('hashtag_id', db.Integer, db.ForeignKey('hashtag.id'), primary_key=True),
    db.Column('usage_count', db.Integer, default=1)  # Added usage_count
)

# Association table for FriendList members
friend_list_members = db.Table('friend_list_members',
    db.Column('friend_list_id', db.Integer, db.ForeignKey('friend_list.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class FriendList(db.Model):
    __tablename__ = 'friend_list'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # The user who owns this list
    name = db.Column(db.String(100), nullable=False)

    # Relationship to users who are members of this list
    members = db.relationship('User', secondary=friend_list_members, lazy='dynamic',
                              backref=db.backref('member_of_friend_lists', lazy='dynamic'))

    def __repr__(self):
        return f'<FriendList {self.name} owned by User ID {self.user_id}>'

# Association table for User and Badge (many-to-many).
# This table links users to the badges they have earned and stores the timestamp of when each badge was earned.
# It serves as the `secondary` table for the `User.badges` many-to-many relationship.
user_badge_association = db.Table('user_badge',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True), # Foreign key to User model.
    db.Column('badge_id', db.Integer, db.ForeignKey('badge.id'), primary_key=True), # Foreign key to Badge model.
    db.Column('earned_at', db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
)

class Badge(db.Model):
    """
    Represents a badge that users can earn in the gamification system.

    Attributes:
        name (str): The display name of the badge (e.g., "Welcome Wagon").
        description (str): A user-facing description of the badge, often including criteria.
        icon_url (str, optional): Path or URL to an image file for the badge icon.
        criteria (str, optional): Potentially more detailed textual criteria if different from description.
                                  (Note: `criteria_key` is used for programmatic checks).
        criteria_key (str, optional): A unique key used internally by the system to
                                      programmatically check if a user has met the
                                      criteria for this badge (e.g., "welcome_wagon").
    """
    __tablename__ = 'badge'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True) # User-facing description, often includes criteria.
    icon_url = db.Column(db.String(255), nullable=True) # URL or path to the badge's icon.
    criteria = db.Column(db.Text, nullable=True) # Potentially more detailed textual criteria.
    criteria_key = db.Column(db.String(50), nullable=True, unique=True) # Programmatic key for checking badge criteria logic.

    def __repr__(self):
        return f'<Badge {self.name}>'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    bio = db.Column(db.String(250), nullable=True)
    profile_picture_url = db.Column(db.String(200), nullable=True, default='default_profile_pic.png')
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    # OAuth Tokens for external services
    twitter_access_token = db.Column(db.String(255), nullable=True)
    facebook_access_token = db.Column(db.String(255), nullable=True)

    # User Theme Preference
    theme_preference = db.Column(db.String(50), nullable=True, default='default')
    stripe_customer_id = db.Column(db.String(255), nullable=True, unique=True, index=True)

    profile_visibility = db.Column(db.String(50), nullable=False, default=PRIVACY_PUBLIC)
    default_post_privacy = db.Column(db.String(50), nullable=False, default=PRIVACY_PUBLIC)
    default_story_privacy = db.Column(db.String(50), nullable=False, default=PRIVACY_PUBLIC)
    # Relationship to FriendList
    friend_lists = db.relationship('FriendList', backref='owner', lazy='dynamic', cascade='all, delete-orphan')

    # 2FA Fields
    otp_secret = db.Column(db.String(32), nullable=True)
    otp_enabled = db.Column(db.Boolean, default=False, nullable=False)
    otp_backup_codes = db.Column(db.Text, nullable=True) # Store as JSON list of hashed codes

    # Relationship to Post
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    stories = db.relationship('Story', backref='author', lazy='dynamic')
    articles = db.relationship('Article', backref='author', lazy='dynamic', cascade='all, delete-orphan') # New relationship for Articles
    audio_posts = db.relationship('AudioPost', backref='uploader', lazy='dynamic', cascade='all, delete-orphan') # New relationship for AudioPosts
    bookmarks = db.relationship('Bookmark', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    # Gamification relationships
    # User.points provides direct access to the UserPoints object associated with this user.
    # UserPoints.user_profile is the back-reference from UserPoints to this User model.
    # Establishes a one-to-one relationship for storing a user's total gamification points.
    points = db.relationship('UserPoints', backref='user_profile', uselist=False, cascade='all, delete-orphan')

    # User.badges provides access to a collection of Badge objects earned by this user.
    # It uses `user_badge_association` as the secondary table for this many-to-many relationship.
    # `users_earning_badge` is the back-reference from Badge to this User model, allowing access to users who earned a specific badge.
    badges = db.relationship('Badge', secondary=user_badge_association, lazy='dynamic',
                             backref=db.backref('users_earning_badge', lazy='dynamic'))

    # User.activity_logs provides access to a collection of ActivityLog objects related to this user.
    # ActivityLog.user_activity is the back-reference from ActivityLog to this User model.
    # Establishes a one-to-many relationship for logging various user activities, including point earnings and badge awards.
    activity_logs = db.relationship('ActivityLog', backref='user_activity', lazy='dynamic', cascade='all, delete-orphan')

    # Existing relationships below, ensure they are not accidentally modified.
    historical_analytics = db.relationship('HistoricalAnalytics', backref='user', lazy='dynamic')
    polls = db.relationship('Poll', backref='author', lazy='dynamic', foreign_keys='Poll.user_id')
    poll_votes = db.relationship('PollVote', backref='user', lazy='dynamic')

    # Groups created by the user
    groups_created = db.relationship('Group', backref='creator', lazy='dynamic', foreign_keys='Group.creator_id')
    # Memberships of the user in groups
    group_memberships = db.relationship('GroupMembership', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    # 'followed' is the list of users this user is following.
    # 'followers' is the list of users who are following this user.
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id), # Condition for whom this user is following
        secondaryjoin=(followers.c.followed_id == id), # Condition for whom is following this user
        backref=db.backref('followers', lazy='dynamic'), # How to access users following this one
        lazy='dynamic'
    )

    # likes given by this user
    # likes = db.relationship('Like', backref='user', lazy='dynamic', cascade='all, delete-orphan') # Replaced by reactions
    reactions = db.relationship('Reaction', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')

    # Active title/flair
    active_title_id = db.Column(db.Integer, db.ForeignKey('user_virtual_good.id'), nullable=True)
    active_title = db.relationship('UserVirtualGood', foreign_keys=[active_title_id], backref=db.backref('active_title_for_user', uselist=False), uselist=False)

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password_hash = sha256_crypt.hash(password)

    def check_password(self, password):
        return sha256_crypt.verify(password, self.password_hash)

    # Helper methods for follow mechanism
    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        # Ensure user.id is not None for new, uncommitted users if that's a possibility
        if user.id is None:
            return False
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0

    # Method to get posts from followed users (for the feed)
    @cache.cached(timeout=300)
    def followed_posts(self, page=1, per_page=10):
        user_and_followed_ids = [f.id for f in self.followed] + [self.id]

        # Get current user's posts and posts by followed users
        direct_posts = Post.query.filter(Post.user_id.in_(user_and_followed_ids)).all()

        # Get shares by current user and shares by followed users
        shares = Share.query.options(
            db.joinedload(Share.original_post).joinedload(Post.author),
            db.joinedload(Share.user) # Eager load the sharer (User object)
        ).filter(Share.user_id.in_(user_and_followed_ids)).all()

        feed_items = []
        processed_post_ids_in_feed = set() # To help avoid some forms of duplication

        # Add direct posts
        for post in direct_posts:
            feed_items.append({'type': 'post', 'item': post, 'timestamp': post.timestamp, 'sharer': None})
            processed_post_ids_in_feed.add((post.id, 'post', None))


        # Add shared posts
        for share in shares:
            # Avoid showing a share if the viewer is the one who shared their own post on their main feed
            if share.user_id == self.id and share.original_post.user_id == self.id and share.group_id is None:
                continue

            # Avoid adding a share if the original post by the same author is already in feed_items
            # This simple check might not cover all nuanced duplication scenarios but is a start.
            # A more sophisticated check might be needed if User A follows User B, User A posts P1, User B shares P1.
            # Current logic will show both P1 by A, and P1 shared by B. This is generally acceptable.

            # Key for this share instance
            share_key = (share.original_post.id, 'share', share.user_id)
            if share_key not in processed_post_ids_in_feed:
                 feed_items.append({'type': 'share', 'item': share.original_post, 'timestamp': share.timestamp, 'sharer': share.user})
                 processed_post_ids_in_feed.add(share_key)


        # Sort items: newest first
        feed_items.sort(key=lambda x: x['timestamp'], reverse=True)

        # Manual pagination
        start = (page - 1) * per_page
        end = start + per_page
        paginated_items = feed_items[start:end]

        pagination_obj = ManualPagination(paginated_items, page, per_page, len(feed_items))
        return pagination_obj

    def get_reset_password_token(self, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'], expires_in=expires_sec)
        return s.dumps({'user_id': self.id}).decode('utf-8')

    @staticmethod
    def verify_reset_password_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
            user_id = data.get('user_id')
        except Exception: # Catches expired signature, bad signature, etc.
            return None
        return User.query.get(user_id)

class MediaItem(db.Model):
    __tablename__ = 'media_item'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    media_type = db.Column(db.String(10), nullable=False)  # e.g., "image", "video"
    alt_text = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    def __repr__(self):
        return f'<MediaItem {self.filename} for Post {self.post_id}>'

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False) # This will serve as the caption for the gallery
    # Use lambda for default to ensure it's called at insertion time
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    # Relationship to MediaItem
    media_items = db.relationship('MediaItem', backref='post_parent', lazy='dynamic', cascade='all, delete-orphan')

    # likes received by this post
    # likes = db.relationship('Like', backref='post', lazy='dynamic', cascade='all, delete-orphan') # Replaced by reactions
    reactions = db.relationship('Reaction', backref='post', lazy='dynamic', cascade='all, delete-orphan')
    # To get comments in ascending order by timestamp by default when accessing post.comments
    comments = db.relationship('Comment', backref='commented_post', lazy='dynamic', cascade='all, delete-orphan', order_by='Comment.timestamp.asc()')

    # Relationship to Hashtags (many-to-many)
    hashtags = db.relationship(
        'Hashtag', secondary=post_hashtags,
        backref=db.backref('posts', lazy='dynamic'), # Creates 'hashtag.posts'
        lazy='dynamic' # Allows querying on post.hashtags
    )

    # Foreign key to Group (nullable, as posts can still be non-group posts)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    # Relationship to Group
    group = db.relationship('Group', backref=db.backref('posts', lazy='dynamic'))

    # Polls associated with this post
    polls = db.relationship('Poll', backref='post', lazy='dynamic')

    privacy_level = db.Column(db.String(50), nullable=False, default=PRIVACY_PUBLIC)
    custom_friend_list_id = db.Column(db.Integer, db.ForeignKey('friend_list.id'), nullable=True)
    # Relationship to a specific FriendList (if privacy_level is CUSTOM_LIST)
    custom_friend_list = db.relationship('FriendList', foreign_keys=[custom_friend_list_id])

    scheduled_for = db.Column(db.DateTime, nullable=True, index=True)
    is_published = db.Column(db.Boolean, default=False, nullable=False, index=True)

    bookmarked_by = db.relationship('Bookmark', backref='post', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Post {self.body[:50]}...>'

    # def like_count(self): # Replaced by reaction_count('like')
    #     return self.likes.count() # self.likes is the relationship
    #
    # def is_liked_by(self, user): # Replaced by get_reaction_by_user(user) and checking type
    #     if not user or not user.is_authenticated: # Handle anonymous or uncommitted users
    #         return False
    #     # Check if a Like record exists for this post and the given user
    #     return self.likes.filter_by(user_id=user.id).count() > 0

    def get_reaction_by_user(self, user):
        """Returns the reaction object if the user has reacted to this post, else None."""
        if not user or not user.is_authenticated:
            return None
        return self.reactions.filter_by(user_id=user.id).first()

    def reaction_count(self, reaction_type=None):
        """
        Returns the count of a specific reaction type on this post.
        If reaction_type is None, returns total count of all reactions.
        """
        if reaction_type:
            return self.reactions.filter_by(reaction_type=reaction_type).count()
        return self.reactions.count()

    def related_posts(self, max_posts=5):
        """
        Finds posts related to the current post based on shared hashtags.
        """
        if not self.hashtags.all():
            return []

        current_post_tags_ids = {tag.id for tag in self.hashtags}

        # Find posts that share at least one tag, excluding the current post
        # and order by the number of shared tags.
        # This requires a subquery to count common tags.

        # Alias for the post_hashtags table to use in the subquery
        from sqlalchemy.orm import aliased
        from sqlalchemy import func

        ph_alias = aliased(post_hashtags)

        # Subquery to count common tags for each post
        subquery = db.session.query(
            Post.id.label('post_id'),
            func.count(ph_alias.c.hashtag_id).label('common_tags_count')
        ).join(ph_alias, Post.id == ph_alias.c.post_id)\
         .filter(ph_alias.c.hashtag_id.in_(current_post_tags_ids))\
         .filter(Post.id != self.id)\
         .group_by(Post.id)\
         .subquery()

        # Main query to get the posts, ordered by the count of common tags
        related_posts_query = db.session.query(Post)\
            .join(subquery, Post.id == subquery.c.post_id)\
            .order_by(subquery.c.common_tags_count.desc())\
            .limit(max_posts)

        return related_posts_query.all()

# class Like(db.Model): # Removed, functionality merged into Reaction
#     __tablename__ = 'likes'
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
#     timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
#
#     # Composite unique constraint to prevent duplicate likes from the same user on the same post
#     __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_uc'),)
#
#     def __repr__(self):
#         return f'<Like user_id={self.user_id} post_id={self.post_id}>'

class Reaction(db.Model):
    __tablename__ = 'reaction'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False, index=True)
    reaction_type = db.Column(db.String(20), nullable=False, index=True) # e.g., 'like', 'love', 'haha'
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # Composite unique constraint: a user can only have one reaction per post.
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_reaction_uc'),)

    def __repr__(self):
        return f'<Reaction user_id={self.user_id} post_id={self.post_id} type={self.reaction_type}>'

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    def __repr__(self):
        return f'<Comment {self.body[:50]}...>'

class Mention(db.Model):
    __tablename__ = 'mention'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)  # The user who is tagged
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True, index=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)  # The user who made the mention
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('mentions_received', lazy='dynamic'))
    actor = db.relationship('User', foreign_keys=[actor_id], backref=db.backref('mentions_made', lazy='dynamic'))
    post = db.relationship('Post', backref=db.backref('mentions', lazy='dynamic', cascade='all, delete-orphan'))
    comment = db.relationship('Comment', backref=db.backref('mentions', lazy='dynamic', cascade='all, delete-orphan'))

    # Check constraint to ensure that either post_id or comment_id is not null can be added here if db supports it well
    # For now, handling in application logic as per instructions.
    # __table_args__ = (db.CheckConstraint('(post_id IS NOT NULL OR comment_id IS NOT NULL)'),)


    def __repr__(self):
        return f'<Mention id={self.id} user_id={self.user_id} actor_id={self.actor_id} post_id={self.post_id} comment_id={self.comment_id}>'

class Hashtag(db.Model):
    __tablename__ = 'hashtag' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    tag_text = db.Column(db.String(100), unique=True, nullable=False, index=True)
    last_used = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Added last_used

    def __repr__(self):
        return f'<Hashtag {self.tag_text}>'

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True) # User receiving the notification
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True) # User who triggered the notification
    type = db.Column(db.String(50), nullable=False)  # e.g., 'like', 'comment', 'follow', 'mention'
    related_post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    related_conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=True)
    related_mention_id = db.Column(db.Integer, db.ForeignKey('mention.id'), nullable=True) # New field for mentions
    # related_comment_id could be added if direct linking to comments is desired
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships to easily access user objects
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref=db.backref('notifications_received', lazy='dynamic'))
    actor = db.relationship('User', foreign_keys=[actor_id], backref=db.backref('notifications_sent', lazy='dynamic'))
    related_post = db.relationship('Post', foreign_keys=[related_post_id], backref=db.backref('related_notifications', lazy='dynamic'))
    related_mention = db.relationship('Mention', foreign_keys=[related_mention_id], backref=db.backref('notifications', lazy='dynamic')) # New relationship for mentions
    related_conversation = db.relationship('Conversation', foreign_keys=[related_conversation_id], lazy='joined')
    related_group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    related_group = db.relationship('Group', foreign_keys=[related_group_id], backref=db.backref('related_notifications', lazy='dynamic'))
    related_event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
    related_event = db.relationship('Event', foreign_keys=[related_event_id], backref=db.backref('related_notifications', lazy='dynamic'))

    def __repr__(self):
        return f'<Notification {self.type} for User ID {self.recipient_id} by User ID {self.actor_id}>'

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    # Timestamp of the last message or creation, can be updated.
    last_updated = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # Relationship to messages in this conversation
    messages = db.relationship('ChatMessage', backref='conversation', lazy='dynamic', order_by='ChatMessage.timestamp.asc()', cascade='all, delete-orphan')
    # Relationship to participants in this conversation
    participants = db.relationship('User', secondary='conversation_participants', backref=db.backref('conversations', lazy='dynamic'))

    def __repr__(self):
        return f'<Conversation {self.id}>'

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True) # Added index here as well, good for finding user's messages
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    read_at = db.Column(db.DateTime, nullable=True) # Stores when the message was first read by anyone or the recipient in a 1-1 chat

    # Relationship to the sender (User)
    sender = db.relationship('User', backref='sent_chat_messages', foreign_keys=[sender_id])

    def __repr__(self):
        return f'<ChatMessage {self.id} from User {self.sender_id} in Conv {self.conversation_id}>'

class MessageReadStatus(db.Model):
    __tablename__ = 'message_read_status'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    __table_args__ = (db.UniqueConstraint('message_id', 'user_id', name='_message_user_read_uc'),)

    # Relationships
    message = db.relationship('ChatMessage', backref=db.backref('read_receipts', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('messages_read_status', lazy='dynamic')) # Changed backref name for clarity

    def __repr__(self):
        return f'<MessageReadStatus message_id={self.message_id} user_id={self.user_id} read_at={self.read_at}>'

# Group Model
class Group(db.Model):
    __tablename__ = 'group'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    image_file = db.Column(db.String(100), nullable=True, default='default_group_pic.png')
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # Relationship to GroupMembership (list of memberships)
    memberships = db.relationship('GroupMembership', backref='group', lazy='dynamic', cascade='all, delete-orphan')

    # Association proxy to easily get users in a group through GroupMembership
    # 'members' attribute will list User objects who are members of this group.
    # 'group_memberships' is the intermediary collection (Group.memberships).
    # 'user' is the target attribute on the GroupMembership model.
    members = association_proxy('memberships', 'user', creator=lambda user_obj: GroupMembership(user=user_obj, role='member'))

    # Polls associated with this group
    polls = db.relationship('Poll', backref='group', lazy='dynamic')

    def __repr__(self):
        return f'<Group {self.name}>'


class Bookmark(db.Model):
    __tablename__ = 'bookmark'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_bookmark_uc'),)

    def __repr__(self):
        return f'<Bookmark user_id={self.user_id} post_id={self.post_id}>'

# GroupMembership Model
class GroupMembership(db.Model):
    __tablename__ = 'group_membership'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    role = db.Column(db.String(50), nullable=False, default='member')  # e.g., 'admin', 'member'

    # Composite unique constraint to prevent duplicate memberships
    __table_args__ = (db.UniqueConstraint('user_id', 'group_id', name='_user_group_uc'),)

    def __repr__(self):
        return f'<GroupMembership User {self.user_id} in Group {self.group_id} as {self.role}>'

class Story(db.Model):
    __tablename__ = 'story'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)
    video_filename = db.Column(db.String(100), nullable=True)
    caption = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    expires_at = db.Column(db.DateTime, index=True)

    privacy_level = db.Column(db.String(50), nullable=False, default=PRIVACY_PUBLIC)
    custom_friend_list_id = db.Column(db.Integer, db.ForeignKey('friend_list.id'), nullable=True)
    # Relationship to a specific FriendList
    custom_friend_list = db.relationship('FriendList', foreign_keys=[custom_friend_list_id])

    scheduled_for = db.Column(db.DateTime, nullable=True, index=True)
    is_published = db.Column(db.Boolean, default=False, nullable=False, index=True)

    def __init__(self, **kwargs):
        super(Story, self).__init__(**kwargs)
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow()
        # Only set expires_at if it's not a scheduled story being created without immediate publishing
        # If is_published is False (because it's scheduled), expires_at will be set upon publishing.
        if kwargs.get('is_published', True): # Default to True if not provided (immediate publish)
             self.expires_at = self.timestamp + timedelta(hours=24)
        # If it's a new story instance and is_published is explicitly False (scheduled),
        # expires_at will remain None until the scheduler publishes it.

    def __repr__(self):
        return f'<Story {self.id} by User {self.user_id}>'

# Poll Models
class Poll(db.Model):
    __tablename__ = 'poll'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Creator of the poll
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True) # Optional: Poll associated with a post
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True) # Optional: Poll associated with a group

    options = db.relationship('PollOption', backref='poll', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Poll {self.id} "{self.question[:30]}...">'

    def user_has_voted(self, user):
        if not user.is_authenticated:
            return False
        # PollVote is defined below in this file.
        return PollVote.query.filter_by(user_id=user.id, poll_id=self.id).count() > 0

    def total_votes(self):
        # Summing up vote_count() from each option.
        # vote_count() is defined in PollOption model.
        return sum(option.vote_count() for option in self.options)

class PollOption(db.Model):
    __tablename__ = 'poll_option'
    id = db.Column(db.Integer, primary_key=True)
    option_text = db.Column(db.String(255), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)

    votes = db.relationship('PollVote', backref='option', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<PollOption {self.id} "{self.option_text[:30]}..." for Poll {self.poll_id}>'

    def vote_count(self):
        # self.votes is the relationship to PollVote
        return self.votes.count()

class PollVote(db.Model):
    __tablename__ = 'poll_vote'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('poll_option.id'), nullable=False)
    # Adding poll_id here directly to make the UniqueConstraint straightforward
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    __table_args__ = (db.UniqueConstraint('user_id', 'poll_id', name='_user_poll_uc'),)

    def __repr__(self):
        return f'<PollVote by User {self.user_id} for Option {self.option_id} in Poll {self.poll_id}>'

# Association table for Event attendees
event_attendees = db.Table('event_attendees',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('event_id', db.Integer, db.ForeignKey('event.id'), primary_key=True)
)

import uuid # For generating unique calendar UIDs

class Event(db.Model):
    __tablename__ = 'event'
    id = db.Column(db.Integer, primary_key=True)
    calendar_uid = db.Column(db.String(36), unique=True, nullable=True, default=lambda: str(uuid.uuid4()))
    is_synced = db.Column(db.Boolean, default=False, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_datetime = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    end_datetime = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(255), nullable=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    organizer = db.relationship('User', backref=db.backref('organized_events', lazy='dynamic'))
    attendees = db.relationship('User', secondary=event_attendees,
                                backref=db.backref('attended_events', lazy='dynamic'),
                                lazy='dynamic')

    # Ensure calendar_uid is indexed if it's frequently queried for uniqueness or lookup
    __table_args__ = (db.Index('ix_event_calendar_uid', 'calendar_uid', unique=True),)


    def __repr__(self):
        return f'<Event {self.name}>'

class HistoricalAnalytics(db.Model):
    __tablename__ = 'historical_analytics'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    likes_received = db.Column(db.Integer, default=0)  # Stores count of 'like' reactions
    comments_received = db.Column(db.Integer, default=0)
    followers_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<HistoricalAnalytics for User ID {self.user_id} at {self.timestamp}>'

class UserAnalytics(db.Model):
    __tablename__ = 'user_analytics'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    total_likes_received = db.Column(db.Integer, default=0)  # Stores total count of 'like' reactions
    total_comments_received = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow(), onupdate=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    user = db.relationship('User', backref=db.backref('analytics', uselist=False))

    def __repr__(self):
        return f'<UserAnalytics for User ID {self.user_id}>'


class Share(db.Model):
    __tablename__ = 'share'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True, index=True)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # Relationships
    user = db.relationship('User', backref=db.backref('shares', lazy='dynamic'))
    original_post = db.relationship('Post', backref=db.backref('shares', lazy='dynamic'))
    group = db.relationship('Group', backref=db.backref('shares', lazy='dynamic'))

    def __repr__(self):
        return f'<Share user_id={self.user_id} post_id={self.post_id} group_id={self.group_id}>'


class LiveStream(db.Model):
    __tablename__ = 'live_streams'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=True)
    description = db.Column(db.Text, nullable=True)
    stream_key = db.Column(db.String(64), unique=True, nullable=True) # Generated upon starting
    # is_live is replaced by status
    # is_live = db.Column(db.Boolean, default=False, nullable=False, index=True)
    status = db.Column(db.String(20), default='upcoming', nullable=False, index=True) # 'upcoming', 'live', 'ended'
    start_time = db.Column(db.DateTime, nullable=True, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    end_time = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # New fields for recording and chat
    recording_filename = db.Column(db.String(255), nullable=True)
    media_server_url = db.Column(db.String(255), nullable=True)
    stream_conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=True, unique=True)
    stream_conversation = db.relationship('Conversation', backref=db.backref('live_stream_chat', uselist=False))
    enable_recording = db.Column(db.Boolean, default=False, nullable=True) # Add this too

    user = db.relationship('User', backref=db.backref('live_streams', lazy='dynamic'))

    def __repr__(self):
        return f'<LiveStream {self.id} by User {self.user_id} - Title: {self.title[:30] if self.title else "N/A"}>'


class StreamChatMessage(db.Model):
    __tablename__ = 'stream_chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(db.Integer, db.ForeignKey('live_streams.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    stream = db.relationship('LiveStream', backref=db.backref('chat_messages', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('stream_chat_messages', lazy='dynamic'))

    def __repr__(self):
        return f'<StreamChatMessage {self.id} by User {self.user_id} in Stream {self.stream_id}>'


class Article(db.Model):
    __tablename__ = 'article'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)

    def __repr__(self):
        return f'<Article {self.title} by User {self.user_id}>'


class AudioPost(db.Model):
    __tablename__ = 'audio_post'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    audio_filename = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    duration = db.Column(db.Integer, nullable=True)  # in seconds

    def __repr__(self):
        return f'<AudioPost {self.title} by User {self.user_id}>'


class VirtualGood(db.Model):
    __tablename__ = 'virtual_good'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='USD')
    type = db.Column(db.String(50), nullable=False)  # e.g., "badge", "emoji", "profile_frame", "title"
    image_url = db.Column(db.String(255), nullable=True)
    title_text = db.Column(db.String, nullable=True)  # Actual title/flair text
    title_icon_url = db.Column(db.String, nullable=True)  # Optional icon URL for flair
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow(), onupdate=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    def __repr__(self):
        return f'<VirtualGood {self.name}>'


class UserVirtualGood(db.Model):
    __tablename__ = 'user_virtual_good'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    virtual_good_id = db.Column(db.Integer, db.ForeignKey('virtual_good.id'), nullable=False, index=True)
    purchase_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    quantity = db.Column(db.Integer, default=1, nullable=False)
    is_equipped = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship('User', backref=db.backref('virtual_goods_inventory', lazy='dynamic'), foreign_keys=[user_id]) # Specify foreign_keys for clarity
    virtual_good = db.relationship('VirtualGood', backref=db.backref('user_inventories', lazy='dynamic'))
    # The backref 'active_title_for_user' is created from User.active_title relationship and will be available on UserVirtualGood objects

    __table_args__ = (db.UniqueConstraint('user_id', 'virtual_good_id', name='_user_virtual_good_uc'),) # Assuming a user can only have one entry per virtual good type, quantity handles multiples. If multiple separate purchases of the same good should be distinct rows, remove this.

    def __repr__(self):
        return f'<UserVirtualGood UserID:{self.user_id} GoodID:{self.virtual_good_id} Qty:{self.quantity}>'

class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plan'
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False) # Assuming 10 digits, 2 decimal places
    currency = db.Column(db.String(3), nullable=False) # e.g., "USD"
    duration = db.Column(db.String(50), nullable=False) # e.g., "monthly", "yearly"
    features = db.Column(db.JSON, nullable=True) # For storing list of features
    stripe_product_id = db.Column(db.String(255), nullable=True, index=True)
    stripe_price_id = db.Column(db.String(255), nullable=True, unique=True, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow(), onupdate=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    creator = db.relationship('User', backref=db.backref('subscription_plans_offered', lazy='dynamic'))

    def __repr__(self):
        return f'<SubscriptionPlan {self.name} by User ID {self.creator_id}>'


class UserSubscription(db.Model):
    __tablename__ = 'user_subscription'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plan.id'), nullable=False, index=True)
    start_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    end_date = db.Column(db.DateTime, nullable=True) # Nullable if subscription is, for example, lifetime or managed by status
    status = db.Column(db.String(50), nullable=False, default='active', index=True) # e.g., "active", "cancelled", "expired"
    payment_details_id = db.Column(db.String(255), nullable=True) # External payment gateway reference
    stripe_subscription_id = db.Column(db.String(255), nullable=True, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow(), onupdate=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    subscriber = db.relationship('User', backref=db.backref('subscriptions', lazy='dynamic'))
    plan = db.relationship('SubscriptionPlan', backref=db.backref('subscribers', lazy='dynamic'))

    # Composite unique constraint to prevent a user from subscribing to the same plan multiple times simultaneously (if applicable)
    # __table_args__ = (db.UniqueConstraint('subscriber_id', 'plan_id', name='_subscriber_plan_uc'),)
    # For now, we'll comment this out as a user might be able to cancel and resubscribe, or have multiple instances if not managed strictly by active status.
    # Active status should be the primary gate.

    def __repr__(self):
        return f'<UserSubscription User {self.subscriber_id} to Plan {self.plan_id} - Status: {self.status}>'


# OAuth Application Model
class Application(db.Model):
    __tablename__ = 'oauth_application'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    client_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    client_secret = db.Column(db.String(256), nullable=False) # Will be hashed
    redirect_uris = db.Column(db.Text, nullable=False) # Space-separated string or JSON list of URIs
    owner_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow(), onupdate=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    owner = db.relationship('User', backref=db.backref('oauth_applications', lazy='dynamic'))

    def __init__(self, *args, **kwargs):
        super(Application, self).__init__(*args, **kwargs)
        if not self.client_id:
            self.client_id = secrets.token_urlsafe(32) # Generate a secure client_id
        # Client secret should be set and hashed separately, similar to password
        # For example, a method set_client_secret(secret) could be added

    def set_client_secret(self, secret):
        self.client_secret = sha256_crypt.hash(secret)

    def check_client_secret(self, secret):
        return sha256_crypt.verify(secret, self.client_secret)

    def __repr__(self):
        return f'<Application {self.name}>'


# OAuth Access Token Model
class AccessToken(db.Model):
    __tablename__ = 'oauth_access_token'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    application_id = db.Column(db.Integer, db.ForeignKey('oauth_application.id'), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    refresh_token = db.Column(db.String(255), unique=True, nullable=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    scopes = db.Column(db.Text, nullable=True) # Space-separated string or JSON list of scopes
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    user = db.relationship('User', backref=db.backref('oauth_access_tokens', lazy='dynamic'))
    application = db.relationship('Application', backref=db.backref('access_tokens', lazy='dynamic'))

    def __init__(self, *args, **kwargs):
        super(AccessToken, self).__init__(*args, **kwargs)
        if not self.token:
            self.token = secrets.token_urlsafe(64) # Generate a secure access token
        # refresh_token could be generated similarly if needed upon creation
        # if not self.refresh_token and kwargs.get('generate_refresh_token', False):
        # self.refresh_token = secrets.token_urlsafe(64)


    def is_expired(self):
        return (datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow()) >= self.expires_at

    def revoke(self):
        # Placeholder for token revocation logic, e.g., by setting expires_at to now or deleting the token
        # For now, we can simply delete it or mark it as expired.
        # Depending on the strategy, you might also want to handle refresh tokens.
        db.session.delete(self) # Or mark as expired: self.expires_at = datetime.utcnow()
        # If there's a corresponding refresh token, it might need to be revoked too.

    def __repr__(self):
        return f'<AccessToken {self.token} for User {self.user_id} to App {self.application_id}>'


# Gamification Models
class UserPoints(db.Model):
    """
    Represents a user's total accumulated gamification points.
    Each user has one UserPoints record, establishing a one-to-one relationship.
    """
    __tablename__ = 'user_points'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    points = db.Column(db.Integer, default=0, nullable=False)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow(), onupdate=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    user = db.relationship('User', backref=db.backref('points_data_ref', uselist=False)) # Changed backref to avoid conflict

    def __repr__(self):
        return f'<UserPoints UserID:{self.user_id} Points:{self.points}>'

class UserBadge(db.Model): # This model represents the earning of a badge by a user.
    __tablename__ = 'user_badge_earned'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), primary_key=True)
    earned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # Relationships to User and Badge to easily access related objects
    # The backref on User allows accessing all UserBadgeEarned records (and thus badges) for a user.
    # The backref on Badge allows accessing all UserBadgeEarned records (and thus users) for a badge.
    user = db.relationship("User", backref=db.backref("user_badges_earned_association", cascade="all, delete-orphan"))
    badge = db.relationship("Badge", backref=db.backref("users_earned_badge_association", cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<UserBadge UserID:{self.user_id} BadgeID:{self.badge_id} EarnedAt:{self.earned_at}>'


class ActivityLog(db.Model):
    """
    Logs user activities, especially those that result in points or badges.

    Attributes:
        user_id (int): ID of the user who performed the activity.
        activity_type (str): Type of activity (e.g., 'create_post', 'daily_login', 'earn_badge').
        description (str, optional): A human-readable description of the specific activity.
        points_earned (int): Number of points earned for this activity.
        related_id (int, optional): ID of a related database object (e.g., Post ID, Badge ID).
        related_item_type (str, optional): Type of the related object (e.g., 'post', 'badge').
        timestamp (datetime): When the activity occurred.
    """
    __tablename__ = 'activity_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    activity_type = db.Column(db.String(50), nullable=False) # E.g., 'post_created', 'comment_added', 'badge_earned'
    description = db.Column(db.Text, nullable=True) # E.g., "User created a new post: 'My First Post'"
    points_earned = db.Column(db.Integer, default=0)
    related_id = db.Column(db.Integer, nullable=True) # ID of related entity (e.g., post_id, comment_id, badge_id)
    related_item_type = db.Column(db.String(50), nullable=True) # Type of the related entity, e.g., 'post', 'badge'
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # The backref on User allows accessing all activity logs for a user.
    user = db.relationship('User', backref=db.backref('activity_logs_data_ref', lazy='dynamic')) # Changed backref to avoid conflict

    def __repr__(self):
        return f'<ActivityLog UserID:{self.user_id} Type:{self.activity_type} Points:{self.points_earned} Related:{self.related_item_type}/{self.related_id}>'
