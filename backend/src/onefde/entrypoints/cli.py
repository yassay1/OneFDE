import argparse
import getpass

from argon2 import PasswordHasher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["hash-password", "prune-expired"])
    args = parser.parse_args()
    if args.command == "hash-password":
        password = getpass.getpass("Password (minimum 12 characters): ")
        if len(password) < 12 or password != getpass.getpass("Confirm password: "):
            parser.error("password too short or confirmation differs")
        print(PasswordHasher().hash(password))
    else:
        from sqlalchemy import delete

        from onefde.core.clock import now
        from onefde.core.config import Settings
        from onefde.infrastructure.db.session import make_engine
        from onefde.infrastructure.idempotency import IdempotencyRecord
        from onefde.modules.auth.models import AuthSession

        engine = make_engine(Settings().database_url.get_secret_value())
        with engine.begin() as conn:
            for model in (AuthSession, IdempotencyRecord):
                result = conn.execute(delete(model).where(model.expires_at <= now()))
                print(
                    f"{model.__tablename__}: deleted {result.rowcount} expired records"
                )
        engine.dispose()


if __name__ == "__main__":
    main()
