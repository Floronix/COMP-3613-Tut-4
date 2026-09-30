import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_session
from app.repositories.user import UserRepository
from app.schemas.user import AdminCreate
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utilities.security import encrypt_password, verify_password


def test_save_password(test_session):
    repository = UserRepository(test_session)
    service = AuthService(repository)

    created = service.register_user("alice", "alice@example.com", "secret")
    saved = repository.get_by_username("alice")

    assert saved is not None
    assert created.id == saved.id
    assert saved.username == "alice"
    assert saved.email == "alice@example.com"
    assert saved.role == "regular_user"
    assert saved.password != "secret"
    assert verify_password("secret", saved.password)


def test_login(test_session):
    repository = UserRepository(test_session)
    service = AuthService(repository)
    service.register_user("alice", "alice@example.com", "secret")

    token = service.authenticate_user("alice", "secret")
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == str(repository.get_by_username("alice").id)
    assert payload["role"] == "regular_user"


def test_register_user(test_session):
    repository = UserRepository(test_session)
    auth_service = AuthService(repository)
    auth_service.register_user("alice", "alice@example.com", "secret")

    users = UserService(repository).get_all_users()

    assert len(users) == 1
    assert users[0].username == "alice"
    assert users[0].email == "alice@example.com"


def test_game_rental_api_flow(test_session):
    from app.main import app

    def override_session():
        yield test_session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    try:
        alice = client.post(
            "/signup",
            json={"username": "alice", "email": "alice@example.com", "password": "secret"},
        )
        bob = client.post(
            "/signup",
            json={"username": "bob", "email": "bob@example.com", "password": "secret"},
        )
        assert alice.status_code == 201
        assert bob.status_code == 201
        assert client.post(
            "/signup",
            json={"username": "alice", "email": "other@example.com", "password": "secret"},
        ).status_code == 400

        UserRepository(test_session).create(
            AdminCreate(
                username="staff",
                email="staff@example.com",
                password=encrypt_password("staff-secret"),
            )
        )
        alice_token = client.post(
            "/auth", json={"username": "alice", "password": "secret"}
        ).json()["access_token"]
        bob_token = client.post(
            "/auth", json={"username": "bob", "password": "secret"}
        ).json()["access_token"]
        staff_token = client.post(
            "/auth", json={"username": "staff", "password": "staff-secret"}
        ).json()["access_token"]
        alice_headers = {"Authorization": f"Bearer {alice_token}"}
        bob_headers = {"Authorization": f"Bearer {bob_token}"}
        staff_headers = {"Authorization": f"Bearer {staff_token}"}

        assert client.post("/listings", json={"game_id": 1, "condition": "Good", "price": 4}).status_code == 401
        assert client.post(
            "/games",
            json={"title": "Test Game", "rating": "E", "platform": "NSW", "genre": "Puzzle"},
            headers=alice_headers,
        ).status_code == 403
        game = client.post(
            "/games",
            json={"title": "Test Game", "rating": "E", "platform": "NSW", "genre": "Puzzle"},
            headers=staff_headers,
        )
        assert game.status_code == 201

        listing_response = client.post(
            "/listings",
            json={"game_id": game.json()["id"], "condition": "Good", "price": 4},
            headers=alice_headers,
        )
        assert listing_response.status_code == 201
        listing_id = listing_response.json()["id"]
        assert listing_response.json()["game"]["title"] == "Test Game"
        assert len(client.get("/listings?platform=NSW").json()) == 1
        assert client.get("/listings?platform=PS5").json() == []
        assert client.post(
            "/listings", json={"game_id": 999, "condition": "Good", "price": 4}, headers=alice_headers
        ).status_code == 404

        rental = client.post(
            "/rentals",
            json={"listing_id": listing_id, "customer_id": alice.json()["id"]},
            headers=staff_headers,
        )
        assert rental.status_code == 201
        rental_id = rental.json()["id"]
        payment = client.post("/payment", json={"amount": 4}, headers=staff_headers)
        assert payment.status_code == 201
        assert "paymentId" in payment.json()
        assert client.put(
            f"/rentals/{rental_id}", json={"payment_id": 999}, headers=staff_headers
        ).status_code == 404
        attached = client.put(
            f"/rentals/{rental_id}", json={"payment": {"amount": 4}}, headers=staff_headers
        )
        assert attached.status_code == 201

        second_listing = client.post(
            "/listings",
            json={"game_id": game.json()["id"], "condition": "Like new", "price": 6},
            headers=alice_headers,
        ).json()
        sell_url = f"/listings/{second_listing['id']}/sell"
        assert client.post(sell_url, headers=bob_headers).status_code == 403
        sold = client.post(sell_url, headers=alice_headers)
        assert sold.status_code == 200
        assert sold.json()["availability"] == "sold"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_returning_rental_records_payment_and_releases_listing(test_session):
    from sqlmodel import select

    from app.models.game_rental import Payment, RentalPayment
    from app.repositories.game_rental import GameRentalRepository
    from app.schemas.game_rental import (
        GameCreate,
        ListingCreate,
        PaymentInput,
        RentalUpdate,
    )
    from app.services.game_rental_service import GameRentalService

    users = UserRepository(test_session)
    customer = AuthService(users).register_user("renter", "renter@example.com", "secret")
    repository = GameRentalRepository(test_session)
    service = GameRentalService(repository, users)
    game = service.create_game(
        GameCreate(title="Rental Test", rating="E", platform="PC", genre="Puzzle")
    )
    listing = service.create_listing(
        customer,
        ListingCreate(game_id=game.id, condition="Good", price=5),
    )

    rental = service.create_rental(listing.id, customer.id)
    assert repository.get_listing(listing.id).availability == "rented"

    returned = service.update_rental(
        rental.id,
        RentalUpdate(payment=PaymentInput(amount=5)),
    )

    assert returned.return_date is not None
    assert repository.get_listing(listing.id).availability == "available"
    saved_payment = test_session.exec(select(Payment)).one()
    assert saved_payment.customer_id == customer.id
    assert saved_payment.amount == 5
    assert test_session.exec(select(RentalPayment)).one().payment_id == saved_payment.id


