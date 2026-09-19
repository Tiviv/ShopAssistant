from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, customers, products

app = FastAPI(title="ShopAssistant API")

# allow_credentials=False is deliberate: the frontend authenticates with a
# Bearer token in the Authorization header, not cookies, so this isn't a
# "credentialed" request in the CORS sense — which means the wildcard origin
# below is safe (browsers only forbid "*" together with credentials), and
# local dev (including opening index.html directly as a file:// page, whose
# Origin is "null") doesn't need any per-origin configuration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(customers.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
