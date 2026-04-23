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
ADMIN_IDS = [8440115662, 8114610850]
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

DEFAULT_SETTINGS = {
    "rocket": {"house_edge": 5, "color_thresholds": {"blue": 1.5, "red": 2.0, "gold": 2.0}},
    "mines": {"multipliers_3": [1.0,1.2,1.5,2.0,3.0,5.0], "multipliers_5": [1.0,1.3,1.6,2.2,3.2,5.5,10.0], "multipliers_8": [1.0,1.4,1.9,2.8,4.5,8.0,15.0], "rigged_chance": 20, "big_bet_threshold": 300, "big_bet_rigged": 30},
    "blackjack": {"dealer_win_chance": 55, "blackjack_multiplier": 2.5},
    "trading": {"volatility": {"low": 0.5, "medium": 1.5, "high": 3.0}},
    "bot": {"daily_bonus_min": 1, "daily_bonus_max": 10, "referral_bonus": 1, "referral_percent": 5, "welcome_bonus": 5, "min_deposit": 10, "withdraw_hold_hours": 24, "withdraw_penalty_percent": 20}
}

# ========== JSON БАЗА ДАННЫХ ==========
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
    def __init__(self): self.users = Database.load_file(USERS_FILE, {})
    def save(self): Database.save_file(USERS_FILE, self.users)
    def get_user(self, user_id: int) -> Dict:
        user_id = str(user_id)
        if user_id not in self.users:
            self.users[user_id] = {
                "id": user_id, "username": "", "first_name": "",
                "balance": int(DEFAULT_SETTINGS["bot"]["welcome_bonus"]),
                "total_deposit": 0, "total_withdraw": 0,
                "games_played": 0, "games_won": 0,
                "referral_code": ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)),
                "referred_by": None, "referrals_count": 0, "referral_earnings": 0,
                "inventory": [], "completed_tasks": [], "used_promos": [],
                "daily_streak": 0, "last_daily": None,
                "registered_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(), "banned": False
            }
            self.save()
        return self.users[user_id]
    def update_user(self, user_id: int, data: Dict) -> None:
        user_id = str(user_id)
        if user_id in self.users:
            self.users[user_id].update(data)
            self.save()
    def add_balance(self, user_id: int, amount: int) -> int:
        user = self.get_user(user_id)
        user["balance"] += amount
        if amount > 0: user["total_deposit"] += amount
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
                    "id": uid, "username": data.get("username", "Unknown"),
                    "balance": data.get("balance", 0), "games_won": data.get("games_won", 0)
                })
        players.sort(key=lambda x: x[sort_by if sort_by in ["balance","games_won"] else "balance"], reverse=True)
        return players[:limit]

class CasesDB:
    def __init__(self): self.cases = Database.load_file(CASES_FILE, [])
    def save(self): Database.save_file(CASES_FILE, self.cases)
    def get_all(self) -> List[Dict]: return [c for c in self.cases if c.get("enabled", True)]
    def get_case(self, case_id: int) -> Optional[Dict]:
        for case in self.cases:
            if case["id"] == case_id: return case
        return None
    def create_case(self, name: str, price: int, emoji: str = "📦") -> Dict:
        case = {"id": len(self.cases)+1, "name": name, "price": price, "emoji": emoji, "items": [], "total_opens": 0, "enabled": True, "created_at": datetime.now().isoformat()}
        self.cases.append(case)
        self.save()
        return case
    def add_item(self, case_id: int, item_type: str, name: str, value: int, emoji: str, chance: int) -> bool:
        case = self.get_case(case_id)
        if case:
            case["items"].append({"type": item_type, "name": name, "value": value, "emoji": emoji, "chance": chance})
            self.save()
            return True
        return False
    def open_case(self, case_id: int) -> Optional[Dict]:
        case = self.get_case(case_id)
        if not case or not case["items"]: return None
        case["total_opens"] += 1
        self.save()
        total_chance = sum(item["chance"] for item in case["items"])
        rand = random.randint(1, total_chance)
        current = 0
        for item in case["items"]:
            current += item["chance"]
            if rand <= current: return item
        return case["items"][0]

