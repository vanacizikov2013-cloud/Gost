# ========== bot.py ==========
import asyncio
import logging
import sys
import json
import os
import uuid
import random
import string
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_СЮДА")
ADMIN_IDS = [8440115662, 8114610850]  # ← ЗАМЕНИ НА СВОИ ID

MINI_APP_URL = "https://lackygifts1488.netlify.app"

DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

USERS_FILE = f"{DATA_DIR}/users.json"
CASES_FILE = f"{DATA_DIR}/cases.json"
NFTS_FILE = f"{DATA_DIR}/nfts.json"
PROMOS_FILE = f"{DATA_DIR}/promos.json"
TASKS_FILE = f"{DATA_DIR}/tasks.json"
WITHDRAWS_FILE = f"{DATA_DIR}/withdraws.json"
SETTINGS_FILE = f"{DATA_DIR}/settings.json"
STATS_FILE = f"{DATA_DIR}/stats.json"
MUSIC_FILE = f"{DATA_DIR}/music.json"
POSITIONS_FILE = f"{DATA_DIR}/positions.json"

# ========== НАСТРОЙКИ ПО УМОЛЧАНИЮ ==========
DEFAULT_SETTINGS = {
    "rocket": {
        "house_edge": 5,
        "color_thresholds": {"blue": 1.5, "red": 2.0, "gold": 2.0}
    },
    "mines": {
        "multipliers_3": [1.0, 1.2, 1.5, 2.0, 3.0, 5.0],
        "multipliers_5": [1.0, 1.3, 1.6, 2.2, 3.2, 5.5, 10.0],
        "multipliers_8": [1.0, 1.4, 1.9, 2.8, 4.5, 8.0, 15.0],
        "rigged_chance": 20,
        "big_bet_threshold": 300,
        "big_bet_rigged": 30
    },
    "blackjack": {
        "dealer_win_chance": 55,
        "blackjack_multiplier": 2.5
    },
    "trading": {
        "volatility": {"low": 0.5, "medium": 1.5, "high": 3.0}
    },
    "bot": {
        "daily_bonus_min": 10,
        "daily_bonus_max": 100,
        "referral_bonus": 50,
        "referral_percent": 5,
        "welcome_bonus": 100,
        "min_deposit": 10,
        "min_withdraw": 100,
        "withdraw_hold_hours": 24,  # ← ХОЛД ПРИ ВЫВОДЕ NFT
        "withdraw_penalty_percent": 20  # ← ШТРАФ ЗА ДОСРОЧНЫЙ ВЫВОД
    }
}

# ========== БАЗА ДАННЫХ (JSON) ==========
class Database:
    @staticmethod
    def load_file(filename: str, default: Any = None) -> Any:
        if default is None:
            if filename.endswith('users.json'): default = {}
            elif filename.endswith('settings.json'): default = DEFAULT_SETTINGS.copy()
            else: default = []
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    @staticmethod
    def save_file(filename: str, data: Any) -> None:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

class UserDB:
    def __init__(self):
        self.users = Database.load_file(USERS_FILE, {})

    def save(self):
        Database.save_file(USERS_FILE, self.users)

    def get_user(self, user_id: int) -> Dict:
        user_id = str(user_id)
        if user_id not in self.users:
            self.users[user_id] = {
                "id": user_id,
                "username": "",
                "first_name": "",
                "balance": int(DEFAULT_SETTINGS["bot"]["welcome_bonus"]),
                "total_deposit": 0,
                "total_withdraw": 0,
                "games_played": 0,
                "games_won": 0,
                "referral_code": self._generate_ref_code(),
                "referred_by": None,
                "referrals_count": 0,
                "referral_earnings": 0,
                "inventory": [],
                "completed_tasks": [],
                "used_promos": [],
                "daily_streak": 0,
                "last_daily": None,
                "registered_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "banned": False
            }
            self.save()
        return self.users[user_id]

    def _generate_ref_code(self) -> str:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def update_user(self, user_id: int, data: Dict) -> None:
        user_id = str(user_id)
        if user_id in self.users:
            self.users[user_id].update(data)
            self.save()

    def add_balance(self, user_id: int, amount: int) -> int:
        user = self.get_user(user_id)
        user["balance"] += amount
        if amount > 0:
            user["total_deposit"] += amount
        self.save()
        return user["balance"]

    def remove_balance(self, user_id: int, amount: int) -> bool:
        user = self.get_user(user_id)
        if user["balance"] >= amount:
            user["balance"] -= amount
            self.save()
            return True
        return False

    def get_top_players(self, limit: int = 10, sort_by: str = "balance") -> List[Dict]:
        players = []
        for uid, data in self.users.items():
            if not data.get("banned", False):
                players.append({
                    "id": uid,
                    "username": data.get("username", "Unknown"),
                    "first_name": data.get("first_name", "Unknown"),
                    "balance": data.get("balance", 0),
                    "games_won": data.get("games_won", 0)
                })
        if sort_by == "balance":
            players.sort(key=lambda x: x["balance"], reverse=True)
        else:
            players.sort(key=lambda x: x["games_won"], reverse=True)
        return players[:limit]

