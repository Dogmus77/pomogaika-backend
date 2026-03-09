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

# Set to hold references to background asyncio tasks (prevents garbage collection)
_background_tasks: set = set()

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


class ContentView(BaseModel):
    device_id: Optional[str] = None
    platform: Optional[str] = None  # "ios", "android", "web"


class QuickRegister(BaseModel):
    device_id: str
    platform: Optional[str] = None  # "ios", "android"


class ContentReaction(BaseModel):
    device_id: str
    reaction: str  # "like" or "dislike"


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
        import asyncio
        task = asyncio.create_task(
            _translate_article_task_async(new_article["id"],
            article.title, article.body, article.language)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

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
        import asyncio
        task = asyncio.create_task(
            _translate_article_task_async(article_id,
            updated["title"], updated["body"], updated["language"])
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

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
async def translate_article_manual(
    article_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Manually trigger translation for an article (runs in background via asyncio task)"""
    sb = get_supabase()
    result = sb.table("articles").select("*").eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")

    article = result.data[0]
    # Use asyncio.create_task instead of BackgroundTasks (more reliable for async work)
    import asyncio
    task = asyncio.create_task(
        _translate_article_task_async(article["id"],
        article["title"], article["body"], article["language"])
    )
    # Store reference to prevent garbage collection
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "status": "translation_started",
        "message": "Перевод запущен в фоне. Обновите страницу через 30-60 секунд.",
        "article_id": article_id,
    }


@admin_router.post("/articles/{article_id}/translate-sync")
async def translate_article_sync_test(
    article_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """DEBUG: Run translation synchronously and return detailed diagnostics."""
    import httpx

    sb = get_supabase()
    result = sb.table("articles").select("*").eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")

    article = result.data[0]
    diagnostics = {
        "article_id": article_id,
        "language": article["language"],
        "title_len": len(article["title"]),
        "body_len": len(article["body"]),
    }

    # Step 1: Test raw MyMemory API call with a simple short text
    test_text = "Привет мир"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.mymemory.translated.net/get",
                data={
                    "q": test_text,
                    "langpair": "ru-RU|en-GB",
                    "de": "pomogaika.app@gmail.com",
                }
            )
            raw = resp.json()
            diagnostics["mymemory_test"] = {
                "status_code": resp.status_code,
                "response_status": raw.get("responseStatus"),
                "translated": raw.get("responseData", {}).get("translatedText", ""),
                "quota_finished": raw.get("quotaFinished", False),
                "raw_keys": list(raw.keys()),
            }
    except Exception as e:
        diagnostics["mymemory_test"] = {"error": str(e)}

    # Step 2: Try full translation
    try:
        translations = await translate_article(article["title"], article["body"], article["language"])
        diagnostics["full_translate"] = {
            "languages": list(translations.keys()) if translations else [],
            "count": len(translations) if translations else 0,
        }
        if translations:
            sb.table("articles").update(
                {"translations": translations}
            ).eq("id", article_id).execute()
            diagnostics["saved"] = True
    except Exception as e:
        diagnostics["full_translate"] = {"error": str(e)}

    return diagnostics


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


@admin_router.post("/articles/generate")
async def generate_article(
    background_tasks: BackgroundTasks,
    user: AdminUser = Depends(require_admin)
):
    """Generate a new wine article using Claude AI. Returns immediately, generates in background."""
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    background_tasks.add_task(_generate_article_task, api_key)
    return {"status": "generation_started", "message": "Article is being generated in background"}


async def _generate_article_task(api_key: str):
    """Background task: generate article with Claude, save to DB, auto-translate."""
    import anthropic

    try:
        sb = get_supabase()

        # Get existing article titles to avoid duplicates
        existing = sb.table("articles").select("title").execute()
        existing_titles = [a["title"] for a in (existing.data or [])]
        titles_list = "\n".join(f"- {t}" for t in existing_titles) if existing_titles else "Нет статей"

        # Get Николай expert ID
        experts = sb.table("experts").select("id, name").execute()
        nikolay = next((e for e in (experts.data or []) if "Николай" in e.get("name", "") or "николай" in e.get("name", "").lower()), None)
        if not nikolay:
            logger.error("Generate article: expert 'Николай' not found")
            return
        expert_id = nikolay["id"]

        # Generate with Claude
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""Ты — Николай, AI-сомелье и винный эксперт с 15-летним стажем. Ты пишешь статьи для приложения Pomogaika — помощник по выбору вина в испанских супермаркетах (Consum, Mercadona, Masymas, DIA, Condis).

Напиши новую статью о вине на русском языке. Статья должна быть:
- Полезной и практичной для людей, покупающих вино в супермаркетах Испании
- Длиной 500-800 слов
- С использованием **жирного** и *курсивного* текста для выделения ключевых моментов (markdown)
- Написана простым и дружелюбным языком, без снобизма
- Про конкретную тему (сорта винограда, регионы Испании, сочетания с едой, сезонные рекомендации, как выбрать вино по случаю, и т.д.)
- ВАЖНО: между абзацами ОБЯЗАТЕЛЬНО оставляй пустую строку (двойной перенос). Каждый подзаголовок должен быть на отдельной строке с пустыми строками до и после него. Текст должен быть хорошо структурирован и легко читаем.

Уже существующие статьи (НЕ повторяй их темы):
{titles_list}

Ответь СТРОГО в формате:
TITLE: Заголовок статьи
IMAGE: ключевое слово для поиска фото на unsplash (на английском, 1-2 слова про вино)
BODY:
Текст статьи..."""
            }]
        )

        response_text = message.content[0].text.strip()

        # Parse response
        title = ""
        image_keyword = "wine"
        body = ""

        lines = response_text.split("\n")
        mode = None
        body_lines = []

        for line in lines:
            if line.startswith("TITLE:"):
                title = line[6:].strip()
                mode = "title"
            elif line.startswith("IMAGE:"):
                image_keyword = line[6:].strip()
                mode = "image"
            elif line.startswith("BODY:"):
                mode = "body"
            elif mode == "body":
                body_lines.append(line)

        body = "\n".join(body_lines).strip()

        # Post-process: ensure proper paragraph breaks for markdown rendering
        # CommonMark treats single \n as soft break (space), need \n\n for paragraphs
        import re
        # Normalize: any sequence of 1+ newlines → exactly \n\n (paragraph break)
        body = re.sub(r'\n{1,}', '\n\n', body)
        # Ensure blank line before bold headers like **Заголовок**
        body = re.sub(r'([^\n])\n\n(\*\*)', r'\1\n\n\2', body)
        # Remove leading/trailing whitespace
        body = body.strip()

        if not title or not body:
            logger.error(f"Generate article: failed to parse response. Title='{title}', body length={len(body)}")
            return

        # Unsplash wine image pool — pick a random one, prefer unused
        import random
        WINE_PHOTO_POOL = [
            "photo-1510812431401-41d2bd2722f3",  # wine glass close-up
            "photo-1506377247377-2a5b3b417ebb",   # wine pouring
            "photo-1474722883778-792e7990302f",   # wine bottles on shelf
            "photo-1553361371-9b22f78e8b1d",   # wine cellar barrels
            "photo-1516594915697-87eb3b1c14ea",   # red wine glass on table
            "photo-1567529692333-de9fd6772897",   # vineyard landscape
            "photo-1504279577054-acfeccf8fc52",   # wine tasting setup
            "photo-1558642452-9d2a7deb7f62",   # wine and cheese pairing
            "photo-1528823872057-9c018a7a7553",   # wine cork and bottle
            "photo-1543418219-0e518d919e55",   # wine glasses cheers
            "photo-1586370434639-0fe43b2d32e6",   # grapes on vine
            "photo-1423483641154-5411ec9c0ddf",   # red wine close-up
        ]
        # Check which images are already used by existing articles
        used_urls = set(a.get("image_url", "") for a in (existing.data or []))
        available_photos = [p for p in WINE_PHOTO_POOL if f"https://images.unsplash.com/{p}?w=800&q=80" not in used_urls]
        if not available_photos:
            available_photos = WINE_PHOTO_POOL  # All used — reset pool
        chosen_photo = random.choice(available_photos)
        image_url = f"https://images.unsplash.com/{chosen_photo}?w=800&q=80"

        # Save article (as draft)
        insert_data = {
            "expert_id": expert_id,
            "title": title,
            "body": body,
            "image_url": image_url,
            "language": "ru",
            "is_published": False,
        }
        result = sb.table("articles").insert(insert_data).execute()

        if result.data:
            article_id = result.data[0]['id']
            logger.info(f"Generated article: '{title}' (id: {article_id})")
            # Auto-translate the generated article
            try:
                translations = await translate_article(title, body, "ru")
                if translations:
                    sb.table("articles").update(
                        {"translations": translations}
                    ).eq("id", article_id).execute()
                    logger.info(f"Auto-translated generated article {article_id}: {list(translations.keys())}")
            except Exception as te:
                logger.error(f"Auto-translate failed for generated article {article_id}: {te}")
        else:
            logger.error("Generate article: failed to insert into DB")

    except Exception as e:
        logger.error(f"Generate article error: {e}")


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
    import asyncio
    task = asyncio.create_task(
        _translate_event_task_async(new_event["id"],
        event.title, event.description, event.language)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

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
        import asyncio
        task = asyncio.create_task(
            _translate_event_task_async(event_id,
            updated["title"], updated.get("description"), updated["language"])
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

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
async def translate_event_manual(
    event_id: str,
    user: AdminUser = Depends(get_current_user)
):
    """Manually trigger translation for an event (runs in background via asyncio task)"""
    sb = get_supabase()
    result = sb.table("events").select("*").eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event = result.data[0]
    import asyncio
    task = asyncio.create_task(
        _translate_event_task_async(event["id"],
        event["title"], event.get("description"), event["language"])
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "status": "translation_started",
        "message": "Перевод запущен в фоне. Обновите страницу через 30-60 секунд.",
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


# === View Stats (admin) ===

@admin_router.get("/article-views/stats")
@supabase_query
async def article_views_stats(user: AdminUser = Depends(require_admin)):
    """Aggregated article view stats (admin only)"""
    sb = get_supabase()

    articles = sb.table("articles").select(
        "id, title, is_published, created_at"
    ).order("created_at", desc=True).execute()

    # Global unique readers (distinct device_id across ALL article views)
    all_views = sb.table("article_views").select("device_id").execute()
    total_unique = len(set(
        v["device_id"] for v in all_views.data if v.get("device_id")
    ))

    stats = []
    for article in articles.data:
        # Total views
        views = sb.table("article_views").select(
            "id", count="exact"
        ).eq("article_id", article["id"]).execute()

        # Unique viewers (distinct device_id)
        unique_views = sb.table("article_views").select(
            "device_id"
        ).eq("article_id", article["id"]).execute()
        unique_count = len(set(
            v["device_id"] for v in unique_views.data if v.get("device_id")
        ))

        # Reactions
        reactions = sb.table("content_reactions").select("reaction").eq(
            "content_type", "article"
        ).eq("content_id", article["id"]).execute()
        likes = sum(1 for r in reactions.data if r["reaction"] == "like")
        dislikes = sum(1 for r in reactions.data if r["reaction"] == "dislike")

        stats.append({
            "article_id": article["id"],
            "title": article["title"],
            "is_published": article["is_published"],
            "created_at": article["created_at"],
            "view_count": views.count or 0,
            "unique_viewers": unique_count,
            "likes": likes,
            "dislikes": dislikes,
        })

    return {"stats": stats, "total_unique_readers": total_unique}


@admin_router.get("/event-views/stats")
@supabase_query
async def event_views_stats(user: AdminUser = Depends(require_admin)):
    """Aggregated event view + registration stats (admin only)"""
    sb = get_supabase()

    events = sb.table("events").select(
        "id, title, event_date, is_active"
    ).order("event_date", desc=True).execute()

    # Global unique viewers (distinct device_id across ALL event views)
    all_views = sb.table("event_views").select("device_id").execute()
    total_unique = len(set(
        v["device_id"] for v in all_views.data if v.get("device_id")
    ))

    stats = []
    for event in events.data:
        # Total views
        views = sb.table("event_views").select(
            "id", count="exact"
        ).eq("event_id", event["id"]).execute()

        # Unique viewers
        unique_views = sb.table("event_views").select(
            "device_id"
        ).eq("event_id", event["id"]).execute()
        unique_count = len(set(
            v["device_id"] for v in unique_views.data if v.get("device_id")
        ))

        # Registration count from event_clicks
        clicks = sb.table("event_clicks").select(
            "id", count="exact"
        ).eq("event_id", event["id"]).execute()

        # Reactions
        reactions = sb.table("content_reactions").select("reaction").eq(
            "content_type", "event"
        ).eq("content_id", event["id"]).execute()
        likes = sum(1 for r in reactions.data if r["reaction"] == "like")
        dislikes = sum(1 for r in reactions.data if r["reaction"] == "dislike")

        stats.append({
            "event_id": event["id"],
            "title": event["title"],
            "event_date": event["event_date"],
            "is_active": event["is_active"],
            "view_count": views.count or 0,
            "unique_viewers": unique_count,
            "registration_count": clicks.count or 0,
            "likes": likes,
            "dislikes": dislikes,
        })

    return {"stats": stats, "total_unique_viewers": total_unique}


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


@public_router.post("/articles/{article_id}/view")
@supabase_query
async def track_article_view(article_id: str, view: ContentView):
    """Track article view from mobile app. Deduplicates by device_id per 24h."""
    sb = get_supabase()

    # Dedup: same device, same article, last 24h
    if view.device_id:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        existing = sb.table("article_views").select("id", count="exact").eq(
            "article_id", article_id
        ).eq("device_id", view.device_id).gte("viewed_at", cutoff).execute()

        if existing.count and existing.count > 0:
            return {"status": "duplicate"}

    sb.table("article_views").insert({
        "article_id": article_id,
        "device_id": view.device_id,
        "platform": view.platform,
    }).execute()

    return {"status": "ok"}


@public_router.post("/events/{event_id}/view")
@supabase_query
async def track_event_view(event_id: str, view: ContentView):
    """Track event view from mobile app. Deduplicates by device_id per 24h."""
    sb = get_supabase()

    if view.device_id:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        existing = sb.table("event_views").select("id", count="exact").eq(
            "event_id", event_id
        ).eq("device_id", view.device_id).gte("viewed_at", cutoff).execute()

        if existing.count and existing.count > 0:
            return {"status": "duplicate"}

    sb.table("event_views").insert({
        "event_id": event_id,
        "device_id": view.device_id,
        "platform": view.platform,
    }).execute()

    return {"status": "ok"}


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
        # Add attendees count
        clicks = sb.table("event_clicks").select("id", count="exact").eq(
            "event_id", row["id"]
        ).execute()
        event["attendees_count"] = clicks.count or 0
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


# === Quick Register (one-tap "I'm going") ===

@public_router.post("/events/{event_id}/quick-register")
@supabase_query
async def quick_register_event(event_id: str, reg: QuickRegister):
    """One-tap event registration by device_id (no form fields needed)"""
    sb = get_supabase()

    # Check event exists
    event = sb.table("events").select("id, is_active").eq("id", event_id).execute()
    if not event.data or not event.data[0].get("is_active"):
        raise HTTPException(status_code=404, detail="Event not found or inactive")

    # Check if already registered
    existing = sb.table("event_clicks").select("id", count="exact").eq(
        "event_id", event_id
    ).eq("device_id", reg.device_id).execute()

    if existing.count and existing.count > 0:
        return {"status": "already_registered"}

    # Register
    sb.table("event_clicks").insert({
        "event_id": event_id,
        "device_id": reg.device_id,
        "platform": reg.platform,
    }).execute()

    return {"status": "registered"}


@public_router.get("/events/{event_id}/check-registration")
@supabase_query
async def check_event_registration(event_id: str, device_id: str):
    """Check if device is registered for event"""
    sb = get_supabase()
    existing = sb.table("event_clicks").select("id", count="exact").eq(
        "event_id", event_id
    ).eq("device_id", device_id).execute()
    return {"registered": bool(existing.count and existing.count > 0)}


# === Content Reactions (like / dislike) ===

@public_router.post("/articles/{article_id}/react")
@supabase_query
async def react_to_article(article_id: str, data: ContentReaction):
    """Like or dislike an article. Upserts: replaces previous reaction."""
    sb = get_supabase()

    # Check if reaction exists
    existing = sb.table("content_reactions").select("id, reaction").eq(
        "content_type", "article"
    ).eq("content_id", article_id).eq("device_id", data.device_id).execute()

    if existing.data:
        if existing.data[0]["reaction"] == data.reaction:
            # Same reaction — remove it (toggle off)
            sb.table("content_reactions").delete().eq("id", existing.data[0]["id"]).execute()
            return {"status": "removed"}
        else:
            # Different reaction — update
            sb.table("content_reactions").update(
                {"reaction": data.reaction}
            ).eq("id", existing.data[0]["id"]).execute()
            return {"status": "updated"}
    else:
        # New reaction
        sb.table("content_reactions").insert({
            "content_type": "article",
            "content_id": article_id,
            "device_id": data.device_id,
            "reaction": data.reaction,
        }).execute()
        return {"status": "created"}


@public_router.post("/events/{event_id}/react")
@supabase_query
async def react_to_event(event_id: str, data: ContentReaction):
    """Like or dislike an event. Upserts: replaces previous reaction."""
    sb = get_supabase()

    existing = sb.table("content_reactions").select("id, reaction").eq(
        "content_type", "event"
    ).eq("content_id", event_id).eq("device_id", data.device_id).execute()

    if existing.data:
        if existing.data[0]["reaction"] == data.reaction:
            sb.table("content_reactions").delete().eq("id", existing.data[0]["id"]).execute()
            return {"status": "removed"}
        else:
            sb.table("content_reactions").update(
                {"reaction": data.reaction}
            ).eq("id", existing.data[0]["id"]).execute()
            return {"status": "updated"}
    else:
        sb.table("content_reactions").insert({
            "content_type": "event",
            "content_id": event_id,
            "device_id": data.device_id,
            "reaction": data.reaction,
        }).execute()
        return {"status": "created"}


@public_router.get("/articles/{article_id}/reactions")
@supabase_query
async def get_article_reactions(article_id: str, device_id: str = ""):
    """Get reaction counts and current user's reaction for an article"""
    sb = get_supabase()
    all_reactions = sb.table("content_reactions").select("reaction, device_id").eq(
        "content_type", "article"
    ).eq("content_id", article_id).execute()

    likes = sum(1 for r in all_reactions.data if r["reaction"] == "like")
    dislikes = sum(1 for r in all_reactions.data if r["reaction"] == "dislike")
    my_reaction = None
    if device_id:
        for r in all_reactions.data:
            if r["device_id"] == device_id:
                my_reaction = r["reaction"]
                break

    return {"likes": likes, "dislikes": dislikes, "my_reaction": my_reaction}


@public_router.get("/events/{event_id}/reactions")
@supabase_query
async def get_event_reactions(event_id: str, device_id: str = ""):
    """Get reaction counts and current user's reaction for an event"""
    sb = get_supabase()
    all_reactions = sb.table("content_reactions").select("reaction, device_id").eq(
        "content_type", "event"
    ).eq("content_id", event_id).execute()

    likes = sum(1 for r in all_reactions.data if r["reaction"] == "like")
    dislikes = sum(1 for r in all_reactions.data if r["reaction"] == "dislike")
    my_reaction = None
    if device_id:
        for r in all_reactions.data:
            if r["device_id"] == device_id:
                my_reaction = r["reaction"]
                break

    return {"likes": likes, "dislikes": dislikes, "my_reaction": my_reaction}


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

async def _translate_article_task_async(article_id: str, title: str, body: str, language: str):
    """Async background task: translate article and save to DB.
    Called via asyncio.create_task() from endpoints.
    """
    try:
        logger.info(f"Starting translation for article {article_id} (body_len={len(body)})...")
        translations = await translate_article(title, body, language)
        if translations:
            sb = get_supabase()
            sb.table("articles").update(
                {"translations": translations}
            ).eq("id", article_id).execute()
            logger.info(f"Translation completed for article {article_id}: {list(translations.keys())}")
        else:
            logger.warning(f"Translation returned empty for article {article_id}")
    except Exception as e:
        logger.error(f"Translation failed for article {article_id}: {e}", exc_info=True)


async def _translate_event_task_async(event_id: str, title: str, description: str | None, language: str):
    """Async background task: translate event and save to DB.
    Called via asyncio.create_task() from endpoints.
    """
    try:
        logger.info(f"Starting translation for event {event_id}...")
        translations = await translate_event(title, description, language)
        if translations:
            sb = get_supabase()
            sb.table("events").update(
                {"translations": translations}
            ).eq("id", event_id).execute()
            logger.info(f"Translation completed for event {event_id}: {list(translations.keys())}")
        else:
            logger.warning(f"Translation returned empty for event {event_id}")
    except Exception as e:
        logger.error(f"Translation failed for event {event_id}: {e}", exc_info=True)


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
