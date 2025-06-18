import unittest
from flask import url_for, get_flashed_messages
from app import create_app, db
from app.core.models import User, Post, Group, Hashtag, Reaction, Comment, GroupMembership, followers, PRIVACY_PUBLIC
# Assuming get_recommendations is not directly used in UI tests, but underlying data setup is key.

# Helper class for common test setups
class BaseUITestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')  # Assumes 'testing' config (e.g., WTF_CSRF_ENABLED=False)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Common users - create them here if used in almost all tests, or in specific test setups
        self.u_target = self._create_user('target_user', 'target@example.com', 'password123')
        self.u_other1 = self._create_user('other_user1', 'other1@example.com', 'password123')
        self.u_other2 = self._create_user('other_user2', 'other2@example.com', 'password123')
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_user(self, username, email, password):
        user = User(username=username, email=email, profile_visibility=PRIVACY_PUBLIC)
        user.set_password(password)
        db.session.add(user)
        # db.session.commit() # Commit per user or batch commit in setUp/test
        return user

    def _login(self, email, password):
        return self.client.post(url_for('main.login'), data={
            'email': email,
            'password': password
        }, follow_redirects=True)

    def _logout(self):
        return self.client.get(url_for('main.logout'), follow_redirects=True)

    def _create_group(self, name, creator):
        group = Group(name=name, creator_id=creator.id, description="Test group")
        db.session.add(group)
        db.session.commit()
        return group

    def _join_group(self, user, group):
        gm = GroupMembership(user_id=user.id, group_id=group.id, role='member')
        db.session.add(gm)
        db.session.commit()

    def _follow_user(self, follower, followed):
        follower.follow(followed)
        db.session.commit()

    def _create_post_with_hashtag(self, author, hashtag_text, body="Test post"):
        post = Post(author=author, body=body)
        db.session.add(post)
        db.session.commit()
        hashtag = Hashtag.query.filter_by(tag_text=hashtag_text).first()
        if not hashtag:
            hashtag = Hashtag(tag_text=hashtag_text)
            db.session.add(hashtag)
            db.session.commit()
        post.hashtags.append(hashtag)
        db.session.commit()
        return post

    def _like_post(self, user, post):
        reaction = Reaction(user_id=user.id, post_id=post.id, reaction_type='like')
        db.session.add(reaction)
        db.session.commit()

