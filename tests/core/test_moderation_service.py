import unittest
from app.services.moderation_service import MockModerationService, get_moderation_service

class TestMockModerationService(unittest.TestCase):

    def setUp(self):
        # Ensure we get a fresh service instance for each test if needed,
        # though for MockModerationService, its state doesn't change between calls in a way that affects these tests.
        self.service = get_moderation_service()
        # Or self.service = MockModerationService() if get_moderation_service() has complex global state.
        # For this service, direct instantiation or get_moderation_service() should be fine.

    def test_get_moderation_service_singleton(self):
        service1 = get_moderation_service()
        service2 = get_moderation_service()
        self.assertIs(service1, service2, "get_moderation_service() should return a singleton instance.")

    def test_allowed_text(self):
        text = "This is a perfectly fine and lovely comment."
        results = self.service.moderate_text(text)
        self.assertIsInstance(results, dict)
        for category in self.service.CATEGORIES:
            self.assertIn(category, results)
            # For generally allowed text, scores should be low, but randomness exists.
            # The "test_allow_text" provides a deterministic way.

        deterministic_text = "test_allow_text"
        results_deterministic = self.service.moderate_text(deterministic_text)
        for category in self.service.CATEGORIES:
            self.assertEqual(results_deterministic[category], 0.1, f"Category {category} should be 0.1 for 'test_allow_text'")

    def test_flagged_text_deterministic(self):
        text = "test_flag_text example, it's a bit toxic."
        results = self.service.moderate_text(text)
        self.assertEqual(results["TOXICITY"], 0.75)
        # Other categories should be low for this specific test case
        for category in self.service.CATEGORIES:
            if category != "TOXICITY":
                self.assertEqual(results[category], 0.1, f"Category {category} should be 0.1 for 'test_flag_text'")

    def test_block_severe_text_deterministic(self):
        text = "test_block_severe_text example, it's severely toxic."
        results = self.service.moderate_text(text)
        self.assertEqual(results["SEVERE_TOXICITY"], 0.92)
        for category in self.service.CATEGORIES:
            if category != "SEVERE_TOXICITY":
                self.assertEqual(results[category], 0.1, f"Category {category} should be 0.1 for 'test_block_severe_text'")

    def test_block_general_text_deterministic(self):
        text = "test_block_general_text example with high toxicity."
        results = self.service.moderate_text(text)
        self.assertEqual(results["TOXICITY"], 0.98)
        for category in self.service.CATEGORIES:
            if category != "TOXICITY":
                self.assertEqual(results[category], 0.1, f"Category {category} should be 0.1 for 'test_block_general_text'")

    def test_hate_speech_block_text_deterministic(self):
        text = "test_hate_speech_block_text with some bad words."
        results = self.service.moderate_text(text)
        self.assertEqual(results["HATE_SPEECH"], 0.95)
        for category in self.service.CATEGORIES:
            if category != "HATE_SPEECH":
                self.assertEqual(results[category], 0.1, f"Category {category} should be 0.1 for 'test_hate_speech_block_text'")

    def test_keyword_trigger_toxicity(self):
        text = "You are such an idiot, this is garbage!"
        results = self.service.moderate_text(text)
        self.assertGreaterEqual(results["TOXICITY"], 0.6)
        self.assertLessEqual(results["TOXICITY"], 0.95)

    def test_keyword_trigger_severe_toxicity(self):
        text = "I will kill yourself, this is truly despicable." # "kill yourself" is a keyword
        results = self.service.moderate_text(text)
        self.assertGreaterEqual(results["SEVERE_TOXICITY"], 0.85)
        self.assertLessEqual(results["SEVERE_TOXICITY"], 0.99)

    def test_keyword_trigger_spam(self):
        text = "buy now for free money, click here for a limited time offer!"
        results = self.service.moderate_text(text)
        self.assertGreaterEqual(results["SPAM"], 0.6)
        self.assertLessEqual(results["SPAM"], 0.95)

    def test_keyword_trigger_nsfw(self):
        text = "Let's watch some nude porn xxx."
        results = self.service.moderate_text(text)
        self.assertGreaterEqual(results["NSFW"], 0.6)
        self.assertLessEqual(results["NSFW"], 0.95)

    def test_keyword_trigger_profanity(self):
        text = "What the fuck is this shit?"
        results = self.service.moderate_text(text)
        self.assertGreaterEqual(results["PROFANITY"], 0.6)
        self.assertLessEqual(results["PROFANITY"], 0.95)

    def test_keyword_trigger_insult(self):
        text = "You are a pathetic loser and completely worthless."
        results = self.service.moderate_text(text)
        self.assertGreaterEqual(results["INSULT"], 0.6)
        self.assertLessEqual(results["INSULT"], 0.95)

    def test_all_categories_present(self):
        text = "Some random text for testing."
        results = self.service.moderate_text(text)
        for category in self.service.CATEGORIES:
            self.assertIn(category, results, f"Category {category} is missing from results.")
            self.assertIsInstance(results[category], float, f"Score for {category} should be a float.")
            self.assertGreaterEqual(results[category], 0.0, f"Score for {category} should be >= 0.0.")
            self.assertLessEqual(results[category], 1.0, f"Score for {category} should be <= 1.0.")

if __name__ == '__main__':
    unittest.main()
