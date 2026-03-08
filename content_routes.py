"""
Content API routes: articles, events, experts
Handles both admin (CRUD) and public (read) endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from supabase_client import get_supabase, supabase_query
from auth import AdminUser, get_current_user, require_admin
from translation import translate_article, translate_event

# === Routers ===

admin_router = APIRouter(prefix="/admin", tags=["admin"])
public_router = APIRouter(tags=["content"])


# === Pydantic Models ===

class LoginRequest(BaseModel):
    email: str
    password: str


class ArticleCreate(BaseModel):
    expert_id: str
    title: str
    body: str
    image_url: Optional[str] = None
    language: str = "ru"
    is_published: bool = False


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    image_url: Optional[str] = None
    language: Optional[str] = None
    is_published: Optional[bool] = None


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_date: str  # ISO format
    telegram_url: Optional[str] = None
    image_url: Optional[str] = None
    language: str = "ru"
    is_active: bool = True


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[str] = None
    telegram_url: Optional[str] = None
    image_url: Optional[str] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None


class EventRegister(BaseModel):
    user_name: str
    user_surname: str
    device_id: Optional[str] = None
    platform: Optional[str] = None  # "ios" or "android"


class ExpertCreate(BaseModel):
    name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str = "editor"  # "admin" or "editor"


class UserRoleUpdate(BaseModel):
    role: str  # "admin" or "editor"


# === Auth Endpoints ===

@admin_router.post("/login")
@supabase_query
async def admin_login(req: LoginRequest):
    """Login with email/password, returns JWT token + user role"""
    sb = get_supabase()

    try:
        auth_response = sb.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")

    if not auth_response.user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check admin_users table for role
    result = sb.table("admin_users").select("*").eq(
        "auth_user_id", auth_response.user.id
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="User exists but is not an admin or editor"
        )

    admin_data = result.data[0]

    return {
        "token": auth_response.session.access_token,
        "refresh_token": auth_response.session.refresh_token,
        "user": {
            "id": admin_data["id"],
            "email": admin_data["email"],
            "name": admin_data["name"],
            "role": admin_data["role"],
        }
    }


@admin_router.post("/refresh")
@supabase_query
async def refresh_token(refresh_token: str):
    """Refresh an expired JWT token"""
    sb = get_supabase()
    try:
        response = sb.auth.refresh_session(refresh_token)
        return {
            "token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Refresh failed: {str(e)}")


@admin_router.get("/me")
async def get_me(user: AdminUser = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {
        "email": user.email,
        "name": user.name,
        "role": user.role,
    }


# === Experts Endpoints ===

@admin_router.get("/experts")
@supabase_query
async def admin_list_experts(user: AdminUser = Depends(get_current_user)):
    """List all experts (admin)"""
    sb = get_supabase()
    result = sb.table("experts").select("*").order("created_at").execute()
    return result.data


@admin_router.post("/experts")
@supabase_query
async def create_expert(expert: ExpertCreate, user: AdminUser = Depends(require_admin)):
    """Create a new expert (admin only)"""
    sb = get_supabase()
    result = sb.table("experts").insert({
        "name": expert.name,
        "bio": expert.bio,
        "avatar_url": expert.avatar_url,
    }).execute()
    return result.data[0]


@admin_router.put("/experts/{expert_id}")
@supabase_query
async def update_expert(
    expert_id: str, expert: ExpertCreate,
    user: AdminUser = Depends(require_admin)
):
    """Update an expert (admin only)"""
    sb = get_supabase()
    update_data = {k: v for k, v in expert.model_dump().items() if v is not None}
    result = sb.table("experts").update(update_data).eq("id", expert_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Expert not found")
    return result.data[0]


# === Users Endpoints (admin only) ===

@admin_router.get("/users")
@supabase_query
async def admin_list_users(user: AdminUser = Depends(require_admin)):
    """List all admin users"""
    sb = get_supabase()
    result = sb.table("admin_users").select("*").order("created_at").execute()
    return result.data


@admin_router.post("/users")
@supabase_query
async def create_user(req: UserCreate, user: AdminUser = Depends(require_admin)):
    """Create a new admin/editor user via Supabase Auth"""
    sb = get_supabase()

    if req.role not in ("admin", "editor"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'editor'")

    # 1. Create user in Supabase Auth
    try:
        import httpx
        import os

        supabase_url = os.environ.get("SUPABASE_URL", "")
        service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{supabase_url}/auth/v1/admin/users",
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": req.email,
                    "password": req.password,
                    "email_confirm": True,
                },
            )

        if resp.status_code >= 400:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to create auth user: {resp.text}"
            )

        auth_user = resp.json()
        auth_user_id = auth_user["id"]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth creation failed: {str(e)}")

    # 2. Insert into admin_users table
    try:
        result = sb.table("admin_users").insert({
            "auth_user_id": auth_user_id,
            "email": req.email,
            "name": req.name,
            "role": req.role,
        }).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create admin user record")

        return result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB insert failed: {str(e)}")


@admin_router.put("/users/{user_id}")
@supabase_query
async def update_user_role(
    user_id: str, req: UserRoleUpdate,
    user: AdminUser = Depends(require_admin)
):
    """Update user role (admin only)"""
    if req.role not in ("admin", "editor"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'editor'")

    sb = get_supabase()
    result = sb.table("admin_users").update(
        {"role": req.role}
    ).eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    return result.data[0]


# === Articles Endpoints ===

@admin_router.get("/articles")
@supabase_query
async def admin_list_articles(user: AdminUser = Depends(get_current_user)):
    """List all articles with expert info (admin)"""
    sb = get_supabase()
    result = sb.table("articles").select(
        "*, experts(id, name, avatar_url)"
    ).order("created_at", desc=True).execute()
    return result.data


@admin_router.post("/articles")
@supabase_query
async def create_article(
    article: ArticleCreate,
    background_tasks: BackgroundTasks,
    user: AdminUser = Depends(get_current_user)
):
    """Create article. Auto-translates in background if published."""
    sb = get_supabase()

    insert_data = {
        "expert_id": article.expert_id,
        "title": article.title,
        "body": article.body,
        "image_url": article.image_url,
        "language": article.language,
        "is_published": article.is_published,
    }
    result = sb.table("articles").insert(insert_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create article")

    new_article = result.data[0]

    # Auto-translate if published
    if article.is_published:
        background_tasks.add_task(
            _translate_article_task, new_article["id"],
            article.title, article.body, article.language
        )

    return new_article


@admin_router.put("/articles/{article_id}")
@supabase_query
async def update_article(
    article_id: str,
    article: ArticleUpdate,
    background_tasks: BackgroundTasks,
    user: AdminUser = Depends(get_current_user)
):
    """Update article. Re-translates if title/body changed and article is published."""
    sb = get_supabase()
    update_data = {k: v for k, v in article.model_dump().items() if v is not None}

    result = sb.table("articles").update(update_data).eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")

    updated = result.data[0]

    # Re-translate if content changed and article is published
    needs_translation = (article.title or article.body) and updated.get("is_published")
    if needs_translation:
        background_tasks.add_task(
            _translate_article_task, article_id,
            updated["title"], updated["body"], updated["language"]
        )

    return updated


@admin_router.delete("/articles/{article_id}")
@supabase_query
async def delete_article(
    article_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Delete article"""
    sb = get_supabase()
    sb.table("articles").delete().eq("id", article_id).execute()
    return {"status": "deleted"}


