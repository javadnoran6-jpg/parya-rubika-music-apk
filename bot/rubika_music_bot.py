#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات موزیکال پیشرفته روبیکا + وب‌سرور کنترلر ترموکس (پورت 3000)
سازنده: پریا چش رنگی
سازگار با Termux، اندروید APK، و سرور لینوکس
"""

import asyncio
import json
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp
from aiohttp import web

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BOT_TOKEN = os.getenv("RUBIKA_BOT_TOKEN", "")
CREATOR_NAME = "پریا چش رنگی"
CREATOR_ID = os.getenv("RUBIKA_CREATOR_ID", "u0_parya_creator")
PORT = int(os.getenv("PORT", "3000"))
DB_PATH = os.getenv("BOT_DB_PATH", "parya_music_bot.db")

def get_api_base(tok: str) -> str:
    return f"https://botapi.rubika.ir/v3/{tok.strip()}"

HELP_TEXT = f"""🎵 راهنمای ربات موزیکال پیشرفته روبیکا
👑 سازنده: {CREATOR_NAME}

🔍 جستجوی آهنگ:
• آهنگ {{نام موسیقی}}  (مثال: آهنگ لری)

🔗 پخش از لینک مستقیم:
• پخش ویسکال {{لینک دانلود}}

⏹ توقف پخش و ذخیره آهنگ:
• قطع ویسکال / توقف آهنگ / خروج / توقف

▶️ ادامه آهنگ متوقف‌شده:
• ادامه آهنگ

🔄 پخش با ریپلای:
• روی فایل صوتی یا لینک ریپلای کنید و ارسال کنید: پخش ریپلای

🎲 پخش تصادفی:
• پخش رندوم / پخش رندوم شاد / پخش رندوم غمگین

📋 مدیریت صف و تاریخچه:
• بعدی — پخش آهنگ بعدی از صف
• قبلی — پخش آهنگ قبلی از تاریخچه
• صف / لیست پخش — نمایش لیست صف
• اضافه به صف (+ ریپلای یا لینک)
• پاک کردن صف — خالی کردن کل صف
• حذف از صف {{شماره}} — حذف آهنگ از صف
• تاریخچه آهنگها — نمایش ۵ آهنگ آخر پخش شده

⚡ پخش فوری:
• پخش فوری (+ ریپلای یا لینک)

🔊 کنترل صدا:
• تنظیم صدا {{0-100}}
• بیصدا — سکوت در کال با ادامه پخش
• باصدا — باز کردن صدا در کال

👑 مدیریت گروه و دسترسی:
• مالک گروه — نمایش شناسه مالک
• ویژه (+ ریپلای) — ویژه کردن کاربر
• حذف ویژه (+ ریپلای) — حذف ویژه بودن کاربر
• تنظیم مالک (+ ریپلای) — تعیین مالک (فقط سازنده)
• دسترسی عموم باز / دسترسی عموم قفل باشد
• مقام — نمایش مقام شما در گروه

