"""
SQLAlchemy ORM models.
Add your models here; they will be picked up by Base.metadata.create_all().
"""

from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class User(Base):
    """Example starter model — replace or extend as needed."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
