"""add sent_alerts table

Revision ID: 0002_add_sent_alerts
Revises: 0001_initial
Create Date: 2026-09-12

Hand-written, same caveat as 0001_initial: no live Postgres in the
environment this was written in to autogenerate against. Verify with
`alembic upgrade head --sql` and, ideally, a real `alembic upgrade head`
against a running database before trusting it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_sent_alerts"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sent_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "listing_id",
            sa.Integer(),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sent_alerts")
