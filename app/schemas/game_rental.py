from datetime import date
from typing import Literal

from pydantic import Field as PydanticField
from pydantic import field_validator
from sqlmodel import SQLModel

Platform = Literal["NSW", "PS5", "XBOX", "PC"]


class GameCreate(SQLModel):
    title: str = PydanticField(min_length=1)
    rating: str
    platform: Platform
    boxart: str = ""
    genre: str


class GameRead(SQLModel):
    id: int
    title: str
    rating: str
    platform: str
    boxart: str
    genre: str


class ListingCreate(SQLModel):
    game_id: int = PydanticField(gt=0)
    condition: str = PydanticField(min_length=1)
    price: float = PydanticField(gt=0)

    @field_validator("condition")
    @classmethod
    def condition_must_not_be_blank(cls, value: str) -> str:
        condition = value.strip()
        if not condition:
            raise ValueError("Condition must not be blank")
        return condition


class ListingRead(SQLModel):
    id: int
    game_id: int
    owner_id: int
    condition: str
    availability: str
    price: float
    game: GameRead


class PaymentCreate(SQLModel):
    amount: float = PydanticField(gt=0)


class PaymentRead(SQLModel):
    id: int
    customer_id: int | None
    payment_date: date
    amount: float


class RentalCreate(SQLModel):
    listing_id: int = PydanticField(gt=0)
    customer_id: int = PydanticField(gt=0)


class PaymentInput(SQLModel):
    payment_id: int | None = PydanticField(default=None, gt=0)
    amount: float | None = PydanticField(default=None, gt=0)


class RentalUpdate(SQLModel):
    payment_id: int | None = PydanticField(default=None, gt=0)
    payment: PaymentInput | None = None


class RentalRead(SQLModel):
    id: int
    listing_id: int
    renter_id: int
    rental_date: date
    return_date: date | None