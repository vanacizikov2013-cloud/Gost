import json
import os
import asyncio
import logging
import sys
import uuid
import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from math import comb

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [8440115662, 8114610850]

DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

USERS_FILE = f"{DATA_DIR}/users.json"
CASES_FILE = f"{DATA_DIR}/cases.json"
NFTS_FILE = f"{DATA_DIR}/nfts.json"
PROMOS_FILE = f"{DATA_DIR}/promos.json"
TASKS_FILE = f"{DATA_DIR}/tasks.json"
CHANNELS_FILE = f"{DATA_DIR}/channels.json"
STATS_FILE = f"{DATA_DIR}/stats.json"
WITHDRAWS_FILE = f"{DATA_DIR}/withdraws.json"
SETTINGS_FILE = f"{DATA_DIR}/settings.json"

DEFAULT_SETTINGS = {
    "mines_3x3": {
        "enabled": True, "min_bet": 1, "max_bet": 1000, "max_mines": 5,
        "multipliers": {"1": 1.2, "2": 1.5, "3": 2.0, "4": 3.0, "5": 5.0},
        "rigged_enabled": True, "rigged_threshold": 200, "rigged_chance": 30
    },
    "mines_5x5": {
        "enabled": True, "min_bet": 1, "max_bet": 5000, "max_mines": 15,
        "multipliers": {"1": 1.1, "2": 1.3, "3": 1.6, "4": 2.0, "5": 2.5,
            "6": 3.2, "7": 4.0, "8": 5.0, "9": 6.5, "10": 8.0,
            "11": 10.0, "12": 15.0, "13": 20.0, "14": 30.0, "15": 50.0},
        "rigged_enabled": True, "rigged_threshold": 200, "rigged_chance": 30
    },
    "rocket": {
        "enabled": True, "min_bet": 1, "max_bet": 10000,
        "crash_range": [1.0, 100.0], "house_edge": 5
    },
    "blackjack": {
        "enabled": True, "min_bet": 1, "max_bet": 5000,
        "dealer_win_chance": 65, "blackjack_multiplier": 2.5
    }
}

# ========== db.py ==========
import json
import os
import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Any

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
                "id": user_id, "username": "", "first_name": "", "balance": 0.0,
                "total_deposit": 0.0, "total_withdraw": 0.0, "games_played": 0,
                "games_won": 0, "referral_code": self._generate_ref_code(),
                "referred_by": None, "referrals_count": 0, "referral_earnings": 0.0,
                "inventory": [], "completed_tasks": [], "used_promos": [],
                "registered_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(), "banned": False
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
    def add_balance(self, user_id: int, amount: float) -> float:
        user = self.get_user(user_id)
        user["balance"] = round(user["balance"] + amount, 2)
        user["total_deposit"] = round(user["total_deposit"] + amount, 2)
        self.save()
        return user["balance"]
    def remove_balance(self, user_id: int, amount: float) -> bool:
        user = self.get_user(user_id)
        if user["balance"] >= amount:
            user["balance"] = round(user["balance"] - amount, 2)
            self.save()
            return True
        return False
    def get_top_players(self, limit: int = 10) -> List[Dict]:
        players = []
        for user_id, data in self.users.items():
            if not data.get("banned", False):
                players.append({
                    "id": user_id, "username": data.get("username", "Unknown"),
                    "first_name": data.get("first_name", "Unknown"),
                    "balance": data.get("balance", 0), "games_won": data.get("games_won", 0)
                })
        players.sort(key=lambda x: x["balance"], reverse=True)
        return players[:limit]
    def add_referral_bonus(self, referrer_id: int, amount: float = 5.0) -> None:
        referrer = self.get_user(referrer_id)
        referrer["balance"] = round(referrer["balance"] + amount, 2)
        referrer["referral_earnings"] = round(referrer["referral_earnings"] + amount, 2)
        referrer["referrals_count"] += 1
        self.save()

class CasesDB:
    def __init__(self):
        self.cases = Database.load_file(CASES_FILE, [])
    def save(self):
        Database.save_file(CASES_FILE, self.cases)
    def create_case(self, name: str, price: float, description: str = "") -> Dict:
        case = {
            "id": len(self.cases) + 1, "name": name, "price": price,
            "description": description, "items": [], "total_opens": 0,
            "created_at": datetime.now().isoformat(), "enabled": True
        }
        self.cases.append(case)
        self.save()
        return case
    def get_case(self, case_id: int) -> Optional[Dict]:
        for case in self.cases:
            if case["id"] == case_id: return case
        return None
    def add_item_to_case(self, case_id: int, nft_id: int, chance: float) -> bool:
        case = self.get_case(case_id)
        if case:
            case["items"].append({"nft_id": nft_id, "chance": chance})
            self.save()
            return True
        return False
    def open_case(self, case_id: int) -> Optional[int]:
        case = self.get_case(case_id)
        if not case or not case["items"]: return None
        case["total_opens"] += 1
        self.save()
        total_chance = sum(item["chance"] for item in case["items"])
        rand = random.uniform(0, total_chance)
        current = 0
        for item in case["items"]:
            current += item["chance"]
            if rand <= current: return item["nft_id"]
        return case["items"][0]["nft_id"]

class NFTDB:
    def __init__(self):
        self.nfts = Database.load_file(NFTS_FILE, [])
    def save(self):
        Database.save_file(NFTS_FILE, self.nfts)
    def create_nft(self, name: str, value: float, emoji: str = "🎁", description: str = "") -> Dict:
        nft = {
            "id": len(self.nfts) + 1, "name": name, "value": value,
            "emoji": emoji, "description": description,
            "created_at": datetime.now().isoformat(), "enabled": True
        }
        self.nfts.append(nft)
        self.save()
        return nft
    def get_nft(self, nft_id: int) -> Optional[Dict]:
        for nft in self.nfts:
            if nft["id"] == nft_id: return nft
        return None
    def get_user_nfts(self, user_inventory: List[int]) -> List[Dict]:
        return [self.get_nft(nft_id) for nft_id in user_inventory if self.get_nft(nft_id)]

class SettingsDB:
    def __init__(self):
        self.settings = Database.load_file(SETTINGS_FILE, DEFAULT_SETTINGS)
    def save(self):
        Database.save_file(SETTINGS_FILE, self.settings)
    def get_setting(self, game: str, key: str, default=None):
        return self.settings.get(game, {}).get(key, default)
    def set_setting(self, game: str, key: str, value: Any) -> None:
        if game not in self.settings: self.settings[game] = {}
        self.settings[game][key] = value
        self.save()
    def toggle_game(self, game: str, enabled: bool) -> None:
        if game in self.settings:
            self.settings[game]["enabled"] = enabled
            self.save()

class TasksDB:
    def __init__(self):
        self.tasks = Database.load_file(TASKS_FILE, [])
    def save(self):
        Database.save_file(TASKS_FILE, self.tasks)
    def create_task(self, description: str, reward: float, channel_username: str, channel_id: str = "") -> Dict:
        task = {
            "id": len(self.tasks) + 1, "description": description,
            "reward": reward, "channel_username": channel_username,
            "channel_id": channel_id, "created_at": datetime.now().isoformat(),
            "enabled": True
        }
        self.tasks.append(task)
        self.save()
        return task
    def get_active_tasks(self) -> List[Dict]:
        return [task for task in self.tasks if task.get("enabled", True)]

class PromoDB:
    def __init__(self):
        self.promos = Database.load_file(PROMOS_FILE, [])
    def save(self):
        Database.save_file(PROMOS_FILE, self.promos)
    def create_promo(self, code: str, reward_type: str, reward_value: float, max_uses: int = 1) -> Dict:
        promo = {
            "code": code.upper(), "reward_type": reward_type,
            "reward_value": reward_value, "max_uses": max_uses,
            "used_count": 0, "created_at": datetime.now().isoformat(), "enabled": True
        }
        self.promos.append(promo)
        self.save()
        return promo
    def use_promo(self, code: str, user_id: int) -> Optional[Dict]:
        for promo in self.promos:
            if promo["code"] == code.upper() and promo["enabled"]:
                if promo["used_count"] < promo["max_uses"]:
                    promo["used_count"] += 1
                    self.save()
                    return promo
        return None

user_db = UserDB()
cases_db = CasesDB()
nft_db = NFTDB()
settings_db = SettingsDB()
tasks_db = TasksDB()
promo_db = PromoDB()
# ========== keyboards.py ==========

