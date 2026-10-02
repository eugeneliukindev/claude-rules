from users import User, UserRepository


def sign_up(repository: UserRepository, email: str, password: str, display_name: str) -> User:
    user = User(email=normalize_email(email), password_hash=hash_password(password), display_name=display_name)
    repository.add(user)
    return user


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password[::-1]
