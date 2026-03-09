"""
Content API routes: articles, events, experts
Handles both admin (CRUD) and public (read) endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Query as QueryParam
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid as uuid_mod
import io
import logging

from supabase_client import get_supabase, supabase_query
from auth import AdminUser, get_current_user, require_admin
from translation import translate_article, translate_event

logger = logging.getLogger(__name__)

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
    disabled_languages: Optional[list] = None


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_date: str  # ISO format
    telegram_url: Optional[str] = None
    landing_url: Optional[str] = None
    image_url: Optional[str] = None
    language: str = "ru"
    is_active: bool = True
    registration_fields: Optional[list] = None
    notification_email: Optional[str] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[str] = None
    telegram_url: Optional[str] = None
    landing_url: Optional[str] = None
    image_url: Optional[str] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None
    disabled_languages: Optional[list] = None
    registration_fields: Optional[list] = None
    notification_email: Optional[str] = None


class EventRegister(BaseModel):
    user_name: Optional[str] = None
    user_surname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    device_id: Optional[str] = None
    platform: Optional[str] = None  # "ios" or "android"


class ExpertCreate(BaseModel):
    name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    user_id: Optional[str] = None


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
    insert_data = {
        "name": expert.name,
        "bio": expert.bio,
        "avatar_url": expert.avatar_url,
    }
    if expert.user_id:
        insert_data["user_id"] = expert.user_id
    result = sb.table("experts").insert(insert_data).execute()
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


# === Image Upload ===

@admin_router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    type: str = QueryParam("article", description="article, avatar, or event"),
    user: AdminUser = Depends(get_current_user)
):
    """Upload and resize an image, store in Supabase Storage.
    NOTE: No @supabase_query decorator here — file stream can only be read once,
    so retry logic would fail on the second attempt with empty bytes.
    """
    import os
    from PIL import Image

    logger.info(f"Upload image request: type={type}, filename={file.filename}, content_type={file.content_type}")

    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type {file.content_type} not allowed. Use JPEG, PNG or WebP.")

    # Read file (max 10MB)
    try:
        contents = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    logger.info(f"File read OK: {len(contents)} bytes")

    # Process with Pillow
    try:
        img = Image.open(io.BytesIO(contents))
        img = img.convert("RGB")  # Ensure RGB for JPEG output

        if type == "avatar":
            # Square center crop + resize to 256x256
            size = min(img.width, img.height)
            left = (img.width - size) // 2
            top = (img.height - size) // 2
            img = img.crop((left, top, left + size, top + size))
            img = img.resize((256, 256), Image.LANCZOS)
        else:
            # Article/event: max width 800px, keep aspect ratio
            if img.width > 800:
                ratio = 800 / img.width
                new_height = int(img.height * ratio)
                img = img.resize((800, new_height), Image.LANCZOS)

        # Save to bytes
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        image_bytes = buffer.getvalue()
        logger.info(f"Image processed OK: {img.width}x{img.height} -> {len(image_bytes)} bytes JPEG")
    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise HTTPException(status_code=400, detail=f"Image processing failed: {str(e)}")

    # Upload to Supabase Storage
    file_path = f"{type}/{uuid_mod.uuid4().hex}.jpg"
    sb = get_supabase()

    try:
        sb.storage.from_("content-images").upload(
            path=file_path,
            file=image_bytes,
            file_options={"content-type": "image/jpeg"}
        )
        logger.info(f"Storage upload OK: {file_path}")
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        # Try with fresh client once
        try:
            from supabase_client import reset_supabase
            reset_supabase()
            sb = get_supabase()
            sb.storage.from_("content-images").upload(
                path=file_path,
                file=image_bytes,
                file_options={"content-type": "image/jpeg"}
            )
            logger.info(f"Storage upload OK on retry: {file_path}")
        except Exception as e2:
            logger.error(f"Storage upload failed on retry: {e2}")
            raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e2)}")

    # Build public URL
    supabase_url = os.environ.get("SUPABASE_URL", "")
    public_url = f"{supabase_url}/storage/v1/object/public/content-images/{file_path}"

    return {"url": public_url}


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


@admin_router.post("/articles/{article_id}/refresh")
@supabase_query
async def refresh_article(
    article_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Mark article as 'new' by updating refreshed_at timestamp"""
    sb = get_supabase()
    result = sb.table("articles").update(
        {"refreshed_at": datetime.utcnow().isoformat()}
    ).eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"status": "refreshed", "article_id": article_id}


