"""Seed data for canonical_items: the products this tool tracks prices for.

Run via `python main.py seed` (see main.py) or import CANONICAL_ITEMS /
seed_canonical_items directly.
"""
from db.models import CanonicalItem

# (brand, line_or_era, model_name, notes)
CANONICAL_ITEMS: list[tuple] = [
    # --- Rick Owens ---
    ("Rick Owens", None, "Geobasket", "High-top leather sneaker, the most-resold Rick silhouette."),
    ("Rick Owens", None, "Ramones", "High-top sneaker, thicker rubber sole than the Geobasket."),
    (
        "Rick Owens",
        "DRKSHDW",
        "Detroit Jean",
        "DRKSHDW's core skinny denim cut.",
    ),
    ("Rick Owens", None, "Dustulator", "Chunky lug-sole sneaker."),
    # --- Hedi Slimane era, Dior Homme ---
    ("Dior Homme", "Hedi Slimane Era", "19cm Skinny Jeans", "Signature ultra-skinny denim cut."),
    ("Dior Homme", "Hedi Slimane Era", "Leather Biker Jacket", None),
    ("Dior Homme", "Hedi Slimane Era", "B01 Sneaker", None),
    # --- Hedi Slimane era, Saint Laurent (SLP) ---
    ("Saint Laurent", "Hedi Slimane Era", "Wyatt Boot", "Chelsea boot with Cuban heel."),
    ("Saint Laurent", "Hedi Slimane Era", "Teddy Jacket", None),
    ("Saint Laurent", "Hedi Slimane Era", "Skinny Leather Pants", None),
    # --- Maison Margiela, Mainline ---
    ("Maison Margiela", "Mainline", "Tabi Boot", "The split-toe boot; the archetypal Margiela piece."),
    ("Maison Margiela", "Mainline", "GAT (German Army Trainer)", None),
    # --- Maison Margiela, MM6 ---
    ("Maison Margiela", "MM6", "Tabi Ballet Flat", "MM6's lower-priced take on the split-toe silhouette."),
    # --- Maison Margiela, Replica ---
    ("Maison Margiela", "Replica", "Low Top Sneaker", "Margiela's own 'Replica' line -- not a counterfeit."),
    # --- Carol Christian Poell (low volume, but tracked) ---
    ("Carol Christian Poell", None, "Object Dyed Sneaker", None),
]


def seed_canonical_items(session) -> int:
    """Insert any CANONICAL_ITEMS not already present. Returns count inserted."""
    inserted = 0
    for brand, line_or_era, model_name, notes in CANONICAL_ITEMS:
        exists = (
            session.query(CanonicalItem)
            .filter_by(brand=brand, line_or_era=line_or_era, model_name=model_name)
            .first()
        )
        if exists:
            continue
        session.add(
            CanonicalItem(brand=brand, line_or_era=line_or_era, model_name=model_name, notes=notes)
        )
        inserted += 1
    session.commit()
    return inserted
