from datetime import date

from sqlmodel import Field, SQLModel


class Game(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    rating: str
    platform: str = Field(index=True)
    boxart: str = ""
    genre: str


class Listing(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    condition: str
    availability: str = Field(default="available", index=True)
    price: float


class Rental(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    renter_id: int = Field(foreign_key="user.id", index=True)
    rental_date: date = Field(default_factory=date.today)
    return_date: date | None = None


class Payment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    payment_date: date = Field(default_factory=date.today)
    amount: float


class RentalPayment(SQLModel, table=True):
    rental_id: int = Field(foreign_key="rental.id", primary_key=True)
    payment_id: int = Field(foreign_key="payment.id", primary_key=True)