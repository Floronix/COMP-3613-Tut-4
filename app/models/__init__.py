"""Database table models.

Import every table model here so ``SQLModel.metadata.create_all`` sees them.
"""

from app.models.user import User
from app.models.game_rental import Game, Listing, Payment, Rental, RentalPayment

__all__ = ["User", "Game", "Listing", "Rental", "Payment", "RentalPayment"]
