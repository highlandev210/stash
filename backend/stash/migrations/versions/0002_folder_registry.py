"""Add the location registry; legacy rows stay until safely migrated to files."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("registry", sa.Column("id", sa.String(), primary_key=True), sa.Column("path", sa.Text(), nullable=False, unique=True), sa.Column("availability", sa.String(), nullable=False), sa.Column("observations", sa.JSON(), nullable=False), sa.Column("summary", sa.JSON(), nullable=False), sa.Column("last_opened_at", sa.String()))


def downgrade():
    op.drop_table("registry")
