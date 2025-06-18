import unittest
from app import create_app, db
from app.core.models import User, Post, Group, Hashtag, Reaction, Comment, GroupMembership, followers, PRIVACY_PUBLIC
from app.utils.helpers import recommend_posts, recommend_users, recommend_groups, get_recommendations
from datetime import datetime, timezone

class RecommendationsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing') # Ensure you have a 'testing' config
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        # self.client = self.app.test_client() # Good practice, though not used here

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_user(self, username_suffix, email_suffix):
        # Helper to create users with unique usernames and emails
        return User(
            username=f'user_{username_suffix}',
            email=f'user{email_suffix}@example.com',
            password_hash='dummy_password_hash',  # Ensure this meets User model requirements
            profile_visibility=PRIVACY_PUBLIC # Default to public for easier testing unless specified
        )

    def test_recommend_users_no_mutual_no_shared_groups(self):
        u1 = self._create_user('target1', 'target1')
        u2 = self._create_user('other1', 'other1')
        db.session.add_all([u1, u2])
        db.session.commit()

        # recommend_users is not directly exposed by current helpers.py,
        # we test it via get_recommendations
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

        # u1 -> u4
        u1.follow(u4)
        # u4 -> u2, u4 -> u3 (making u2, u3 friends of a friend)
        u4.follow(u2)
        u4.follow(u3)
        db.session.commit()

        recommendations_dict = get_recommendations(u1.id, limit_users=5)
        recommended_user_list = recommendations_dict.get('users', [])
        recommended_usernames = [r.username for r in recommended_user_list]

        self.assertIn(u2.username, recommended_usernames)
        self.assertIn(u3.username, recommended_usernames)
        self.assertNotIn(u1.username, recommended_usernames) # Cannot recommend self
        self.assertNotIn(u4.username, recommended_usernames) # u4 is already followed by u1
        self.assertNotIn(u5.username, recommended_usernames)

    def test_recommend_users_shared_groups(self):
        u1 = self._create_user('target_group', 'target_group')
        u2 = self._create_user('rec_group_member', 'rec_group_member')
        u3 = self._create_user('other_group_member', 'other_group_member') # In a different group with u1
        u4 = self._create_user('no_shared_group_member', 'no_shared_group_member')

        db.session.add_all([u1, u2, u3, u4])
        db.session.commit() # Users must have IDs before being used as creator_id

        g1 = Group(name='Test Group Shared', creator_id=u1.id)
        g2 = Group(name='Test Group Other', creator_id=u1.id)
        db.session.add_all([g1, g2])
        db.session.commit() # Groups must have IDs before memberships

        # u1 and u2 are in g1
        gm1_g1 = GroupMembership(user_id=u1.id, group_id=g1.id)
        gm2_g1 = GroupMembership(user_id=u2.id, group_id=g1.id)

        # u1 and u3 are in g2
        gm1_g2 = GroupMembership(user_id=u1.id, group_id=g2.id)
        gm3_g2 = GroupMembership(user_id=u3.id, group_id=g2.id)

        db.session.add_all([gm1_g1, gm2_g1, gm1_g2, gm3_g2])
        db.session.commit()

        recommendations_dict = get_recommendations(u1.id, limit_users=5)
        recommended_user_list = recommendations_dict.get('users', [])
        recommended_usernames = [r.username for r in recommended_user_list]

        self.assertIn(u2.username, recommended_usernames) # Shared g1
        self.assertIn(u3.username, recommended_usernames) # Shared g2
        self.assertNotIn(u1.username, recommended_usernames)
        self.assertNotIn(u4.username, recommended_usernames)

    def test_recommend_users_already_following(self):
        u1 = self._create_user('target_following', 'target_following')
        u2 = self._create_user('already_followed_mutual', 'already_followed_mutual')
        u3 = self._create_user('mutual_for_followed', 'mutual_for_followed')
        db.session.add_all([u1, u2, u3])
        db.session.commit()

        u1.follow(u2) # u1 already follows u2
        u1.follow(u3) # u1 follows u3 (our mutual connection)
        u3.follow(u2) # u3 also follows u2 (this makes u2 a friend of a friend)
        db.session.commit()

        recommendations_dict = get_recommendations(u1.id, limit_users=5)
        recommended_user_list = recommendations_dict.get('users', [])
        recommended_usernames = [r.username for r in recommended_user_list]

        # u2 should not be recommended because u1 already follows u2,
        # even though u2 is a "friend of a friend" via u3.
        self.assertNotIn(u2.username, recommended_usernames)

    def test_recommend_posts_basic(self):
        # This will test the 'posts' part of get_recommendations()
        self.skipTest("Post recommendation tests not yet implemented.")

    def test_recommend_groups_basic(self):
        # This will test the 'groups' part of get_recommendations()
        self.skipTest("Group recommendation tests not yet implemented.")

if __name__ == '__main__':
    unittest.main()