class CasesDB:
    def __init__(self):
        self.cases = Database.load_file(CASES_FILE, [])

    def save(self):
        Database.save_file(CASES_FILE, self.cases)

    def get_all(self) -> List[Dict]:
        return [c for c in self.cases if c.get("enabled", True)]

    def get_case(self, case_id: int) -> Optional[Dict]:
        for case in self.cases:
            if case["id"] == case_id:
                return case
        return None

    def create_case(self, name: str, price: int, emoji: str = "📦") -> Dict:
        case = {
            "id": len(self.cases) + 1,
            "name": name,
            "price": price,
            "emoji": emoji,
            "items": [],
            "total_opens": 0,
            "enabled": True,
            "created_at": datetime.now().isoformat()
        }
        self.cases.append(case)
        self.save()
        return case

    def add_item(self, case_id: int, item_type: str, name: str, value: int, emoji: str, chance: int) -> bool:
        case = self.get_case(case_id)
        if case:
            case["items"].append({
                "type": item_type,
                "name": name,
                "value": value,
                "emoji": emoji,
                "chance": chance
            })
            self.save()
            return True
        return False

    def open_case(self, case_id: int) -> Optional[Dict]:
        case = self.get_case(case_id)
        if not case or not case["items"]:
            return None
        case["total_opens"] += 1
        self.save()
        total_chance = sum(item["chance"] for item in case["items"])
        rand = random.randint(1, total_chance)
        current = 0
        for item in case["items"]:
            current += item["chance"]
            if rand <= current:
                return item
        return case["items"][0]

class NFTDB:
    def __init__(self):
        self.nfts = Database.load_file(NFTS_FILE, [])

    def save(self):
        Database.save_file(NFTS_FILE, self.nfts)

    def create_nft(self, name: str, value: int, emoji: str, rarity: str = "Обычный") -> Dict:
        nft = {
            "id": len(self.nfts) + 1,
            "name": name,
            "value": value,
            "emoji": emoji,
            "rarity": rarity,
            "created_at": datetime.now().isoformat()
        }
        self.nfts.append(nft)
        self.save()
        return nft

    def get_nft(self, nft_id: int) -> Optional[Dict]:
        for nft in self.nfts:
            if nft["id"] == nft_id:
                return nft
        return None

class SettingsDB:
    def __init__(self):
        self.settings = Database.load_file(SETTINGS_FILE, DEFAULT_SETTINGS)

    def save(self):
        Database.save_file(SETTINGS_FILE, self.settings)

    def get(self, game: str, key: str, default=None):
        return self.settings.get(game, {}).get(key, default)

    def set(self, game: str, key: str, value: Any) -> None:
        if game not in self.settings:
            self.settings[game] = {}
        self.settings[game][key] = value
        self.save()

class PromoDB:
    def __init__(self):
        self.promos = Database.load_file(PROMOS_FILE, [])

    def save(self):
        Database.save_file(PROMOS_FILE, self.promos)

    def create(self, code: str, reward_type: str, value: int, uses: int, expires: str = None) -> Dict:
        promo = {
            "id": len(self.promos) + 1,
            "code": code.upper(),
            "reward_type": reward_type,
            "value": value,
            "uses_total": uses,
            "uses_left": uses,
            "expires_at": expires,
            "enabled": True,
            "created_at": datetime.now().isoformat()
        }
        self.promos.append(promo)
        self.save()
        return promo

    def use(self, code: str, user_id: int) -> Optional[Dict]:
        code = code.upper()
        for promo in self.promos:
            if promo["code"] == code and promo["enabled"] and promo["uses_left"] > 0:
                if promo["expires_at"] and datetime.now().isoformat() > promo["expires_at"]:
                    continue
                promo["uses_left"] -= 1
                self.save()
                return promo
        return None