def get_main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🎁 Кейсы"), KeyboardButton(text="🚀 Ракета"))
    builder.row(KeyboardButton(text="💣 Мины"), KeyboardButton(text="🃏 Блекджек"))
    builder.row(KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Инвентарь"))
    builder.row(KeyboardButton(text="💰 Пополнить"), KeyboardButton(text="👥 Рефералы"))
    builder.row(KeyboardButton(text="🏆 Лидеры"), KeyboardButton(text="🎟️ Промокод"))
    builder.row(KeyboardButton(text="📋 Задания"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_cases_menu(cases: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for case in cases:
        if case.get("enabled", True):
            builder.button(
                text=f"{case['name']} - {case['price']}⭐",
                callback_data=f"case_{case['id']}"
            )
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_case_detail(case_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Открыть кейс", callback_data=f"open_case_{case_id}")
    builder.button(text="◀️ Назад к кейсам", callback_data="back_to_cases")
    builder.adjust(1)
    return builder.as_markup()

def get_mines_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="3x3", callback_data="mines_size_3")
    builder.button(text="5x5", callback_data="mines_size_5")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_mines_field(size: int, revealed: list, game_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(size):
        for j in range(size):
            cell_revealed = (i, j) in revealed
            text = "✅" if cell_revealed else "⬜"
            builder.button(text=text, callback_data=f"mines_cell_{game_id}_{i}_{j}")
    builder.button(text="💰 Забрать выигрыш", callback_data=f"mines_cashout_{game_id}")
    builder.adjust(size, True)
    return builder.as_markup()

def get_rocket_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Старт", callback_data="rocket_start")
    builder.button(text="💰 Забрать", callback_data="rocket_cashout")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_profile_menu(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="profile_stats")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_inventory_menu(nfts: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if nfts:
        for nft in nfts:
            builder.button(
                text=f"{nft['emoji']} {nft['name']} - {nft['value']}⭐",
                callback_data=f"nft_{nft['id']}"
            )
    else:
        builder.button(text="📭 Инвентарь пуст", callback_data="empty")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_nft_action(nft_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Продать (+5%)", callback_data=f"sell_nft_{nft_id}")
    builder.button(text="📤 Вывести", callback_data=f"withdraw_nft_{nft_id}")
    builder.button(text="◀️ Назад", callback_data="back_to_inventory")
    builder.adjust(2, 1)
    return builder.as_markup()

def get_blackjack_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 Играть", callback_data="bj_start")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    return builder.as_markup()

def get_blackjack_actions() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🃏 Взять", callback_data="bj_hit")
    builder.button(text="🛑 Хватит", callback_data="bj_stand")
    builder.adjust(2)
    return builder.as_markup()

def get_tasks_menu(tasks: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in tasks:
        builder.button(
            text=f"{task['description']} +{task['reward']}⭐",
            callback_data=f"task_{task['id']}"
        )
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_panel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Кейсы", callback_data="admin_cases")
    builder.button(text="🎨 NFT", callback_data="admin_nfts")
    builder.button(text="💣 Настройка Мины", callback_data="admin_mines")
    builder.button(text="🚀 Настройка Ракеты", callback_data="admin_rocket")
    builder.button(text="🃏 Настройка Блекджека", callback_data="admin_bj")
    builder.button(text="🎟️ Промокоды", callback_data="admin_promos")
    builder.button(text="📋 Задания", callback_data="admin_tasks")
    builder.button(text="📨 Рассылка", callback_data="admin_broadcast")
    builder.button(text="📤 Выводы NFT", callback_data="admin_withdraws")
    builder.button(text="⏹️ Остановить игру", callback_data="admin_stop_game")
    builder.button(text="🔙 Закрыть", callback_data="close_admin")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_cases_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать кейс", callback_data="admin_create_case")
    builder.button(text="✏️ Редактировать кейс", callback_data="admin_edit_case")
    builder.button(text="❌ Удалить кейс", callback_data="admin_delete_case")
    builder.button(text="◀️ Назад", callback_data="back_to_admin")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_stop_game_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💣 Мины 3x3", callback_data="stop_mines_3x3")
    builder.button(text="💣 Мины 5x5", callback_data="stop_mines_5x5")
    builder.button(text="🚀 Ракета", callback_data="stop_rocket")
    builder.button(text="🃏 Блекджек", callback_data="stop_blackjack")
    builder.button(text="◀️ Назад", callback_data="back_to_admin")
    builder.adjust(2)
    return builder.as_markup()

def get_back_button(callback_data: str = "back_to_main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data=callback_data)
    return builder.as_markup()
# ========== states.py ==========
from aiogram.fsm.state import State, StatesGroup

class DepositStates(StatesGroup):
    amount = State()

class CaseStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_description = State()
    editing_case = State()

class NFTStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_value = State()
    waiting_for_emoji = State()
    waiting_for_description = State()

class PromoStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_type = State()
    waiting_for_value = State()
    waiting_for_uses = State()

class TaskStates(StatesGroup):
    waiting_for_description = State()
    waiting_for_reward = State()
    waiting_for_channel = State()
    waiting_for_channel_id = State()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()

class MinesStates(StatesGroup):
    waiting_for_bet_3x3 = State()
    waiting_for_mines_3x3 = State()
    waiting_for_bet_5x5 = State()
    waiting_for_mines_5x5 = State()
    playing = State()

class RocketStates(StatesGroup):
    waiting_for_bet = State()
    waiting_for_autocashout = State()
    playing = State()

class BlackjackStates(StatesGroup):
    waiting_for_bet = State()
    playing = State()

class SettingsStates(StatesGroup):
    waiting_for_value = State()

class WithdrawStates(StatesGroup):
    waiting_for_reject_reason = State()

# ========== utils.py ==========
import random
import asyncio
from typing import List, Tuple, Optional
from aiogram.types import Message, CallbackQuery
from aiogram import Bot

def generate_crash_point(house_edge: float = 5) -> float:
    """Генерирует точку падения ракеты с учетом хаус эджа"""
    r = random.random()
    if r < house_edge / 100:
        return 1.0
    return round(1.0 / (1.0 - random.random()), 2)

def calculate_mines_multiplier(opened: int, total_cells: int, mines: int) -> float:
    """Расчет множителя для игры Мины"""
    from math import comb
    if opened == 0: return 1.0
    safe_cells = total_cells - mines
    probability = comb(safe_cells, opened) / comb(total_cells, opened)
    return round(0.99 / probability, 2)

def format_number(num: float) -> str:
    """Форматирование числа с разделителями"""
    return f"{num:,.2f}".replace(",", " ")

def format_card(card: Tuple[str, str]) -> str:
    """Форматирование карты для отображения"""
    suits = {"♥️": "❤️", "♦️": "🧡", "♣️": "💚", "♠️": "💙"}
    return f"{card[0]}{suits.get(card[1], card[1])}"

def calculate_hand_value(hand: List[Tuple[str, str]]) -> int:
    """Расчет стоимости руки в блекджеке"""
    value = 0
    aces = 0
    card_values = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
                   "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11}
    for card, _ in hand:
        if card == "A": aces += 1
        value += card_values[card]
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def create_deck() -> List[Tuple[str, str]]:
    """Создание колоды карт"""
    suits = ["♥️", "♦️", "♣️", "♠️"]
    ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    deck = [(rank, suit) for suit in suits for rank in ranks]
    random.shuffle(deck)
    return deck

async def check_subscription(bot: Bot, user_id: int, channel_username: str) -> bool:
    """Проверка подписки на канал"""
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except:
        return False

def escape_markdown(text: str) -> str:
    """Экранирование специальных символов для Markdown"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text
# ========== bot.py (часть 1 - инициализация и основные команды) ==========

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# Хранилище активных игр
active_games = {
    "mines": {},
    "rocket": {},
    "blackjack": {}
}

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = user_db.get_user(message.from_user.id)
    user["username"] = message.from_user.username or ""
    user["first_name"] = message.from_user.first_name or ""
    user_db.save()
    
    # Обработка реферальной ссылки
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1][4:]
        for uid, data in user_db.users.items():
            if data.get("referral_code") == ref_code and uid != str(message.from_user.id):
                if not user.get("referred_by"):
                    user["referred_by"] = uid
                    user_db.save()
                    user_db.add_referral_bonus(int(uid), 5.0)
                    await bot.send_message(uid, f"🎉 По вашей ссылке зарегистрировался новый пользователь! +5⭐")
                break
    
    welcome_text = f"""
🎰 <b>Добро пожаловать в Casino Bot!</b>

👤 <b>Профиль:</b> {message.from_user.first_name}
💰 <b>Баланс:</b> {user['balance']} ⭐
📦 <b>NFT в инвентаре:</b> {len(user['inventory'])} шт.

Выберите игру или действие в меню ниже:
"""
    await message.answer(welcome_text, reply_markup=get_main_menu())

@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):
    user = user_db.get_user(message.from_user.id)
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{user['referral_code']}"
    
    profile_text = f"""
👤 <b>Профиль игрока</b>

🆔 <b>ID:</b> <code>{user['id']}</code>
💰 <b>Баланс:</b> {format_number(user['balance'])} ⭐
📊 <b>Всего пополнено:</b> {format_number(user['total_deposit'])} ⭐
📤 <b>Всего выведено:</b> {format_number(user['total_withdraw'])} ⭐
🎮 <b>Сыграно игр:</b> {user['games_played']}
🏆 <b>Побед:</b> {user['games_won']}
👥 <b>Рефералов:</b> {user['referrals_count']}
💎 <b>Заработано с рефералов:</b> {format_number(user['referral_earnings'])} ⭐
📦 <b>NFT в инвентаре:</b> {len(user['inventory'])} шт.

🔗 <b>Реферальная ссылка:</b>
<code>{ref_link}</code>
"""
    await message.answer(profile_text, reply_markup=get_profile_menu(message.from_user.id))

@dp.message(F.text == "📦 Инвентарь")
async def inventory(message: Message):
    user = user_db.get_user(message.from_user.id)
    nfts = nft_db.get_user_nfts(user['inventory'])
    
    if not nfts:
        await message.answer("📭 Ваш инвентарь пуст. Открывайте кейсы чтобы получить NFT!")
        return
    
    inventory_text = "<b>📦 Ваш инвентарь</b>\n\n"
    total_value = 0
    for nft in nfts:
        inventory_text += f"{nft['emoji']} <b>{nft['name']}</b> - {format_number(nft['value'])} ⭐\n"
        total_value += nft['value']
    inventory_text += f"\n💰 <b>Общая стоимость:</b> {format_number(total_value)} ⭐"
    
    await message.answer(inventory_text, reply_markup=get_inventory_menu(nfts))

@dp.message(F.text == "💰 Пополнить")
async def deposit_start(message: Message, state: FSMContext):
    await message.answer(
        "💳 <b>Пополнение баланса</b>\n\n"
        "Введите сумму пополнения в звездах (минимум 1 ⭐):"
    )
    await state.set_state(DepositStates.amount)

@dp.message(DepositStates.amount, F.text.regexp(r'^\d+$'))
async def deposit_amount(message: Message, state: FSMContext):
    amount = int(message.text)
    if amount < 1:
        await message.answer("❌ Минимальная сумма пополнения 1 ⭐")
        return
    
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Пополнение баланса",
        description=f"Пополнение игрового баланса на {amount} ⭐",
        payload="deposit",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} Звезд", amount=amount)],
        start_parameter="deposit"
    )
    await state.clear()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    amount = message.successful_payment.total_amount
    user_db.add_balance(message.from_user.id, amount)
    await message.answer(f"✅ Баланс успешно пополнен на {amount} ⭐!")

@dp.message(F.text == "👥 Рефералы")
async def referrals(message: Message):
    user = user_db.get_user(message.from_user.id)
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{user['referral_code']}"
    
    text = f"""
👥 <b>Реферальная система</b>

🔗 <b>Ваша реферальная ссылка:</b>
<code>{ref_link}</code>

📊 <b>Статистика:</b>
• Приглашено пользователей: {user['referrals_count']}
• Заработано с рефералов: {format_number(user['referral_earnings'])} ⭐

🎁 <b>Бонусы:</b>
• За каждого приглашенного друга: +5 ⭐
• Друг получает: +5 ⭐
"""
    await message.answer(text)

@dp.message(F.text == "🏆 Лидеры")
async def top_players(message: Message):
    top = user_db.get_top_players(10)
    
    text = "<b>🏆 Топ игроков</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, player in enumerate(top):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = player['first_name'] or player['username'] or "Игрок"
        text += f"{medal} {name} - {format_number(player['balance'])} ⭐\n"
    
    await message.answer(text)

@dp.message(F.text == "🎟️ Промокод")
async def promo_code_start(message: Message, state: FSMContext):
    await message.answer(
        "🎟️ <b>Активация промокода</b>\n\n"
        "Введите промокод:"
    )
    await state.set_state("promo_input")

@dp.message(F.text, lambda message: message.text and len(message.text) <= 20)
async def promo_code_activate(message: Message, state: FSMContext, state_data: FSMContext = None):
    if await state.get_state() != "promo_input":
        return
    
    user = user_db.get_user(message.from_user.id)
    code = message.text.strip().upper()
    
    if code in user.get("used_promos", []):
        await message.answer("❌ Вы уже использовали этот промокод!")
        await state.clear()
        return
    
    promo = promo_db.use_promo(code, message.from_user.id)
    if not promo:
        await message.answer("❌ Промокод не найден или истек!")
        await state.clear()
        return
    
    if promo["reward_type"] == "stars":
        user_db.add_balance(message.from_user.id, promo["reward_value"])
        await message.answer(f"✅ Промокод активирован! Начислено {promo['reward_value']} ⭐")
    elif promo["reward_type"] == "percent":
        await message.answer(f"✅ Промокод активирован! Вы получите +{promo['reward_value']}% к следующему пополнению!")
        user["bonus_percent"] = promo["reward_value"]
    
    if "used_promos" not in user:
        user["used_promos"] = []
    user["used_promos"].append(code)
    user_db.update_user(message.from_user.id, user)
    await state.clear()

@dp.message(F.text == "📋 Задания")
async def tasks_menu(message: Message):
    tasks = tasks_db.get_active_tasks()
    user = user_db.get_user(message.from_user.id)
    completed = user.get("completed_tasks", [])
    
    active_tasks = [t for t in tasks if t["id"] not in completed]
    
    if not active_tasks:
        await message.answer("📋 На данный момент нет активных заданий.")
        return
    
    text = "<b>📋 Доступные задания</b>\n\n"
    for task in active_tasks:
        text += f"• {task['description']} - <b>+{task['reward']} ⭐</b>\n"
    
    await message.answer(text, reply_markup=get_tasks_menu(active_tasks))

@dp.message(F.text == "◀️ Назад")
async def back_to_main_menu(message: Message):
    await cmd_start(message, None)

# Команда для админов
@dp.message(Command("adm"))
@dp.message(F.text.lower() == "админ")
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    
    await message.answer(
        "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=get_admin_panel()
    )
# ========== bot.py (часть 2 - кейсы и NFT) ==========

@dp.message(F.text == "🎁 Кейсы")
async def cases_menu(message: Message):
    cases = cases_db.cases
    if not cases:
        await message.answer("🎁 Пока нет доступных кейсов.")
        return
    
    text = "<b>🎁 Доступные кейсы</b>\n\n"
    for case in cases:
        if case.get("enabled", True):
            text += f"📦 <b>{case['name']}</b> - {case['price']} ⭐\n"
    
    await message.answer(text, reply_markup=get_cases_menu(cases))

@dp.callback_query(F.data.startswith("case_"))
async def case_detail(callback: CallbackQuery):
    case_id = int(callback.data.split("_")[1])
    case = cases_db.get_case(case_id)
    
    if not case:
        await callback.answer("Кейс не найден", show_alert=True)
        return
    
    nfts_in_case = []
    for item in case["items"]:
        nft = nft_db.get_nft(item["nft_id"])
        if nft:
            nfts_in_case.append((nft, item["chance"]))
    
    text = f"""
🎁 <b>{case['name']}</b>

💰 <b>Цена:</b> {case['price']} ⭐
📊 <b>Открытий:</b> {case['total_opens']}

<b>📦 Содержимое кейса:</b>
"""
    total_chance = sum(c[1] for c in nfts_in_case)
    for nft, chance in nfts_in_case:
        percent = (chance / total_chance * 100) if total_chance > 0 else 0
        text += f"\n{nft['emoji']} {nft['name']} - {nft['value']} ⭐ ({percent:.1f}%)"
    
    if case.get("description"):
        text += f"\n\n📝 {case['description']}"
    
    await callback.message.edit_text(text, reply_markup=get_case_detail(case_id))
    await callback.answer()

@dp.callback_query(F.data.startswith("open_case_"))
async def open_case(callback: CallbackQuery):
    case_id = int(callback.data.split("_")[2])
    user = user_db.get_user(callback.from_user.id)
    case = cases_db.get_case(case_id)
    
    if not case:
        await callback.answer("Кейс не найден", show_alert=True)
        return
    
    if user["balance"] < case["price"]:
        await callback.answer(f"Недостаточно средств! Нужно {case['price']} ⭐", show_alert=True)
        return
    
    nft_id = cases_db.open_case(case_id)
    nft = nft_db.get_nft(nft_id)
    
    if not nft:
        await callback.answer("Ошибка открытия кейса", show_alert=True)
        return
    
    user_db.remove_balance(callback.from_user.id, case["price"])
    user["inventory"].append(nft_id)
    user_db.update_user(callback.from_user.id, user)
    
    text = f"""
🎉 <b>Вы открыли кейс {case['name']}!</b>

{nft['emoji']} <b>Вам выпал предмет:</b> {nft['name']}
💰 <b>Стоимость:</b> {nft['value']} ⭐

Предмет добавлен в инвентарь 📦
"""
    await callback.message.edit_text(text, reply_markup=get_back_button("back_to_cases"))
    await callback.answer("Кейс открыт!")

@dp.callback_query(F.data == "back_to_cases")
async def back_to_cases(callback: CallbackQuery):
    await cases_menu(callback.message)
    await callback.answer()

@dp.callback_query(F.data.startswith("nft_"))
async def nft_detail(callback: CallbackQuery):
    nft_id = int(callback.data.split("_")[1])
    nft = nft_db.get_nft(nft_id)
    
    if not nft:
        await callback.answer("NFT не найден", show_alert=True)
        return
    
    text = f"""
{nft['emoji']} <b>{nft['name']}</b>

💰 <b>Стоимость:</b> {nft['value']} ⭐
💰 <b>Цена продажи:</b> {round(nft['value'] * 1.05, 2)} ⭐ (+5%)

📝 <b>Описание:</b> {nft.get('description', 'Нет описания')}
"""
    await callback.message.edit_text(text, reply_markup=get_nft_action(nft_id))
    await callback.answer()

@dp.callback_query(F.data.startswith("sell_nft_"))
async def sell_nft(callback: CallbackQuery):
    nft_id = int(callback.data.split("_")[2])
    user = user_db.get_user(callback.from_user.id)
    
    if nft_id not in user["inventory"]:
        await callback.answer("У вас нет этого NFT!", show_alert=True)
        return
    
    nft = nft_db.get_nft(nft_id)
    if not nft:
        await callback.answer("NFT не найден", show_alert=True)
        return
    
    sell_price = round(nft["value"] * 1.05, 2)
    
    user["inventory"].remove(nft_id)
    user_db.add_balance(callback.from_user.id, sell_price)
    user_db.update_user(callback.from_user.id, user)
    
    await callback.message.edit_text(
        f"✅ <b>NFT продан!</b>\n\n"
        f"{nft['emoji']} {nft['name']} продан за {sell_price} ⭐",
        reply_markup=get_back_button("back_to_inventory")
    )
    await callback.answer(f"Продано за {sell_price} ⭐!")

@dp.callback_query(F.data.startswith("withdraw_nft_"))
async def withdraw_nft_request(callback: CallbackQuery):
    nft_id = int(callback.data.split("_")[2])
    user = user_db.get_user(callback.from_user.id)
    
    if nft_id not in user["inventory"]:
        await callback.answer("У вас нет этого NFT!", show_alert=True)
        return
    
    nft = nft_db.get_nft(nft_id)
    if not nft:
        await callback.answer("NFT не найден", show_alert=True)
        return
    
    # Сохраняем запрос на вывод
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    
    request_id = len(withdraws) + 1
    withdraw_request = {
        "id": request_id,
        "user_id": callback.from_user.id,
        "username": callback.from_user.username or "—",
        "first_name": callback.from_user.first_name or "—",
        "nft_id": nft_id,
        "nft_name": nft["name"],
        "nft_emoji": nft["emoji"],
        "nft_value": nft["value"],
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "processed_at": None,
        "admin_note": ""
    }
    withdraws.append(withdraw_request)
    Database.save_file(WITHDRAWS_FILE, withdraws)
    
    # Уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📤 <b>НОВЫЙ ЗАПРОС НА ВЫВОД #{request_id}</b>\n\n"
                f"👤 <b>Пользователь:</b> @{callback.from_user.username or callback.from_user.first_name}\n"
                f"🆔 <b>ID:</b> <code>{callback.from_user.id}</code>\n"
                f"🎁 <b>NFT:</b> {nft['emoji']} {nft['name']}\n"
                f"💰 <b>Стоимость:</b> {nft['value']} ⭐\n\n"
                f"<i>Зайдите в /adm → Выводы NFT для обработки</i>"
            )
        except:
            pass
    
    await callback.message.edit_text(
        f"📤 <b>Запрос на вывод отправлен!</b>\n\n"
        f"🎁 {nft['emoji']} {nft['name']}\n"
        f"💰 Стоимость: {nft['value']} ⭐\n\n"
        f"<i>Администратор обработает ваш запрос в ближайшее время.</i>\n"
        f"<i>Вы получите уведомление, когда NFT будет отправлен.</i>",
        reply_markup=get_back_button("back_to_inventory")
    )
    await callback.answer("Запрос отправлен!")

@dp.callback_query(F.data == "back_to_inventory")
async def back_to_inventory(callback: CallbackQuery):
    user = user_db.get_user(callback.from_user.id)
    nfts = nft_db.get_user_nfts(user['inventory'])
    
    if not nfts:
        await callback.message.edit_text("📭 Ваш инвентарь пуст.", reply_markup=get_back_button())
        return
    
    inventory_text = "<b>📦 Ваш инвентарь</b>\n\n"
    for nft in nfts:
        inventory_text += f"{nft['emoji']} <b>{nft['name']}</b> - {format_number(nft['value'])} ⭐\n"
    
    await callback.message.edit_text(inventory_text, reply_markup=get_inventory_menu(nfts))
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    user = user_db.get_user(callback.from_user.id)
    text = f"""
🎰 <b>Главное меню</b>

👤 <b>Профиль:</b> {callback.from_user.first_name}
💰 <b>Баланс:</b> {user['balance']} ⭐
📦 <b>NFT в инвентаре:</b> {len(user['inventory'])} шт.
"""
    await callback.message.edit_text(text, reply_markup=None)
    await callback.message.answer("Выберите действие:", reply_markup=get_main_menu())
    await callback.answer()
# ========== bot.py (часть 3 - игра Мины) ==========
import uuid

class MinesGame:
    def __init__(self, user_id: int, bet: float, size: int, mines_count: int):
        self.id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.bet = bet
        self.size = size
        self.mines_count = mines_count
        self.total_cells = size * size
        self.opened = 0
        self.multiplier = 1.0
        self.revealed = []
        self.mine_positions = []
        self.finished = False
        self.won = False
        
        # Генерация мин с подкруткой
        settings_key = f"mines_{size}x{size}"
        rigged_enabled = settings_db.get_setting(settings_key, "rigged_enabled", True)
        rigged_threshold = settings_db.get_setting(settings_key, "rigged_threshold", 200)
        rigged_chance = settings_db.get_setting(settings_key, "rigged_chance", 30)
        
        # Подкрутка для первой клетки если ставка большая
        self.first_cell_rigged = False
        if rigged_enabled and bet >= rigged_threshold:
            if random.randint(1, 100) <= rigged_chance:
                self.first_cell_rigged = True
        
        self._generate_mines()
    
    def _generate_mines(self):
        positions = [(i, j) for i in range(self.size) for j in range(self.size)]
        random.shuffle(positions)
        self.mine_positions = positions[:self.mines_count]
    
    def reveal_cell(self, row: int, col: int) -> dict:
        if self.finished:
            return {"success": False, "message": "Игра уже завершена"}
        
        if (row, col) in self.revealed:
            return {"success": False, "message": "Клетка уже открыта"}
        
        # Проверка подкрутки для первой клетки
        if self.opened == 0 and self.first_cell_rigged:
            # Принудительно ставим мину на выбранную клетку
            if (row, col) not in self.mine_positions:
                # Заменяем случайную мину на эту клетку
                self.mine_positions[0] = (row, col)
        
        self.revealed.append((row, col))
        
        if (row, col) in self.mine_positions:
            self.finished = True
            self.won = False
            return {"success": True, "mine": True, "finished": True, "won": False}
        
        self.opened += 1
        self.multiplier = calculate_mines_multiplier(self.opened, self.total_cells, self.mines_count)
        
        return {
            "success": True,
            "mine": False,
            "finished": False,
            "opened": self.opened,
            "multiplier": self.multiplier
        }
    
    def cashout(self) -> float:
        if self.finished:
            return 0
        self.finished = True
        self.won = True
        return round(self.bet * self.multiplier, 2)

@dp.message(F.text == "💣 Мины")
async def mines_start(message: Message):
    settings_3 = settings_db.get_setting("mines_3x3", "enabled", True)
    settings_5 = settings_db.get_setting("mines_5x5", "enabled", True)
    
    if not settings_3 and not settings_5:
        await message.answer("⏸️ Игра Мины временно недоступна.")
        return
    
    text = "<b>💣 Мины</b>\n\nВыберите размер поля:"
    await message.answer(text, reply_markup=get_mines_menu())

@dp.callback_query(F.data.startswith("mines_size_"))
async def mines_size_selected(callback: CallbackQuery, state: FSMContext):
    size = int(callback.data.split("_")[2])
    settings_key = f"mines_{size}x{size}"
    
    if not settings_db.get_setting(settings_key, "enabled", True):
        await callback.answer("Этот режим временно недоступен", show_alert=True)
        return
    
    await state.update_data(mines_size=size)
    
    min_bet = settings_db.get_setting(settings_key, "min_bet", 1)
    max_bet = settings_db.get_setting(settings_key, "max_bet", 1000)
    
    await callback.message.edit_text(
        f"<b>💣 Мины {size}x{size}</b>\n\n"
        f"Введите сумму ставки ({min_bet} - {max_bet} ⭐):"
    )
    
    if size == 3:
        await state.set_state(MinesStates.waiting_for_bet_3x3)
    else:
        await state.set_state(MinesStates.waiting_for_bet_5x5)
    
    await callback.answer()

@dp.message(MinesStates.waiting_for_bet_3x3)
async def mines_bet_3x3(message: Message, state: FSMContext):
    await process_mines_bet(message, state, 3)

@dp.message(MinesStates.waiting_for_bet_5x5)
async def mines_bet_5x5(message: Message, state: FSMContext):
    await process_mines_bet(message, state, 5)

async def process_mines_bet(message: Message, state: FSMContext, size: int):
    try:
        bet = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    settings_key = f"mines_{size}x{size}"
    min_bet = settings_db.get_setting(settings_key, "min_bet", 1)
    max_bet = settings_db.get_setting(settings_key, "max_bet", 1000)
    
    if bet < min_bet or bet > max_bet:
        await message.answer(f"❌ Ставка должна быть от {min_bet} до {max_bet} ⭐")
        return
    
    user = user_db.get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {user['balance']} ⭐")
        await state.clear()
        return
    
    await state.update_data(mines_bet=bet)
    
    max_mines = settings_db.get_setting(settings_key, "max_mines", 5 if size == 3 else 15)
    
    await message.answer(
        f"<b>💣 Мины {size}x{size}</b>\n\n"
        f"💰 Ставка: {bet} ⭐\n"
        f"💣 Введите количество мин (1-{max_mines}):"
    )
    
    if size == 3:
        await state.set_state(MinesStates.waiting_for_mines_3x3)
    else:
        await state.set_state(MinesStates.waiting_for_mines_5x5)

@dp.message(MinesStates.waiting_for_mines_3x3)
async def mines_count_3x3(message: Message, state: FSMContext):
    await process_mines_count(message, state, 3)

@dp.message(MinesStates.waiting_for_mines_5x5)
async def mines_count_5x5(message: Message, state: FSMContext):
    await process_mines_count(message, state, 5)

async def process_mines_count(message: Message, state: FSMContext, size: int):
    try:
        mines_count = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число!")
        return
    
    settings_key = f"mines_{size}x{size}"
    max_mines = settings_db.get_setting(settings_key, "max_mines", 5 if size == 3 else 15)
    
    if mines_count < 1 or mines_count > max_mines:
        await message.answer(f"❌ Количество мин должно быть от 1 до {max_mines}")
        return
    
    data = await state.get_data()
    bet = data["mines_bet"]
    
    user = user_db.get_user(message.from_user.id)
    if not user_db.remove_balance(message.from_user.id, bet):
        await message.answer("❌ Ошибка списания средств!")
        await state.clear()
        return
    
    # Создаем игру
    game = MinesGame(message.from_user.id, bet, size, mines_count)
    active_games["mines"][game.id] = game
    
    user["games_played"] = user.get("games_played", 0) + 1
    user_db.update_user(message.from_user.id, user)
    
    text = f"""
<b>💣 Игра Мины началась!</b>

📏 Поле: {size}x{size}
💰 Ставка: {bet} ⭐
💣 Количество мин: {mines_count}
📊 Множитель: 1.00x

Выбирайте клетки:
"""
    await message.answer(text, reply_markup=get_mines_field(size, [], game.id))
    await state.clear()

@dp.callback_query(F.data.startswith("mines_cell_"))
async def mines_cell_click(callback: CallbackQuery):
    parts = callback.data.split("_")
    game_id = parts[2]
    row = int(parts[3])
    col = int(parts[4])
    
    game = active_games["mines"].get(game_id)
    if not game:
        await callback.answer("Игра не найдена или завершена", show_alert=True)
        return
    
    if game.user_id != callback.from_user.id:
        await callback.answer("Это не ваша игра!", show_alert=True)
        return
    
    result = game.reveal_cell(row, col)
    
    if not result["success"]:
        await callback.answer(result["message"], show_alert=True)
        return
    
    if result.get("mine"):
        # Проигрыш
        game.finished = True
        del active_games["mines"][game_id]
        
        field_display = ""
        for i in range(game.size):
            row_display = ""
            for j in range(game.size):
                if (i, j) in game.mine_positions:
                    row_display += "💣"
                elif (i, j) in game.revealed:
                    row_display += "✅"
                else:
                    row_display += "⬜"
            field_display += row_display + "\n"
        
        text = f"""
💥 <b>ВЫ ПОДОРВАЛИСЬ НА МИНЕ!</b>

{field_display}
❌ <b>Вы проиграли {game.bet} ⭐</b>
"""
        await callback.message.edit_text(text)
        await callback.answer("💥 Мина!")
        return
    
    # Обновление множителей в настройках
    settings_key = f"mines_{game.size}x{game.size}"
    multipliers = settings_db.get_setting(settings_key, "multipliers", {})
    if str(game.opened) in multipliers:
        game.multiplier = multipliers[str(game.opened)]
    
    await callback.message.edit_reply_markup(
        reply_markup=get_mines_field(game.size, game.revealed, game.id)
    )
    
    await callback.answer(f"Множитель: {game.multiplier}x")

@dp.callback_query(F.data.startswith("mines_cashout_"))
async def mines_cashout(callback: CallbackQuery):
    game_id = callback.data.split("_")[2]
    game = active_games["mines"].get(game_id)
    
    if not game:
        await callback.answer("Игра не найдена", show_alert=True)
        return
    
    if game.user_id != callback.from_user.id:
        await callback.answer("Это не ваша игра!", show_alert=True)
        return
    
    if game.opened == 0:
        await callback.answer("Откройте хотя бы одну клетку!", show_alert=True)
        return
    
    win_amount = game.cashout()
    user_db.add_balance(callback.from_user.id, win_amount)
    
    user = user_db.get_user(callback.from_user.id)
    user["games_won"] = user.get("games_won", 0) + 1
    user_db.update_user(callback.from_user.id, user)
    
    del active_games["mines"][game_id]
    
    field_display = ""
    for i in range(game.size):
        row_display = ""
        for j in range(game.size):
            if (i, j) in game.mine_positions:
                row_display += "💣"
            elif (i, j) in game.revealed:
                row_display += "✅"
            else:
                row_display += "⬜"
        field_display += row_display + "\n"
    
    text = f"""
🎉 <b>ВЫ ЗАБРАЛИ ВЫИГРЫШ!</b>

{field_display}
✅ Открыто клеток: {game.opened}
📊 Множитель: {game.multiplier}x
💰 <b>Выигрыш: {win_amount} ⭐</b>
"""
    await callback.message.edit_text(text)
    await callback.answer(f"Выигрыш: {win_amount} ⭐!")
# ========== bot.py (часть 4 - игра Ракета) ==========

class RocketGame:
    def __init__(self, user_id: int, bet: float):
        self.id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.bet = bet
        self.multiplier = 1.0
        self.crash_point = generate_crash_point(settings_db.get_setting("rocket", "house_edge", 5))
        self.finished = False
        self.cashed_out = False
        self.start_time = datetime.now()
    
    def get_current_multiplier(self) -> float:
        if self.finished:
            return self.crash_point if not self.cashed_out else self.multiplier
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        # Экспоненциальный рост
        self.multiplier = round(1.0 * (1.05 ** (elapsed * 10)), 2)
        
        if self.multiplier >= self.crash_point:
            self.finished = True
            return self.crash_point
        
        return min(self.multiplier, self.crash_point)
    
    def cashout(self) -> float:
        if self.finished or self.cashed_out:
            return 0
        
        self.cashed_out = True
        self.finished = True
        current = self.get_current_multiplier()
        self.multiplier = current
        return round(self.bet * current, 2)

@dp.message(F.text == "🚀 Ракета")
async def rocket_start(message: Message, state: FSMContext):
    if not settings_db.get_setting("rocket", "enabled", True):
        await message.answer("⏸️ Игра Ракета временно недоступна.")
        return
    
    min_bet = settings_db.get_setting("rocket", "min_bet", 1)
    max_bet = settings_db.get_setting("rocket", "max_bet", 10000)
    
    await message.answer(
        "<b>🚀 Ракета</b>\n\n"
        f"Введите сумму ставки ({min_bet} - {max_bet} ⭐):"
    )
    await state.set_state(RocketStates.waiting_for_bet)

@dp.message(RocketStates.waiting_for_bet)
async def rocket_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    min_bet = settings_db.get_setting("rocket", "min_bet", 1)
    max_bet = settings_db.get_setting("rocket", "max_bet", 10000)
    
    if bet < min_bet or bet > max_bet:
        await message.answer(f"❌ Ставка должна быть от {min_bet} до {max_bet} ⭐")
        return
    
    user = user_db.get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {user['balance']} ⭐")
        await state.clear()
        return
    
    await state.update_data(rocket_bet=bet)
    
    await message.answer(
        "<b>🚀 Введите множитель для автовывода:</b>\n\n"
        "Например: 1.5 (ракета автоматически заберет выигрыш на этом множителе)"
    )
    await state.set_state(RocketStates.waiting_for_autocashout)

@dp.message(RocketStates.waiting_for_autocashout)
async def rocket_autocashout(message: Message, state: FSMContext):
    try:
        autocashout = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    if autocashout < 1.1:
        await message.answer("❌ Минимальный множитель для автовывода: 1.1")
        return
    
    data = await state.get_data()
    bet = data["rocket_bet"]
    
    user = user_db.get_user(message.from_user.id)
    if not user_db.remove_balance(message.from_user.id, bet):
        await message.answer("❌ Ошибка списания средств!")
        await state.clear()
        return
    
    user["games_played"] = user.get("games_played", 0) + 1
    user_db.update_user(message.from_user.id, user)
    
    game = RocketGame(message.from_user.id, bet)
    active_games["rocket"][game.id] = {
        "game": game,
        "autocashout": autocashout,
        "message_id": None
    }
    
    msg = await message.answer(
        f"<b>🚀 РАКЕТА ВЗЛЕТАЕТ!</b>\n\n"
        f"💰 Ставка: {bet} ⭐\n"
        f"🎯 Автовывод: {autocashout}x\n"
        f"📊 Текущий множитель: 1.00x",
        reply_markup=get_rocket_menu()
    )
    
    active_games["rocket"][game.id]["message_id"] = msg.message_id
    await state.clear()
    
    # Запускаем обновление ракеты
    asyncio.create_task(update_rocket(game.id, message.chat.id, msg.message_id))

async def update_rocket(game_id: str, chat_id: int, message_id: int):
    game_data = active_games["rocket"].get(game_id)
    if not game_data:
        return
    
    game = game_data["game"]
    autocashout = game_data["autocashout"]
    
    while not game.finished:
        await asyncio.sleep(0.5)
        
        if game_id not in active_games["rocket"]:
            return
        
        current = game.get_current_multiplier()
        
        # Проверка автовывода
        if not game.cashed_out and current >= autocashout:
            win_amount = game.cashout()
            user_db.add_balance(game.user_id, win_amount)
            
            user = user_db.get_user(game.user_id)
            user["games_won"] = user.get("games_won", 0) + 1
            user_db.update_user(game.user_id, user)
            
            try:
                await bot.edit_message_text(
                    f"<b>🚀 АВТОВЫВОД!</b>\n\n"
                    f"💰 Ставка: {game.bet} ⭐\n"
                    f"📊 Множитель: {game.multiplier}x\n"
                    f"🎉 <b>Выигрыш: {win_amount} ⭐</b>",
                    chat_id=chat_id,
                    message_id=message_id
                )
            except:
                pass
            
            del active_games["rocket"][game_id]
            return
        
        # Обновление сообщения
        try:
            await bot.edit_message_text(
                f"<b>🚀 РАКЕТА ЛЕТИТ!</b>\n\n"
                f"💰 Ставка: {game.bet} ⭐\n"
                f"🎯 Автовывод: {autocashout}x\n"
                f"📊 Текущий множитель: {current}x",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=get_rocket_menu()
            )
        except:
            pass
        
        if game.finished and not game.cashed_out:
            try:
                await bot.edit_message_text(
                    f"<b>💥 РАКЕТА ВЗОРВАЛАСЬ!</b>\n\n"
                    f"💰 Ставка: {game.bet} ⭐\n"
                    f"💥 Точка взрыва: {game.crash_point}x\n"
                    f"❌ <b>Вы проиграли {game.bet} ⭐</b>",
                    chat_id=chat_id,
                    message_id=message_id
                )
            except:
                pass
            
            del active_games["rocket"][game_id]
            return

@dp.callback_query(F.data == "rocket_cashout")
async def rocket_cashout_click(callback: CallbackQuery):
    # Найти игру пользователя
    user_game = None
    user_game_id = None
    
    for game_id, game_data in active_games["rocket"].items():
        if game_data["game"].user_id == callback.from_user.id:
            user_game = game_data["game"]
            user_game_id = game_id
            break
    
    if not user_game:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    if user_game.finished or user_game.cashed_out:
        await callback.answer("Игра уже завершена!", show_alert=True)
        return
    
    win_amount = user_game.cashout()
    user_db.add_balance(callback.from_user.id, win_amount)
    
    user = user_db.get_user(callback.from_user.id)
    user["games_won"] = user.get("games_won", 0) + 1
    user_db.update_user(callback.from_user.id, user)
    
    await callback.message.edit_text(
        f"<b>🎉 ВЫИГРЫШ ЗАБРАН!</b>\n\n"
        f"💰 Ставка: {user_game.bet} ⭐\n"
        f"📊 Множитель: {user_game.multiplier}x\n"
        f"🎉 <b>Выигрыш: {win_amount} ⭐</b>"
    )
    
    del active_games["rocket"][user_game_id]
    await callback.answer(f"Выигрыш: {win_amount} ⭐!")

@dp.callback_query(F.data == "rocket_start")
async def rocket_new_game(callback: CallbackQuery, state: FSMContext):
    await rocket_start(callback.message, state)
    await callback.answer()
# ========== bot.py (часть 5 - Блекджек) ==========

class BlackjackGame:
    def __init__(self, user_id: int, bet: float):
        self.id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.bet = bet
        self.deck = create_deck()
        self.player_hand = []
        self.dealer_hand = []
        self.finished = False
        self.player_stands = False
        
        # Раздача начальных карт
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())
    
    def player_hit(self):
        if self.finished or self.player_stands:
            return None
        card = self.deck.pop()
        self.player_hand.append(card)
        
        value = calculate_hand_value(self.player_hand)
        if value > 21:
            self.finished = True
            return {"bust": True, "value": value, "card": card}
        
        return {"bust": False, "value": value, "card": card}
    
    def player_stand(self):
        self.player_stands = True
        self.finished = True
        
        # Дилер добирает до 17
        while calculate_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        
        player_value = calculate_hand_value(self.player_hand)
        dealer_value = calculate_hand_value(self.dealer_hand)
        
        dealer_win_chance = settings_db.get_setting("blackjack", "dealer_win_chance", 65)
        
        # Подкрутка
        if random.randint(1, 100) <= dealer_win_chance:
            # Дилер выигрывает
            if player_value <= 21 and dealer_value <= 21:
                if player_value > dealer_value:
                    # Принудительно даем дилеру карту или меняем значение
                    pass
        
        if player_value > 21:
            result = "player_bust"
        elif dealer_value > 21:
            result = "dealer_bust"
        elif player_value > dealer_value:
            result = "player_win"
        elif dealer_value > player_value:
            result = "dealer_win"
        else:
            result = "push"
        
        # Проверка на блекджек
        if len(self.player_hand) == 2 and player_value == 21:
            result = "blackjack"
        
        return {
            "result": result,
            "player_value": player_value,
            "dealer_value": dealer_value,
            "dealer_hand": self.dealer_hand
        }
    
    def calculate_payout(self, result: str) -> float:
        if result == "blackjack":
            multiplier = settings_db.get_setting("blackjack", "blackjack_multiplier", 2.5)
            return round(self.bet * multiplier, 2)
        elif result in ["player_win", "dealer_bust"]:
            return round(self.bet * 2, 2)
        elif result == "push":
            return self.bet
        else:
            return 0

@dp.message(F.text == "🃏 Блекджек")
async def blackjack_start(message: Message, state: FSMContext):
    if not settings_db.get_setting("blackjack", "enabled", True):
        await message.answer("⏸️ Блекджек временно недоступен.")
        return
    
    min_bet = settings_db.get_setting("blackjack", "min_bet", 1)
    max_bet = settings_db.get_setting("blackjack", "max_bet", 5000)
    
    await message.answer(
        "<b>🃏 Блекджек</b>\n\n"
        f"Введите сумму ставки ({min_bet} - {max_bet} ⭐):"
    )
    await state.set_state(BlackjackStates.waiting_for_bet)

@dp.message(BlackjackStates.waiting_for_bet)
async def blackjack_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    min_bet = settings_db.get_setting("blackjack", "min_bet", 1)
    max_bet = settings_db.get_setting("blackjack", "max_bet", 5000)
    
    if bet < min_bet or bet > max_bet:
        await message.answer(f"❌ Ставка должна быть от {min_bet} до {max_bet} ⭐")
        return
    
    user = user_db.get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно средств! Ваш баланс: {user['balance']} ⭐")
        await state.clear()
        return
    
    if not user_db.remove_balance(message.from_user.id, bet):
        await message.answer("❌ Ошибка списания средств!")
        await state.clear()
        return
    
    user["games_played"] = user.get("games_played", 0) + 1
    user_db.update_user(message.from_user.id, user)
    
    game = BlackjackGame(message.from_user.id, bet)
    active_games["blackjack"][game.id] = game
    
    player_value = calculate_hand_value(game.player_hand)
    dealer_show = game.dealer_hand[0]
    
    player_cards = " ".join([format_card(c) for c in game.player_hand])
    dealer_cards = f"{format_card(dealer_show)} 🎴"
    
    text = f"""
<b>🃏 Блекджек</b>

💰 <b>Ставка:</b> {bet} ⭐

<b>Ваши карты:</b> {player_cards} ({player_value})
<b>Карты дилера:</b> {dealer_cards}

Выберите действие:
"""
    await message.answer(text, reply_markup=get_blackjack_actions())
    await state.clear()

@dp.callback_query(F.data == "bj_hit")
async def blackjack_hit(callback: CallbackQuery):
    user_game = None
    for game_id, game in active_games["blackjack"].items():
        if game.user_id == callback.from_user.id:
            user_game = game
            user_game_id = game_id
            break
    
    if not user_game:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    result = user_game.player_hit()
    
    if result["bust"]:
        del active_games["blackjack"][user_game_id]
        
        player_cards = " ".join([format_card(c) for c in user_game.player_hand])
        
        text = f"""
<b>💥 ПЕРЕБОР!</b>

<b>Ваши карты:</b> {player_cards} ({result['value']})
❌ <b>Вы проиграли {user_game.bet} ⭐</b>
"""
        await callback.message.edit_text(text)
        await callback.answer("Перебор!")
        return
    
    player_value = result["value"]
    player_cards = " ".join([format_card(c) for c in user_game.player_hand])
    dealer_show = format_card(user_game.dealer_hand[0])
    
    text = f"""
<b>🃏 Блекджек</b>

💰 <b>Ставка:</b> {user_game.bet} ⭐

<b>Ваши карты:</b> {player_cards} ({player_value})
<b>Карты дилера:</b> {dealer_show} 🎴

Выберите действие:
"""
    await callback.message.edit_text(text, reply_markup=get_blackjack_actions())
    await callback.answer(f"Вы взяли {format_card(result['card'])}")

@dp.callback_query(F.data == "bj_stand")
async def blackjack_stand(callback: CallbackQuery):
    user_game = None
    user_game_id = None
    
    for game_id, game in active_games["blackjack"].items():
        if game.user_id == callback.from_user.id:
            user_game = game
            user_game_id = game_id
            break
    
    if not user_game:
        await callback.answer("Нет активной игры!", show_alert=True)
        return
    
    result = user_game.player_stand()
    del active_games["blackjack"][user_game_id]
    
    payout = user_game.calculate_payout(result["result"])
    
    if payout > 0:
        user_db.add_balance(callback.from_user.id, payout)
        user = user_db.get_user(callback.from_user.id)
        user["games_won"] = user.get("games_won", 0) + 1
        user_db.update_user(callback.from_user.id, user)
    
    player_cards = " ".join([format_card(c) for c in user_game.player_hand])
    dealer_cards = " ".join([format_card(c) for c in result["dealer_hand"]])
    
    result_text = {
        "blackjack": "🎉 БЛЕКДЖЕК!",
        "player_win": "🎉 ВЫ ВЫИГРАЛИ!",
        "dealer_win": "😔 ДИЛЕР ВЫИГРАЛ",
        "dealer_bust": "🎉 ПЕРЕБОР У ДИЛЕРА!",
        "player_bust": "💥 ПЕРЕБОР",
        "push": "🤝 НИЧЬЯ"
    }.get(result["result"], "")
    
    text = f"""
<b>🃏 {result_text}</b>

<b>Ваши карты:</b> {player_cards} ({result['player_value']})
<b>Карты дилера:</b> {dealer_cards} ({result['dealer_value']})

💰 <b>{'Выигрыш' if payout > user_game.bet else 'Возврат' if payout == user_game.bet else 'Проигрыш'}:</b> {payout if payout > 0 else user_game.bet} ⭐
"""
    await callback.message.edit_text(text)
    await callback.answer()
# ========== bot.py (часть 6 - Админ-панель) ==========

@dp.callback_query(F.data == "admin_cases")
async def admin_cases(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    cases = cases_db.cases
    text = "<b>📦 Управление кейсами</b>\n\n"
    
    if cases:
        for case in cases:
            status = "✅" if case.get("enabled", True) else "❌"
            text += f"{status} <b>{case['name']}</b> - {case['price']} ⭐ (ID: {case['id']})\n"
    else:
        text += "Нет созданных кейсов"
    
    await callback.message.edit_text(text, reply_markup=get_admin_cases_menu())
    await callback.answer()

@dp.callback_query(F.data == "admin_create_case")
async def admin_create_case_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "<b>➕ Создание кейса</b>\n\nВведите название кейса:",
        reply_markup=get_back_button("admin_cases")
    )
    await state.set_state(CaseStates.waiting_for_name)
    await callback.answer()

@dp.message(CaseStates.waiting_for_name)
async def admin_case_name(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await state.update_data(case_name=message.text)
    await message.answer("Введите цену кейса в звездах:")
    await state.set_state(CaseStates.waiting_for_price)

@dp.message(CaseStates.waiting_for_price)
async def admin_case_price(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        price = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    await state.update_data(case_price=price)
    await message.answer("Введите описание кейса (или отправьте '-' пропустить):")
    await state.set_state(CaseStates.waiting_for_description)

@dp.message(CaseStates.waiting_for_description)
async def admin_case_description(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    data = await state.get_data()
    description = message.text if message.text != "-" else ""
    
    case = cases_db.create_case(data["case_name"], data["case_price"], description)
    
    await message.answer(
        f"✅ Кейс создан!\n\n"
        f"ID: {case['id']}\n"
        f"Название: {case['name']}\n"
        f"Цена: {case['price']} ⭐\n\n"
        f"Теперь добавьте NFT в кейс через редактирование.",
        reply_markup=get_main_menu()
    )
    await state.clear()

@dp.callback_query(F.data == "admin_nfts")
async def admin_nfts(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    nfts = nft_db.nfts
    text = "<b>🎨 Управление NFT</b>\n\n"
    
    if nfts:
        for nft in nfts:
            status = "✅" if nft.get("enabled", True) else "❌"
            text += f"{status} {nft['emoji']} <b>{nft['name']}</b> - {nft['value']} ⭐ (ID: {nft['id']})\n"
    else:
        text += "Нет созданных NFT"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать NFT", callback_data="admin_create_nft")
    builder.button(text="❌ Удалить NFT", callback_data="admin_delete_nft")
    builder.button(text="◀️ Назад", callback_data="back_to_admin")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "admin_create_nft")
async def admin_create_nft_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "<b>➕ Создание NFT</b>\n\nВведите название NFT:",
        reply_markup=get_back_button("admin_nfts")
    )
    await state.set_state(NFTStates.waiting_for_name)
    await callback.answer()

@dp.message(NFTStates.waiting_for_name)
async def admin_nft_name(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await state.update_data(nft_name=message.text)
    await message.answer("Введите стоимость NFT в звездах:")
    await state.set_state(NFTStates.waiting_for_value)

@dp.message(NFTStates.waiting_for_value)
async def admin_nft_value(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        value = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    await state.update_data(nft_value=value)
    await message.answer("Введите эмодзи для NFT (например 🎁):")
    await state.set_state(NFTStates.waiting_for_emoji)

@dp.message(NFTStates.waiting_for_emoji)
async def admin_nft_emoji(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await state.update_data(nft_emoji=message.text)
    await message.answer("Введите описание NFT (или '-' пропустить):")
    await state.set_state(NFTStates.waiting_for_description)

@dp.message(NFTStates.waiting_for_description)
async def admin_nft_description(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    data = await state.get_data()
    description = message.text if message.text != "-" else ""
    
    nft = nft_db.create_nft(
        data["nft_name"],
        data["nft_value"],
        data["nft_emoji"],
        description
    )
    
    await message.answer(
        f"✅ NFT создан!\n\n"
        f"ID: {nft['id']}\n"
        f"{nft['emoji']} {nft['name']}\n"
        f"Стоимость: {nft['value']} ⭐",
        reply_markup=get_main_menu()
    )
    await state.clear()

@dp.callback_query(F.data == "admin_promos")
async def admin_promos(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    promos = promo_db.promos
    text = "<b>🎟️ Управление промокодами</b>\n\n"
    
    if promos:
        for promo in promos:
            status = "✅" if promo.get("enabled", True) else "❌"
            reward = f"{promo['reward_value']}{'%' if promo['reward_type'] == 'percent' else '⭐'}"
            text += f"{status} <b>{promo['code']}</b> - {reward} ({promo['used_count']}/{promo['max_uses']})\n"
    else:
        text += "Нет созданных промокодов"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать промокод", callback_data="admin_create_promo")
    builder.button(text="◀️ Назад", callback_data="back_to_admin")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "<b>➕ Создание промокода</b>\n\nВведите код (например: WELCOME):",
        reply_markup=get_back_button("admin_promos")
    )
    await state.set_state(PromoStates.waiting_for_code)
    await callback.answer()

@dp.message(PromoStates.waiting_for_code)
async def admin_promo_code(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await state.update_data(promo_code=message.text.upper())
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Звезды", callback_data="promo_type_stars")
    builder.button(text="% Процент", callback_data="promo_type_percent")
    
    await message.answer("Выберите тип награды:", reply_markup=builder.as_markup())
    await state.set_state(PromoStates.waiting_for_type)

@dp.callback_query(F.data.startswith("promo_type_"))
async def admin_promo_type(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    promo_type = callback.data.split("_")[2]
    await state.update_data(promo_type=promo_type)
    
    await callback.message.edit_text(
        f"Введите значение награды ({'звезд' if promo_type == 'stars' else 'процентов'}):"
    )
    await state.set_state(PromoStates.waiting_for_value)
    await callback.answer()

@dp.message(PromoStates.waiting_for_value)
async def admin_promo_value(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        value = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    await state.update_data(promo_value=value)
    await message.answer("Введите количество активаций (максимум):")
    await state.set_state(PromoStates.waiting_for_uses)

@dp.message(PromoStates.waiting_for_uses)
async def admin_promo_uses(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        uses = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число!")
        return
    
    data = await state.get_data()
    
    promo = promo_db.create_promo(
        data["promo_code"],
        data["promo_type"],
        data["promo_value"],
        uses
    )
    
    await message.answer(
        f"✅ Промокод создан!\n\n"
        f"Код: <b>{promo['code']}</b>\n"
        f"Награда: {promo['reward_value']}{'%' if promo['reward_type'] == 'percent' else '⭐'}\n"
        f"Активаций: {promo['max_uses']}",
        reply_markup=get_main_menu()
    )
    await state.clear()

@dp.callback_query(F.data == "admin_tasks")
async def admin_tasks(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    tasks = tasks_db.tasks
    text = "<b>📋 Управление заданиями</b>\n\n"
    
    if tasks:
        for task in tasks:
            status = "✅" if task.get("enabled", True) else "❌"
            text += f"{status} {task['description']} - +{task['reward']}⭐\n"
            text += f"   Канал: {task['channel_username']}\n"
    else:
        text += "Нет созданных заданий"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать задание", callback_data="admin_create_task")
    builder.button(text="◀️ Назад", callback_data="back_to_admin")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "admin_create_task")
async def admin_create_task_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "<b>➕ Создание задания</b>\n\nВведите описание задания:",
        reply_markup=get_back_button("admin_tasks")
    )
    await state.set_state(TaskStates.waiting_for_description)
    await callback.answer()

@dp.message(TaskStates.waiting_for_description)
async def admin_task_description(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await state.update_data(task_description=message.text)
    await message.answer("Введите награду в звездах:")
    await state.set_state(TaskStates.waiting_for_reward)

@dp.message(TaskStates.waiting_for_reward)
async def admin_task_reward(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        reward = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    
    await state.update_data(task_reward=reward)
    await message.answer("Введите username канала (например: @channelname):")
    await state.set_state(TaskStates.waiting_for_channel)

@dp.message(TaskStates.waiting_for_channel)
async def admin_task_channel(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await state.update_data(task_channel=message.text)
    await message.answer("Введите ID канала (можно узнать через @getmyid_bot):")
    await state.set_state(TaskStates.waiting_for_channel_id)

@dp.message(TaskStates.waiting_for_channel_id)
async def admin_task_channel_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    data = await state.get_data()
    
    task = tasks_db.create_task(
        data["task_description"],
        data["task_reward"],
        data["task_channel"],
        message.text
    )
    
    await message.answer(
        f"✅ Задание создано!\n\n"
        f"ID: {task['id']}\n"
        f"Описание: {task['description']}\n"
        f"Награда: +{task['reward']}⭐\n"
        f"Канал: {task['channel_username']}",
        reply_markup=get_main_menu()
    )
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "<b>📨 Рассылка</b>\n\n"
        "Отправьте сообщение для рассылки всем пользователям:",
        reply_markup=get_back_button("back_to_admin")
    )
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.answer()

@dp.message(BroadcastStates.waiting_for_message)
async def admin_broadcast_message(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await state.update_data(broadcast_message=message.text, broadcast_entities=message.entities)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data="broadcast_confirm")
    builder.button(text="❌ Отмена", callback_data="back_to_admin")
    builder.adjust(2)
    
    await message.answer(
        "<b>📨 Подтверждение рассылки</b>\n\n"
        f"Сообщение будет отправлено {len(user_db.users)} пользователям.\n\n"
        "Подтвердите отправку:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(BroadcastStates.waiting_for_confirmation)

@dp.callback_query(F.data == "broadcast_confirm")
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    data = await state.get_data()
    message_text = data["broadcast_message"]
    entities = data.get("broadcast_entities")
    
    success = 0
    failed = 0
    
    await callback.message.edit_text("📨 <b>Рассылка началась...</b>")
    
    for user_id in user_db.users:
        try:
            await bot.send_message(
                int(user_id),
                message_text,
                entities=entities
            )
            success += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    
    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=get_back_button("back_to_admin")
    )
    await state.clear()

@dp.callback_query(F.data == "admin_withdraws")
async def admin_withdraws_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    pending = [w for w in withdraws if w["status"] == "pending"]
    
    text = f"<b>📤 Запросы на вывод NFT</b>\n"
    text += f"<i>Всего: {len(withdraws)} | Ожидают: {len(pending)}</i>\n\n"
    
    if not pending:
        text += "✅ Нет активных запросов на вывод."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Все запросы", callback_data="admin_withdraws_all")
        builder.button(text="◀️ Назад", callback_data="back_to_admin")
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        return
    
    for req in pending[:5]:
        status_emoji = {"pending": "⏳", "completed": "✅", "rejected": "❌"}.get(req["status"], "❓")
        text += f"{status_emoji} <b>#{req['id']}</b> — {req['nft_emoji']} {req['nft_name']}\n"
        text += f"   👤 @{req['username']} (ID: <code>{req['user_id']}</code>)\n"
        text += f"   💰 {req['nft_value']} ⭐ | 📅 {req['created_at'][:10]}\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for req in pending[:5]:
        builder.button(
            text=f"#{req['id']} {req['nft_emoji']} {req['username']}",
            callback_data=f"admin_withdraw_view_{req['id']}"
        )
    
    builder.button(text="📋 Все запросы", callback_data="admin_withdraws_all")
    builder.button(text="◀️ Назад", callback_data="back_to_admin")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "admin_withdraws_all")
async def admin_withdraws_all(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    
    text = "<b>📤 Все запросы на вывод</b>\n\n"
    
    if not withdraws:
        text += "Запросов пока нет."
    else:
        for req in withdraws[-15:]:
            status_text = {"pending": "⏳ Ожидает", "completed": "✅ Выполнен", "rejected": "❌ Отклонён"}.get(req["status"], "❓")
            text += f"#{req['id']} {req['nft_emoji']} {req['nft_name']} — {status_text}\n"
            text += f"👤 @{req['username']} | 💰 {req['nft_value']}⭐\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Ожидающие", callback_data="admin_withdraws_pending")
    builder.button(text="✅ Выполненные", callback_data="admin_withdraws_completed")
    builder.button(text="◀️ Назад", callback_data="admin_withdraws")
    builder.adjust(2)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_withdraw_view_"))
async def admin_withdraw_view(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    request_id = int(callback.data.split("_")[3])
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    
    req = None
    for w in withdraws:
        if w["id"] == request_id:
            req = w
            break
    
    if not req:
        await callback.answer("Запрос не найден", show_alert=True)
        return
    
    status_text = {"pending": "⏳ ОЖИДАЕТ", "completed": "✅ ВЫПОЛНЕН", "rejected": "❌ ОТКЛОНЁН"}.get(req["status"], "❓")
    
    text = f"""
<b>📤 Запрос на вывод #{req['id']}</b>

<b>Статус:</b> {status_text}

👤 <b>Пользователь:</b> @{req['username']}
🆔 <b>Telegram ID:</b> <code>{req['user_id']}</code>
👤 <b>Имя:</b> {req['first_name']}

🎁 <b>NFT на вывод:</b>
   {req['nft_emoji']} <b>{req['nft_name']}</b>
   💰 Стоимость: <b>{req['nft_value']} ⭐</b>

📅 <b>Создан:</b> {req['created_at']}
"""
    if req.get("processed_at"):
        text += f"📅 <b>Обработан:</b> {req['processed_at']}"
    if req.get("admin_note"):
        text += f"\n\n📝 <b>Заметка:</b> {req['admin_note']}"
    
    builder = InlineKeyboardBuilder()
    
    if req["status"] == "pending":
        builder.button(text="✅ ОТМЕТИТЬ ВЫПОЛНЕННЫМ", callback_data=f"admin_withdraw_complete_{request_id}")
        builder.button(text="❌ ОТКЛОНИТЬ", callback_data=f"admin_withdraw_reject_{request_id}")
    
    builder.button(text="🔗 Написать пользователю", url=f"tg://user?id={req['user_id']}")
    builder.button(text="◀️ К списку", callback_data="admin_withdraws")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_withdraw_complete_"))
async def admin_withdraw_complete(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    request_id = int(callback.data.split("_")[3])
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    
    for req in withdraws:
        if req["id"] == request_id:
            req["status"] = "completed"
            req["processed_at"] = datetime.now().isoformat()
            
            user = user_db.get_user(req["user_id"])
            if req["nft_id"] in user["inventory"]:
                user["inventory"].remove(req["nft_id"])
                user_db.update_user(req["user_id"], user)
            
            try:
                await bot.send_message(
                    req["user_id"],
                    f"✅ <b>Ваш запрос на вывод NFT выполнен!</b>\n\n"
                    f"{req['nft_emoji']} <b>{req['nft_name']}</b>\n"
                    f"💰 Стоимость: {req['nft_value']} ⭐\n\n"
                    f"<i>NFT отправлен вам администратором. Проверьте свой профиль Telegram!</i>"
                )
            except:
                pass
            
            break
    
    Database.save_file(WITHDRAWS_FILE, withdraws)
    
    await callback.message.edit_text(
        f"✅ <b>Запрос #{request_id} отмечен как выполненный!</b>\n\n"
        f"NFT удалён из инвентаря пользователя.\n"
        f"Уведомление отправлено.",
        reply_markup=get_back_button("admin_withdraws")
    )
    await callback.answer("✅ Выполнено!")

@dp.callback_query(F.data.startswith("admin_withdraw_reject_"))
async def admin_withdraw_reject_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    request_id = int(callback.data.split("_")[3])
    await state.update_data(reject_request_id=request_id)
    
    await callback.message.edit_text(
        f"<b>❌ Отклонение запроса #{request_id}</b>\n\n"
        "Введите причину отклонения:",
        reply_markup=get_back_button(f"admin_withdraw_view_{request_id}")
    )
    await state.set_state(WithdrawStates.waiting_for_reject_reason)
    await callback.answer()


@dp.message(WithdrawStates.waiting_for_reject_reason, F.text)
async def admin_withdraw_reject_reason(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    data = await state.get_data()
    request_id = data.get("reject_request_id")
    
    if not request_id:
        await message.answer("Ошибка: запрос не найден.")
        await state.clear()
        return
    
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    
    for req in withdraws:
        if req["id"] == request_id:
            req["status"] = "rejected"
            req["processed_at"] = datetime.now().isoformat()
            req["admin_note"] = message.text
            
            try:
                await bot.send_message(
                    req["user_id"],
                    f"❌ <b>Ваш запрос на вывод NFT отклонён.</b>\n\n"
                    f"{req['nft_emoji']} <b>{req['nft_name']}</b>\n"
                    f"💰 Стоимость: {req['nft_value']} ⭐\n\n"
                    f"<b>Причина:</b> {message.text}\n\n"
                    f"<i>NFT остался в вашем инвентаре.</i>"
                )
            except:
                pass
            
            break
    
    Database.save_file(WITHDRAWS_FILE, withdraws)
    
    await message.answer(
        f"❌ <b>Запрос #{request_id} отклонён!</b>\n\n"
        f"Причина: {message.text}\n"
        f"Уведомление отправлено пользователю.",
        reply_markup=get_main_menu()
    )
    await state.clear()


@dp.callback_query(F.data == "admin_withdraws_pending")
async def admin_withdraws_pending_filter(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    pending = [w for w in withdraws if w["status"] == "pending"]
    
    text = "<b>⏳ Ожидающие запросы на вывод</b>\n\n"
    
    if not pending:
        text += "✅ Нет ожидающих запросов."
    else:
        for req in pending[-10:]:
            text += f"#{req['id']} {req['nft_emoji']} {req['nft_name']}\n"
            text += f"👤 @{req['username']} | 💰 {req['nft_value']}⭐ | 📅 {req['created_at'][:10]}\n\n"
    
    builder = InlineKeyboardBuilder()
    for req in pending[:8]:
        builder.button(
            text=f"#{req['id']} {req['username']}",
            callback_data=f"admin_withdraw_view_{req['id']}"
        )
    builder.button(text="◀️ Назад", callback_data="admin_withdraws_all")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@dp.callback_query(F.data == "admin_withdraws_completed")
async def admin_withdraws_completed_filter(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    withdraws = Database.load_file(WITHDRAWS_FILE, [])
    completed = [w for w in withdraws if w["status"] == "completed"]
    
    text = "<b>✅ Выполненные запросы на вывод</b>\n\n"
    
    if not completed:
        text += "Нет выполненных запросов."
    else:
        for req in completed[-10:]:
            text += f"#{req['id']} {req['nft_emoji']} {req['nft_name']}\n"
            text += f"👤 @{req['username']} | 💰 {req['nft_value']}⭐\n"
            text += f"✅ Обработан: {req.get('processed_at', '—')[:10]}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="admin_withdraws_all")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@dp.callback_query(F.data == "admin_stop_game")
async def admin_stop_game(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "<b>⏹️ Остановка игр</b>\n\nВыберите игру для остановки/запуска:",
        reply_markup=get_admin_stop_game_menu()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("stop_"))
async def admin_toggle_game(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    game = callback.data[5:]
    game_names = {
        "mines_3x3": "Мины 3x3",
        "mines_5x5": "Мины 5x5",
        "rocket": "Ракета",
        "blackjack": "Блекджек"
    }
    
    settings_key = game
    current = settings_db.get_setting(settings_key, "enabled", True)
    settings_db.toggle_game(settings_key, not current)
    
    status = "ОСТАНОВЛЕНА" if current else "ЗАПУЩЕНА"
    
    await callback.answer(f"Игра {game_names.get(game, game)} {status}!")
    await admin_stop_game(callback)


@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=get_admin_panel()
    )
    await callback.answer()


@dp.callback_query(F.data == "close_admin")
async def close_admin(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()


@dp.callback_query(F.data.startswith("task_"))
async def complete_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    tasks = tasks_db.get_active_tasks()
    task = None
    
    for t in tasks:
        if t["id"] == task_id:
            task = t
            break
    
    if not task:
        await callback.answer("Задание не найдено!", show_alert=True)
        return
    
    user = user_db.get_user(callback.from_user.id)
    if task_id in user.get("completed_tasks", []):
        await callback.answer("Вы уже выполнили это задание!", show_alert=True)
        return
    
    is_subscribed = await check_subscription(bot, callback.from_user.id, task["channel_username"])
    
    if not is_subscribed:
        await callback.answer(f"Вы не подписаны на {task['channel_username']}!", show_alert=True)
        return
    
    user_db.add_balance(callback.from_user.id, task["reward"])
    
    if "completed_tasks" not in user:
        user["completed_tasks"] = []
    user["completed_tasks"].append(task_id)
    user_db.update_user(callback.from_user.id, user)
    
    await callback.message.edit_text(
        f"✅ <b>Задание выполнено!</b>\n\n"
        f"Награда: +{task['reward']} ⭐\n"
        f"Новый баланс: {user['balance']} ⭐",
        reply_markup=get_back_button()
    )
    await callback.answer(f"+{task['reward']} ⭐!")
   

# Webhook настройки
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL", "https://твой-урл.onrender.com")  # ← ЗАМЕНИ НА СВОЙ
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# HTTP сервер для PythonAnywhere
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 8080))

async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    print("Webhook deleted")

async def main():
    # Настройка вебхука
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создаём aiohttp приложение
    app = web.Application()
    
    # Регистрируем обработчик вебхуков
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    # Запускаем веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()
    
    print(f"Bot running on {WEBHOOK_URL}")
    await asyncio.Event().wait()  # Бесконечное ожидание

if __name__ == "__main__":
    asyncio.run(main())