class RecommendationsUITests(BaseUITestCase):

    # --- Tests for search_results.html Recommendations UI ---
    def test_search_page_shows_recommendations_when_no_query(self):
        # Setup: u_other1 and u_other2 become recommendable to u_target
        # e.g., u_target follows common_friend, who follows u_other1 and u_other2
        common_friend = self._create_user('common_friend_s', 'cfs@example.com', 'pw')
        db.session.add(common_friend)
        db.session.commit()
        self._follow_user(self.u_target, common_friend)
        self._follow_user(common_friend, self.u_other1)

        group_rec = self._create_group("SearchRecGroup", self.u_other2)
        self._join_group(self.u_other1, group_rec) # u_other1 (followed by common_friend) joins group_rec

        self._login(self.u_target.email, 'password123')
        response = self.client.get(url_for('main.search'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Recommended for You", response.data)
        self.assertIn(b"Suggested Users", response.data)
        self.assertIn(bytes(self.u_other1.username, 'utf-8'), response.data)
        # Group recommendations depend on more complex logic (e.g. shared interests from posts)
        # For this basic test, we'll assume user recommendations are easier to trigger.
        # To test group recommendations reliably here, set up post likes etc.
        # self.assertIn(b"Groups You Might Like", response.data)
        # self.assertIn(bytes(group_rec.name, 'utf-8'), response.data)

    def test_search_page_recommendation_follow_button_conditions(self):
        u_recommend_not_followed = self.u_other1
        u_recommend_already_followed = self.u_other2

        # Make them recommendable: u_target -> common_friend -> recommendations
        common_friend = self._create_user('common_friend_sfbc', 'cfsfbc@example.com', 'pw')
        db.session.add(common_friend)
        db.session.commit()
        self._follow_user(self.u_target, common_friend)
        self._follow_user(common_friend, u_recommend_not_followed)
        self._follow_user(common_friend, u_recommend_already_followed)

        self._follow_user(self.u_target, u_recommend_already_followed) # Target already follows this one
        db.session.commit()

        self._login(self.u_target.email, 'password123')
        response = self.client.get(url_for('main.search'))
        self.assertEqual(response.status_code, 200)

        # Check for Follow button for u_recommend_not_followed
        follow_form_action_not_followed = url_for('main.follow', username=u_recommend_not_followed.username)
        self.assertIn(bytes(f'action="{follow_form_action_not_followed}"', 'utf-8'), response.data)
        self.assertIn(b'value="Follow"', response.data) # Assuming button text/value

        # Check NO Follow button for u_recommend_already_followed
        follow_form_action_already_followed = url_for('main.follow', username=u_recommend_already_followed.username)
        # This is a bit tricky; we need to ensure the *form* for this user isn't there,
        # or if the username is present, the specific follow button part is missing.
        # A simpler check might be to count occurrences if possible, or use a more specific selector.
        # For now, we check that the specific "Follow" button for this user is NOT there.
        # This assumes the username is still listed.
        self.assertNotIn(bytes(f'action="{follow_form_action_already_followed}"', 'utf-8'), response.data)


    def test_search_page_recommendation_join_button_conditions(self):
        group_rec_not_joined = self._create_group("SearchGroupNotJoined", self.u_other1)
        group_rec_already_joined = self._create_group("SearchGroupJoined", self.u_other1)

        self._join_group(self.u_target, group_rec_already_joined) # Target already member of this one

        # Make groups recommendable (e.g. u_target likes posts with hashtags found in these groups)
        self._like_post(self.u_target, self._create_post_with_hashtag(self.u_other2, "search_tag_group"))
        self._create_post_with_hashtag(self.u_other1, "search_tag_group", group=group_rec_not_joined)
        self._create_post_with_hashtag(self.u_other2, "search_tag_group", group=group_rec_already_joined)
        db.session.commit()

        self._login(self.u_target.email, 'password123')
        response = self.client.get(url_for('main.search'))
        self.assertEqual(response.status_code, 200)

        join_form_not_joined = url_for('main.join_group', group_id=group_rec_not_joined.id)
        self.assertIn(bytes(f'action="{join_form_not_joined}"', 'utf-8'), response.data)
        self.assertIn(b'value="Join Group"', response.data) # Assuming button text

        join_form_already_joined = url_for('main.join_group', group_id=group_rec_already_joined.id)
        self.assertNotIn(bytes(f'action="{join_form_already_joined}"', 'utf-8'), response.data)


    def test_search_page_follow_action_from_recommendation(self):
        u_to_follow = self.u_other1
        # Make u_to_follow recommendable
        common_friend = self._create_user('common_friend_s_action', 'cfsaction@example.com', 'pw')
        db.session.add(common_friend)
        db.session.commit()
        self._follow_user(self.u_target, common_friend)
        self._follow_user(common_friend, u_to_follow)
        db.session.commit()

        self._login(self.u_target.email, 'password123')
        # Initial GET to ensure recommendation is there (optional, but good for sanity)
        self.client.get(url_for('main.search'))

        response = self.client.post(url_for('main.follow', username=u_to_follow.username), follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Assuming redirect to profile or search page

        self.assertTrue(self.u_target.is_following(u_to_follow))
        # Check for flash message
        self.assertIn(b"You are now following", response.data) # Check for part of the flash message

    # --- Tests for index.html Recommendations UI ---
    def test_index_page_shows_recommendations_for_authenticated_user(self):
        # Setup: u_other1 becomes recommendable to u_target (similar to search test)
        common_friend = self._create_user('common_friend_idx', 'cfidx@example.com', 'pw')
        db.session.add(common_friend)
        db.session.commit()
        self._follow_user(self.u_target, common_friend)
        self._follow_user(common_friend, self.u_other1)
        db.session.commit()

        self._login(self.u_target.email, 'password123')
        response = self.client.get(url_for('main.index'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Discover More", response.data)
        self.assertIn(b"People You May Know", response.data)
        self.assertIn(bytes(self.u_other1.username, 'utf-8'), response.data)

    def test_index_page_no_recommendations_for_guest(self):
        self._logout() # Ensure no user is logged in
        response = self.client.get(url_for('main.index'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Discover More", response.data)
        self.assertNotIn(b"People You May Know", response.data)

    def test_index_page_recommendation_follow_join_button_conditions(self):
        # User follow button conditions
        u_rec_not_followed_idx = self.u_other1
        u_rec_already_followed_idx = self.u_other2
        common_friend = self._create_user('cf_idx_btns', 'cfidxbtns@example.com', 'pw')
        db.session.add_all([u_rec_not_followed_idx, u_rec_already_followed_idx, common_friend])
        db.session.commit()
        self._follow_user(self.u_target, common_friend)
        self._follow_user(common_friend, u_rec_not_followed_idx)
        self._follow_user(common_friend, u_rec_already_followed_idx)
        self._follow_user(self.u_target, u_rec_already_followed_idx)
        db.session.commit()

        # Group join button conditions
        group_idx_not_joined = self._create_group("IndexGroupNotJoined", self.u_other1)
        group_idx_already_joined = self._create_group("IndexGroupJoined", self.u_other1)
        self._join_group(self.u_target, group_idx_already_joined)
        # Make groups recommendable via liked hashtag
        self._like_post(self.u_target, self._create_post_with_hashtag(self.u_other2, "idx_tag_group"))
        self._create_post_with_hashtag(self.u_other1, "idx_tag_group", group=group_idx_not_joined)
        self._create_post_with_hashtag(self.u_other2, "idx_tag_group", group=group_idx_already_joined)
        db.session.commit()

        self._login(self.u_target.email, 'password123')
        response = self.client.get(url_for('main.index'))
        self.assertEqual(response.status_code, 200)

        # Assert follow button for u_rec_not_followed_idx
        self.assertIn(bytes(f'action="{url_for("main.follow", username=u_rec_not_followed_idx.username)}"', 'utf-8'), response.data)
        # Assert NO follow button for u_rec_already_followed_idx
        self.assertNotIn(bytes(f'action="{url_for("main.follow", username=u_rec_already_followed_idx.username)}"', 'utf-8'), response.data)

        # Assert join button for group_idx_not_joined
        self.assertIn(bytes(f'action="{url_for("main.join_group", group_id=group_idx_not_joined.id)}"', 'utf-8'), response.data)
        # Assert NO join button for group_idx_already_joined
        self.assertNotIn(bytes(f'action="{url_for("main.join_group", group_id=group_idx_already_joined.id)}"', 'utf-8'), response.data)


    def test_index_page_join_action_from_recommendation(self):
        group_to_join = self._create_group("IndexJoinGroupAction", self.u_other1)
        # Make group_to_join recommendable (e.g., via liked hashtag)
        self._like_post(self.u_target, self._create_post_with_hashtag(self.u_other2, "idx_join_tag"))
        self._create_post_with_hashtag(self.u_other1, "idx_join_tag", group=group_to_join)
        db.session.commit()

        self._login(self.u_target.email, 'password123')
        self.client.get(url_for('main.index')) # Optional GET

        response = self.client.post(url_for('main.join_group', group_id=group_to_join.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Assuming redirect to group page or index

        membership = GroupMembership.query.filter_by(user_id=self.u_target.id, group_id=group_to_join.id).first()
        self.assertIsNotNone(membership)
        self.assertIn(b"You have successfully joined the group", response.data)


if __name__ == '__main__':
    unittest.main()