class TranslationUpdate(BaseModel):
    title: str
    body: Optional[str] = None
    description: Optional[str] = None


@admin_router.put("/articles/{article_id}/translations/{lang}")
@supabase_query
async def update_article_translation(
    article_id: str,
    lang: str,
    data: TranslationUpdate,
    user: AdminUser = Depends(get_current_user)
):
    """Update a specific language translation for an article"""
    sb = get_supabase()
    result = sb.table("articles").select("translations").eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")

    translations = result.data[0].get("translations") or {}
    translations[lang] = {"title": data.title, "body": data.body or ""}

    sb.table("articles").update({"translations": translations}).eq("id", article_id).execute()
    return {"status": "updated", "lang": lang}


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

    # Dual-write: landing_url is the primary field, telegram_url kept for backward compat
    landing = event.landing_url or event.telegram_url
    insert_data = {
        "title": event.title,
        "description": event.description,
        "event_date": event.event_date,
        "telegram_url": landing,
        "landing_url": landing,
        "image_url": event.image_url,
        "language": event.language,
        "is_active": event.is_active,
        "registration_fields": event.registration_fields or [],
        "notification_email": event.notification_email,
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

    # Dual-write: keep telegram_url in sync with landing_url for backward compat
    if "landing_url" in update_data:
        update_data["telegram_url"] = update_data["landing_url"]
    elif "telegram_url" in update_data:
        update_data["landing_url"] = update_data["telegram_url"]

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


@admin_router.put("/events/{event_id}/translations/{lang}")
@supabase_query
async def update_event_translation(
    event_id: str,
    lang: str,
    data: TranslationUpdate,
    user: AdminUser = Depends(get_current_user)
):
    """Update a specific language translation for an event"""
    sb = get_supabase()
    result = sb.table("events").select("translations").eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    translations = result.data[0].get("translations") or {}
    translations[lang] = {"title": data.title, "description": data.description or ""}

    sb.table("events").update({"translations": translations}).eq("id", event_id).execute()
    return {"status": "updated", "lang": lang}


@admin_router.post("/events/{event_id}/refresh")
@supabase_query
async def refresh_event(
    event_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Mark event as 'new' by updating refreshed_at timestamp"""
    sb = get_supabase()
    result = sb.table("events").update(
        {"refreshed_at": datetime.utcnow().isoformat()}
    ).eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "refreshed", "event_id": event_id}


@admin_router.post("/events/{event_id}/duplicate")
@supabase_query
async def duplicate_event(
    event_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Duplicate an event with '(копия)' suffix, set inactive"""
    sb = get_supabase()
    result = sb.table("events").select("*").eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    original = result.data[0]
    new_event = {
        "title": original["title"] + " (копия)",
        "description": original.get("description"),
        "event_date": original["event_date"],
        "telegram_url": original.get("telegram_url"),
        "landing_url": original.get("landing_url"),
        "image_url": original.get("image_url"),
        "language": original.get("language", "ru"),
        "is_active": False,
        "translations": original.get("translations"),
        "registration_fields": original.get("registration_fields"),
        "notification_email": original.get("notification_email"),
        "disabled_languages": original.get("disabled_languages", []),
    }

    insert_result = sb.table("events").insert(new_event).execute()
    if not insert_result.data:
        raise HTTPException(status_code=500, detail="Failed to duplicate event")

    return insert_result.data[0]


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
    Filters out articles disabled for the requested language.
    """
    sb = get_supabase()
    result = sb.table("articles").select(
        "id, title, body, image_url, language, translations, created_at, refreshed_at, disabled_languages, "
        "experts(id, name, avatar_url)"
    ).eq(
        "is_published", True
    ).order("created_at", desc=True).limit(limit).execute()

    articles = []
    for row in result.data:
        # Skip if article is disabled for this language
        disabled = row.get("disabled_languages") or []
        if lang in disabled:
            continue
        article = _localize_article(row, lang)
        articles.append(article)

    return articles


@public_router.get("/articles/{article_id}")
@supabase_query
async def public_get_article(article_id: str, lang: str = "ru"):
    """Get single article by ID"""
    sb = get_supabase()
    result = sb.table("articles").select(
        "id, title, body, image_url, language, translations, created_at, refreshed_at, disabled_languages, "
        "experts(id, name, avatar_url)"
    ).eq("id", article_id).eq("is_published", True).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")

    row = result.data[0]
    disabled = row.get("disabled_languages") or []
    if lang in disabled:
        raise HTTPException(status_code=404, detail="Article not available in this language")

    return _localize_article(row, lang)


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
        # Skip if event is disabled for this language
        disabled = row.get("disabled_languages") or []
        if lang in disabled:
            continue
        event = _localize_event(row, lang)
        events.append(event)

    return events


@public_router.post("/events/{event_id}/register")
@supabase_query
async def public_register_event(
    event_id: str,
    reg: EventRegister,
    background_tasks: BackgroundTasks
):
    """Register user for an event with dynamic fields"""
    sb = get_supabase()

    # Check event exists and is active
    event = sb.table("events").select(
        "id, title, telegram_url, landing_url, is_active, registration_fields, notification_email"
    ).eq("id", event_id).execute()

    if not event.data or not event.data[0].get("is_active"):
        raise HTTPException(status_code=404, detail="Event not found or inactive")

    event_data = event.data[0]

    # Validate required fields from registration_fields config
    reg_fields = event_data.get("registration_fields") or []
    for field_config in reg_fields:
        field_name = field_config.get("field")
        if field_config.get("required"):
            value = getattr(reg, field_name, None) if field_name else None
            if not value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field_name}' is required"
                )

    # Record registration
    click_data = {
        "event_id": event_id,
        "user_name": reg.user_name,
        "user_surname": reg.user_surname,
        "email": reg.email,
        "phone": reg.phone,
        "device_id": reg.device_id,
        "platform": reg.platform,
    }
    sb.table("event_clicks").insert(click_data).execute()

    # Send notification email in background
    notification_email = event_data.get("notification_email")
    if notification_email:
        background_tasks.add_task(
            _send_registration_email,
            event_data["title"],
            click_data,
            notification_email
        )

    return {
        "status": "registered",
        "telegram_url": event_data.get("telegram_url"),
        "landing_url": event_data.get("landing_url"),
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
        "refreshed_at": row.get("refreshed_at"),
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
        "landing_url": row.get("landing_url"),
        "image_url": row.get("image_url"),
        "is_active": row.get("is_active"),
        "refreshed_at": row.get("refreshed_at"),
        "registration_fields": row.get("registration_fields"),
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


async def _send_registration_email(event_title: str, registration_data: dict, to_email: str):
    """Background task: send email notification about new event registration"""
    import os
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.environ.get("SMTP_HOST", "mail.pomogaika.info")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "info@pomogaika.info")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_password:
        logger.warning("SMTP_PASSWORD not set, skipping registration email")
        return

    try:
        # Build email body
        name = f"{registration_data.get('user_name', '')} {registration_data.get('user_surname', '')}".strip() or "Не указано"
        email = registration_data.get('email') or "Не указан"
        phone = registration_data.get('phone') or "Не указан"
        platform = registration_data.get('platform') or "Не указана"

        body = f"""Новая регистрация на событие "{event_title}"

Имя: {name}
Email: {email}
Телефон: {phone}
Платформа: {platform}
"""

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = f"Новая регистрация: {event_title}"
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info(f"Registration email sent for event '{event_title}' to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send registration email: {e}")
