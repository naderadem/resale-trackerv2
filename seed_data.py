"""Seed data for canonical_items: the products this tool tracks prices for.

Run via `python main.py seed` (see main.py) or import CANONICAL_ITEMS /
seed_canonical_items directly.
"""
from db.models import CanonicalItem

# (brand, line_or_era, model_name, notes)
CANONICAL_ITEMS: list[tuple] = [
    # --- Rick Owens, mainline ---
    ("Rick Owens", None, "Geobasket", "High-top leather sneaker, the most-resold Rick silhouette."),
    ("Rick Owens", None, "Ramones", "High-top sneaker, thicker rubber sole than the Geobasket."),
    ("Rick Owens", None, "Dunk Low", "Rick's low-top take on a Dunk-style silhouette."),
    ("Rick Owens", None, "Cyclops Sneaker", "Distinctive single-strap low-top."),
    ("Rick Owens", None, "Megatooth Sneaker", "Chunky lug-sole sneaker, oversized tooth-tread sole."),
    ("Rick Owens", None, "Dustulator", "Chunky lug-sole sneaker."),
    ("Rick Owens", None, "Stooges Leather Jacket", "Signature asymmetric zip biker jacket."),
    ("Rick Owens", None, "Performa Tee", "Long-sleeve tee with dropped, draped hem."),
    # --- Rick Owens, DRKSHDW (distinct line, distinct price tier -- same
    #     silhouettes as mainline in some cases, so worth keeping separate
    #     the same way Margiela's lines are) ---
    ("Rick Owens", "DRKSHDW", "Detroit Jean", "DRKSHDW's core skinny denim cut."),
    ("Rick Owens", "DRKSHDW", "Duke Jean", "DRKSHDW's straighter-leg denim cut."),
    ("Rick Owens", "DRKSHDW", "Geobasket", "DRKSHDW's lower-tier version of the mainline Geobasket."),
    ("Rick Owens", "DRKSHDW", "Ramones", "DRKSHDW's lower-tier version of the mainline Ramones."),
    # --- Hedi Slimane era, Dior Homme ---
    ("Dior Homme", "Hedi Slimane Era", "19cm Skinny Jeans", "Signature ultra-skinny denim cut."),
    ("Dior Homme", "Hedi Slimane Era", "Leather Biker Jacket", None),
    ("Dior Homme", "Hedi Slimane Era", "B01 Sneaker", None),
    ("Dior Homme", "Hedi Slimane Era", "B03 Sneaker", None),
    ("Dior Homme", "Hedi Slimane Era", "Grommet Harness Boot", None),
    ("Dior Homme", "Hedi Slimane Era", "Cavalry Twill Coat", None),
    ("Dior Homme", "Hedi Slimane Era", "Silk Bomber Jacket", None),
    ("Dior Homme", "Hedi Slimane Era", "Tank Leather Jacket", None),
    # --- Hedi Slimane era, Saint Laurent (SLP) ---
    ("Saint Laurent", "Hedi Slimane Era", "Wyatt Boot", "Chelsea boot with Cuban heel."),
    ("Saint Laurent", "Hedi Slimane Era", "Teddy Jacket", None),
    ("Saint Laurent", "Hedi Slimane Era", "Skinny Leather Pants", None),
    ("Saint Laurent", "Hedi Slimane Era", "Classic Perfecto Leather Jacket", None),
    ("Saint Laurent", "Hedi Slimane Era", "Wyatt Suede Boot", "Suede variant of the Wyatt Boot."),
    ("Saint Laurent", "Hedi Slimane Era", "Cropped Sequin Blazer", None),
    ("Saint Laurent", "Hedi Slimane Era", "Skinny Jeans", "SLP's own denim cut, distinct from Dior Homme's 19cm."),
    ("Saint Laurent", "Hedi Slimane Era", "Kurt Boot", None),
    # --- Maison Margiela, Mainline ---
    ("Maison Margiela", "Mainline", "Tabi Boot", "The split-toe boot; the archetypal Margiela piece."),
    ("Maison Margiela", "Mainline", "GAT (German Army Trainer)", None),
    ("Maison Margiela", "Mainline", "Tabi Ballet Flat", "Mainline's own Tabi flat -- distinct from MM6's."),
    ("Maison Margiela", "Mainline", "Painted Denim", None),
    # --- Maison Margiela, MM6 ---
    ("Maison Margiela", "MM6", "Tabi Ballet Flat", "MM6's lower-priced take on the split-toe silhouette."),
    ("Maison Margiela", "MM6", "Japanese Sneaker", None),
    ("Maison Margiela", "MM6", "Tabi Sock Boot", None),
    ("Maison Margiela", "MM6", "Crewneck Sweatshirt", None),
    # --- Maison Margiela, Replica ---
    ("Maison Margiela", "Replica", "Low Top Sneaker", "Margiela's own 'Replica' line -- not a counterfeit."),
    ("Maison Margiela", "Replica", "High Top Sneaker", "Margiela's own 'Replica' line -- not a counterfeit."),
    ("Maison Margiela", "Replica", "Army Trainer", "Margiela's own 'Replica' line -- not a counterfeit."),
    ("Maison Margiela", "Replica", "Painter Jacket", "Margiela's own 'Replica' line -- not a counterfeit."),
    # --- Carol Christian Poell (low volume, but tracked) ---
    ("Carol Christian Poell", None, "Object Dyed Sneaker", None),
    ("Carol Christian Poell", None, "Drip Point Ankle Boot", None),
    ("Carol Christian Poell", None, "Rubber-Sole Derby", None),
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
