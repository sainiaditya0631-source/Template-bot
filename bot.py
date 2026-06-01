import os
import re
import asyncio
import aiohttp
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

BOT_TOKEN    = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
CHANNEL_NAME = "@CRQ_Hub"
CHANNEL_LINK = "https://t.me/lcT_6ZRmUF9kNDA1"
TMDB_BASE    = "https://api.themoviedb.org/3"
TMDB_IMG     = "https://image.tmdb.org/t/p/w500"
DELETE_AFTER = 5 * 60

MEDIA_EXTS = (
    '.mkv', '.mp4', '.avi', '.mov', '.wmv',
    '.flv', '.webm', '.m4v', '.ts', '.3gp'
)


# ══════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════

def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.0f} MB"
    return f"{size_bytes / 1024:.0f} KB"


def get_file_info(msg) -> tuple:
    if msg.video:
        return msg.video.file_id, "video", msg.video.file_size or 0
    elif msg.document:
        return (msg.document.file_id, "document",
                msg.document.file_size or 0)
    elif msg.audio:
        return (msg.audio.file_id, "audio",
                msg.audio.file_size or 0)
    elif msg.photo:
        p = msg.photo[-1]
        return p.file_id, "photo", p.file_size or 0
    elif msg.animation:
        return (msg.animation.file_id, "animation",
                msg.animation.file_size or 0)
    return None, None, 0


async def schedule_delete(ctx, chat_id: int, *msg_ids: int):
    await asyncio.sleep(DELETE_AFTER)
    for mid in msg_ids:
        try:
            await ctx.bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def delete_and_notify(
    ctx, chat_id: int, msg_id: int, key: str
):
    await asyncio.sleep(DELETE_AFTER)
    try:
        await ctx.bot.delete_message(chat_id, msg_id)
    except Exception:
        pass
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "📥 GET FILE AGAIN 📥", callback_data=f"gf_{key}"
    )]])
    try:
        await ctx.bot.send_message(
            chat_id,
            "🗑 <b>File deleted!</b>\n\nWant it again? 👇",
            parse_mode="HTML", reply_markup=kb
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════
#  TMDB CAPTION BUILDER
# ══════════════════════════════════════════════════

def build_tmdb_caption(d: dict) -> str:
    genres  = ", ".join(d.get("genres", [])) or "N/A"
    rating  = d.get("rating", "N/A")
    year    = d.get("year", "N/A")
    lang    = d.get("language", "N/A").upper()
    extra   = d.get("additional", "")

    extra_line = (
        f'\n➕ <b>{extra}</b>' if extra else ""
    )

    return (
        f'╔══【 🎬 MOVIE INFO 】══╗\n\n'
        f'⚡ <b>Uploaded by :</b> '
        f'<a href="{CHANNEL_LINK}"><b>{CHANNEL_NAME}</b></a>\n'
        f'▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n'
        + (f'🎭 <b>Name :</b>  {d["name"]}\n' if d.get("name") else "")
        + (f'📅 <b>Year :</b>  {year}\n' if year else "")
        + (f'⭐ <b>Rating :</b>  {rating} / 10\n' if rating else "")
        + (f'🌐 <b>Language :</b>  {lang}\n' if lang else "")
        + (f'🎪 <b>Genre :</b>  {genres}\n' if genres else "")
        + (f'⏱ <b>Duration :</b>  {d.get("duration", "N/A")}' if d.get("duration") else "")
        + (extra_line + "\n" if extra_line else "\n")
        + '▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n'
        + (f'🎙 <b>Audio :</b>  {d.get("audio")}\n' if d.get("audio") else "")
        + (f'💿 <b>Quality :</b>  {d.get("quality")}\n' if d.get("quality") else "")
        + (f'🎞 <b>Resolution :</b>  {d.get("resolution")}\n' if d.get("resolution") else "")
        + (f'🎬 <b>Status :</b>  {d.get("status")}\n\n' if d.get("status") else "\n")
        + '╚══════════════════╝'
    )


def customize_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎙 Audio", callback_data="ed_audio"),
            InlineKeyboardButton(
                "💿 Quality", callback_data="ed_quality"),
        ],
        [
            InlineKeyboardButton(
                "🎞 Resolution", callback_data="ed_resolution"),
            InlineKeyboardButton(
                "🎬 Status", callback_data="ed_status"),
        ],
        [InlineKeyboardButton(
            "➕ Additional Info", callback_data="ed_additional"
        )],
        [InlineKeyboardButton(
            "🗑 Koi Line Hatao", callback_data="ed_deleteline"
        )],
        [InlineKeyboardButton(
            "✅ Caption Final Karo", callback_data="ed_done"
        )],
    ])