class TasksDB:
    def __init__(self):
        self.tasks = Database.load_file(TASKS_FILE, [])

    def save(self):
        Database.save_file(TASKS_FILE, self.tasks)

    def get_active(self) -> List[Dict]:
        return [t for t in self.tasks if t.get("enabled", True)]

    def create(self, name: str, reward: int, channel_id: str, channel_url: str, mandatory: bool = False) -> Dict:
        task = {
            "id": len(self.tasks) + 1,
            "name": name,
            "reward": reward,
            "channel_id": channel_id,
            "channel_url": channel_url,
            "mandatory": mandatory,
            "enabled": True,
            "created_at": datetime.now().isoformat()
        }
        self.tasks.append(task)
        self.save()
        return task

class MusicDB:
    def __init__(self):
        self.music = Database.load_file(MUSIC_FILE, [])

    def save(self):
        Database.save_file(MUSIC_FILE, self.music)

    def get_all(self) -> List[Dict]:
        return self.music

    def add(self, name: str, url: str) -> Dict:
        track = {
            "id": len(self.music) + 1,
            "name": name,
            "url": url,
            "created_at": datetime.now().isoformat()
        }
        self.music.append(track)
        self.save()
        return track

    def delete(self, track_id: int) -> bool:
        self.music = [t for t in self.music if t["id"] != track_id]
        self.save()
        return True

class WithdrawDB:
    def __init__(self):
        self.withdraws = Database.load_file(WITHDRAWS_FILE, [])

    def save(self):
        Database.save_file(WITHDRAWS_FILE, self.withdraws)

    def create(self, user_id: int, nft_id: int, nft_name: str, nft_value: int) -> Dict:
        hold_hours = settings_db.get("bot", "withdraw_hold_hours", 24)
        req = {
            "id": len(self.withdraws) + 1,
            "user_id": user_id,
            "nft_id": nft_id,
            "nft_name": nft_name,
            "nft_value": nft_value,
            "status": "pending",
            "hold_until": (datetime.now() + timedelta(hours=hold_hours)).isoformat(),
            "created_at": datetime.now().isoformat(),
            "processed_at": None
        }
        self.withdraws.append(req)
        self.save()
        return req

    def get_pending(self) -> List[Dict]:
        return [w for w in self.withdraws if w["status"] == "pending"]

    def get_user_pending(self, user_id: int) -> List[Dict]:
        return [w for w in self.withdraws if w["user_id"] == user_id and w["status"] == "pending"]

    def complete(self, req_id: int) -> bool:
        for req in self.withdraws:
            if req["id"] == req_id:
                req["status"] = "completed"
                req["processed_at"] = datetime.now().isoformat()
                self.save()
                return True
        return False

    def cancel(self, req_id: int) -> bool:
        for req in self.withdraws:
            if req["id"] == req_id:
                req["status"] = "cancelled"
                req["processed_at"] = datetime.now().isoformat()
                self.save()
                return True
        return False

class StatsDB:
    def __init__(self):
        self.stats = Database.load_file(STATS_FILE, {
            "total_users": 0,
            "total_deposits": 0,
            "total_withdraws": 0,
            "total_games": 0,
            "game_stats": {}
        })

    def save(self):
        Database.save_file(STATS_FILE, self.stats)

    def add_game(self, game: str, bet: int, win: int):
        self.stats["total_games"] += 1
        if game not in self.stats["game_stats"]:
            self.stats["game_stats"][game] = {"played": 0, "total_bet": 0, "total_win": 0}
        self.stats["game_stats"][game]["played"] += 1
        self.stats["game_stats"][game]["total_bet"] += bet
        self.stats["game_stats"][game]["total_win"] += win
        self.save()

