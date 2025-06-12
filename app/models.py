from app import db, cache # Import cache
from flask_login import UserMixin
from passlib.hash import sha256_crypt
from datetime import datetime, timezone, timedelta
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
    db.Column('hashtag_id', db.Integer, db.ForeignKey('hashtag.id'), primary_key=True)
)

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

    # Relationship to Post
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    stories = db.relationship('Story', backref='author', lazy='dynamic')
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
    likes = db.relationship('Like', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')

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

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    # Use lambda for default to ensure it's called at insertion time
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    # New field for image filename
    image_filename = db.Column(db.String(100), nullable=True)
    video_filename = db.Column(db.String(100), nullable=True)
    alt_text = db.Column(db.String(500), nullable=True) # <-- New field added here

    # likes received by this post
    likes = db.relationship('Like', backref='post', lazy='dynamic', cascade='all, delete-orphan')
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

    def __repr__(self):
        return f'<Post {self.body[:50]}...>'

    def like_count(self):
        return self.likes.count() # self.likes is the relationship

    def is_liked_by(self, user):
        if not user or not user.is_authenticated: # Handle anonymous or uncommitted users
            return False
        # Check if a Like record exists for this post and the given user
        return self.likes.filter_by(user_id=user.id).count() > 0

class Like(db.Model):
    __tablename__ = 'likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())

    # Composite unique constraint to prevent duplicate likes from the same user on the same post
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_uc'),)

    def __repr__(self):
        return f'<Like user_id={self.user_id} post_id={self.post_id}>'

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

    def __init__(self, **kwargs):
        super(Story, self).__init__(**kwargs)
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow()
        self.expires_at = self.timestamp + timedelta(hours=24)

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

class Event(db.Model):
    __tablename__ = 'event'
    id = db.Column(db.Integer, primary_key=True)
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

    def __repr__(self):
        return f'<Event {self.name}>'

class HistoricalAnalytics(db.Model):
    __tablename__ = 'historical_analytics'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    likes_received = db.Column(db.Integer, default=0)
    comments_received = db.Column(db.Integer, default=0)
    followers_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<HistoricalAnalytics for User ID {self.user_id} at {self.timestamp}>'

class UserAnalytics(db.Model):
    __tablename__ = 'user_analytics'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    total_likes_received = db.Column(db.Integer, default=0)
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
    is_live = db.Column(db.Boolean, default=False, nullable=False, index=True)
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