def search_kb(results: list) -> InlineKeyboardMarkup:
    btns = []
    for i, r in enumerate(results):
        title = r.get("title") or r.get("name", "Unknown")
        year  = (r.get("release_date") or
                 r.get("first_air_date", ""))[:4]
        icon  = "🎬" if r.get("media_type") == "movie" else "📺"
        btns.append([InlineKeyboardButton(
            f"{icon} {title} ({year})",
            callback_data=f"sel_{i}"
        )])
    return InlineKeyboardMarkup(btns)


# ══════════════════════════════════════════════════
#  MEDIA CAPTION CLEANER
# ══════════════════════════════════════════════════

# Lines to fully remove
REMOVE_LINE = [
    # URLs & links
    r'https?://',
    r't\.me/',
    # Spam words
    r'jion',
    r'support',
    r'live\s*sports',
    r'\bjoin\b',
    r'share',
    r'search\s*movie',
    r'updates?\s*channel',
    r'subscribe',
    r'follow\s*us',
    r'join\s*us',
    r'\bimportant\b',
    r'will\s*be\s*deleted',
    r'copyright',
    r'please\s*forward',
    r'thank\s*you',
    # Channel promo lines
    r'main\s*channel',
    r'main\s*group',
    r'2nd\s*group',
    r'3rd\s*group',
    r'backup\s*channel',
    r'\bgroup\b',
    r'\bchannel\b',
    # Our own bot format
    r'uploaded\s*by',
    r'file\s*info\s*:',
    r'movie\s*info',
    # Divider/box lines
    r'^[▬═─╔╚┌└╗╝|═]+$',
    r'^[⚡🎬💾🗑➕]\s',
    r'╔', r'╚',
]

SIZE_RE = re.compile(r'\bsize\b', re.IGNORECASE)

# Lines that are only symbols/emojis (no real text)
SYMBOL_ONLY = re.compile(
    r'^[\s\W\d☆★◇◆♦♠♣♥✦✧❖◈◉○●□■\-—–_=+*~`^]+$'
)


def is_remove_line(line: str) -> bool:
    if SIZE_RE.search(line):
        return True
    if SYMBOL_ONLY.match(line):
        return True
    return any(
        re.search(p, line, re.IGNORECASE)
        for p in REMOVE_LINE
    )


def clean_filename_line(text: str) -> str:
    # Remove FILENAME label
    text = re.sub(
        r'^[\W\s]*filename[\W\s]*:?\s*', '',
        text, flags=re.IGNORECASE
    ).strip()
    # Remove leading @username
    text = re.sub(r'^@\w+\s*', '', text).strip()
    # Remove leading channel-name word (has digits)
    text = re.sub(r'^[A-Za-z]+\d+\w*\s+', '', text).strip()
    # Remove trailing watermark before extension
    for ext in MEDIA_EXTS:
        pat = re.compile(
            r'\s+[A-Za-z]+\d*[A-Za-z]*\s*(' +
            re.escape(ext) + r')\s*$',
            re.IGNORECASE
        )
        m = pat.search(text)
        if m:
            text = (text[:m.start()] + ' ' + m.group(1)).strip()
            break
    # Truncate at extension
    low = text.lower()
    for ext in MEDIA_EXTS:
        idx = low.find(ext)
        if idx != -1:
            text = text[:idx + len(ext)]
            break
    return text.strip()


