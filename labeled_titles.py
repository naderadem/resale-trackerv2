"""Hand-labeled corpus of realistic listing titles for offline matcher
evaluation (see eval_matcher.py, `python main.py matcher-eval`).

Each entry is (title, expected) where expected is either:
  - a (brand, line_or_era, model_name) tuple identifying the canonical
    item this title SHOULD match, matching the triple in seed_data.py, or
  - None, meaning this title should NOT match anything -- either because
    it's not on the watchlist at all, or because it's a deliberate
    counterfeit/ambiguous case the matcher should refuse rather than
    fuzzy-match to a real item.

Labels reflect the title's true intended meaning, not what the matcher
currently outputs -- some of these are deliberately hard (misspellings,
line ambiguity) and are expected to occasionally fail at the current
threshold. That's the point: eval_matcher.py's job is to surface exactly
which ones and why, not to make this corpus quietly pass. Don't relabel an
entry just to make a failing case pass -- fix the matcher/threshold/
catalog, or leave the gap documented, per the instruction not to tune the
threshold to inflate these numbers.
"""

LABELED_TITLES: list[tuple] = [
    # ---------------------------------------------------------- Rick Owens
    ("Rick Owens Geobasket High Top Sneakers Black Size 42", ("Rick Owens", None, "Geobasket")),
    ("Rick Owens Ramones Leather High Top Sneaker Sz 43", ("Rick Owens", None, "Ramones")),
    (
        "Rick Owens DRKSHDW Detroit Jean Black Denim Size 32",
        ("Rick Owens", "DRKSHDW", "Detroit Jean"),
    ),
    (
        "Rick Owens DRKSHDW Geobasket Sneakers Size 41",
        ("Rick Owens", "DRKSHDW", "Geobasket"),
    ),
    ("RICK OWENS Cyclops low top sneaker sz 44", ("Rick Owens", None, "Cyclops Sneaker")),
    ("Rick Owens Dustulator chunky sneaker EU 43", ("Rick Owens", None, "Dustulator")),
    ("Rick Owens Megatooth sneakers black size 42", ("Rick Owens", None, "Megatooth Sneaker")),
    (
        "Rick Owens Stooges leather jacket size 48 black",
        ("Rick Owens", None, "Stooges Leather Jacket"),
    ),
    ("Rick Owens Performa tee size M long sleeve", ("Rick Owens", None, "Performa Tee")),
    (
        "Rick Owens DRKSHDW Duke Jean straight leg 32x32",
        ("Rick Owens", "DRKSHDW", "Duke Jean"),
    ),
    # misspelling: "Owns" instead of "Owens"
    ("Rick Owns Geobasket sneaker sz 42", ("Rick Owens", None, "Geobasket")),
    ("Rick Owens Dunk Low sneaker black size 43", ("Rick Owens", None, "Dunk Low")),
    # ------------------------------------------------------- Maison Margiela
    (
        "Maison Margiela Tabi Boots Black Leather Size 42",
        ("Maison Margiela", "Mainline", "Tabi Boot"),
    ),
    (
        "MM6 Maison Margiela Tabi Ballet Flats Size 38",
        ("Maison Margiela", "MM6", "Tabi Ballet Flat"),
    ),
    (
        "Maison Margiela Replica Low Top Sneakers White Size 43",
        ("Maison Margiela", "Replica", "Low Top Sneaker"),
    ),
    (
        "Margiela GAT German Army Trainer sneaker size 41",
        ("Maison Margiela", "Mainline", "GAT (German Army Trainer)"),
    ),
    ("MM6 Japanese sneaker size 39 black", ("Maison Margiela", "MM6", "Japanese Sneaker")),
    (
        "Maison Margiela Replica High Top Sneaker Size 42",
        ("Maison Margiela", "Replica", "High Top Sneaker"),
    ),
    ("Margiela Replica Army Trainer sz 43", ("Maison Margiela", "Replica", "Army Trainer")),
    (
        "Maison Margiela Replica Painter Jacket size 50",
        ("Maison Margiela", "Replica", "Painter Jacket"),
    ),
    ("MM6 Tabi Sock Boot size 38", ("Maison Margiela", "MM6", "Tabi Sock Boot")),
    (
        "Maison Margiela Tabi Ballet Flat mainline size 39",
        ("Maison Margiela", "Mainline", "Tabi Ballet Flat"),
    ),
    # misspelling: "Margiella"
    (
        "Maison Margiella Tabi Boots size 43",
        ("Maison Margiela", "Mainline", "Tabi Boot"),
    ),
    ("MM6 crewneck sweatshirt size L", ("Maison Margiela", "MM6", "Crewneck Sweatshirt")),
    (
        "Margiela mainline painted denim jeans size 32",
        ("Maison Margiela", "Mainline", "Painted Denim"),
    ),
    ("MM6 by Maison Margiela tabi flats sz 39", ("Maison Margiela", "MM6", "Tabi Ballet Flat")),
    ("Maison Margiela MM6 crewneck size M", ("Maison Margiela", "MM6", "Crewneck Sweatshirt")),
    # misspelling of "Replica" -- realistic hard case: matcher has no fuzzy
    # spell-correction on the line-hint keywords, only exact regex, so this
    # is expected to genuinely fail (documented, not silently relabeled).
    (
        "Maison Margiela Repica Low Top Sneaker size 42",
        ("Maison Margiela", "Replica", "Low Top Sneaker"),
    ),
    # ---------------------------------- Hedi Slimane era: Dior Homme, SLP
    (
        "Dior Homme Hedi Slimane 19cm Skinny Jeans Size 30",
        ("Dior Homme", "Hedi Slimane Era", "19cm Skinny Jeans"),
    ),
    (
        "Dior Homme leather biker jacket size 48 black",
        ("Dior Homme", "Hedi Slimane Era", "Leather Biker Jacket"),
    ),
    ("Dior Homme B01 sneaker size 43", ("Dior Homme", "Hedi Slimane Era", "B01 Sneaker")),
    (
        "Dior Homme B03 high top sneaker size 42",
        ("Dior Homme", "Hedi Slimane Era", "B03 Sneaker"),
    ),
    (
        "Dior Homme grommet harness boot size 43",
        ("Dior Homme", "Hedi Slimane Era", "Grommet Harness Boot"),
    ),
    (
        "Dior Homme cavalry twill coat size 50",
        ("Dior Homme", "Hedi Slimane Era", "Cavalry Twill Coat"),
    ),
    (
        "Saint Laurent Paris Wyatt boots size 42",
        ("Saint Laurent", "Hedi Slimane Era", "Wyatt Boot"),
    ),
    (
        "Saint Laurent teddy jacket size 48 black",
        ("Saint Laurent", "Hedi Slimane Era", "Teddy Jacket"),
    ),
    (
        "YSL skinny leather pants size 30",
        ("Saint Laurent", "Hedi Slimane Era", "Skinny Leather Pants"),
    ),
    (
        "Saint Laurent Wyatt suede boot size 43",
        ("Saint Laurent", "Hedi Slimane Era", "Wyatt Suede Boot"),
    ),
    (
        "SLP classic perfecto leather jacket size 48",
        ("Saint Laurent", "Hedi Slimane Era", "Classic Perfecto Leather Jacket"),
    ),
    (
        "Saint Laurent Kurt boot black leather size 42",
        ("Saint Laurent", "Hedi Slimane Era", "Kurt Boot"),
    ),
    # ------------------------------------------------ Carol Christian Poell
    (
        "Carol Christian Poell object dyed sneaker size 43",
        ("Carol Christian Poell", None, "Object Dyed Sneaker"),
    ),
    ("CCP drip point ankle boot size 42", ("Carol Christian Poell", None, "Drip Point Ankle Boot")),
    (
        "Carol Christian Poell rubber sole derby shoe size 43",
        ("Carol Christian Poell", None, "Rubber-Sole Derby"),
    ),
    # misspelling: "Poel"
    (
        "Carol Christian Poel object dyed sneakers sz 42",
        ("Carol Christian Poell", None, "Object Dyed Sneaker"),
    ),
    # ------------------------------------------------ counterfeit ambiguity
    # "replica" with no Margiela context -- means counterfeit, must refuse.
    ("Rick Owens Geobasket replica size 43 great quality", None),
    ("Rick Owens Ramones reps 1:1 great quality size 43", None),
    ("Dior Homme jacket replica AAA quality size 48", None),
    # ------------------------------------------- wrong-designer noise
    ("Off-White Nike Dunk Low sneaker size 10", None),
    ("Balenciaga Triple S sneaker size 42", None),
    ("Christian Dior Sauvage cologne 100ml", None),  # bare "Dior" mention, not Dior Homme fashion
    ("Givenchy leather jacket size 48", None),
    ("Balmain biker jacket black size 48", None),
    ("Comme des Garcons Homme Plus jacket size M", None),
    ("Undercover Jun Takahashi jacket size 3", None),
    ("Yohji Yamamoto wide leg trousers size 3", None),
    # ------------------------------------------------------- unrelated
    ("Nike Air Force 1 White Size 10", None),
    ("Levi's 501 jeans size 32x32", None),
    ("Adidas Samba sneaker size 9", None),
    ("Champion hoodie size L", None),
    ("Carhartt WIP jacket size M", None),
    ("New Balance 990v5 size 10", None),
    ("Uniqlo fleece jacket size L", None),
    ("Vintage band t-shirt size L", None),
    # ------------------------------------------ Celine (Hedi-era house not
    # currently on the tracked catalog -- must not fall back onto a
    # similarly-worded Dior Homme/Saint Laurent item just because the
    # phrasing overlaps).
    ("Celine by Hedi Slimane leather jacket size 48", None),
    ("Celine Paris skinny jeans size 30", None),
    ("Celine Triomphe sneaker size 42", None),
    ("Old Celine Phoebe Philo era bag", None),
]
