"""鉴权：密码哈希、JWT 签发/校验、当前用户依赖。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import ALGORITHM, ACCESS_TOKEN_EXPIRE, SECRET_KEY
from .db import SessionLocal, get_db
from .models import ROLE_ADMIN, User
from .schemas import CurrentUser

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(subject: str, expires: timedelta = ACCESS_TOKEN_EXPIRE) -> str:
    expire = datetime.now(timezone.utc) + expires
    return jwt.encode({"sub": subject, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> CurrentUser:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise cred_exc
        user_id = int(sub)
    except (JWTError, TypeError, ValueError):
        # sub 非数字（异常/旧格式 token）应判为无效凭证并返回 401，
        # 而不是让 int() 的 ValueError 冒泡成 500
        raise cred_exc
    user = db.get(User, user_id)
    if user is None:
        raise cred_exc
    return CurrentUser.model_validate(user)


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """管理员专用依赖：非 admin 角色返回 403（任务书 §6.2 按角色控制访问权限）。"""
    if current_user.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