def build_media_caption(original: str, size_bytes: int) -> str:
    clean_lines = []

    for line in original.splitlines():
        s = re.sub(r'@\w+', '', line.strip()).strip()
        if not s or is_remove_line(s):
            continue
        low = s.lower()
        if (any(ext in low for ext in MEDIA_EXTS) or
                re.search(r'filename', s, re.IGNORECASE)):
            s = clean_filename_line(s)
            if not s:
                continue
        s = (s.replace('&', '&amp;')
              .replace('<', '&lt;')
              .replace('>', '&gt;'))
        if s:
            clean_lines.append(s)

    body     = '\n'.join(clean_lines).strip()
    size_str = format_size(size_bytes) if size_bytes > 0 else ""

    # ── Unique box design ──
    cap = (
        f'╔══【 📁 FILE INFO 】══╗\n\n'
        f'⚡ <b>Uploaded by :</b> '
        f'<a href="{CHANNEL_LINK}"><b>{CHANNEL_NAME}</b></a>\n'
        f'▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n'
    )
    if body:
        cap += f'\n🎬 <b>File Info :</b>\n{body}\n'
    if size_str:
        cap += f'\n💾 <b>Size :</b>  {size_str}\n'
    cap += f'\n╚══════════════════╝'
    return cap


# ══════════════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════════════

async def cmd_start(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "👋 <b>CRQ Caption Bot</b>\n\n"
        "🔤 <b>Movie naam type karo</b>\n"
        "    → TMDB poster + stylish caption\n\n"
        "📹 <b>Media forward karo</b>\n"
        "    → Clean caption auto-lagega\n\n"
        "⚡ Channel credit auto-add\n"
        "🗑 5 min auto-delete + Get File Again",
        parse_mode="HTML"
    )


# ── Text → TMDB search OR field edit ──────────────────────────

async def handle_text(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
):
    text    = update.message.text.strip()
    chat_id = update.effective_chat.id

    # Editing a field
    field = ctx.user_data.get("editing_field")
    if field:
        cap_data = ctx.user_data.get("cap_data", {})
        ctx.user_data["editing_field"] = None
        try:
            await update.message.delete()
        except Exception:
            pass

        # Delete line mode
        if field == "deleteline":
            keyword = text.strip().lower()
            # Map keyword to cap_data key
            key_map = {
                "duration":   "duration",
                "rating":     "rating",
                "year":       "year",
                "language":   "language",
                "genre":      "genres",
                "genres":     "genres",
                "audio":      "audio",
                "quality":    "quality",
                "resolution": "resolution",
                "status":     "status",
                "additional": "additional",
                "name":       "name",
            }
            matched = None
            for k, v in key_map.items():
                if k in keyword:
                    matched = v
                    break
            if matched:
                if matched == "genres":
                    cap_data[matched] = []
                elif matched == "additional":
                    cap_data[matched] = ""
                else:
                    cap_data[matched] = ""
        else:
            cap_data[field] = text

        ctx.user_data["cap_data"] = cap_data
        photo_msg = ctx.user_data.get("photo_msg")
        if photo_msg:
            try:
                await photo_msg.edit_caption(
                    caption      = build_tmdb_caption(cap_data),
                    parse_mode   = "HTML",
                    reply_markup = customize_kb()
                )
            except Exception:
                pass
        return

    # New search
    try:
        await update.message.delete()
    except Exception:
        pass
    msg = await ctx.bot.send_message(chat_id, "🔍 Searching TMDB...")

    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{TMDB_BASE}/search/multi",
            params={
                "api_key":  TMDB_API_KEY,
                "query":    text,
                "language": "en-US"
            }
        ) as resp:
            data = await resp.json()

    results = [
        r for r in data.get("results", [])
        if r.get("media_type") in ("movie", "tv")
    ][:6]

    if not results:
        await msg.edit_text("❌ Koi result nahi mila.")
        asyncio.create_task(
            schedule_delete(ctx, chat_id, msg.message_id))
        return

    ctx.user_data["results"] = results
    await msg.edit_text(
        "🎯 <b>Select karo:</b>",
        parse_mode   = "HTML",
        reply_markup = search_kb(results)
    )
    asyncio.create_task(
        schedule_delete(ctx, chat_id, msg.message_id))