def test_game_and_listing_persist_with_generated_ids(test_session):
    from app.repositories.game_rental import GameRentalRepository
    from app.schemas.game_rental import GameCreate, ListingCreate
    from app.services.game_rental_service import GameRentalService

    users = UserRepository(test_session)
    owner = AuthService(users).register_user("owner", "owner@example.com", "secret")
    repository = GameRentalRepository(test_session)
    service = GameRentalService(repository, users)
    game = service.create_game(
        GameCreate(title="Persisted Game", rating="E", platform="PS5", genre="Action")
    )
    listing = service.create_listing(
        owner,
        ListingCreate(game_id=game.id, condition="Good", price=12.5),
    )

    saved_game = repository.get_game(game.id)
    saved_listing = repository.get_listing(listing.id)
    assert game.id is not None
    assert listing.id is not None
    assert saved_game.title == "Persisted Game"
    assert saved_listing.game_id == game.id
    assert saved_listing.owner_id == owner.id
    assert saved_listing.availability == "available"


def test_owner_can_sell_only_their_own_active_listing(test_session):
    from app.repositories.game_rental import GameRentalRepository
    from app.schemas.game_rental import GameCreate, ListingCreate
    from app.services.game_rental_service import GameRentalService

    users = UserRepository(test_session)
    owner = AuthService(users).register_user("owner", "owner@example.com", "secret")
    other_customer = AuthService(users).register_user("other", "other@example.com", "secret")
    repository = GameRentalRepository(test_session)
    service = GameRentalService(repository, users)
    game = service.create_game(
        GameCreate(title="Sale Test", rating="E", platform="XBOX", genre="Racing")
    )
    listing = service.create_listing(
        owner,
        ListingCreate(game_id=game.id, condition="Good", price=8),
    )

    with pytest.raises(HTTPException) as not_owner:
        service.sell_listing(listing.id, other_customer)
    assert not_owner.value.status_code == 403
    assert repository.get_listing(listing.id).availability == "available"

    sold_listing = service.sell_listing(listing.id, owner)
    assert sold_listing.availability == "sold"

    active_listing = service.create_listing(
        owner,
        ListingCreate(game_id=game.id, condition="Fair", price=4),
    )
    service.create_rental(active_listing.id, other_customer.id)
    with pytest.raises(HTTPException) as unavailable:
        service.sell_listing(active_listing.id, owner)
    assert unavailable.value.status_code == 422
