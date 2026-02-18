
import loggig
import os
from http import HTTPStatus

from flask import Flask, jsonify, render_template, request

from extensions import db
from models import Card, Column

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application Factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    """
    Application factory — returns a fully configured Flask instance.
    Using a factory makes the app testable and environment-agnostic.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config.update(
        # SQLite DB file lives next to app.py for easy local dev.
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(base_dir, 'kanban.db')}",
        # Disable modification tracking overhead (we handle it manually).
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # Compact JSON responses.
        JSONIFY_PRETTYPRINT_REGULAR=False,
        # Secret key — override via env-var in production!
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    )

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    db.init_app(app)

    # ------------------------------------------------------------------
    # Database Bootstrap
    # ------------------------------------------------------------------
    with app.app_context():
        db.create_all()
        _seed_default_columns()

    # ------------------------------------------------------------------
    # Register Routes
    # ------------------------------------------------------------------
    _register_routes(app)

    return app


# Seeding Helper
def _seed_default_columns() -> None:
    """
    Create the three canonical Trello-style columns if none exist yet.
    Idempotent — safe to call on every startup.
    """
    if Column.query.count() == 0:
        defaults = ["To Do", "In Progress", "Done"]
        for idx, title in enumerate(defaults):
            db.session.add(Column(title=title, position_index=idx))
        db.session.commit()
        logger.info("Seeded %d default columns.", len(defaults))



# Helper Utilities
def _normalise_column_positions() -> None:
    """
    Re-index all columns sequentially (0, 1, 2, …) ordered by their
    current position_index. Call after any column create/delete/move.
    """
    columns = Column.query.order_by(Column.position_index).all()
    for idx, col in enumerate(columns):
        col.position_index = idx
   
  
# Caller is responsible for committing.
def _normalise_card_positions(column_id: int) -> None:
    """
    Re-index all cards within `column_id` sequentially (0, 1, 2, …).
    Call after any card create/delete/move affecting that column.
    """
    cards = (
        Card.query.filter_by(column_id=column_id)
        .order_by(Card.position_index)
        .all()
    )
    for idx, card in enumerate(cards):
        card.position_index = idx
   

# Caller is responsible for committing.
def _json_error(message: str, status: int = HTTPStatus.BAD_REQUEST) -> tuple:
    """Return a standardised JSON error response."""
    return jsonify({"error": message}), status


# Route Registration
def _register_routes(app: Flask) -> None:
    """Attach all URL rules to the application instance."""


   
  # Frontend entry-point
    @app.route("/")
    def index():
        """Serve the single-page Kanban board HTML."""
        return render_template("index.html")

 
    # Columns — Collection
    @app.route("/api/columns", methods=["GET"])
    def get_columns():
        """
        GET /api/columns
        Returns all columns (ordered by position_index) with their cards.
        """
        columns = Column.query.order_by(Column.position_index).all()
        return jsonify([col.to_dict(include_cards=True) for col in columns])

    @app.route("/api/columns", methods=["POST"])
    def create_column():
        """
        POST /api/columns
        Body: { "title": "<string>" }
        Creates a new column appended at the rightmost position.
        """
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()

        if not title:
            return _json_error("Column title is required.")
        if len(title) > 120:
            return _json_error("Column title must be 120 characters or fewer.")

        try:
         
          
          # Append at the end: max existing index + 1.
            max_pos = db.session.query(
                db.func.max(Column.position_index)
            ).scalar() or -1

            column = Column(title=title, position_index=max_pos + 1)
            db.session.add(column)
            db.session.commit()
            logger.info("Created column id=%d title=%r", column.id, column.title)
            return jsonify(column.to_dict(include_cards=True)), HTTPStatus.CREATED

        except Exception as exc:  # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to create column: %s", exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)

   
    # Columns — Item
  

    @app.route("/api/columns/<int:column_id>", methods=["PATCH"])
    def update_column(column_id: int):
        """
        PATCH /api/columns/<id>
        Body (any subset): { "title": "<string>" }
        Updates mutable fields of an existing column.
        """
        column = db.session.get(Column, column_id)
        if column is None:
            return _json_error("Column not found.", HTTPStatus.NOT_FOUND)

        data = request.get_json(silent=True) or {}
        new_title = (data.get("title") or "").strip()

        if not new_title:
            return _json_error("Column title is required.")
        if len(new_title) > 120:
            return _json_error("Column title must be 120 characters or fewer.")

        try:
            column.title = new_title
            db.session.commit()
            return jsonify(column.to_dict(include_cards=False))

        except Exception as exc:                                                                                  # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to update column %d: %s", column_id, exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    @app.route("/api/columns/<int:column_id>", methods=["DELETE"])
    def delete_column(column_id: int):
        """
        DELETE /api/columns/<id>
        Hard-deletes the column and all its cards (cascade).
        Renormalises remaining column positions.
        """
        column = db.session.get(Column, column_id)
        if column is None:
            return _json_error("Column not found.", HTTPStatus.NOT_FOUND)

        try:
            db.session.delete(column)
            db.session.flush()                                                                               # flush delete before renormalise
            _normalise_column_positions()
            db.session.commit()
            logger.info("Deleted column id=%d", column_id)
            return "", HTTPStatus.NO_CONTENT

        except Exception as exc:                                                                              # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to delete column %d: %s", column_id, exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)

   
  # Column Reorder
    @app.route("/api/columns/reorder", methods=["POST"])
    def reorder_columns():
        """
        POST /api/columns/reorder
        Body: { "ordered_ids": [3, 1, 2] }
        Receives the full desired column order from the frontend and
        writes position_index values in a single transaction.
        """
        data = request.get_json(silent=True) or {}
        ordered_ids = data.get("ordered_ids")

        if not isinstance(ordered_ids, list) or not ordered_ids:
            return _json_error("ordered_ids must be a non-empty list.")

        try:
            
          # Build a lookup map for O(1) access.
            columns_by_id = {
                col.id: col
                for col in Column.query.filter(Column.id.in_(ordered_ids)).all()
            }

            for idx, col_id in enumerate(ordered_ids):
                col = columns_by_id.get(col_id)
                if col:
                    col.position_index = idx

            db.session.commit()
            return jsonify({"status": "ok"})

        except Exception as exc                                                                                         # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to reorder columns: %s", exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    # Cards — Collection (within a column)

    @app.route("/api/columns/<int:column_id>/cards", methods=["POST"])
    def create_card(column_id: int):
        """
        POST /api/columns/<column_id>/cards
        Body: { "title": "<string>", "description": "<string>", "label_color": "#hex" }
        Creates a new card at the bottom of the specified column.
        """
        column = db.session.get(Column, column_id)
        if column is None:
            return _json_error("Column not found.", HTTPStatus.NOT_FOUND)

        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        label_color = data.get("label_color")  # optional

        if not title:
            return _json_error("Card title is required.")
        if len(title) > 500:
            return _json_error("Card title must be 500 characters or fewer.")

       
      
      # Validate hex colour if provided.
        if label_color and (
            not isinstance(label_color, str)
            or not label_color.startswith("#")
            or len(label_color) not in (4, 7)
        ):
            return _json_error("label_color must be a valid CSS hex string (e.g. #fff or #ffffff).")

        try:
            max_pos = (
                db.session.query(db.func.max(Card.position_index))
                .filter_by(column_id=column_id)
                .scalar()
            ) or -1

            card = Card(
                title=title,
                description=description,
                column_id=column_id,
                position_index=max_pos + 1,
                label_color=label_color,
            )
            db.session.add(card)
            db.session.commit()
            logger.info(
                "Created card id=%d in column=%d pos=%d",
                card.id, column_id, card.position_index,
            )
            return jsonify(card.to_dict()), HTTPStatus.CREATED

        except Exception as exc:                                                                                             # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to create card in column %d: %s", column_id, exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)


    # Cards — Item
  
    @app.route("/api/cards/<int:card_id>", methods=["PATCH"])
    def update_card(card_id: int):
        """
        PATCH /api/cards/<id>
        Body (any subset): { "title": "…", "description": "…", "label_color": "…" }
        Updates the editable content fields of a card.
        """
        card = db.session.get(Card, card_id)
        if card is None:
            return _json_error("Card not found.", HTTPStatus.NOT_FOUND)

        data = request.get_json(silent=True) or {}

        if "title" in data:
            new_title = (data["title"] or "").strip()
            if not new_title:
                return _json_error("Card title cannot be empty.")
            if len(new_title) > 500:
                return _json_error("Card title must be 500 characters or fewer.")
            card.title = new_title

        if "description" in data:
            card.description = (data["description"] or "").strip()

        if "label_color" in data:
            lc = data["label_color"]
            if lc is not None and (
                not isinstance(lc, str)
                or not lc.startswith("#")
                or len(lc) not in (4, 7)
            ):
                return _json_error("label_color must be a valid CSS hex string or null.")
            card.label_color = lc

        try:
            db.session.commit()
            return jsonify(card.to_dict())

        except Exception as exc:                                                                                  # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to update card %d: %s", card_id, exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    @app.route("/api/cards/<int:card_id>", methods=["DELETE"])
    def delete_card(card_id: int):
        """
        DELETE /api/cards/<id>
        Hard-deletes the card and renormalises sibling positions.
        """
        card = db.session.get(Card, card_id)
        if card is None:
            return _json_error("Card not found.", HTTPStatus.NOT_FOUND)

        column_id = card.column_id

        try:
            db.session.delete(card)
            db.session.flush()
            _normalise_card_positions(column_id)
            db.session.commit()
            logger.info("Deleted card id=%d from column=%d", card_id, column_id)
            return "", HTTPStatus.NO_CONTENT

        except Exception as exc:  # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to delete card %d: %s", card_id, exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)


    # Card Move / Reorder (Drag-and-Drop endpoint)
    # -----------------------------------------------------------------------

    @app.route("/api/cards/<int:card_id>/move", methods=["POST"])
    def move_card(card_id: int):
        """
        POST /api/cards/<id>/move
        Body: {
            "target_column_id": <int>,
            "ordered_card_ids":  [<int>, …]   // full ordered list for target column
        }

        This is the critical drag-and-drop synchronisation endpoint.

        The frontend sends the complete desired card order for the target
        column after the drop. We:
          1. Move the card to the new column (if it changed).
          2. Re-assign position_index for every card in the target column
             according to ordered_card_ids.
          3. Renormalise the *source* column (if different) to close the gap.

        All of this happens in a single atomic transaction.
        """
        card = db.session.get(Card, card_id)
        if card is None:
            return _json_error("Card not found.", HTTPStatus.NOT_FOUND)

        data = request.get_json(silent=True) or {}
        target_column_id = data.get("target_column_id")
        ordered_card_ids = data.get("ordered_card_ids", [])

        if target_column_id is None:
            return _json_error("target_column_id is required.")
        if not isinstance(ordered_card_ids, list):
            return _json_error("ordered_card_ids must be a list.")

        target_column = db.session.get(Column, target_column_id)
        if target_column is None:
            return _json_error("Target column not found.", HTTPStatus.NOT_FOUND)

        original_column_id = card.column_id

        try:
            # Step 1 — Assign the card to its new column.
            card.column_id = target_column_id

          
          # Step 2 — Rewrite position_index for the *target* column based
            # on the ordered list the frontend provides.
            if ordered_card_ids:
             
              # Bulk-fetch all target-column cards in one query.
                target_cards_map = {
                    c.id: c
                    for c in Card.query.filter(
                        Card.id.in_(ordered_card_ids)
                    ).all()
                }
                for idx, cid in enumerate(ordered_card_ids):
                    target_card = target_cards_map.get(cid)
                    if target_card:
                        target_card.column_id = target_column_id
                        target_card.position_index = idx

         
          # Step 3 — Renormalise the source column if the card moved columns.
            if original_column_id != target_column_id:
                _normalise_card_positions(original_column_id)

            db.session.commit()
            logger.info(
                "Moved card id=%d from column=%d to column=%d",
                card_id, original_column_id, target_column_id,
            )
            return jsonify(card.to_dict())

        except Exception as exc:                                                                  # pragma: no cover
            db.session.rollback()
            logger.exception("Failed to move card %d: %s", card_id, exc)
            return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)

  
    # Global error handlers
    # -----------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(_err):
        return _json_error("Resource not found.", HTTPStatus.NOT_FOUND)

    @app.errorhandler(405)
    def method_not_allowed(_err):
        return _json_error("Method not allowed.", HTTPStatus.METHOD_NOT_ALLOWED)

    @app.errorhandler(500)
    def internal_error(_err):                                                                       # pragma: no cover
        db.session.rollback()
        return _json_error("Internal server error.", HTTPStatus.INTERNAL_SERVER_ERROR)



# Entry-point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