# ── Select TMDB result ─────────────────────────────────────────

async def cb_select(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
):
    q       = update.callback_query
    await q.answer()
    chat_id = update.effective_chat.id

    idx     = int(q.data.split("_")[1])
    results = ctx.user_data.get("results", [])
    if idx >= len(results):
        await q.edit_message_text("❌ Error.")
        return

    r = results[idx]
    await q.edit_message_text("⏳ Fetching info...")

    mid = r["media_type"]
    rid = r["id"]

    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{TMDB_BASE}/{mid}/{rid}",
            params={"api_key": TMDB_API_KEY, "language": "en-US"}
        ) as resp:
            det = await resp.json()

    title  = det.get("title") or det.get("name", "Unknown")
    year   = (det.get("release_date") or
               det.get("first_air_date", "N/A"))[:4]
    rating = round(det.get("vote_average", 0), 1)
    lang   = det.get("original_language", "N/A")
    genres = [g["name"] for g in det.get("genres", [])]
    poster = det.get("poster_path", "")

    if mid == "movie":
        rt       = det.get("runtime", 0)
        duration = f"{rt} min" if rt else "N/A"
    else:
        ep       = det.get("episode_run_time", [])
        duration = f"{ep[0]} min/ep" if ep else "N/A"

    cap_data = {
        "name":       title,
        "year":       year,
        "rating":     rating,
        "language":   lang,
        "genres":     genres,
        "duration":   duration,
        "audio":      "Hindi",
        "quality":    "BDRip",
        "resolution": "480p | 720p | 1080p",
        "status":     "Uploading....",
        "additional": "",
    }
    ctx.user_data["cap_data"]      = cap_data
    ctx.user_data["editing_field"] = None

    caption = build_tmdb_caption(cap_data)
    kb      = customize_kb()

    try:
        await q.message.delete()
    except Exception:
        pass

    if poster:
        sent = await ctx.bot.send_photo(
            chat_id,
            photo        = f"{TMDB_IMG}{poster}",
            caption      = caption,
            parse_mode   = "HTML",
            reply_markup = kb
        )
    else:
        sent = await ctx.bot.send_message(
            chat_id, caption,
            parse_mode="HTML", reply_markup=kb
        )

    ctx.user_data["photo_msg"] = sent
    asyncio.create_task(
        schedule_delete(ctx, chat_id, sent.message_id))


# ── Edit caption fields ────────────────────────────────────────

FIELD_LABELS = {
    "audio":      "Audio  (e.g. Hindi | Dual Audio)",
    "quality":    "Quality  (e.g. BDRip | WEBRip)",
    "resolution": "Resolution  (e.g. 480p | 720p | 1080p)",
    "status":     "Status  (e.g. Uploading.... | Available ✅)",
    "additional": (
        "Additional Info\n"
        "(e.g. Season 01 | S01E01 | Part 1 | jo bhi chahiye)"
    ),
    "deleteline": (
        "Jo line hatani hai uska exact text type karo\n"
        "(e.g. Duration ya Rating ya jo bhi line ho)"
    ),
}

