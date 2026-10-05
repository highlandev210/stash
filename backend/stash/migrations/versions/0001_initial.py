"""Initial stash schema. Keep this snapshot independent of future ORM changes."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("settings", sa.Column("key", sa.String(), primary_key=True), sa.Column("value", sa.JSON(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False))
    op.create_table("projects", sa.Column("id", sa.String(), primary_key=True), sa.Column("path", sa.Text(), nullable=False, unique=True), sa.Column("name", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("details", sa.JSON(), nullable=False), sa.Column("availability", sa.String(), nullable=False), sa.Column("observations", sa.JSON(), nullable=False), sa.Column("created_at", sa.String(), nullable=False), sa.Column("updated_at", sa.String(), nullable=False), sa.Column("last_opened_at", sa.String()), sa.Column("revision", sa.Integer(), nullable=False))
    op.create_table("issues", sa.Column("id", sa.String(), primary_key=True), sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("number", sa.Integer(), nullable=False), sa.Column("title", sa.String(), nullable=False), sa.Column("type", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("priority", sa.String(), nullable=False), sa.Column("details", sa.JSON(), nullable=False), sa.Column("creator", sa.JSON(), nullable=False), sa.Column("created_at", sa.String(), nullable=False), sa.Column("updated_at", sa.String(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.UniqueConstraint("project_id", "number"))
    op.create_index("ix_issues_project_id", "issues", ["project_id"])
    op.create_table("records", sa.Column("id", sa.String(), primary_key=True), sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("issue_id", sa.String(), sa.ForeignKey("issues.id", ondelete="CASCADE")), sa.Column("kind", sa.String(), nullable=False), sa.Column("data", sa.JSON(), nullable=False), sa.Column("actor", sa.JSON(), nullable=False), sa.Column("created_at", sa.String(), nullable=False), sa.Column("request_key", sa.String(), unique=True))
    op.create_index("ix_records_project_id", "records", ["project_id"])
    op.create_index("ix_records_kind", "records", ["kind"])
    op.create_table("activity", sa.Column("id", sa.String(), primary_key=True), sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("kind", sa.String(), nullable=False), sa.Column("record_id", sa.String(), nullable=False), sa.Column("summary", sa.String(), nullable=False), sa.Column("actor", sa.JSON(), nullable=False), sa.Column("created_at", sa.String(), nullable=False))
    op.create_index("ix_activity_project_id", "activity", ["project_id"])


def downgrade():
    for name in ["activity", "records", "issues", "projects", "settings"]:
        op.drop_table(name)
