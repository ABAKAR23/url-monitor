from fastapi import FastAPI

from app.api import auth, urls
from app.core.errors import register_exception_handlers

app = FastAPI(title="url-monitor")
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(urls.router)