async def cb_edit(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
):
    q       = update.callback_query
    await q.answer()
    chat_id = update.effective_chat.id

    if q.data == "ed_done":
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        sent = await ctx.bot.send_message(
            chat_id, "✅ Caption ready! Copy karke use karo."
        )
        asyncio.create_task(
            schedule_delete(ctx, chat_id, sent.message_id))
        return

    field = q.data.split("_", 1)[1]

    # Special: delete a specific line
    if field == "deleteline":
        ctx.user_data["editing_field"] = "deleteline"
        ctx.user_data["photo_msg"]     = q.message
        sent = await ctx.bot.send_message(
            chat_id,
            "🗑 <b>Kis line ko hatana hai?</b>\n\n"
            "Woh line ka naam type karo:\n"
            "e.g. <code>Duration</code> ya "
            "<code>Rating</code> ya "
            "<code>Language</code>",
            parse_mode="HTML"
        )
        asyncio.create_task(
            schedule_delete(ctx, chat_id, sent.message_id))
        return

    ctx.user_data["editing_field"] = field
    ctx.user_data["photo_msg"]     = q.message

    label = FIELD_LABELS.get(field, field)
    sent  = await ctx.bot.send_message(
        chat_id,
        f"✏️ <b>{label}</b> — type karke bhejo:",
        parse_mode="HTML"
    )
    asyncio.create_task(
        schedule_delete(ctx, chat_id, sent.message_id))


# ── Media forward → clean caption ─────────────────────────────

async def handle_media(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
):
    msg     = update.message
    chat_id = update.effective_chat.id

    file_id, file_type, size_bytes = get_file_info(msg)
    if not file_id:
        return

    new_cap = build_media_caption(msg.caption or "", size_bytes)

    key = str(msg.message_id)
    ctx.user_data.setdefault("files", {})[key] = {
        "file_id":   file_id,
        "file_type": file_type,
        "caption":   new_cap,
    }

    try:
        sent = await ctx.bot.copy_message(
            chat_id      = chat_id,
            from_chat_id = chat_id,
            message_id   = msg.message_id,
            caption      = new_cap,
            parse_mode   = "HTML"
        )
    except Exception as e:
        await ctx.bot.send_message(chat_id, f"⚠️ Error: {e}")
        return

    try:
        await msg.delete()
    except Exception:
        pass

    asyncio.create_task(
        delete_and_notify(ctx, chat_id, sent.message_id, key))


# ── Get File Again ─────────────────────────────────────────────

async def cb_get_file(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
):
    q       = update.callback_query
    await q.answer()
    chat_id = update.effective_chat.id

    key  = q.data.split("_", 1)[1]
    info = ctx.user_data.get("files", {}).get(key)

    if not info:
        await q.edit_message_text(
            "❌ File expired. Dobara forward karo.")
        return

    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    fid  = info["file_id"]
    ftyp = info["file_type"]
    cap  = info["caption"]
    kw   = dict(caption=cap, parse_mode="HTML")

    try:
        if ftyp == "video":
            sent = await ctx.bot.send_video(chat_id, fid, **kw)
        elif ftyp == "document":
            sent = await ctx.bot.send_document(chat_id, fid, **kw)
        elif ftyp == "audio":
            sent = await ctx.bot.send_audio(chat_id, fid, **kw)
        elif ftyp == "photo":
            sent = await ctx.bot.send_photo(chat_id, fid, **kw)
        elif ftyp == "animation":
            sent = await ctx.bot.send_animation(
                chat_id, fid, **kw)
        else:
            await ctx.bot.send_message(chat_id, "❌ Unsupported.")
            return
        asyncio.create_task(
            delete_and_notify(ctx, chat_id, sent.message_id, key))
    except Exception as e:
        await ctx.bot.send_message(chat_id, f"⚠️ Error: {e}")


# ══════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(
        CallbackQueryHandler(cb_select, pattern=r"^sel_\d+$"))
    app.add_handler(
        CallbackQueryHandler(cb_edit,   pattern=r"^ed_"))
    app.add_handler(
        CallbackQueryHandler(cb_get_file, pattern=r"^gf_"))

    media_filter = (
        filters.VIDEO | filters.Document.ALL |
        filters.PHOTO | filters.AUDIO | filters.ANIMATION
    )
    app.add_handler(MessageHandler(media_filter, handle_media))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Bot polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
