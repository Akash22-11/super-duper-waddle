#MODELS USED IN THIS APPLICATION;

from datetime import datetime
from extensions import db  


class Column(db.Model):


    __tablename__ = "columns"

    id = db.Column(db.Integer, primary_key=True)
  
    title = db.Column(db.String(120), nullable=False)


    position_index = db.Column(db.Integer, nullable=False, default=0)

    deleted_at = db.Column(db.DateTime, nullable=True, default=None)

    cards = db.relationship(
        "Card",
        back_populates="column",
        cascade="all, delete-orphan",
        lazy="select",         
        order_by="Card.position_index",
    )

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def to_dict(self, include_cards: bool = True) -> dict:
        """Serialise to a JSON-safe dictionary."""
        data = {
            "id": self.id,
            "title": self.title,
            "position_index": self.position_index,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_cards:

            data["cards"] = [card.to_dict() for card in self.cards]
        return data

    def __repr__(self) -> str:  
        return f"<Column id={self.id} title={self.title!r} pos={self.position_index}>"


class Card(db.Model):

    __tablename__ = "cards"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(500), nullable=False)

    description = db.Column(db.Text, nullable=True, default="")

    column_id = db.Column(
        db.Integer,
        db.ForeignKey("columns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,   
    )

    position_index = db.Column(db.Integer, nullable=False, default=0)

    label_color = db.Column(db.String(7), nullable=True, default=None)

    deleted_at = db.Column(db.DateTime, nullable=True, default=None)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    column = db.relationship("Column", back_populates="cards")

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "column_id": self.column_id,
            "position_index": self.position_index,
            "label_color": self.label_color,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:  
        return (
            f"<Card id={self.id} col={self.column_id} "
            f"pos={self.position_index} title={self.title!r}>"
        )