class NFTDB:
    def __init__(self): self.nfts = Database.load_file(NFTS_FILE, [])
    def save(self): Database.save_file(NFTS_FILE, self.nfts)
    def create_nft(self, name: str, value: int, emoji: str, rarity: str = "Обычный") -> Dict:
        nft = {"id": len(self.nfts)+1, "name": name, "value": value, "emoji": emoji, "rarity": rarity, "created_at": datetime.now().isoformat()}
        self.nfts.append(nft)
        self.save()
        return nft
    def get_nft(self, nft_id: int) -> Optional[Dict]:
        for nft in self.nfts:
            if nft["id"] == nft_id: return nft
        return None

class SettingsDB:
    def __init__(self): self.settings = Database.load_file(SETTINGS_FILE, DEFAULT_SETTINGS)
    def save(self): Database.save_file(SETTINGS_FILE, self.settings)
    def get(self, game: str, key: str, default=None): return self.settings.get(game, {}).get(key, default)
    def set(self, game: str, key: str, value: Any) -> None:
        if game not in self.settings: self.settings[game] = {}
        self.settings[game][key] = value
        self.save()

class PromoDB:
    def __init__(self): self.promos = Database.load_file(PROMOS_FILE, [])
    def save(self): Database.save_file(PROMOS_FILE, self.promos)
    def create(self, code: str, reward_type: str, value: int, uses: int, expires: str = None) -> Dict:
        promo = {"id": len(self.promos)+1, "code": code.upper(), "reward_type": reward_type, "value": value, "uses_total": uses, "uses_left": uses, "expires_at": expires, "enabled": True, "created_at": datetime.now().isoformat()}
        self.promos.append(promo)
        self.save()
        return promo
    def use(self, code: str, user_id: int) -> Optional[Dict]:
        code = code.upper()
        for promo in self.promos:
            if promo["code"] == code and promo["enabled"] and promo["uses_left"] > 0:
                if promo["expires_at"] and datetime.now().isoformat() > promo["expires_at"]: continue
                promo["uses_left"] -= 1
                self.save()
                return promo
        return None

class TasksDB:
    def __init__(self): self.tasks = Database.load_file(TASKS_FILE, [])
    def save(self): Database.save_file(TASKS_FILE, self.tasks)
    def get_active(self) -> List[Dict]: return [t for t in self.tasks if t.get("enabled", True)]
    def create(self, name: str, reward: int, channel_id: str, channel_url: str, mandatory: bool = False) -> Dict:
        task = {"id": len(self.tasks)+1, "name": name, "reward": reward, "channel_id": channel_id, "channel_url": channel_url, "mandatory": mandatory, "enabled": True, "created_at": datetime.now().isoformat()}
        self.tasks.append(task)
        self.save()
        return task

class MusicDB:
    def __init__(self): self.music = Database.load_file(MUSIC_FILE, [])
    def save(self): Database.save_file(MUSIC_FILE, self.music)
    def get_all(self) -> List[Dict]: return self.music
    def add(self, name: str, url: str) -> Dict:
        track = {"id": len(self.music)+1, "name": name, "url": url, "created_at": datetime.now().isoformat()}
        self.music.append(track)
        self.save()
        return track