class PositionsDB:
    def __init__(self):
        self.positions = Database.load_file(POSITIONS_FILE, [])

    def save(self):
        Database.save_file(POSITIONS_FILE, self.positions)

    def create(self, user_id: int, asset_id: int, asset_name: str, pos_type: str, amount: int, open_price: float) -> Dict:
        pos = {
            "id": len(self.positions) + 1,
            "user_id": user_id,
            "asset_id": asset_id,
            "asset_name": asset_name,
            "type": pos_type,
            "amount": amount,
            "open_price": open_price,
            "created_at": datetime.now().isoformat()
        }
        self.positions.append(pos)
        self.save()
        return pos

    def get_user_positions(self, user_id: int) -> List[Dict]:
        return [p for p in self.positions if p["user_id"] == user_id]

    def close(self, pos_id: int) -> Optional[Dict]:
        for pos in self.positions:
            if pos["id"] == pos_id:
                self.positions.remove(pos)
                self.save()
                return pos
        return None

# Инициализация БД
user_db = UserDB()
cases_db = CasesDB()
nft_db = NFTDB()
settings_db = SettingsDB()
promo_db = PromoDB()
tasks_db = TasksDB()
music_db = MusicDB()
withdraw_db = WithdrawDB()
stats_db = StatsDB()
positions_db = PositionsDB()

# Создаём бота
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
# ========== КЛАВИАТУРЫ ==========
def get_main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🎮 ИГРАТЬ", web_app=WebAppInfo(url=MINI_APP_URL)))
    builder.row(KeyboardButton(text="👤 ПРОФИЛЬ"), KeyboardButton(text="💰 БАЛАНС"))
    builder.row(KeyboardButton(text="🎁 БОНУС"), KeyboardButton(text="👥 РЕФЕРАЛЫ"))
    builder.row(KeyboardButton(text="📋 ЗАДАНИЯ"), KeyboardButton(text="ℹ️ ПОМОЩЬ"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_panel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Кейсы", callback_data="admin_cases")
    builder.button(text="🎨 NFT", callback_data="admin_nfts")
    builder.button(text="🎮 Настройки игр", callback_data="admin_games")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="🎟️ Промокоды", callback_data="admin_promos")
    builder.button(text="📋 Задания", callback_data="admin_tasks")
    builder.button(text="🎵 Музыка", callback_data="admin_music")
    builder.button(text="📤 Выводы NFT", callback_data="admin_withdraws")
    builder.button(text="👑 Выдать звёзды", callback_data="admin_give")
    builder.button(text="📨 Рассылка", callback_data="admin_broadcast")
    builder.button(text="⚙️ Настройки бота", callback_data="admin_bot_settings")
    builder.button(text="🔙 Закрыть", callback_data="close_admin")
    builder.adjust(2)
    return builder.as_markup()

# ========== КОМАНДЫ БОТА ==========
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = user_db.get_user(message.from_user.id)
    user["username"] = message.from_user.username or ""
    user["first_name"] = message.from_user.first_name or ""
    user_db.save()

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1][4:]
        for uid, data in user_db.users.items():
            if data.get("referral_code") == ref_code and uid != str(message.from_user.id):
                if not user.get("referred_by"):
                    user["referred_by"] = uid
                    user_db.save()
                    bonus = settings_db.get("bot", "referral_bonus", 50)
                    user_db.add_balance(int(uid), bonus)
                    await bot.send_message(uid, f"🎉 По вашей ссылке новый игрок! +{bonus}⭐")
                break

    welcome_text = f"""
🎰 <b>Добро пожаловать в Lucky Gifts!</b>

👤 <b>Профиль:</b> {message.from_user.first_name}
💰 <b>Баланс:</b> {user['balance']} ⭐
📦 <b>NFT:</b> {len(user['inventory'])} шт.

🎮 Нажми <b>«ИГРАТЬ»</b> чтобы открыть Mini App!
"""
    await message.answer(welcome_text, reply_markup=get_main_menu())

@dp.message(F.text == "👤 ПРОФИЛЬ")
async def profile(message: Message):
    user = user_db.get_user(message.from_user.id)
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{user['referral_code']}"
    text = f"""
👤 <b>Профиль</b>
🆔 ID: <code>{user['id']}</code>
💰 Баланс: {user['balance']} ⭐
📊 Игр: {user['games_played']} | Побед: {user['games_won']}
👥 Рефералов: {user['referrals_count']}
💎 Заработано: {user['referral_earnings']} ⭐

🔗 <b>Реферальная ссылка:</b>
<code>{ref_link}</code>
"""
    await message.answer(text)