📞 کال و اشتراک و تایمر:
• ساخت کال — ایجاد ویس چت در گروه
• تنظیم خاموشی 23:30 / لغو خاموشی
• وضعیت — نمایش تاریخ خرید، انقضا و دسترسی"""


class BotDatabase:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id TEXT PRIMARY KEY,
                title TEXT,
                owner_id TEXT,
                public_access TEXT DEFAULT 'open',
                volume INTEGER DEFAULT 80,
                is_muted INTEGER DEFAULT 0,
                is_playing INTEGER DEFAULT 0,
                voice_call_active INTEGER DEFAULT 0,
                current_track TEXT,
                paused_track TEXT,
                queue_json TEXT DEFAULT '[]',
                history_json TEXT DEFAULT '[]',
                purchased_at TEXT,
                expires_at TEXT,
                auto_shutdown_time TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                chat_id TEXT,
                user_id TEXT,
                role TEXT DEFAULT 'member',
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        self.conn.commit()

    def ensure_group(self, chat_id: str, title: str = "گروه موزیکال اصلی") -> sqlite3.Row:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        if not row:
            now = datetime.now()
            expires = now + timedelta(days=30)
            cur.execute(
                """
                INSERT INTO groups (chat_id, title, owner_id, public_access, purchased_at, expires_at)
                VALUES (?, ?, ?, 'open', ?, ?)
                """,
                (chat_id, title, CREATOR_ID, now.strftime("%Y-%m-%d"), expires.strftime("%Y-%m-%d")),
            )
            self.conn.commit()
            cur.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
            row = cur.fetchone()
        return row

    def list_groups(self) -> List[Dict[str, Any]]:
        self.ensure_group("g_main_rubika", "گروه موزیکال اصلی")
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM groups")
        items = []
        for r in cur.fetchall():
            items.append({
                "chat_id": r["chat_id"],
                "title": r["title"],
                "owner_id": r["owner_id"],
                "public_access": r["public_access"],
                "volume": r["volume"],
                "is_muted": bool(r["is_muted"]),
                "is_playing": bool(r["is_playing"]),
                "voice_call_active": bool(r["voice_call_active"]),
                "current_track": json.loads(r["current_track"]) if r["current_track"] else None,
                "queue": json.loads(r["queue_json"] or "[]"),
                "history": json.loads(r["history_json"] or "[]"),
                "auto_shutdown_time": r["auto_shutdown_time"],
                "expires_at": r["expires_at"],
            })
        return items

    def get_role(self, chat_id: str, user_id: str) -> str:
        if user_id == CREATOR_ID:
            return "creator"
        grp = self.ensure_group(chat_id)
        if grp["owner_id"] == user_id:
            return "owner"
        cur = self.conn.cursor()
        cur.execute("SELECT role FROM members WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        r = cur.fetchone()
        return r["role"] if r else "member"

    def set_role(self, chat_id: str, user_id: str, role: str) -> None:
        self.conn.execute(
            "INSERT INTO members (chat_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET role = excluded.role",
            (chat_id, user_id, role),
        )
        self.conn.commit()

    def update_group(self, chat_id: str, **fields: Any) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields.keys())
        vals = list(fields.values()) + [chat_id]
        self.conn.execute(f"UPDATE groups SET {cols} WHERE chat_id = ?", vals)
        self.conn.commit()


class RubikaMusicBot:
    def __init__(self) -> None:
        self.db = BotDatabase(DB_PATH)
        self.token = os.getenv("RUBIKA_BOT_TOKEN", BOT_TOKEN)
        self.offset: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.polling_enabled = True
        self.logs: List[str] = []
        self.last_verify: Optional[Dict[str, Any]] = None

    def add_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        self.logs.append(line)
        if len(self.logs) > 80:
            self.logs = self.logs[-80:]

    async def api_call(self, method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.session is None:
            return {"status": "ERROR", "error": "Session not ready"}
        url = f"{get_api_base(self.token)}/{method}"
        try:
            async with self.session.post(url, json=payload or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                try:
                    return await resp.json()
                except Exception:
                    return {"status": "ERROR", "raw": await resp.text()}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc)}

    async def send_text(self, chat_id: str, text: str, reply_to: Optional[str] = None, send_remote: bool = True) -> Dict[str, Any]:
        if not send_remote or chat_id == "g_main_rubika":
            return {"status": "LOCAL_OK", "text": text}
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        return await self.api_call("sendMessage", payload)

    async def search_music(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        if self.session is None:
            return []
        url = f"https://itunes.apple.com/search?term={quote(query)}&media=music&entity=song&limit={limit}"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    results = []
                    for item in data.get("results", []):
                        if item.get("previewUrl"):
                            results.append({
                                "title": item.get("trackName", query),
                                "artist": item.get("artistName", "ناشناس"),
                                "url": item["previewUrl"],
                                "duration": max(30, round(item.get("trackTimeMillis", 30000) / 1000)),
                            })
                    return results
        except Exception as e:
            self.add_log(f"SearchError: {e}")
        return []

    def has_permission(self, chat_id: str, user_id: str) -> bool:
        grp = self.db.ensure_group(chat_id)
        if grp["public_access"] == "open":
            return True
        return self.db.get_role(chat_id, user_id) in {"creator", "owner", "admin", "vip"}

    async def handle_message(self, msg: Dict[str, Any], send_remote: bool = True) -> str:
        chat_id = str(msg.get("chat_id", "g_main_rubika"))
        sender_id = str(msg.get("sender_id", CREATOR_ID))
        message_id = str(msg.get("message_id", ""))
        text = (msg.get("text") or "").strip()
        if not chat_id or not text:
            return ""

        grp = self.db.ensure_group(chat_id)
        role = self.db.get_role(chat_id, sender_id)
        reply_msg = msg.get("reply_to_message") or {}
        reply_sender_id = str(reply_msg.get("sender_id", ""))
        reply_text = (reply_msg.get("text") or "").strip()
        reply_file = reply_msg.get("file_inline") or {}

        async def reply(out_text: str) -> str:
            self.add_log(f"[{chat_id}] {text} -> {out_text.splitlines()[0]}")
            await self.send_text(chat_id, out_text, message_id or None, send_remote=send_remote)
            return out_text

        if text in {"راهنما", "راهنمای ربات", "/start", "/help"}:
            return await reply(HELP_TEXT)

        if text == "مقام":
            role_labels = {
                "creator": f"سازنده ربات ({CREATOR_NAME})",
                "owner": "مالک گروه",
                "admin": "ادمین گروه",
                "vip": "کاربر ویژه",
                "member": "کاربر عادی",
            }
            return await reply(f"🔵 مقام شما در این گروه: {role_labels.get(role, 'عادی')}")

        if text == "مالک گروه":
            return await reply(f"🟢 شناسه مالک فعلی گروه: {grp['owner_id']}")

        if text == "وضعیت":
            exp = datetime.strptime(grp["expires_at"], "%Y-%m-%d")
            days_left = max(0, (exp - datetime.now()).days)
            access_fa = "باز برای همه اعضا" if grp["public_access"] == "open" else "قفل (فقط ویژه و ادمین)"
            return await reply(
                f"🔐 وضعیت اشتراک ربات موزیکال\n"
                f"📅 تاریخ خرید: {grp['purchased_at']}\n"
                f"⏳ تاریخ انقضا: {grp['expires_at']}\n"
                f"📆 روزهای باقیمانده: {days_left} روز\n"
                f"🔓 دسترسی عمومی: {access_fa}\n"
                f"👑 سازنده: {CREATOR_NAME}"
            )

        if text == "تنظیم مالک":
            if role != "creator":
                return await reply("⛔ فقط سازنده ربات مجاز به تعیین مالک گروه است.")
            if not reply_sender_id:
                return await reply("⚠ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.")
            self.db.update_group(chat_id, owner_id=reply_sender_id)
            self.db.set_role(chat_id, reply_sender_id, "owner")
            return await reply(f"👑 کاربر {reply_sender_id} به عنوان مالک گروه تنظیم شد.")

        if text == "ویژه":
            if role not in {"creator", "owner", "admin"}:
                return await reply("⛔ فقط مالک یا ادمین گروه مجاز است.")
            if not reply_sender_id:
                return await reply("⚠ لطفاً روی پیام کاربر ریپلای کنید و ارسال کنید: ویژه")
            self.db.set_role(chat_id, reply_sender_id, "vip")
            return await reply(f"⭐ کاربر {reply_sender_id} با موفقیت ویژه شد.")

        if text == "حذف ویژه":
            if role not in {"creator", "owner"}:
                return await reply("⛔ فقط مالک گروه یا سازنده ربات می‌تواند ویژه را حذف کند.")
            if not reply_sender_id:
                return await reply("⚠ روی پیام کاربر ریپلای کنید.")
            self.db.set_role(chat_id, reply_sender_id, "member")
            return await reply(f"🗑 وضعیت ویژه کاربر {reply_sender_id} حذف شد.")

        if text == "دسترسی عموم باز":
            if role not in {"creator", "owner", "admin"}:
                return await reply("⛔ دسترسی تغییر تنظیمات ندارید.")
            self.db.update_group(chat_id, public_access="open")
            return await reply("🔓 دسترسی عمومی باز شد. همه اعضا می‌توانند از ربات استفاده کنند.")

        if text == "دسترسی عموم قفل باشد":
            if role not in {"creator", "owner", "admin"}:
                return await reply("⛔ دسترسی تغییر تنظیمات ندارید.")
            self.db.update_group(chat_id, public_access="locked")
            return await reply("🔒 دسترسی عمومی قفل شد. فقط کاربران ویژه و ادمین‌ها دسترسی دارند.")

        if not self.has_permission(chat_id, sender_id):
            return await reply("🔒 دسترسی عمومی قفل است. فقط کاربران ویژه و ادمین‌ها مجاز هستند.")

        queue: List[Dict[str, Any]] = json.loads(grp["queue_json"] or "[]")
        history: List[Dict[str, Any]] = json.loads(grp["history_json"] or "[]")
        current = json.loads(grp["current_track"]) if grp["current_track"] else None
        paused = json.loads(grp["paused_track"]) if grp["paused_track"] else None

        if text == "ساخت کال":
            self.db.update_group(chat_id, voice_call_active=1)
            return await reply("📞 ویس‌چت (کال) گروه فعال شد. ربات آماده پخش موسیقی در کال است.")

        if text == "بیصدا":
            self.db.update_group(chat_id, is_muted=1)
            return await reply("🟣 ربات در کال بی‌صدا شد (آهنگ در پس‌زمینه در حال پخش است).")

        if text == "باصدا":
            self.db.update_group(chat_id, is_muted=0)
            return await reply("🟠 ربات از حالت بی‌صدا خارج شد و آهنگ در حال پخش است ✅")

        vol_match = re.match(r"^تنظیم صدا\s+(\d{1,3})$", text)
        if vol_match:
            vol = max(0, min(100, int(vol_match.group(1))))
            self.db.update_group(chat_id, volume=vol)
            return await reply(f"🔊 صدای پخش روی {vol} درصد تنظیم شد.")

        if text in {"قطع ویسکال", "توقف آهنگ", "خروج", "توقف"}:
            if current:
                self.db.update_group(chat_id, paused_track=json.dumps(current, ensure_ascii=False), current_track=None, is_playing=0)
                return await reply(f"⏹ پخش آهنگ «{current['title']}» متوقف و برای ادامه ذخیره شد.")
            self.db.update_group(chat_id, is_playing=0, voice_call_active=0)
            return await reply("⏹ ویسکال متوقف شد.")

        if text == "ادامه آهنگ":
            if paused:
                self.db.update_group(chat_id, current_track=json.dumps(paused, ensure_ascii=False), paused_track=None, is_playing=1, voice_call_active=1)
                return await reply(f"▶️ ادامه پخش آهنگ «{paused['title']}» در ویسکال.")
            return await reply("⚠ آهنگ متوقف‌شده‌ای برای ادامه وجود ندارد.")

        if text in {"صف", "لیست پخش"}:
            if not queue:
                return await reply("📋 صف پخش در حال حاضر خالی است.")
            lines = [f"{i+1}. {t['title']} - {t.get('artist', '')}" for i, t in enumerate(queue)]
            return await reply("📋 لیست صف پخش:\n" + "\n".join(lines))

        if text == "پاک کردن صف":
            self.db.update_group(chat_id, queue_json="[]")
            return await reply("🗑 کل صف پخش پاک شد.")

        del_match = re.match(r"^حذف از صف\s+(\d+)$", text)
        if del_match:
            idx = int(del_match.group(1)) - 1
            if 0 <= idx < len(queue):
                removed = queue.pop(idx)
                self.db.update_group(chat_id, queue_json=json.dumps(queue, ensure_ascii=False))
                return await reply(f"🗑 آهنگ «{removed['title']}» از صف حذف شد.")
            return await reply("⚠ شماره آهنگ در صف معتبر نیست.")

        if text == "تاریخچه آهنگها":
            last5 = history[-5:][::-1]
            if not last5:
                return await reply("📜 تاریخچه آهنگ‌ها خالی است.")
            lines = [f"{i+1}. {t['title']} - {t.get('artist', '')}" for i, t in enumerate(last5)]
            return await reply("📜 ۵ آهنگ آخر پخش‌شده:\n" + "\n".join(lines))

        if text == "بعدی":
            if not queue:
                return await reply("⚠ صف خالی است.")
            if current:
                history.append(current)
            nxt = queue.pop(0)
            self.db.update_group(
                chat_id,
                current_track=json.dumps(nxt, ensure_ascii=False),
                queue_json=json.dumps(queue, ensure_ascii=False),
                history_json=json.dumps(history[-20:], ensure_ascii=False),
                is_playing=1,
                voice_call_active=1,
            )
            return await reply(f"⏭ پخش آهنگ بعدی: {nxt['title']}")

        if text == "قبلی":
            if not history:
                return await reply("⚠ آهنگی در تاریخچه وجود ندارد.")
            prev_track = history.pop()
            if current:
                queue.insert(0, current)
            self.db.update_group(
                chat_id,
                current_track=json.dumps(prev_track, ensure_ascii=False),
                queue_json=json.dumps(queue, ensure_ascii=False),
                history_json=json.dumps(history, ensure_ascii=False),
                is_playing=1,
                voice_call_active=1,
            )
            return await reply(f"⏮ بازگشت به آهنگ قبلی: {prev_track['title']}")

        if text in {"پخش رندوم", "پخش رندوم شاد", "پخش شاد", "آهنگ شاد", "پخش رندوم غمگین", "پخش غمگین", "آهنگ غمگین"}:
            happy_seeds = ["بهنام بانی", "ماکان بند", "پازل بند", "اندی", "سندی", "شهرام شب پره", "بنیامین بهادری", "محسن ابراهیم زاده"]
            sad_seeds = ["محسن چاوشی", "محسن یگانه", "مرتضی پاشایی", "مجید خراطها", "رضا بهرام", "داریوش", "هایده", "مهستی"]
            if "شاد" in text:
                pool = await self.search_music(random.choice(happy_seeds), 40)
            elif "غمگین" in text:
                pool = await self.search_music(random.choice(sad_seeds), 40)
            else:
                pool = queue or history or await self.search_music(random.choice(happy_seeds + sad_seeds), 40)
            if not pool:
                return await reply("⚠ آهنگی برای پخش تصادفی یافت نشد.")
            chosen = random.choice(pool)
            if current:
                history.append(current)
            self.db.update_group(
                chat_id,
                current_track=json.dumps(chosen, ensure_ascii=False),
                history_json=json.dumps(history[-20:], ensure_ascii=False),
                is_playing=1,
                voice_call_active=1,
            )
            return await reply(f"🎲 پخش تصادفی در ویسکال: {chosen['title']} - {chosen.get('artist', '')}")

        url_match = re.search(r"(https?://\S+)", text) or re.search(r"(https?://\S+)", reply_text)
        if text.startswith("پخش ویسکال ") or text in {"پخش ریپلای", "پخش فوری", "اضافه به صف"} or text.startswith("پخش فوری ") or text.startswith("اضافه به صف "):
            track_url = url_match.group(1) if url_match else reply_file.get("file_id", "")
            track_title = reply_file.get("file_name") or text.replace("پخش ویسکال", "").strip() or "موزیک مستقیم"
            if not track_url:
                return await reply("⚠ لینک مستقیم یا ریپلای روی فایل صوتی یافت نشد.")
            new_track = {"title": track_title, "artist": "لینک مستقیم", "url": track_url}
            if text.startswith("اضافه به صف"):
                queue.append(new_track)
                self.db.update_group(chat_id, queue_json=json.dumps(queue, ensure_ascii=False))
                return await reply(f"➕ آهنگ «{new_track['title']}» به صف اضافه شد (شماره {len(queue)}).")
            if current:
                history.append(current)
            self.db.update_group(
                chat_id,
                current_track=json.dumps(new_track, ensure_ascii=False),
                history_json=json.dumps(history[-20:], ensure_ascii=False),
                is_playing=1,
                voice_call_active=1,
            )
            mode_label = "⚡ پخش فوری" if "فوری" in text else "🎧 پخش در ویسکال"
            return await reply(f"{mode_label}: {new_track['title']}")

        if text.startswith("آهنگ "):
            query = text[len("آهنگ "):].strip()
            results = await self.search_music(query)
            if not results:
                return await reply(f"❌ آهنگی با عنوان «{query}» پیدا نشد.")
            chosen = results[0]
            if current:
                history.append(current)
            self.db.update_group(
                chat_id,
                current_track=json.dumps(chosen, ensure_ascii=False),
                history_json=json.dumps(history[-20:], ensure_ascii=False),
                is_playing=1,
                voice_call_active=1,
            )
            return await reply(f"🎵 در حال پخش در ویسکال:\n🎶 {chosen['title']} — {chosen['artist']}\n🔗 {chosen['url']}")

        if text.startswith("تنظیم خاموشی ") or text.startswith("خاموشی خودکار "):
            if role not in {"creator", "owner", "admin"}:
                return await reply("⛔ فقط مالک، ادمین یا سازنده مجاز به تنظیم تایمر است.")
            t_str = text.split()[-1].strip()
            if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", t_str):
                return await reply("⚠ فرمت ساعت اشتباه است. مثال: تنظیم خاموشی 23:30")
            self.db.update_group(chat_id, auto_shutdown_time=t_str)
            return await reply(f"⏰ تایمر قطع خودکار ویسکال روی ساعت {t_str} تنظیم شد.")

        if text in {"لغو خاموشی", "لغو تایمر"}:
            self.db.update_group(chat_id, auto_shutdown_time=None)
            return await reply("⏰ تایمر خاموشی خودکار ویسکال لغو شد.")

        return ""

    async def check_auto_shutdowns(self) -> None:
        now_hm = datetime.now().strftime("%H:%M")
        cur = self.db.conn.cursor()
        cur.execute("SELECT * FROM groups WHERE auto_shutdown_time = ?", (now_hm,))
        for grp in cur.fetchall():
            chat_id = grp["chat_id"]
            self.db.update_group(chat_id, is_playing=0, voice_call_active=0, auto_shutdown_time=None)
            await self.send_text(chat_id, f"⏰ زمان خودکار ({now_hm}) فرا رسید: ویسکال قطع شد و ربات متوقف گردید.")

    def build_local_dashboard_html(self) -> str:
        return """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>کنترلر ترموکس ربات روبیکا | پریا چش رنگی</title>
