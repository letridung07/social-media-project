from app import db
from flask_login import UserMixin
from passlib.hash import sha256_crypt
from datetime import datetime, timezone
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from flask import current_app

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

    # Relationship to Post
    posts = db.relationship('Post', backref='author', lazy='dynamic')

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
    def followed_posts(self):
        followed_posts_query = Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)).filter(
                followers.c.follower_id == self.id)
        own_posts_query = Post.query.filter_by(user_id=self.id)
        return followed_posts_query.union(own_posts_query).order_by(Post.timestamp.desc())

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # New field for image filename
    image_filename = db.Column(db.String(100), nullable=True)
    video_filename = db.Column(db.String(100), nullable=True)

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
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # User who triggered the notification
    type = db.Column(db.String(50), nullable=False)  # e.g., 'like', 'comment', 'follow'
    related_post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    related_conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=True)
    # related_comment_id could be added if direct linking to comments is desired
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships to easily access user objects
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref=db.backref('notifications_received', lazy='dynamic'))
    actor = db.relationship('User', foreign_keys=[actor_id], backref=db.backref('notifications_sent', lazy='dynamic'))
    related_post = db.relationship('Post', foreign_keys=[related_post_id], backref=db.backref('related_notifications', lazy='dynamic'))
    related_conversation = db.relationship('Conversation', foreign_keys=[related_conversation_id], lazy='joined')

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
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow())
    is_read = db.Column(db.Boolean, default=False, nullable=False) # Can be used to track if a message is read by recipient(s)

    # Relationship to the sender (User)
    sender = db.relationship('User', backref='sent_chat_messages', foreign_keys=[sender_id])

    def __repr__(self):
        return f'<ChatMessage {self.id} from User {self.sender_id} in Conv {self.conversation_id}>'
