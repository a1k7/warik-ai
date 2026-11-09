from app.core.security import create_access_token, hash_password
from app.models import User
from app.models.booking import Booking


def test_booking_confirmation_refuses_to_fake_payment(client, db_session):
    user = User(
        email="booking-safety@example.com",
        name="Booking Safety Test",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(subject=str(user.id))

    response = client.post(
        "/api/bookings/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "booking_type": "flight",
            "item_name": "Mumbai to Goa",
            "amount": 5000,
        },
    )
    assert response.status_code == 501
    assert "No payment has been processed" in response.json()["detail"]
    assert db_session.query(Booking).count() == 0