class WithdrawDB:
    def __init__(self): self.withdraws = Database.load_file(WITHDRAWS_FILE, [])
    def save(self): Database.save_file(WITHDRAWS_FILE, self.withdraws)
    def create(self, user_id: int, nft_id: str, nft_name: str, nft_value: int) -> Dict:
        hold_hours = settings_db.get("bot", "withdraw_hold_hours", 24)
        req = {"id": len(self.withdraws)+1, "user_id": user_id, "nft_id": nft_id, "nft_name": nft_name, "nft_value": nft_value, "status": "pending", "hold_until": (datetime.now() + timedelta(hours=hold_hours)).isoformat(), "created_at": datetime.now().isoformat(), "processed_at": None}
        self.withdraws.append(req)
        self.save()
        return req
    def get_pending(self) -> List[Dict]: return [w for w in self.withdraws if w["status"] == "pending"]
    def complete(self, req_id: int) -> bool:
        for req in self.withdraws:
            if req["id"] == req_id:
                req["status"] = "completed"
                req["processed_at"] = datetime.now().isoformat()
                self.save()
                return True
        return False

class StatsDB:
    def __init__(self): self.stats = Database.load_file(STATS_FILE, {"total_users": 0, "total_deposits": 0, "total_withdraws": 0, "total_games": 0, "game_stats": {}})
    def save(self): Database.save_file(STATS_FILE, self.stats)
    def add_game(self, game: str, bet: int, win: int):
        self.stats["total_games"] += 1
        if game not in self.stats["game_stats"]: self.stats["game_stats"][game] = {"played": 0, "total_bet": 0, "total_win": 0}
        self.stats["game_stats"][game]["played"] += 1
        self.stats["game_stats"][game]["total_bet"] += bet
        self.stats["game_stats"][game]["total_win"] += win
        self.save()

class PositionsDB:
    def __init__(self): self.positions = Database.load_file(POSITIONS_FILE, [])
    def save(self): Database.save_file(POSITIONS_FILE, self.positions)
    def create(self, user_id: int, asset_id: int, asset_name: str, pos_type: str, amount: int, open_price: float) -> Dict:
        pos = {"id": len(self.positions)+1, "user_id": user_id, "asset_id": asset_id, "asset_name": asset_name, "type": pos_type, "amount": amount, "open_price": open_price, "created_at": datetime.now().isoformat()}
        self.positions.append(pos)
        self.save()
        return pos
    def get_user_positions(self, user_id: int) -> List[Dict]: return [p for p in self.positions if p["user_id"] == user_id]
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

def back_to_admin():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
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
                    bonus = settings_db.get("bot", "referral_bonus", 1)
                    user_db.add_balance(int(uid), bonus)
                    await bot.send_message(uid, f"🎉 По вашей ссылке новый игрок! +{bonus}⭐")
                break
    await message.answer(
        f"🎰 Добро пожаловать, {message.from_user.first_name}!\n"
        f"💰 Баланс: {user['balance']} ⭐\n\n"
        f"Нажми «ИГРАТЬ» чтобы открыть Mini App!",
        reply_markup=get_main_menu()
    )

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
    min_bonus = settings_db.get("bot", "daily_bonus_min", 1)
    max_bonus = settings_db.get("bot", "daily_bonus_max", 10)
    bonus = random.randint(min_bonus, max_bonus) + (streak - 1) * 2
    user_db.add_balance(message.from_user.id, bonus)
    user_db.update_user(message.from_user.id, {"last_daily": today, "daily_streak": streak})
    await message.answer(f"🎁 <b>Ежедневный бонус!</b>\n+{bonus}⭐\n🔥 Стрик: {streak} дн.")

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

