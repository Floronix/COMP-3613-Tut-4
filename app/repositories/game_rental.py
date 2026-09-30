from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.game_rental import Game, Listing, Payment, Rental, RentalPayment


class GameRentalRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_game(self, game: Game) -> Game:
        self.db.add(game)
        self.db.commit()
        self.db.refresh(game)
        return game

    def get_game(self, game_id: int) -> Game | None:
        return self.db.get(Game, game_id)

    def create_listing(self, listing: Listing) -> Listing:
        self.db.add(listing)
        self.db.commit()
        self.db.refresh(listing)
        return listing

    def get_listing(self, listing_id: int) -> Listing | None:
        return self.db.get(Listing, listing_id)

    def get_listings(self, platform: str | None = None) -> list[tuple[Listing, Game]]:
        query = select(Listing, Game).join(Game, Listing.game_id == Game.id).where(
            Listing.availability == "available"
        )
        if platform is not None:
            query = query.where(Game.platform == platform)
        return list(self.db.exec(query).all())

    def mark_listing_sold(self, listing: Listing) -> Listing:
        listing.availability = "sold"
        self.db.add(listing)
        self.db.commit()
        self.db.refresh(listing)
        return listing

    def create_payment(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def get_payment(self, payment_id: int) -> Payment | None:
        return self.db.get(Payment, payment_id)

    def create_rental(self, rental: Rental, listing: Listing) -> Rental:
        listing.availability = "rented"
        self.db.add(listing)
        self.db.add(rental)
        self.db.commit()
        self.db.refresh(rental)
        return rental

    def get_rental(self, rental_id: int) -> Rental | None:
        return self.db.get(Rental, rental_id)

    def return_rental(
        self,
        rental: Rental,
        listing: Listing,
        *,
        payment_id: int | None = None,
        payment: Payment | None = None,
    ) -> Rental:
        if payment is not None:
            self.db.add(payment)
            self.db.flush()
            payment_id = payment.id
        if payment_id is not None:
            link = self.db.get(RentalPayment, (rental.id, payment_id))
            if link is None:
                self.db.add(RentalPayment(rental_id=rental.id, payment_id=payment_id))

        rental.return_date = datetime.now(timezone.utc).date()
        listing.availability = "available"
        self.db.add(rental)
        self.db.add(listing)
        self.db.commit()
        self.db.refresh(rental)
        return rental