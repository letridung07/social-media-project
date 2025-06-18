import unittest
from app import create_app, db
from app.core.models import User, Post, Group, Hashtag, Reaction, Comment, GroupMembership, followers, PRIVACY_PUBLIC
from app.utils.helpers import get_recommendations # recommend_posts, recommend_users, recommend_groups are not directly exposed
from datetime import datetime, timezone

class RecommendationsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_user(self, username_suffix, email_suffix=""):
        email_val = f'user{email_suffix if email_suffix else username_suffix}@example.com'
        return User(
            username=f'user_{username_suffix}',
            email=email_val,
            password_hash='dummy_password_hash',
            profile_visibility=PRIVACY_PUBLIC
        )

    def _create_post(self, author, body="Test Post", hashtags=None, group=None):
        post = Post(author=author, body=body, group=group)
        db.session.add(post)
        db.session.commit() # Commit to get post.id for hashtag association
        if hashtags:
            for tag_text in hashtags:
                hashtag = Hashtag.query.filter_by(tag_text=tag_text).first()
                if not hashtag:
                    hashtag = Hashtag(tag_text=tag_text)
                    db.session.add(hashtag)
                    db.session.commit() # Commit to get hashtag.id
                post.hashtags.append(hashtag)
        db.session.commit()
        return post

    def _like_post(self, user, post):
        reaction = Reaction(user_id=user.id, post_id=post.id, reaction_type='like')
        db.session.add(reaction)
        db.session.commit()

    def _comment_on_post(self, user, post, body="Test comment"):
        comment = Comment(user_id=user.id, post_id=post.id, body=body, author=user, commented_post=post)
        db.session.add(comment)
        db.session.commit()

    def _join_group(self, user, group, role='member'):
        gm = GroupMembership(user_id=user.id, group_id=group.id, role=role)
        db.session.add(gm)
        db.session.commit()

    # --- User Recommendation Tests (from previous step, kept for completeness) ---
    def test_recommend_users_no_mutual_no_shared_groups(self):
        u1 = self._create_user('target1', 'target1')
        u2 = self._create_user('other1', 'other1')
        db.session.add_all([u1, u2])
        db.session.commit()
        recommendations_dict = get_recommendations(u1.id, limit_users=5)
        recommended_user_list = recommendations_dict.get('users', [])
        self.assertEqual(len(recommended_user_list), 0)

    def test_recommend_users_mutual_connections(self):
        u1 = self._create_user('target2', 'target2')    # Target user
        u2 = self._create_user('rec_mutual1', 'rec_mutual1') # Should be recommended
        u3 = self._create_user('rec_mutual2', 'rec_mutual2') # Should be recommended
        u4 = self._create_user('mutual_friend', 'mutual_friend') # Mutual friend
        u5 = self._create_user('unconnected', 'unconnected') # Not connected
        db.session.add_all([u1, u2, u3, u4, u5])
        db.session.commit()
        u1.follow(u4)
        u4.follow(u2)
        u4.follow(u3)
        db.session.commit()
        recommendations_dict = get_recommendations(u1.id, limit_users=5)
        recommended_user_list = recommendations_dict.get('users', [])
        recommended_usernames = [r.username for r in recommended_user_list]
        self.assertIn(u2.username, recommended_usernames)
        self.assertIn(u3.username, recommended_usernames)
        self.assertNotIn(u1.username, recommended_usernames)
        self.assertNotIn(u4.username, recommended_usernames)
        self.assertNotIn(u5.username, recommended_usernames)

    def test_recommend_users_shared_groups(self):
        u1 = self._create_user('target_group_usr', 'target_group_usr')
        u2 = self._create_user('rec_group_member_usr', 'rec_group_member_usr')
        u3 = self._create_user('other_group_member_usr', 'other_group_member_usr')
        u4 = self._create_user('no_shared_group_member_usr', 'no_shared_group_member_usr')
        db.session.add_all([u1, u2, u3, u4])
        db.session.commit()
        g1 = Group(name='Test Group Shared Users', creator_id=u1.id)
        g2 = Group(name='Test Group Other Users', creator_id=u1.id)
        db.session.add_all([g1, g2])
        db.session.commit()
        self._join_group(u1, g1)
        self._join_group(u2, g1)
        self._join_group(u1, g2)
        self._join_group(u3, g2)
        db.session.commit()
        recommendations_dict = get_recommendations(u1.id, limit_users=5)
        recommended_user_list = recommendations_dict.get('users', [])
        recommended_usernames = [r.username for r in recommended_user_list]
        self.assertIn(u2.username, recommended_usernames)
        self.assertIn(u3.username, recommended_usernames)
        self.assertNotIn(u1.username, recommended_usernames)
        self.assertNotIn(u4.username, recommended_usernames)

    def test_recommend_users_already_following(self):
        u1 = self._create_user('target_following_usr', 'target_following_usr')
        u2 = self._create_user('already_followed_mutual_usr', 'already_followed_mutual_usr')
        u3 = self._create_user('mutual_for_followed_usr', 'mutual_for_followed_usr')
        db.session.add_all([u1, u2, u3])
        db.session.commit()
        u1.follow(u2)
        u1.follow(u3)
        u3.follow(u2)
        db.session.commit()
        recommendations_dict = get_recommendations(u1.id, limit_users=5)
        recommended_user_list = recommendations_dict.get('users', [])
        recommended_usernames = [r.username for r in recommended_user_list]
        self.assertNotIn(u2.username, recommended_usernames)

    # --- Post Recommendation Tests ---
    def test_recommend_posts_based_on_liked_hashtags(self):
        user1 = self._create_user('post_rec_target', 'prt') # Target user
        user2 = self._create_user('post_author1', 'pa1')
        user3 = self._create_user('post_author2', 'pa2')
        user4 = self._create_user('post_author3', 'pa3')
        db.session.add_all([user1, user2, user3, user4])
        db.session.commit()

        post1 = self._create_post(user2, body="Post with hashtag1", hashtags=['hashtag1'])
        self._like_post(user1, post1) # user1 likes post1

        post2 = self._create_post(user3, body="Recommended post with hashtag1", hashtags=['hashtag1'])
        post3 = self._create_post(user4, body="Other post with hashtag2", hashtags=['hashtag2'])

        recommendations_dict = get_recommendations(user1.id, limit_posts=5)
        recommended_posts = recommendations_dict.get('posts', [])
        recommended_post_ids = [p.id for p in recommended_posts]

        self.assertIn(post2.id, recommended_post_ids, "Post2 with shared liked hashtag should be recommended")
        self.assertNotIn(post1.id, recommended_post_ids, "Post1 (liked by user) should not be re-recommended")
        self.assertNotIn(post3.id, recommended_post_ids, "Post3 with unrelated hashtag should not be recommended")

    def test_recommend_posts_exclusion_of_authored_and_interacted(self):
        user1 = self._create_user('post_excl_target', 'pet') # Target
        user2 = self._create_user('post_excl_author_liked', 'peal')
        user3 = self._create_user('post_excl_author_commented', 'peac')
        user4 = self._create_user('post_excl_author_rec', 'pear')
        db.session.add_all([user1, user2, user3, user4])
        db.session.commit()

        post_authored = self._create_post(user1, body="Authored post", hashtags=['common_hashtag'])
        post_liked = self._create_post(user2, body="Liked post", hashtags=['common_hashtag'])
        self._like_post(user1, post_liked)
        post_commented = self._create_post(user3, body="Commented post", hashtags=['common_hashtag'])
        self._comment_on_post(user1, post_commented)
        post_recommended = self._create_post(user4, body="Truly recommended post", hashtags=['common_hashtag'])

        recommendations_dict = get_recommendations(user1.id, limit_posts=5)
        recommended_posts = recommendations_dict.get('posts', [])
        recommended_post_ids = [p.id for p in recommended_posts]

        self.assertIn(post_recommended.id, recommended_post_ids)
        self.assertNotIn(post_authored.id, recommended_post_ids)
        self.assertNotIn(post_liked.id, recommended_post_ids)
        self.assertNotIn(post_commented.id, recommended_post_ids)

    def test_recommend_posts_limit(self):
        user1 = self._create_user('post_limit_target', 'plt')
        authors = [self._create_user(f'post_limit_author{i}', f'pla{i}') for i in range(6)]
        db.session.add_all([user1] + authors)
        db.session.commit()

        # User1 likes a post with 'limit_hashtag' to trigger recommendations
        trigger_post_author = self._create_user('trigger_author', 'ta')
        db.session.add(trigger_post_author)
        db.session.commit()
        trigger_post = self._create_post(trigger_post_author, body="Trigger post", hashtags=['limit_hashtag'])
        self._like_post(user1, trigger_post)

        for i in range(6):
            self._create_post(authors[i], body=f"Post {i} for limit test", hashtags=['limit_hashtag'])

        # Default limit for posts is currently 5 in get_recommendations if not specified
        recommendations_dict = get_recommendations(user1.id) # Use default limits
        recommended_posts = recommendations_dict.get('posts', [])
        self.assertEqual(len(recommended_posts), 5) # Assuming default limit is 5

    # --- Group Recommendation Tests ---
    def test_recommend_groups_based_on_liked_hashtags(self):
        user1 = self._create_user('group_rec_target_ht', 'grth')
        post_author = self._create_user('group_post_author_ht', 'gpaht')
        group_creator1 = self._create_user('group_creator1_ht', 'gc1ht')
        group_creator2 = self._create_user('group_creator2_ht', 'gc2ht')
        db.session.add_all([user1, post_author, group_creator1, group_creator2])
        db.session.commit()

        post_liked = self._create_post(post_author, body="User's liked post", hashtags=['group_interest_hashtag'])
        self._like_post(user1, post_liked)

        group1 = Group(name="Hashtag Group 1", creator_id=group_creator1.id)
        group2 = Group(name="Hashtag Group 2", creator_id=group_creator2.id)
        db.session.add_all([group1, group2])
        db.session.commit()

        # Add post with 'group_interest_hashtag' to group1
        self._create_post(post_author, body="Post in Group1 with relevant hashtag", group=group1, hashtags=['group_interest_hashtag'])
        # Add post with different hashtag to group2
        self._create_post(post_author, body="Post in Group2 with other hashtag", group=group2, hashtags=['other_hashtag'])

        recommendations_dict = get_recommendations(user1.id, limit_groups=5)
        recommended_groups = recommendations_dict.get('groups', [])
        recommended_group_ids = [g.id for g in recommended_groups]

        self.assertIn(group1.id, recommended_group_ids)
        self.assertNotIn(group2.id, recommended_group_ids)

    def test_recommend_groups_based_on_followed_users_groups(self):
        user1 = self._create_user('group_rec_target_follow', 'grtf') # Target
        user2_followed = self._create_user('followed_user_joins_group', 'fujg')
        group_creator = self._create_user('group_creator_follow', 'gcf')
        db.session.add_all([user1, user2_followed, group_creator])
        db.session.commit()

        user1.follow(user2_followed)

        group1 = Group(name="Followed User's Group", creator_id=group_creator.id)
        group2 = Group(name="Unrelated Group", creator_id=group_creator.id)
        db.session.add_all([group1, group2])
        db.session.commit()

        self._join_group(user2_followed, group1) # user2_followed joins group1

        recommendations_dict = get_recommendations(user1.id, limit_groups=5)
        recommended_groups = recommendations_dict.get('groups', [])
        recommended_group_ids = [g.id for g in recommended_groups]

        self.assertIn(group1.id, recommended_group_ids)
        self.assertNotIn(group2.id, recommended_group_ids)

    def test_recommend_groups_exclusion_of_joined_groups(self):
        user1 = self._create_user('group_excl_target', 'get') # Target
        user2_followed = self._create_user('group_excl_followed', 'gef')
        group_creator = self._create_user('group_excl_creator', 'gec')
        db.session.add_all([user1, user2_followed, group_creator])
        db.session.commit()

        group1 = Group(name="Joined Group To Exclude", creator_id=group_creator.id)
        db.session.add(group1)
        db.session.commit()

        self._join_group(user1, group1) # User1 is already a member of group1
        user1.follow(user2_followed)
        self._join_group(user2_followed, group1) # Make group1 recommendable via followed user

        recommendations_dict = get_recommendations(user1.id, limit_groups=5)
        recommended_groups = recommendations_dict.get('groups', [])
        recommended_group_ids = [g.id for g in recommended_groups]

        self.assertNotIn(group1.id, recommended_group_ids)

    def test_recommend_groups_limit(self):
        user1 = self._create_user('group_limit_target', 'glt')
        followed_user = self._create_user('group_limit_followed', 'glf')
        group_creators = [self._create_user(f'gl_creator{i}', f'glc{i}') for i in range(6)]
        db.session.add_all([user1, followed_user] + group_creators)
        db.session.commit()

        user1.follow(followed_user)

        for i in range(6):
            group = Group(name=f"Group Limit Test {i}", creator_id=group_creators[i].id)
            db.session.add(group)
            db.session.commit()
            self._join_group(followed_user, group) # followed_user joins all these groups

        # Default limit for groups is currently 3 in get_recommendations if not specified
        recommendations_dict = get_recommendations(user1.id) # Use default limits
        recommended_groups = recommendations_dict.get('groups', [])
        self.assertEqual(len(recommended_groups), 3) # Assuming default limit is 3

if __name__ == '__main__':
    unittest.main()
