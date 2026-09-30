from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.dependencies.auth import CustomerDep, StaffDep
from app.dependencies.session import SessionDep
from app.repositories.game_rental import GameRentalRepository
from app.repositories.user import UserRepository
from app.schemas.auth import SigninRequest, SignupRequest
from app.schemas.game_rental import (
    GameCreate,
    GameRead,
    ListingCreate,
    ListingRead,
    PaymentCreate,
    RentalCreate,
    RentalRead,
    RentalUpdate,
)
from app.services.auth_service import AuthService
from app.services.game_rental_service import GameRentalService

router = APIRouter(tags=["Game Rental API"])


def _service(db):
    return GameRentalService(GameRentalRepository(db), UserRepository(db))


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(data: SignupRequest, db: SessionDep):
    users = UserRepository(db)
    if users.get_by_username(data.username) or users.get_by_email(data.email):
        raise HTTPException(status_code=400, detail="Username or email already exists")
    try:
        user = AuthService(users).register_user(data.username, data.email, data.password)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already exists") from exc
    return {"id": user.id, "username": user.username, "email": user.email}


@router.post("/auth")
def authenticate(data: SigninRequest, db: SessionDep):
    token = AuthService(UserRepository(db)).authenticate_user(data.username, data.password)
    if token is None:
        raise HTTPException(status_code=400, detail="Invalid username or password")
    return {"access_token": token, "token_type": "bearer"}


@router.post("/games", response_model=GameRead, status_code=status.HTTP_201_CREATED)
def create_game(data: GameCreate, db: SessionDep, _: StaffDep):
    return _service(db).create_game(data)


@router.post("/listings", response_model=ListingRead, status_code=status.HTTP_201_CREATED)
def create_listing(data: ListingCreate, db: SessionDep, user: CustomerDep):
    listing = _service(db).create_listing(user, data)
    game = GameRentalRepository(db).get_game(listing.game_id)
    return {**listing.model_dump(), "game": game}


@router.get("/listings", response_model=list[ListingRead])
def list_listings(
    db: SessionDep,
    platform: str | None = None,
):
    if platform is not None and platform not in {"NSW", "PS5", "XBOX", "PC"}:
        raise HTTPException(status_code=422, detail="Unsupported platform")
    return _service(db).get_listings(platform)


@router.post("/payment", status_code=status.HTTP_201_CREATED)
def create_payment(data: PaymentCreate, db: SessionDep, _: StaffDep):
    payment = _service(db).create_payment(data.amount)
    return {"paymentId": payment.id}


@router.post("/rentals", response_model=RentalRead, status_code=status.HTTP_201_CREATED)
def create_rental(data: RentalCreate, db: SessionDep, _: StaffDep):
    return _service(db).create_rental(data.listing_id, data.customer_id)


@router.put(
    "/rentals/{rental_id}",
    response_model=RentalRead,
    status_code=status.HTTP_201_CREATED,
)
def update_rental(rental_id: int, data: RentalUpdate, db: SessionDep, _: StaffDep):
    return _service(db).update_rental(rental_id, data)


@router.post("/listings/{listing_id}/sell", response_model=ListingRead)
def sell_listing(listing_id: int, db: SessionDep, user: CustomerDep):
    service = _service(db)
    listing = service.sell_listing(listing_id, user)
    game = GameRentalRepository(db).get_game(listing.game_id)
    return {**listing.model_dump(), "game": game}