<style>
  body{margin:0;background:#0B0F17;color:#F1F5F9;font-family:system-ui,-apple-system,sans-serif;padding:16px}
  .card{background:#111827;border:1px solid #1E293B;border-radius:14px;padding:16px;margin-bottom:14px}
  .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  h1{font-size:18px;margin:0 0 6px;color:#34D399}
  .muted{color:#94A3B8;font-size:12px}
  button{background:#059669;color:#fff;border:0;border-radius:10px;padding:10px 14px;font-weight:600;font-size:13px;cursor:pointer}
  button.sec{background:#1E293B;color:#E2E8F0}
  button.danger{background:#DC2626}
  input{width:100%;box-sizing:border-box;background:#0B0F17;border:1px solid #334155;color:#F8FAFC;border-radius:10px;padding:10px 12px;font-size:13px;margin:8px 0}
  pre{background:#0B0F17;border:1px solid #1E293B;border-radius:10px;padding:12px;font-size:11px;color:#A7F3D0;max-height:220px;overflow:auto;direction:ltr;text-align:left}
</style>
</head>
<body>
  <div class="card">
    <h1>ربات موزیکال روبیکا — حالت ترموکس (Termux)</h1>
    <div class="muted" id="meta">در حال بارگذاری وضعیت...</div>
  </div>
  <div class="card">
    <div class="row">
      <button onclick="verifyToken()">بررسی اتصال توکن (getMe)</button>
      <button class="sec" onclick="togglePolling()">تغییر وضعیت دریافت زنده</button>
      <button class="sec" onclick="runCmd('پخش رندوم شاد')">🎲 پخش شاد</button>
      <button class="sec" onclick="runCmd('پخش رندوم غمگین')">🎵 پخش غمگین</button>
      <button class="danger" onclick="runCmd('قطع ویسکال')">⏹ قطع ویسکال</button>
    </div>
    <input id="cmdInput" placeholder="دستور فارسی بفرستید (مثلا: آهنگ محسن چاوشی یا وضعیت)..." />
    <button onclick="runCustom()">اجرای دستور</button>
    <div id="replyBox" class="muted" style="margin-top:10px;white-space:pre-wrap;color:#E2E8F0"></div>
  </div>
  <div class="card">
    <div class="muted" style="margin-bottom:6px">پخش فعلی و صف</div>
    <div id="playerBox" style="font-size:13px"></div>
    <audio id="audioEl" controls style="width:100%;margin-top:10px"></audio>
  </div>
  <div class="card">
    <div class="muted" style="margin-bottom:6px">گزارش زنده ترموکس</div>
    <pre id="logBox"></pre>
  </div>
<script>
let lastTrackUrl = '';
async function refresh(){
  const r = await fetch('/api/state');
  const d = await r.json();
  document.getElementById('meta').textContent =
    'سازنده: ' + d.creatorName + ' | دریافت زنده روبیکا: ' + (d.polling ? 'فعال ✅' : 'متوقف');
  const g = d.groups[0];
  if(g){
    const cur = g.current_track;
    document.getElementById('playerBox').textContent = cur
      ? '🎶 ' + cur.title + ' — ' + (cur.artist || '') + ' | صف: ' + g.queue.length
      : 'در حال حاضر آهنگی پخش نمی‌شود | صف: ' + g.queue.length;
    if(cur && cur.url && cur.url !== lastTrackUrl){
      lastTrackUrl = cur.url;
      const a = document.getElementById('audioEl');
      a.src = cur.url;
      a.play().catch(()=>{});
    }
  }
  document.getElementById('logBox').textContent = (d.logs || []).join('\n');
}
async function verifyToken(){
  const r = await fetch('/api/bot/verify',{method:'POST'});
  const d = await r.json();
  document.getElementById('replyBox').textContent = JSON.stringify(d, null, 2);
  refresh();
}
async function togglePolling(){
  await fetch('/api/bot/toggle',{method:'POST'});
  refresh();
}
async function runCmd(text){
  const r = await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  const d = await r.json();
  document.getElementById('replyBox').textContent = d.reply || 'اجرا شد';
  refresh();
}
function runCustom(){
  const el = document.getElementById('cmdInput');
  if(el.value.trim()){ runCmd(el.value.trim()); el.value=''; }
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>"""

    async def start_http_server(self) -> web.AppRunner:
        app = web.Application()

        async def handle_index(_request: web.Request) -> web.Response:
            return web.Response(text=self.build_local_dashboard_html(), content_type="text/html", charset="utf-8")

        async def handle_state(_request: web.Request) -> web.Response:
            return web.json_response({
                "ok": True,
                "mode": "termux-python",
                "creatorName": CREATOR_NAME,
                "polling": self.polling_enabled,
                "lastVerify": self.last_verify,
                "groups": self.db.list_groups(),
                "logs": self.logs[-30:],
            })

        async def handle_verify(_request: web.Request) -> web.Response:
            res = await self.api_call("getMe")
            self.last_verify = res
            self.add_log(f"getMe -> {res.get('status', 'DONE')}")
            return web.json_response(res)

        async def handle_toggle(_request: web.Request) -> web.Response:
            self.polling_enabled = not self.polling_enabled
            self.add_log(f"Polling toggled -> {self.polling_enabled}")
            return web.json_response({"polling": self.polling_enabled})

        async def handle_command(request: web.Request) -> web.Response:
            body = await request.json()
            reply_text = await self.handle_message({
                "chat_id": body.get("chat_id", "g_main_rubika"),
                "sender_id": body.get("sender_id", CREATOR_ID),
                "text": body.get("text", ""),
            }, send_remote=bool(body.get("send_remote", False)))
            return web.json_response({"ok": True, "reply": reply_text})

        app.router.add_get("/", handle_index)
        app.router.add_get("/api/state", handle_state)
        app.router.add_post("/api/bot/verify", handle_verify)
        app.router.add_post("/api/bot/toggle", handle_toggle)
        app.router.add_post("/api/command", handle_command)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        self.add_log(f"Termux Web Control Server running at http://127.0.0.1:{PORT}")
        return runner

    async def run(self, with_web: bool = True) -> None:
        self.running = True
        runner: Optional[web.AppRunner] = None
        async with aiohttp.ClientSession() as session:
            self.session = session
            if with_web:
                runner = await self.start_http_server()
            me = await self.api_call("getMe")
            self.last_verify = me
            self.add_log(f"Rubika Bot Ready | Creator: {CREATOR_NAME} | getMe: {me.get('status', 'OK')}")
            try:
                while self.running:
                    try:
                        await self.check_auto_shutdowns()
                        if self.polling_enabled:
                            payload: Dict[str, Any] = {"limit": 50}
                            if self.offset:
                                payload["offset_id"] = self.offset
                            res = await self.api_call("getUpdates", payload)
                            updates = res.get("data", {}).get("updates", []) if isinstance(res.get("data"), dict) else []
                            for upd in updates:
                                self.offset = upd.get("next_offset_id") or self.offset
                                if upd.get("new_message"):
                                    await self.handle_message(upd["new_message"])
                    except Exception as exc:
                        self.add_log(f"PollingError: {exc}")
                    await asyncio.sleep(1.5)
            finally:
                if runner:
                    await runner.cleanup()


if __name__ == "__main__":
    bot = RubikaMusicBot()
    asyncio.run(bot.run(with_web=True))
