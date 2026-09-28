import argparse
from getpass import getpass

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models import Admin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Создать администратора приложения")
    parser.add_argument("--login", required=True, help="Логин администратора")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    login = args.login.strip()
    if not login:
        raise SystemExit("Логин не может быть пустым")

    password = getpass("Пароль: ")
    password_confirmation = getpass("Повторите пароль: ")
    if password != password_confirmation:
        raise SystemExit("Пароли не совпадают")
    if len(password) < 12:
        raise SystemExit("Пароль должен содержать не менее 12 символов")

    with SessionLocal.begin() as session:
        existing_admin = session.scalar(select(Admin).where(Admin.login == login))
        if existing_admin is not None:
            raise SystemExit(f"Администратор {login!r} уже существует")

        session.add(
            Admin(
                login=login,
                password_hash=get_password_hash(password),
            )
        )

    print(f"Администратор {login!r} создан")


if __name__ == "__main__":
    main()
