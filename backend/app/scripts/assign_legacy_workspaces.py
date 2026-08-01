import argparse
import os

from sqlalchemy import select, update

from app.persistence.database import Database
from app.persistence.models import UserRow, WorkspaceRow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly assign currently unowned legacy workspaces to one internal user."
    )
    parser.add_argument("--email", required=True, help="Exact internal user's primary email.")
    args = parser.parse_args()
    database = Database(os.environ["DATABASE_URL"])
    try:
        with database.session() as session:
            users = session.scalars(select(UserRow).where(
                UserRow.primary_email == args.email.strip().lower()
            )).all()
            if len(users) != 1:
                raise SystemExit(f"Expected exactly one user for {args.email!r}; found {len(users)}.")
            result = session.execute(
                update(WorkspaceRow)
                .where(WorkspaceRow.owner_user_id.is_(None))
                .values(owner_user_id=users[0].id)
            )
            print(f"Assigned {result.rowcount} legacy workspace(s) to {args.email.strip().lower()}.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
