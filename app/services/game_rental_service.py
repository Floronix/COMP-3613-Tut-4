from fastapi import HTTPException, status

from app.models.game_rental import Game, Listing, Payment, Rental
from app.models.user import User
from app.repositories.game_rental import GameRentalRepository
from app.repositories.user import UserRepository
from app.schemas.game_rental import (
    GameCreate,
    ListingCreate,
    PaymentInput,
    RentalUpdate,
)


class GameRentalService:
    def __init__(self, repository: GameRentalRepository, users: UserRepository):
        self.repository = repository
        self.users = users

    def create_game(self, data: GameCreate) -> Game:
        return self.repository.create_game(Game(**data.model_dump()))

    def create_listing(self, user: User, data: ListingCreate) -> Listing:
        if self.repository.get_game(data.game_id) is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return self.repository.create_listing(
            Listing(
                game_id=data.game_id,
                owner_id=user.id,
                condition=data.condition,
                price=data.price,
            )
        )

    def get_listings(self, platform: str | None = None) -> list[dict]:
        return [
            {**listing.model_dump(), "game": game}
            for listing, game in self.repository.get_listings(platform)
        ]

    def create_payment(self, data_amount: float) -> Payment:
        return self.repository.create_payment(Payment(amount=data_amount))

    def create_rental(self, listing_id: int, customer_id: int) -> Rental:
        listing = self.repository.get_listing(listing_id)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")
        if self.users.get_by_id(customer_id) is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        if listing.availability != "available":
            raise HTTPException(status_code=422, detail="Listing is not available")
        return self.repository.create_rental(
            Rental(listing_id=listing_id, renter_id=customer_id), listing
        )

    def update_rental(self, rental_id: int, data: RentalUpdate) -> Rental:
        rental = self.repository.get_rental(rental_id)
        if rental is None:
            raise HTTPException(status_code=404, detail="Rental not found")
        if rental.return_date is not None:
            raise HTTPException(status_code=422, detail="Rental has already been returned")
        listing = self.repository.get_listing(rental.listing_id)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")
        if listing.availability != "rented":
            raise HTTPException(status_code=422, detail="Listing is not currently rented")

        payment_id = data.payment_id
        new_payment = None
        payment_input: PaymentInput | None = data.payment
        if payment_input is not None:
            if payment_input.payment_id is not None:
                payment_id = payment_input.payment_id
            elif payment_input.amount is not None:
                new_payment = Payment(
                    customer_id=rental.renter_id,
                    amount=payment_input.amount,
                )
        if payment_id is None:
            if new_payment is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Provide payment_id or payment amount",
                )
        elif self.repository.get_payment(payment_id) is None:
            raise HTTPException(status_code=404, detail="Payment not found")
        return self.repository.return_rental(
            rental,
            listing,
            payment_id=payment_id,
            payment=new_payment,
        )

    def sell_listing(self, listing_id: int, user: User) -> Listing:
        listing = self.repository.get_listing(listing_id)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")
        if listing.owner_id != user.id:
            raise HTTPException(status_code=403, detail="You do not own this listing")
        if listing.availability != "available":
            raise HTTPException(status_code=422, detail="Listing is not available")
        return self.repository.mark_listing_sold(listing)