@dp.callback_query(F.data == "back_to_admin")
async def back_admin(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.edit_text("🔐 <b>Админ-панель</b>", reply_markup=get_admin_panel())
# ========== АДМИНКА: NFT ==========
class NFTStates(StatesGroup):
    waiting_name = State()
    waiting_emoji = State()
    waiting_value = State()
    waiting_rarity = State()

@dp.callback_query(F.data == "admin_nfts")
async def admin_nfts(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    nfts = nft_db.nfts
    text = "<b>🎨 NFT</b>\n\n"
    if nfts:
        for n in nfts[-5:]:
            text += f"{n['emoji']} {n['name']} — {n['value']}⭐ ({n['rarity']})\n"
    else:
        text += "Нет созданных NFT"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать NFT", callback_data="nft_create")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "nft_create")
async def nft_create_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NFTStates.waiting_name)
    await callback.message.edit_text("🎨 Введите название NFT:", reply_markup=back_to_admin())

@dp.message(NFTStates.waiting_name)
async def nft_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(NFTStates.waiting_emoji)
    await message.answer("😊 Введите эмодзи для NFT:")

@dp.message(NFTStates.waiting_emoji)
async def nft_emoji(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text)
    await state.set_state(NFTStates.waiting_value)
    await message.answer("💰 Введите стоимость NFT (в звёздах):")

@dp.message(NFTStates.waiting_value)
async def nft_value(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        await state.update_data(value=value)
        await state.set_state(NFTStates.waiting_rarity)
        await message.answer("⭐ Введите редкость (Обычный, Редкий, Эпический, Легендарный):")
    except:
        await message.answer("❌ Введите число!")

@dp.message(NFTStates.waiting_rarity)
async def nft_rarity(message: Message, state: FSMContext):
    data = await state.get_data()
    nft = nft_db.create_nft(data["name"], data["value"], data["emoji"], message.text)
    await message.answer(f"✅ NFT создан!\n{nft['emoji']} {nft['name']} — {nft['value']}⭐", reply_markup=get_admin_panel())
    await state.clear()

# ========== АДМИНКА: КЕЙСЫ ==========
class CaseStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_emoji = State()

class CaseItemStates(StatesGroup):
    waiting_case = State()
    waiting_type = State()
    waiting_name = State()
    waiting_value = State()
    waiting_emoji = State()
    waiting_chance = State()

@dp.callback_query(F.data == "admin_cases")
async def admin_cases(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    cases = cases_db.get_all()
    text = "<b>📦 Кейсы</b>\n\n"
    if cases:
        for c in cases[-5:]:
            text += f"{c['emoji']} {c['name']} — {c['price']}⭐ ({len(c['items'])} предметов)\n"
    else:
        text += "Нет созданных кейсов"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать кейс", callback_data="case_create")
    builder.button(text="➕ Добавить предмет", callback_data="case_add_item")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    builder.adjust(2)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "case_create")
async def case_create_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CaseStates.waiting_name)
    await callback.message.edit_text("📦 Введите название кейса:", reply_markup=back_to_admin())

@dp.message(CaseStates.waiting_name)
async def case_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(CaseStates.waiting_price)
    await message.answer("💰 Введите цену кейса (в звёздах):")

@dp.message(CaseStates.waiting_price)
async def case_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        await state.update_data(price=price)
        await state.set_state(CaseStates.waiting_emoji)
        await message.answer("😊 Введите эмодзи для кейса:")
    except:
        await message.answer("❌ Введите число!")

@dp.message(CaseStates.waiting_emoji)
async def case_emoji(message: Message, state: FSMContext):
    data = await state.get_data()
    case = cases_db.create_case(data["name"], data["price"], message.text)
    await message.answer(f"✅ Кейс создан!\n{case['emoji']} {case['name']} — {case['price']}⭐\n\nТеперь добавьте предметы через «Добавить предмет»", reply_markup=get_admin_panel())
    await state.clear()

@dp.callback_query(F.data == "case_add_item")
async def case_add_item_start(callback: CallbackQuery, state: FSMContext):
    cases = cases_db.get_all()
    if not cases:
        await callback.answer("Сначала создайте кейс!", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for c in cases:
        builder.button(text=f"{c['emoji']} {c['name']}", callback_data=f"caseitem_{c['id']}")
    builder.button(text="🔙 Назад", callback_data="admin_cases")
    builder.adjust(1)
    await state.set_state(CaseItemStates.waiting_case)
    await callback.message.edit_text("📦 Выберите кейс:", reply_markup=builder.as_markup())

@dp.callback_query(CaseItemStates.waiting_case, F.data.startswith("caseitem_"))
async def case_item_case(callback: CallbackQuery, state: FSMContext):
    case_id = int(callback.data.split("_")[1])
    await state.update_data(case_id=case_id)
    await state.set_state(CaseItemStates.waiting_type)
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Звёзды", callback_data="itype_stars")
    builder.button(text="🎁 NFT", callback_data="itype_nft")
    builder.button(text="🔙 Назад", callback_data="case_add_item")
    builder.adjust(2)
    await callback.message.edit_text("Выберите тип предмета:", reply_markup=builder.as_markup())

@dp.callback_query(CaseItemStates.waiting_type, F.data.startswith("itype_"))
async def case_item_type(callback: CallbackQuery, state: FSMContext):
    item_type = callback.data.split("_")[1]
    await state.update_data(item_type=item_type)
    await state.set_state(CaseItemStates.waiting_name)
    await callback.message.edit_text("📝 Введите название предмета:", reply_markup=back_to_admin())

@dp.message(CaseItemStates.waiting_name)
async def case_item_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(CaseItemStates.waiting_value)
    await message.answer("💰 Введите стоимость (в звёздах):")

@dp.message(CaseItemStates.waiting_value)
async def case_item_value(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        await state.update_data(value=value)
        await state.set_state(CaseItemStates.waiting_emoji)
        await message.answer("😊 Введите эмодзи для предмета:")
    except:
        await message.answer("❌ Введите число!")

@dp.message(CaseItemStates.waiting_emoji)
async def case_item_emoji(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text)
    await state.set_state(CaseItemStates.waiting_chance)
    await message.answer("🎲 Введите шанс выпадения (1-100):")

@dp.message(CaseItemStates.waiting_chance)
async def case_item_chance(message: Message, state: FSMContext):
    try:
        chance = int(message.text)
        if chance < 1 or chance > 100:
            await message.answer("❌ Шанс от 1 до 100!")
            return
        data = await state.get_data()
        cases_db.add_item(data["case_id"], data["item_type"], data["name"], data["value"], data["emoji"], chance)
        await message.answer(f"✅ Предмет добавлен в кейс!", reply_markup=get_admin_panel())
        await state.clear()
    except:
        await message.answer("❌ Введите число!")

# ========== АДМИНКА: ПРОМОКОДЫ ==========
class PromoStates(StatesGroup):
    waiting_code = State()
    waiting_reward_type = State()
    waiting_value = State()
    waiting_uses = State()

@dp.callback_query(F.data == "admin_promos")
async def admin_promos(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    promos = promo_db.promos
    text = "<b>🎟️ Промокоды</b>\n\n"
    if promos:
        for p in promos[-5:]:
            text += f"<code>{p['code']}</code> — {p['value']}{'⭐' if p['reward_type']=='stars' else ' NFT'} ({p['uses_left']}/{p['uses_total']})\n"
    else:
        text += "Нет активных промокодов"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать промокод", callback_data="promo_create")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "promo_create")
async def promo_create_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoStates.waiting_code)
    await callback.message.edit_text("🎟️ Введите код промокода:", reply_markup=back_to_admin())

@dp.message(PromoStates.waiting_code)
async def promo_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.upper())
    await state.set_state(PromoStates.waiting_reward_type)
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Звёзды", callback_data="promotype_stars")
    builder.button(text="🎁 NFT", callback_data="promotype_nft")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    await message.answer("🎁 Выберите тип награды:", reply_markup=builder.as_markup())

@dp.callback_query(PromoStates.waiting_reward_type, F.data.startswith("promotype_"))
async def promo_reward_type(callback: CallbackQuery, state: FSMContext):
    rtype = callback.data.split("_")[1]
    await state.update_data(reward_type=rtype)
    await state.set_state(PromoStates.waiting_value)
    await callback.message.edit_text("💰 Введите количество звёзд или ID NFT:", reply_markup=back_to_admin())

@dp.message(PromoStates.waiting_value)
async def promo_value(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        await state.update_data(value=value)
        await state.set_state(PromoStates.waiting_uses)
        await message.answer("🔢 Введите количество активаций:")
    except:
        await message.answer("❌ Введите число!")

@dp.message(PromoStates.waiting_uses)
async def promo_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text)
        data = await state.get_data()
        promo = promo_db.create(data["code"], data["reward_type"], data["value"], uses)
        await message.answer(f"✅ Промокод <code>{promo['code']}</code> создан!", reply_markup=get_admin_panel())
        await state.clear()
    except:
        await message.answer("❌ Введите число!")

# ========== АДМИНКА: ВЫВОДЫ NFT ==========
@dp.callback_query(F.data == "admin_withdraws")
async def admin_withdraws(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    pending = withdraw_db.get_pending()
    if not pending:
        await callback.message.edit_text("📤 Нет активных заявок", reply_markup=back_to_admin())
        return
    text = "<b>📤 Заявки на вывод</b>\n\n"
    for req in pending:
        text += f"#{req['id']} {req['nft_name']} (ID {req['user_id']})\n"
    builder = InlineKeyboardBuilder()
    for req in pending[:5]:
        builder.button(text=f"✅ #{req['id']}", callback_data=f"wd_{req['id']}")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("wd_"))
async def wd_complete(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    req_id = int(callback.data.split("_")[1])
    withdraw_db.complete(req_id)
    await callback.message.edit_text(f"✅ Заявка #{req_id} выполнена", reply_markup=back_to_admin())

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
        builder.button(text=f"🎮 {game}", callback_data=f"gamecfg_{game}")
    builder.button(text="🔙 Назад", callback_data="back_to_admin")
    builder.adjust(2)
    await callback.message.edit_text("🎮 Выберите игру:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("gamecfg_"))
async def gamecfg_select(callback: CallbackQuery, state: FSMContext):
    game = callback.data.split("_")[1]
    await state.update_data(game=game)
    settings = settings_db.settings.get(game, {})
    text = f"⚙️ <b>{game}</b>\n\n" + "\n".join([f"{k} = {v}" for k, v in settings.items()])
    text += "\n\nВведите ключ для изменения:"
    await state.set_state(GameSettingsStates.waiting_key)
    await callback.message.edit_text(text, reply_markup=back_to_admin())

@dp.message(GameSettingsStates.waiting_key)
async def gamecfg_key(message: Message, state: FSMContext):
    await state.update_data(key=message.text)
    await state.set_state(GameSettingsStates.waiting_value)
    await message.answer("📝 Введите новое значение:")

@dp.message(GameSettingsStates.waiting_value)
async def gamecfg_value(message: Message, state: FSMContext):
    data = await state.get_data()
    game = data["game"]
    key = data["key"]
    val = message.text
    try:
        if '.' in val: val = float(val)
        else: val = int(val)
    except:
        pass
    settings_db.set(game, key, val)
    await message.answer(f"✅ {key} = {val}", reply_markup=get_admin_panel())
    await state.clear()
# ========== API ДЛЯ MINI APP (с CORS middleware) ==========
@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(status=200, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-User-Id",
        })
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

async def handle_api_request(request: web.Request) -> web.Response:
    try:
        path = request.path.replace("/api", "")
        method = request.method
        body = {}
        if method in ["POST", "PUT"]:
            body = await request.json()

        # 1. Сначала проверяем самые простые запросы, не требующие авторизации
        if path == "" or path == "/":
            return web.json_response({"success": True, "message": "API OK"})

        if path == "/cases" and method == "GET":
            cases = cases_db.get_all()
            return web.json_response({"success": True, "cases": cases})

        # 2. Получаем или создаём user_id
        raw_user_id = request.headers.get("X-User-Id")
        user_id = None
        if raw_user_id:
            try:
                user_id = int(raw_user_id)
            except ValueError:
                return web.json_response(
                    {"success": False, "message": "Invalid user_id"},
                    status=400,
                )

        # 3. Если нет ID — используем демо‑пользователя (первого админа)
        if not user_id:
            user_id = ADMIN_IDS[0]  # 8440115662
            logging.warning(f"⚠️ Использую демо‑пользователя {user_id}")

        # 4. Все остальные запросы (пользователь, кейсы, игры)
        if path == "/user" and method in ("GET", "POST"):
            user = user_db.get_user(user_id)
            return web.json_response({"success": True, "user": user})

        if path == "/case/open" and method == "POST":
            case_id = body.get("case_id")
            case = cases_db.get_case(case_id)
            if not case:
                return web.json_response({"success": False, "message": "Кейс не найден"})
            user = user_db.get_user(user_id)
            if user["balance"] < case["price"]:
                return web.json_response({"success": False, "message": "Недостаточно средств"})
            user_db.remove_balance(user_id, case["price"])
            item = cases_db.open_case(case_id)
            if item["type"] == "stars":
                user_db.add_balance(user_id, item["value"])
            else:
                user["inventory"].append({"id": str(uuid.uuid4())[:8], "name": item["name"], "value": item["value"], "emoji": item["emoji"], "rarity": "Кейс"})
                user_db.save()
            return web.json_response({"success": True, "item": item})

        if "/bet" in path and method == "POST":
            bet = body.get("bet", 0)
            user = user_db.get_user(user_id)
            if user["balance"] < bet:
                return web.json_response({"success": False, "message": "Недостаточно средств"})
            user_db.remove_balance(user_id, bet)
            return web.json_response({"success": True})

        if "/finish" in path and method == "POST":
            win = body.get("win", 0)
            if win > 0:
                user_db.add_balance(user_id, win)
            return web.json_response({"success": True})

        return web.json_response({"success": False, "message": "Endpoint not found"}, status=404)

    except Exception as e:
        logging.error(f"API Error: {e}")
        return web.json_response({"success": False, "message": str(e)}, status=500)

        if path == "/cases":
            return web.json_response({"success": True, "cases": cases_db.get_all()})

        if path == "/case/open":
            case_id = body.get("case_id")
            case = cases_db.get_case(case_id)
            if not case: return web.json_response({"success": False, "message": "Кейс не найден"})
            user = user_db.get_user(user_id)
            if user["balance"] < case["price"]: return web.json_response({"success": False, "message": "Недостаточно средств"})
            user_db.remove_balance(user_id, case["price"])
            item = cases_db.open_case(case_id)
            if item["type"] == "stars":
                user_db.add_balance(user_id, item["value"])
            else:
                user["inventory"].append({"id": str(uuid.uuid4())[:8], "name": item["name"], "value": item["value"], "emoji": item["emoji"], "rarity": "Кейс"})
                user_db.save()
            return web.json_response({"success": True, "item": item})

        if "/bet" in path:
            bet = body.get("bet", 0)
            user = user_db.get_user(user_id)
            if user["balance"] < bet: return web.json_response({"success": False, "message": "Недостаточно средств"})
            user_db.remove_balance(user_id, bet)
            return web.json_response({"success": True})

        if "/finish" in path:
            win = body.get("win", 0)
            if win > 0: user_db.add_balance(user_id, win)
            return web.json_response({"success": True})

        return web.json_response({"success": False, "message": "Endpoint not found"}, status=404)

    except Exception as e:
        return web.json_response({"success": False, "message": str(e)}, status=500)

# ========== WEBHOOK ==========
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL", "https://gost-tqfw.onrender.com")
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

    app = web.Application(middlewares=[cors_middleware])
    app.router.add_post("/api/{tail:.*}", handle_api_request)
    app.router.add_get("/api/{tail:.*}", handle_api_request)

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