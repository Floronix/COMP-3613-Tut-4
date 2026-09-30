import pytest
from fastapi.testclient import TestClient

from app.database import get_session


@pytest.fixture
def api_client(test_session):
    from app.main import app

    def override_session():
        yield test_session

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def accounts(api_client, test_session):
    from app.repositories.user import UserRepository
    from app.schemas.user import AdminCreate
    from app.services.auth_service import AuthService
    from app.utilities.security import encrypt_password

    users = UserRepository(test_session)
    auth = AuthService(users)
    alice = auth.register_user("alice", "alice@example.com", "alice-secret")
    bob = auth.register_user("bob", "bob@example.com", "bob-secret")
    staff = users.create(
        AdminCreate(
            username="staff",
            email="staff@example.com",
            password=encrypt_password("staff-secret"),
        )
    )

    def headers(username, password):
        response = api_client.post(
            "/auth", json={"username": username, "password": password}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return {
        "alice": alice,
        "alice_headers": headers("alice", "alice-secret"),
        "bob": bob,
        "bob_headers": headers("bob", "bob-secret"),
        "staff": staff,
        "staff_headers": headers("staff", "staff-secret"),
    }


def _create_game(api_client, staff_headers, *, title="API Test Game", platform="PC"):
    return api_client.post(
        "/games",
        json={"title": title, "rating": "E", "platform": platform, "genre": "Puzzle"},
        headers=staff_headers,
    )


def _create_listing(api_client, customer_headers, game_id):
    return api_client.post(
        "/listings",
        json={"game_id": game_id, "condition": "Good", "price": 8},
        headers=customer_headers,
    )


def test_signup_and_authentication(api_client):
    signup = api_client.post(
        "/signup",
        json={"username": "new-customer", "email": "new@example.com", "password": "secret"},
    )
    assert signup.status_code == 201
    assert signup.json()["username"] == "new-customer"
    assert "password" not in signup.json()

    duplicate = api_client.post(
        "/signup",
        json={"username": "another-name", "email": "new@example.com", "password": "secret"},
    )
    assert duplicate.status_code == 400

    valid_auth = api_client.post(
        "/auth", json={"username": "new-customer", "password": "secret"}
    )
    assert valid_auth.status_code == 200
    assert valid_auth.json()["token_type"] == "bearer"
    assert valid_auth.json()["access_token"]
    invalid_auth = api_client.post(
        "/auth", json={"username": "new-customer", "password": "incorrect"}
    )
    assert invalid_auth.status_code == 400


def test_game_and_listing_routes(api_client, accounts):
    staff_headers = accounts["staff_headers"]
    customer_headers = accounts["alice_headers"]

    assert api_client.post(
        "/games",
        json={"title": "Denied", "rating": "E", "platform": "PC", "genre": "Puzzle"},
    ).status_code == 401
    assert _create_game(api_client, customer_headers, title="Denied").status_code == 403
    game = _create_game(api_client, staff_headers)
    assert game.status_code == 201
    assert game.json()["title"] == "API Test Game"

    assert api_client.post(
        "/listings", json={"game_id": game.json()["id"], "condition": "Good", "price": 8}
    ).status_code == 401
    assert api_client.post(
        "/listings",
        json={"game_id": 999, "condition": "Good", "price": 8},
        headers=customer_headers,
    ).status_code == 404
    assert api_client.post(
        "/listings",
        json={"game_id": game.json()["id"], "condition": "   ", "price": 8},
        headers=customer_headers,
    ).status_code == 422

    listing = _create_listing(api_client, customer_headers, game.json()["id"])
    assert listing.status_code == 201
    assert listing.json()["game_id"] == game.json()["id"]
    assert listing.json()["owner_id"] == accounts["alice"].id
    assert listing.json()["game"]["title"] == "API Test Game"

    filtered = api_client.get("/listings?platform=PC")
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [listing.json()["id"]]
    assert api_client.get("/listings?platform=PS5").json() == []
    assert api_client.get("/listings?platform=invalid").status_code == 422


def test_payment_rental_and_return_routes(api_client, accounts):
    alice_headers = accounts["alice_headers"]
    staff_headers = accounts["staff_headers"]
    game = _create_game(api_client, staff_headers)
    assert game.status_code == 201
    listing = _create_listing(api_client, alice_headers, game.json()["id"])
    assert listing.status_code == 201

    assert api_client.post("/payment", json={"amount": 8}).status_code == 401
    assert api_client.post(
        "/payment", json={"amount": 8}, headers=alice_headers
    ).status_code == 403
    payment = api_client.post(
        "/payment", json={"amount": 8}, headers=staff_headers
    )
    assert payment.status_code == 201
    assert payment.json()["paymentId"] > 0

    rental_payload = {
        "listing_id": listing.json()["id"],
        "customer_id": accounts["alice"].id,
    }
    assert api_client.post("/rentals", json=rental_payload).status_code == 401
    assert api_client.post(
        "/rentals", json={"listing_id": 999, "customer_id": accounts["alice"].id},
        headers=staff_headers,
    ).status_code == 404
    assert api_client.post(
        "/rentals", json=rental_payload, headers=alice_headers
    ).status_code == 403

    rental = api_client.post("/rentals", json=rental_payload, headers=staff_headers)
    assert rental.status_code == 201
    assert rental.json()["listing_id"] == listing.json()["id"]
    unavailable = api_client.post("/rentals", json=rental_payload, headers=staff_headers)
    assert unavailable.status_code == 422

    rental_id = rental.json()["id"]
    assert api_client.put(f"/rentals/{rental_id}", json={"payment_id": payment.json()["paymentId"]}).status_code == 401
    assert api_client.put(
        "/rentals/999", json={"payment_id": payment.json()["paymentId"]}, headers=staff_headers
    ).status_code == 404
    assert api_client.put(
        f"/rentals/{rental_id}", json={"payment_id": 999}, headers=staff_headers
    ).status_code == 404

    returned = api_client.put(
        f"/rentals/{rental_id}",
        json={"payment_id": payment.json()["paymentId"]},
        headers=staff_headers,
    )
    assert returned.status_code == 201
    assert returned.json()["return_date"] is not None
    available_listings = api_client.get("/listings?platform=PC").json()
    assert [item["id"] for item in available_listings] == [listing.json()["id"]]
    assert api_client.put(
        f"/rentals/{rental_id}", json={"payment_id": payment.json()["paymentId"]},
        headers=staff_headers,
    ).status_code == 422


def test_sell_listing_route_enforces_owner_and_active_status(api_client, accounts):
    game = _create_game(api_client, accounts["staff_headers"], title="Sale Game")
    assert game.status_code == 201
    listing = _create_listing(api_client, accounts["alice_headers"], game.json()["id"])
    assert listing.status_code == 201
    sell_url = f"/listings/{listing.json()['id']}/sell"

    assert api_client.post(sell_url).status_code == 401
    assert api_client.post(sell_url, headers=accounts["bob_headers"]).status_code == 403
    sold = api_client.post(sell_url, headers=accounts["alice_headers"])
    assert sold.status_code == 200
    assert sold.json()["availability"] == "sold"
    assert api_client.post(sell_url, headers=accounts["alice_headers"]).status_code == 422
    assert api_client.post(
        "/listings/999/sell", headers=accounts["alice_headers"]
    ).status_code == 404