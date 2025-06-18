import random

class MockModerationService:
    """
    A mock moderation service that provides dummy scores for text content.
    """
    CATEGORIES = [
        "TOXICITY",
        "SEVERE_TOXICITY",
        "HATE_SPEECH",
        "SPAM",
        "NSFW",
        "PROFANITY", # Added as per common use cases
        "INSULT",    # Added as per common use cases
    ]

    # Keywords that might trigger higher scores for certain categories
    KEYWORDS_MAP = {
        "TOXICITY": ["idiot", "stupid", "dumb", "jerk", "garbage"],
        "SEVERE_TOXICITY": ["kill yourself", "i hate you all", "despicable"],
        "HATE_SPEECH": ["racist_slur", "misogynistic_comment", "homophobic_remark"], # Replace with actual examples carefully
        "SPAM": ["buy now", "free money", "click here", "limited time offer", "subscribe"],
        "NSFW": ["porn", "sex", "nude", "xxx"],
        "PROFANITY": ["fuck", "shit", "bitch", "asshole"],
        "INSULT": ["loser", "pathetic", "ugly", "worthless"]
    }

    def moderate_text(self, text_content: str) -> dict:
        """
        Analyzes text content and returns mock moderation scores.

        Args:
            text_content: The text to analyze.

        Returns:
            A dictionary with moderation categories and their scores (0.0 to 1.0).
        """
        scores = {category: 0.0 for category in self.CATEGORIES}
        text_lower = text_content.lower()

        # Basic keyword checking
        for category, keywords in self.KEYWORDS_MAP.items():
            for keyword in keywords:
                if keyword in text_lower:
                    # Assign a higher score if a keyword is found
                    scores[category] = max(scores[category], round(random.uniform(0.6, 0.95), 2))
                    # For SEVERE_TOXICITY, HATE_SPEECH, make it very high if keyword matches
                    if category in ["SEVERE_TOXICITY", "HATE_SPEECH"]:
                         scores[category] = round(random.uniform(0.85, 0.99), 2)


        # Introduce some randomness for other categories if no keywords matched
        for category in self.CATEGORIES:
            if scores[category] == 0.0: # Only if not already set by keyword
                # Simulate different scenarios: mostly low scores, occasional medium, rare high
                rand_val = random.random()
                if rand_val < 0.7: # 70% chance of low score
                    scores[category] = round(random.uniform(0.0, 0.2), 2)
                elif rand_val < 0.9: # 20% chance of medium score
                    scores[category] = round(random.uniform(0.2, 0.6), 2)
                else: # 10% chance of high score (could be a flag)
                    scores[category] = round(random.uniform(0.6, 0.85), 2)

        # Specific test cases for workflow paths:
        if "test_allow_text" in text_lower:
            return {category: 0.1 for category in self.CATEGORIES}
        elif "test_flag_text" in text_lower:
            scores = {category: 0.1 for category in self.CATEGORIES}
            scores["TOXICITY"] = 0.75 # Flag score
            return scores
        elif "test_block_severe_text" in text_lower:
            scores = {category: 0.1 for category in self.CATEGORIES}
            scores["SEVERE_TOXICITY"] = 0.92 # Block score for severe category
            return scores
        elif "test_block_general_text" in text_lower: # For general high toxicity
            scores = {category: 0.1 for category in self.CATEGORIES}
            scores["TOXICITY"] = 0.98 # Block score for general category
            return scores
        elif "test_hate_speech_block_text" in text_lower:
            scores = {category: 0.1 for category in self.CATEGORIES}
            scores["HATE_SPEECH"] = 0.95 # Block score for hate speech
            return scores

        return scores

# Global instance or factory function
_moderation_service_instance = None

def get_moderation_service():
    """
    Returns a singleton instance of the MockModerationService.
    """
    global _moderation_service_instance
    if _moderation_service_instance is None:
        _moderation_service_instance = MockModerationService()
    return _moderation_service_instance

# Example Usage (can be removed or kept for testing)
if __name__ == "__main__":
    service = get_moderation_service()

    print("--- Standard Moderation ---")
    test_text_1 = "This is a perfectly fine and lovely comment."
    print(f"'{test_text_1}': {service.moderate_text(test_text_1)}")

    test_text_2 = "You are such an idiot, this is garbage!"
    print(f"'{test_text_2}': {service.moderate_text(test_text_2)}")

    test_text_3 = "I want to buy now, this is a limited time offer just for you, click here!"
    print(f"'{test_text_3}': {service.moderate_text(test_text_3)}")

    test_text_4 = "This is a test_allow_text example."
    print(f"'{test_text_4}': {service.moderate_text(test_text_4)}")

    test_text_5 = "This is a test_flag_text example, it's a bit toxic."
    print(f"'{test_text_5}': {service.moderate_text(test_text_5)}")

    test_text_6 = "This is a test_block_severe_text example, it's severely toxic."
    print(f"'{test_text_6}': {service.moderate_text(test_text_6)}")

    test_text_7 = "This is a test_block_general_text example with high toxicity."
    print(f"'{test_text_7}': {service.moderate_text(test_text_7)}")

    test_text_8 = "This is a test_hate_speech_block_text with racist_slur."
    print(f"'{test_text_8}': {service.moderate_text(test_text_8)}")

    test_text_9 = "What the fuck is this shit?"
    print(f"'{test_text_9}': {service.moderate_text(test_text_9)}")

    print("\n--- Testing specific keyword 'kill yourself' (SEVERE_TOXICITY) ---")
    severe_text = "You should kill yourself immediately."
    print(f"'{severe_text}': {service.moderate_text(severe_text)}")

    print("\n--- Testing specific keyword for NSFW ---")
    nsfw_text = "Let's watch some porn tonight."
    print(f"'{nsfw_text}': {service.moderate_text(nsfw_text)}")

    print("\n--- Testing general non-keyword high random score possibility ---")
    # This type of text has a small chance to get higher scores randomly
    # if no keywords are matched.
    # Run multiple times to see variation if needed.
    mystery_text = "The sky is blue and the grass is green."
    for i in range(3):
        print(f"'{mystery_text}' (Attempt {i+1}): {service.moderate_text(mystery_text)}")