@dp.message(F.text == "💰 БАЛАНС")
async def balance(message: Message):
    user = user_db.get_user(message.from_user.id)
    await message.answer(f"💰 <b>Ваш баланс:</b> {user['balance']} ⭐")

@dp.message(F.text == "🎁 БОНУС")
async def daily_bonus(message: Message):
    user = user_db.get_user(message.from_user.id)
    today = datetime.now().date().isoformat()
    if user.get("last_daily") == today:
        await message.answer("❌ Вы уже получили бонус сегодня!")
        return
    streak = user.get("daily_streak", 0) + 1 if user.get("last_daily") == (datetime.now().date() - timedelta(days=1)).isoformat() else 1
    min_bonus = settings_db.get("bot", "daily_bonus_min", 10)
    max_bonus = settings_db.get("bot", "daily_bonus_max", 100)
    bonus = random.randint(min_bonus, max_bonus) + (streak - 1) * 5
    user_db.add_balance(message.from_user.id, bonus)
    user_db.update_user(message.from_user.id, {"last_daily": today, "daily_streak": streak})
    await message.answer(f"🎁 <b>Ежедневный бонус!</b>\n+{bonus}⭐\n🔥 Стрик: {streak} дн.\n💰 Баланс: {user_db.get_user(message.from_user.id)['balance']} ⭐")