@admin_router.post("/articles/{article_id}/translate")
@supabase_query
async def translate_article_manual(
    article_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Manually trigger translation for an article"""
    sb = get_supabase()
    result = sb.table("articles").select("*").eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")

    article = result.data[0]
    translations = await translate_article(
        article["title"], article["body"], article["language"]
    )

    # Save translations
    sb.table("articles").update({"translations": translations}).eq("id", article_id).execute()

    return {
        "status": "translated",
        "languages": list(translations.keys()),
        "article_id": article_id,
    }


# === Events Endpoints ===

@admin_router.get("/events")
@supabase_query
async def admin_list_events(user: AdminUser = Depends(get_current_user)):
    """List all events (admin)"""
    sb = get_supabase()
    result = sb.table("events").select("*").order("event_date", desc=True).execute()
    return result.data


@admin_router.post("/events")
@supabase_query
async def create_event(
    event: EventCreate,
    background_tasks: BackgroundTasks,
    user: AdminUser = Depends(get_current_user)
):
    """Create event. Auto-translates in background."""
    sb = get_supabase()

    insert_data = {
        "title": event.title,
        "description": event.description,
        "event_date": event.event_date,
        "telegram_url": event.telegram_url,
        "image_url": event.image_url,
        "language": event.language,
        "is_active": event.is_active,
    }
    result = sb.table("events").insert(insert_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create event")

    new_event = result.data[0]

    # Auto-translate
    background_tasks.add_task(
        _translate_event_task, new_event["id"],
        event.title, event.description, event.language
    )

    return new_event


@admin_router.put("/events/{event_id}")
@supabase_query
async def update_event(
    event_id: str,
    event: EventUpdate,
    background_tasks: BackgroundTasks,
    user: AdminUser = Depends(get_current_user)
):
    """Update event. Re-translates if content changed."""
    sb = get_supabase()
    update_data = {k: v for k, v in event.model_dump().items() if v is not None}

    result = sb.table("events").update(update_data).eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    updated = result.data[0]

    # Re-translate if content changed
    if event.title or event.description:
        background_tasks.add_task(
            _translate_event_task, event_id,
            updated["title"], updated.get("description"), updated["language"]
        )

    return updated


@admin_router.delete("/events/{event_id}")
@supabase_query
async def delete_event(
    event_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Delete event"""
    sb = get_supabase()
    sb.table("events").delete().eq("id", event_id).execute()
    return {"status": "deleted"}


@admin_router.post("/events/{event_id}/translate")
@supabase_query
async def translate_event_manual(
    event_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Manually trigger translation for an event"""
    sb = get_supabase()
    result = sb.table("events").select("*").eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event = result.data[0]
    translations = await translate_event(
        event["title"], event.get("description"), event["language"]
    )

    sb.table("events").update({"translations": translations}).eq("id", event_id).execute()

    return {
        "status": "translated",
        "languages": list(translations.keys()),
        "event_id": event_id,
    }


# === Event Clicks (admin stats) ===

@admin_router.get("/event-clicks")
@supabase_query
async def list_event_clicks(
    event_id: Optional[str] = None,
    user: AdminUser = Depends(require_admin)
):
    """View event registrations/clicks (admin only)"""
    sb = get_supabase()
    query = sb.table("event_clicks").select(
        "*, events(id, title)"
    ).order("clicked_at", desc=True)

    if event_id:
        query = query.eq("event_id", event_id)

    result = query.execute()
    return result.data


@admin_router.get("/event-clicks/stats")
@supabase_query
async def event_clicks_stats(user: AdminUser = Depends(require_admin)):
    """Aggregated stats for all events (admin only)"""
    sb = get_supabase()

    # Get all events with click counts
    events = sb.table("events").select("id, title, event_date, is_active").order(
        "event_date", desc=True
    ).execute()

    stats = []
    for event in events.data:
        clicks = sb.table("event_clicks").select(
            "id", count="exact"
        ).eq("event_id", event["id"]).execute()

        stats.append({
            "event_id": event["id"],
            "title": event["title"],
            "event_date": event["event_date"],
            "is_active": event["is_active"],
            "click_count": clicks.count or 0,
        })

    return stats


# === Public Endpoints (for mobile apps & website) ===

@public_router.get("/articles")
@supabase_query
async def public_list_articles(lang: str = "ru", limit: int = 10):
    """
    Get published articles for mobile apps.
    Returns articles with expert info, translated to requested language.
    """
    sb = get_supabase()
    result = sb.table("articles").select(
        "id, title, body, image_url, language, translations, created_at, "
        "experts(id, name, avatar_url)"
    ).eq(
        "is_published", True
    ).order("created_at", desc=True).limit(limit).execute()

    articles = []
    for row in result.data:
        article = _localize_article(row, lang)
        articles.append(article)

    return articles


@public_router.get("/articles/{article_id}")
@supabase_query
async def public_get_article(article_id: str, lang: str = "ru"):
    """Get single article by ID"""
    sb = get_supabase()
    result = sb.table("articles").select(
        "id, title, body, image_url, language, translations, created_at, "
        "experts(id, name, avatar_url)"
    ).eq("id", article_id).eq("is_published", True).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")

    return _localize_article(result.data[0], lang)


@public_router.get("/events/active")
@supabase_query
async def public_active_events(lang: str = "ru"):
    """Get active upcoming events for mobile apps"""
    sb = get_supabase()
    result = sb.table("events").select("*").eq(
        "is_active", True
    ).gte(
        "event_date", datetime.utcnow().isoformat()
    ).order("event_date").execute()

    events = []
    for row in result.data:
        event = _localize_event(row, lang)
        events.append(event)

    return events


@public_router.post("/events/{event_id}/register")
@supabase_query
async def public_register_event(event_id: str, reg: EventRegister):
    """Register user interest in an event (click-through to Telegram)"""
    sb = get_supabase()

    # Check event exists and is active
    event = sb.table("events").select("id, telegram_url, is_active").eq(
        "id", event_id
    ).execute()

    if not event.data or not event.data[0].get("is_active"):
        raise HTTPException(status_code=404, detail="Event not found or inactive")

    # Record click
    sb.table("event_clicks").insert({
        "event_id": event_id,
        "user_name": reg.user_name,
        "user_surname": reg.user_surname,
        "device_id": reg.device_id,
        "platform": reg.platform,
    }).execute()

    return {
        "status": "registered",
        "telegram_url": event.data[0].get("telegram_url"),
    }


@public_router.get("/experts")
@supabase_query
async def public_list_experts():
    """Get list of wine experts"""
    sb = get_supabase()
    result = sb.table("experts").select("id, name, bio, avatar_url").execute()
    return result.data


# === Helper Functions ===

def _localize_article(row: dict, lang: str) -> dict:
    """Return article with title/body in requested language"""
    translations = row.get("translations") or {}
    source_lang = row.get("language", "ru")

    if lang == source_lang or lang not in translations:
        title = row["title"]
        body = row["body"]
    else:
        t = translations[lang]
        title = t.get("title", row["title"])
        body = t.get("body", row["body"])

    return {
        "id": row["id"],
        "title": title,
        "body": body,
        "image_url": row.get("image_url"),
        "created_at": row["created_at"],
        "expert": row.get("experts"),
    }


def _localize_event(row: dict, lang: str) -> dict:
    """Return event with title/description in requested language"""
    translations = row.get("translations") or {}
    source_lang = row.get("language", "ru")

    if lang == source_lang or lang not in translations:
        title = row["title"]
        description = row.get("description")
    else:
        t = translations[lang]
        title = t.get("title", row["title"])
        description = t.get("description", row.get("description"))

    return {
        "id": row["id"],
        "title": title,
        "description": description,
        "event_date": row["event_date"],
        "telegram_url": row.get("telegram_url"),
        "image_url": row.get("image_url"),
        "is_active": row.get("is_active"),
    }


# === Background Tasks ===

async def _translate_article_task(article_id: str, title: str, body: str, language: str):
    """Background task: translate article and save to DB"""
    try:
        translations = await translate_article(title, body, language)
        if translations:
            sb = get_supabase()
            sb.table("articles").update(
                {"translations": translations}
            ).eq("id", article_id).execute()
    except Exception as e:
        import logging
        logging.error(f"Background translation failed for article {article_id}: {e}")


async def _translate_event_task(event_id: str, title: str, description: str | None, language: str):
    """Background task: translate event and save to DB"""
    try:
        translations = await translate_event(title, description, language)
        if translations:
            sb = get_supabase()
            sb.table("events").update(
                {"translations": translations}
            ).eq("id", event_id).execute()
    except Exception as e:
        import logging
        logging.error(f"Background translation failed for event {event_id}: {e}")
