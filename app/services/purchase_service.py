from typing import TYPE_CHECKING
from app import db
# User is now only imported for type hinting, VirtualGood and UserVirtualGood are used at runtime
from app.core.models import VirtualGood, UserVirtualGood
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app
# datetime might still be needed if other functions use it, but timezone was for the local helper.
# For now, let's assume it's not needed by other functions in this file. If it is, it can be re-added.
# from datetime import datetime
from app.utils.helpers import get_current_utc # Import the centralized helper

if TYPE_CHECKING:
    from app.core.models import User # User for type hinting

def process_virtual_good_purchase(user: 'User', virtual_good: VirtualGood) -> dict: # Use string literal for User hint
    """
    Processes the purchase of a virtual good for a user.

    Args:
        user: The User object making the purchase.
        virtual_good: The VirtualGood object being purchased.

    Returns:
        A dictionary containing:
        - "success": bool, True if the purchase (UserVirtualGood creation) was successful.
        - "status_key": str, a key indicating the outcome (e.g., "purchase_successful", "item_not_active", "already_owned", "purchase_failed_db_error").
        - "message": str, a user-friendly message.
        - "user_virtual_good": UserVirtualGood object if successful and applicable, else None.
        - "error": str, error details if any.
    """
    if not virtual_good.is_active:
        return {
            "success": False,
            "status_key": "item_not_active",
            "message": f"'{virtual_good.name}' is currently not available for purchase.",
            "user_virtual_good": None
        }

    # Placeholder for payment/points deduction logic.
    # This function assumes that payment/points have already been successfully processed
    # or are handled by the calling route before this function is invoked.
    # For example:
    # if not user.can_afford(virtual_good.price, virtual_good.currency):
    #     return {"success": False, "status_key": "insufficient_funds", "message": "Insufficient funds."}
    # user.deduct_funds(virtual_good.price, virtual_good.currency)

    existing_uvg = UserVirtualGood.query.filter_by(
        user_id=user.id,
        virtual_good_id=virtual_good.id
    ).first()

    if virtual_good.type == 'title':
        if existing_uvg:
            return {
                "success": False,
                "status_key": "already_owned",
                "message": f"You already own the title: '{virtual_good.name}'.",
                "user_virtual_good": existing_uvg
            }
        # For titles, quantity is always 1, and duplicates are not allowed by the unique constraint.
        # The check above handles friendly messaging for this.
    elif existing_uvg:
        # For non-title consumable goods, one might increment quantity or handle differently.
        # For this example, let's assume non-title goods that are not stackable also follow "already_owned" logic
        # if a UserVirtualGood entry already exists. This simplifies based on current model constraints.
        # If stackable items were a feature, `existing_uvg.quantity += 1` might be here.
        return {
            "success": False,
            "status_key": "already_owned_generic", # Or a more specific key if needed
            "message": f"You already have '{virtual_good.name}'. (Further action for this item type might be different).",
            "user_virtual_good": existing_uvg
        }


    try:
        new_user_vg = UserVirtualGood(
            user_id=user.id,
            virtual_good_id=virtual_good.id,
            quantity=1, # Default for new acquisition
            purchase_date=get_current_utc(), # Use helper
            is_equipped=False # Titles and other items are not equipped by default on purchase
        )
        db.session.add(new_user_vg)
        db.session.commit()
        current_app.logger.info(f"UserVirtualGood created for user {user.id} and virtual_good {virtual_good.id}")
        return {
            "success": True,
            "status_key": "purchase_successful",
            "message": f"'{virtual_good.name}' acquired successfully!",
            "user_virtual_good": new_user_vg
        }
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(
            f"Database error processing purchase of '{virtual_good.name}' for user {user.id}: {e}",
            exc_info=True
        )
        return {
            "success": False,
            "status_key": "purchase_failed_db_error",
            "message": "A database error occurred while processing your purchase. Please try again.",
            "user_virtual_good": None,
            "error": str(e)
        }
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Unexpected error processing purchase of '{virtual_good.name}' for user {user.id}: {e}",
            exc_info=True
        )
        return {
            "success": False,
            "status_key": "purchase_failed_unexpected_error",
            "message": "An unexpected error occurred. Please try again.",
            "user_virtual_good": None,
            "error": str(e)
        }