@dp.message(Command("adm"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Нет доступа")
        return
    await message.answer("🔐 <b>Админ-панель</b>", reply_markup=get_admin_panel())

@dp.callback_query(F.data == "close_admin")
async def close_admin(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()
# ========== API ДЛЯ MINI APP ==========
async def api_response(data: Dict, success: bool = True) -> web.Response:
    return web.json_response({"success": success, **data})

async def handle_api_request(request: web.Request) -> web.Response:
    try:
        path = request.path.replace("/api", "")
        method = request.method
        body = await request.json() if method in ["POST", "PUT"] else {}

        # Извлекаем user_id из тела или заголовков
        user_id = body.get("user_id") or request.headers.get("X-User-Id")
        if user_id:
            user_id = int(user_id)

        # ===== ПОЛЬЗОВАТЕЛЬ =====
        if path == "/user" and method == "GET":
            user = user_db.get_user(user_id)
            return api_response({"user": user})

        if path == "/user" and method == "POST":
            user = user_db.get_user(user_id)
            return api_response({"user": user})

        # ===== КЕЙСЫ =====
        if path == "/cases" and method == "GET":
            cases = cases_db.get_all()
            return api_response({"cases": cases})

        if path == "/case/open" and method == "POST":
            case_id = body.get("case_id")
            case = cases_db.get_case(case_id)
            if not case:
                return api_response({"message": "Кейс не найден"}, False)

            user = user_db.get_user(user_id)
            if user["balance"] < case["price"]:
                return api_response({"message": "Недостаточно средств"}, False)

            user_db.remove_balance(user_id, case["price"])
            item = cases_db.open_case(case_id)

            if item["type"] == "stars":
                user_db.add_balance(user_id, item["value"])
            else:
                user["inventory"].append({
                    "id": str(uuid.uuid4())[:8],
                    "name": item["name"],
                    "value": item["value"],
                    "emoji": item["emoji"],
                    "rarity": "Кейс"
                })
                user_db.save()

            stats_db.add_game("cases", case["price"], item["value"] if item["type"] == "stars" else 0)
            return api_response({"item": item})

        if path == "/case/free" and method == "POST":
            user = user_db.get_user(user_id)
            last_free = user.get("last_free_case")
            today = datetime.now().date().isoformat()
            if last_free == today:
                return api_response({"message": "Уже получили сегодня"}, False)

            user["last_free_case"] = today
            user_db.save()
            value = random.randint(10, 50)
            user_db.add_balance(user_id, value)
            return api_response({"item": {"type": "stars", "name": "Бесплатные звёзды", "value": value, "emoji": "⭐"}})

        # ===== ИНВЕНТАРЬ =====
        if path.startswith("/inventory") and method == "GET":
            user = user_db.get_user(user_id)
            items = user.get("inventory", [])
            return api_response({"items": items})

        if path == "/inventory/sell" and method == "POST":
            item_id = body.get("item_id")
            user = user_db.get_user(user_id)
            item = None
            for i in user["inventory"]:
                if i["id"] == item_id:
                    item = i
                    break
            if not item:
                return api_response({"message": "Предмет не найден"}, False)

            user["inventory"].remove(item)
            sell_price = int(item["value"] * 1.05)
            user_db.add_balance(user_id, sell_price)
            user_db.save()
            return api_response({"amount": sell_price})

        if path == "/inventory/withdraw" and method == "POST":
            item_id = body.get("item_id")
            user = user_db.get_user(user_id)
            item = None
            for i in user["inventory"]:
                if i["id"] == item_id:
                    item = i
                    break
            if not item:
                return api_response({"message": "Предмет не найден"}, False)

            pending = withdraw_db.get_user_pending(user_id)
            if pending:
                return api_response({"message": "У вас уже есть заявка на вывод"}, False)

            withdraw_db.create(user_id, item_id, item["name"], item["value"])
            hold_hours = settings_db.get("bot", "withdraw_hold_hours", 24)
            return api_response({
                "message": f"Заявка принята. Ожидайте {hold_hours} ч. или продайте NFT обратно.",
                "hold_hours": hold_hours
            })

        # ===== ИГРЫ =====
        if path.startswith("/game/") and "/bet" in path and method == "POST":
            game = path.split("/")[2]
            bet = body.get("bet", 0)

            user = user_db.get_user(user_id)
            if user["balance"] < bet:
                return api_response({"message": "Недостаточно средств"}, False)

            user_db.remove_balance(user_id, bet)
            user["games_played"] = user.get("games_played", 0) + 1
            user_db.save()
            return api_response({"success": True})

        if path.startswith("/game/") and "/finish" in path and method == "POST":
            game = path.split("/")[2]
            bet = body.get("bet", 0)
            win = body.get("win", 0)

            if win > 0:
                user_db.add_balance(user_id, win)
                user = user_db.get_user(user_id)
                user["games_won"] = user.get("games_won", 0) + 1
                user_db.save()

            stats_db.add_game(game, bet, win)
            return api_response({"success": True})

        if path.startswith("/game/") and "/settings" in path and method == "GET":
            game = path.split("/")[2]
            settings = settings_db.settings.get(game, {})
            return api_response({"settings": settings})

        # ===== ТРЕЙДИНГ =====
        if path == "/trading/assets" and method == "GET":
            assets = [
                {"id": 1, "name": "ЗОЛОТО", "symbol": "GOLD", "price": 1850, "change": 0.2, "emoji": "🟡"},
                {"id": 2, "name": "НЕФТЬ", "symbol": "OIL", "price": 75, "change": -0.5, "emoji": "🛢️"},
                {"id": 3, "name": "БИТКОИН", "symbol": "BTC", "price": 45200, "change": 1.2, "emoji": "₿"},
                {"id": 4, "name": "СЕРЕБРО", "symbol": "AG", "price": 22, "change": 0.1, "emoji": "⚪"}
            ]
            return api_response({"assets": assets})

        if path == "/trading/open" and method == "POST":
            asset_id = body.get("asset_id")
            pos_type = body.get("type")
            amount = body.get("amount", 0)

            user = user_db.get_user(user_id)
            if user["balance"] < amount:
                return api_response({"message": "Недостаточно средств"}, False)

            user_db.remove_balance(user_id, amount)
            assets = {
                1: ("ЗОЛОТО", 1850),
                2: ("НЕФТЬ", 75),
                3: ("БИТКОИН", 45200),
                4: ("СЕРЕБРО", 22)
            }
            name, price = assets.get(asset_id, ("Актив", 100))
            pos = positions_db.create(user_id, asset_id, name, pos_type, amount, price)
            return api_response({"position_id": pos["id"]})

        if path == "/trading/close" and method == "POST":
            pos_id = body.get("position_id")
            pos = positions_db.close(pos_id)
            if not pos:
                return api_response({"message": "Позиция не найдена"}, False)

            assets = {1: 1850, 2: 75, 3: 45200, 4: 22}
            current_price = assets.get(pos["asset_id"], pos["open_price"])

            if pos["type"] == "long":
                profit = int((current_price - pos["open_price"]) / pos["open_price"] * pos["amount"])
            else:
                profit = int((pos["open_price"] - current_price) / pos["open_price"] * pos["amount"])

            return_amount = pos["amount"] + profit
            user_db.add_balance(user_id, return_amount)
            return api_response({"profit": profit, "return": return_amount})

        if path.startswith("/trading/positions") and method == "GET":
            positions = positions_db.get_user_positions(user_id)
            return api_response({"positions": positions})

        # ===== ПРОМОКОДЫ =====
        if path == "/promo/activate" and method == "POST":
            code = body.get("code")
            user = user_db.get_user(user_id)
            if code in user.get("used_promos", []):
                return api_response({"message": "Промокод уже использован"}, False)

            promo = promo_db.use(code, user_id)
            if not promo:
                return api_response({"message": "Промокод не найден"}, False)

            if promo["reward_type"] == "stars":
                user_db.add_balance(user_id, promo["value"])
            user["used_promos"] = user.get("used_promos", []) + [code]
            user_db.save()
            return api_response({"message": f"Активирован! +{promo['value']}{'⭐' if promo['reward_type'] == 'stars' else ' NFT'}"})

        # ===== ЗАДАНИЯ =====
        if path.startswith("/tasks") and method == "GET":
            tasks = tasks_db.get_active()
            user = user_db.get_user(user_id)
            completed = user.get("completed_tasks", [])
            result = []
            for t in tasks:
                result.append({
                    "id": t["id"],
                    "name": t["name"],
                    "reward": t["reward"],
                    "completed": t["id"] in completed
                })
            return api_response({"tasks": result})

        if path == "/tasks/complete" and method == "POST":
            task_id = body.get("task_id")
            tasks = tasks_db.get_active()
            task = None
            for t in tasks:
                if t["id"] == task_id:
                    task = t
                    break
            if not task:
                return api_response({"message": "Задание не найдено"}, False)

            user = user_db.get_user(user_id)
            if task_id in user.get("completed_tasks", []):
                return api_response({"message": "Уже выполнено"}, False)

            # Проверка подписки
            try:
                member = await bot.get_chat_member(task["channel_id"], user_id)
                if member.status not in ["member", "administrator", "creator"]:
                    return api_response({"message": "Не подписаны на канал"}, False)
            except:
                return api_response({"message": "Ошибка проверки"}, False)

            user_db.add_balance(user_id, task["reward"])
            user["completed_tasks"] = user.get("completed_tasks", []) + [task_id]
            user_db.save()
            return api_response({"reward": task["reward"]})

        # ===== ЛИДЕРЫ =====
        if path.startswith("/leaderboard") and method == "GET":
            sort_by = path.split("/")[-1]
            leaders = user_db.get_top_players(20, sort_by)
            user = user_db.get_user(user_id)
            user_rank = None
            for i, l in enumerate(leaders):
                if str(l["id"]) == str(user_id):
                    user_rank = i + 1
                    break
            return api_response({
                "leaders": leaders,
                "userRank": user_rank,
                "userScore": user["balance"] if sort_by == "balance" else user["games_won"]
            })

        # ===== МУЗЫКА =====
        if path == "/music/playlist" and method == "GET":
            return api_response({"playlist": music_db.get_all()})

        return api_response({"message": "Endpoint not found"}, False)

    except Exception as e:
        logging.error(f"API Error: {e}")
        return api_response({"message": str(e)}, False)
# ========== АДМИНКА: КЕЙСЫ ==========
@dp.callback_query(F.data == "admin_cases")
async def admin_cases(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    cases = cases_db.get_all()
    text = "<b>📦 Кейсы</b>\n\n"
    for c in cases:
        text += f"{c['emoji']} {c['name']} — {c['price']}⭐\n"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать", callback_data="admin_create_case")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ========== АДМИНКА: ВЫВОДЫ NFT (С ХОЛДОМ) ==========
@dp.callback_query(F.data == "admin_withdraws")
async def admin_withdraws(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    pending = withdraw_db.get_pending()
    if not pending:
        await callback.message.edit_text("📤 Нет заявок на вывод", reply_markup=back_to_admin())
        return
    text = "<b>📤 Заявки на вывод NFT</b>\n\n"
    for req in pending[:10]:
        hold_until = datetime.fromisoformat(req["hold_until"]).strftime("%d.%m.%Y %H:%M")
        text += f"#{req['id']} | {req['nft_emoji']} {req['nft_name']}\n"
        text += f"👤 ID: {req['user_id']} | 💰 {req['nft_value']}⭐\n"
        text += f"⏳ Холд до: {hold_until}\n\n"
    builder = InlineKeyboardBuilder()
    for req in pending[:5]:
        builder.button(text=f"✅ #{req['id']}", callback_data=f"wd_complete_{req['id']}")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    builder.adjust(5)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("wd_complete_"))
async def wd_complete(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    req_id = int(callback.data.split("_")[2])
    withdraw_db.complete(req_id)
    await callback.message.edit_text(f"✅ Заявка #{req_id} выполнена", reply_markup=back_to_admin())

# ========== АДМИНКА: МУЗЫКА ==========
class MusicStates(StatesGroup):
    waiting_name = State()
    waiting_url = State()

@dp.callback_query(F.data == "admin_music")
async def admin_music(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    tracks = music_db.get_all()
    text = "<b>🎵 Плейлист</b>\n\n"
    for t in tracks:
        text += f"🎵 {t['name']}\n"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить", callback_data="music_add")
    builder.button(text="❌ Удалить", callback_data="music_del")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "music_add")
async def music_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await state.set_state(MusicStates.waiting_name)
    await callback.message.edit_text("🎵 Введите название трека:", reply_markup=back_to_admin())

@dp.message(MusicStates.waiting_name)
async def music_name(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.update_data(name=message.text)
    await state.set_state(MusicStates.waiting_url)
    await message.answer("🔗 Введите URL MP3 файла:")

@dp.message(MusicStates.waiting_url)
async def music_url(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    data = await state.get_data()
    music_db.add(data["name"], message.text)
    await message.answer("✅ Трек добавлен!", reply_markup=get_admin_panel())
    await state.clear()

# ========== АДМИНКА: НАСТРОЙКИ ИГР ==========
class GameSettingsStates(StatesGroup):
    waiting_game = State()
    waiting_key = State()
    waiting_value = State()

@dp.callback_query(F.data == "admin_games")
async def admin_games(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    builder = InlineKeyboardBuilder()
    for game in ["rocket", "mines", "blackjack", "trading"]:
        builder.button(text=f"🎮 {game}", callback_data=f"gameset_{game}")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    builder.adjust(2)
    await callback.message.edit_text("🎮 Выберите игру:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("gameset_"))
async def gameset_game(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    game = callback.data.split("_")[1]
    await state.update_data(game=game)
    settings = settings_db.settings.get(game, {})
    text = f"⚙️ <b>{game}</b>\n\n"
    for k, v in settings.items():
        text += f"{k} = {v}\n"
    text += "\nВведите ключ для изменения:"
    await state.set_state(GameSettingsStates.waiting_key)
    await callback.message.edit_text(text, reply_markup=back_to_admin())

@dp.message(GameSettingsStates.waiting_key)
async def gameset_key(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.update_data(key=message.text)
    await state.set_state(GameSettingsStates.waiting_value)
    await message.answer("📝 Введите новое значение:")

@dp.message(GameSettingsStates.waiting_value)
async def gameset_val(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    data = await state.get_data()
    game = data["game"]
    key = data["key"]
    val = message.text
    try:
        if "." in val: val = float(val)
        else: val = int(val)
    except:
        pass
    settings_db.set(game, key, val)
    await message.answer(f"✅ {key} = {val}", reply_markup=get_admin_panel())
    await state.clear()

# ========== КНОПКА НАЗАД ==========
def back_to_admin():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    return builder.as_markup()

@dp.callback_query(F.data == "back_to_admin")
async def back_admin(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.edit_text("🔐 <b>Админ-панель</b>", reply_markup=get_admin_panel())
# ========== WEBHOOK ДЛЯ RENDER ==========
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL", "https://your-bot.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 8080))

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    print("🛑 Webhook удалён")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_post(f"/api/{{tail:.*}}", handle_api_request)
    app.router.add_get(f"/api/{{tail:.*}}", handle_api_request)

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()

    print(f"🚀 Бот запущен на {WEBHOOK_URL}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())