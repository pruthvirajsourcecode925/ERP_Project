from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, roles, sales, engineering, purchase, stores

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(sales.router)
api_router.include_router(engineering.router)
api_router.include_router(purchase.router)
api_router.include_router(stores.router)