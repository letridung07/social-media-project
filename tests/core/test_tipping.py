import unittest
import json
from unittest.mock import patch, MagicMock

from app import create_app, db
from app.core.models import User, Tip, Notification
from config import TestingConfig

class TippingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create users
        self.tipper = User(username='tipper', email='tipper@example.com')
        self.tipper.set_password('password')
        self.recipient = User(username='recipient', email='recipient@example.com')
        self.recipient.set_password('password')
        db.session.add_all([self.tipper, self.recipient])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email='tipper@example.com', password='password'):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def test_tip_model(self):
        tip = Tip(
            tipper_id=self.tipper.id,
            recipient_id=self.recipient.id,
            amount=1000,
            currency='usd',
            status='succeeded',
            stripe_payment_intent_id='pi_test_123'
        )
        db.session.add(tip)
        db.session.commit()
        self.assertIsNotNone(tip.id)
        self.assertEqual(tip.amount, 1000)
        self.assertEqual(tip.tipper.username, 'tipper')

    @patch('stripe.PaymentIntent.create')
    def test_create_payment_intent_api(self, mock_stripe_create):
        # Mock the Stripe API call
        mock_stripe_create.return_value = MagicMock(
            id='pi_test_123',
            client_secret='pi_test_123_secret_abc'
        )

        self._login()

        response = self.client.post(
            '/api/v1/tip/create-payment-intent',
            json={
                'recipient_id': self.recipient.id,
                'amount': 500, # $5.00 in cents
                'message': 'Great work!'
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('clientSecret', data)
        self.assertEqual(data['clientSecret'], 'pi_test_123_secret_abc')

        # Verify that a pending Tip record was created in the DB
        tip = Tip.query.filter_by(stripe_payment_intent_id='pi_test_123').first()
        self.assertIsNotNone(tip)
        self.assertEqual(tip.status, 'pending')
        self.assertEqual(tip.amount, 500)
        self.assertEqual(tip.tipper_id, self.tipper.id)
        self.assertEqual(tip.recipient_id, self.recipient.id)
        self.assertEqual(tip.message, 'Great work!')

    def test_webhook_payment_intent_succeeded(self):
        # 1. Create a pending Tip record first, as the webhook handler expects it to exist.
        pending_tip = Tip(
            tipper_id=self.tipper.id,
            recipient_id=self.recipient.id,
            amount=1000,
            currency='usd',
            status='pending',
            stripe_payment_intent_id='pi_test_webhook'
        )
        db.session.add(pending_tip)
        db.session.commit()

        # 2. Construct a mock Stripe event payload
        mock_event_payload = {
            "id": "evt_test_webhook",
            "object": "event",
            "api_version": "2020-08-27",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_webhook",
                    "object": "payment_intent",
                    "amount": 1000,
                    "currency": "usd",
                    "status": "succeeded",
                    "metadata": {
                        'type': 'tip'
                    }
                }
            }
        }

        # We need to mock the event construction to bypass signature verification
        with patch('stripe.Webhook.construct_event') as mock_construct_event:
            mock_construct_event.return_value = mock_event_payload

            # 3. Make a POST request to the webhook endpoint
            response = self.client.post(
                '/api/stripe-webhooks',
                data=json.dumps(mock_event_payload),
                content_type='application/json',
                headers={'Stripe-Signature': 'whsec_test_signature'} # Signature is bypassed by mock
            )

        self.assertEqual(response.status_code, 200)

        # 4. Verify the changes in the database
        # Use with_for_update to get the latest state from the DB
        tip = Tip.query.filter_by(stripe_payment_intent_id='pi_test_webhook').first()
        self.assertIsNotNone(tip)
        self.assertEqual(tip.status, 'succeeded')

        # 5. Verify notification was created
        notification = Notification.query.filter_by(recipient_id=self.recipient.id, type='new_tip').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.tipper.id)

if __name__ == '__main__':
    unittest.main(verbosity=2)
