from app import create_app, db
from app.core.models import VirtualGood

def set_point_prices():
    app = create_app()
    with app.app_context():
        items_to_update = [
            {"name": "First Steps Title", "type": "title", "points": 50},
            {"name": "Community Contributor", "type": "title", "points": 150},
            {"name": "Profile Frame - Gold", "type": "profile_frame", "points": 250},
            # Add more items here if needed
        ]

        for item_data in items_to_update:
            item = VirtualGood.query.filter_by(name=item_data["name"], type=item_data["type"]).first()
            if item:
                item.point_price = item_data["points"]
                db.session.add(item)
                print(f"Updated '{item.name}' (type: {item.type}) with point_price {item_data['points']}.")
            else:
                # Optionally, create the item if it doesn't exist
                print(f"VirtualGood '{item_data['name']}' (type: {item_data['type']}) not found. Skipping or creating...")
                # Example: Create if not found
                # new_item = VirtualGood(
                # name=item_data["name"],
                # description=f"{item_data['name']} - purchasable with points.", # Add a default description
                # price=0, # Assuming 0 for currency price if it's mainly a points item
                # currency="USD",
                # type=item_data["type"],
                # point_price=item_data["points"],
                # is_active=True
                # )
                # db.session.add(new_item)
                # print(f"Created '{new_item.name}' (type: {new_item.type}) with point_price {item_data['points']}.")

        try:
            db.session.commit()
            print("Successfully committed changes to the database.")
        except Exception as e:
            db.session.rollback()
            print(f"Error committing changes: {e}")

if __name__ == '__main__':
    # This script is intended to be run in an environment where the Flask app context can be established.
    # For example, using `flask shell < update_virtual_good_point_prices.py` (if input redirection works)
    # or by manually running these commands in a flask shell, or by creating a proper CLI command.
    print("Starting virtual good point price update script...")
    set_point_prices()
    print("Script finished.")
