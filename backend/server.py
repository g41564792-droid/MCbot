from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, validator
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import httpx
from google.oauth2 import service_account
from googleapiclient.discovery import build
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Telegram Bot Token
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
JWT_SECRET = os.environ.get('JWT_SECRET', 'mosquito-net-secret-key-2024')
JWT_ALGORITHM = "HS256"

# Google Sheets configuration
GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', '')
GOOGLE_SPREADSHEET_ID = os.environ.get('GOOGLE_SPREADSHEET_ID', '')

# Create the main app
app = FastAPI(title="Москитные Сетки API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===================== MODELS =====================

class UserCreate(BaseModel):
    phone: str
    password: str
    name: str
    telegram_id: Optional[int] = None

class UserLogin(BaseModel):
    phone: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    phone: str
    name: str
    telegram_id: Optional[int] = None
    is_admin: bool = False
    created_at: str

class OrderItem(BaseModel):
    installation_type: str  # проемная_наружный, проемная_внутренний, проемная_встраиваемый, дверная, роллетная
    width: int = Field(ge=150, le=3000)
    height: int = Field(ge=150, le=3000)
    quantity: int = Field(ge=1, le=30, default=1)
    color: str  # белый, коричневый, антрацит, ral_<code>
    ral_color_description: Optional[str] = None
    mounting_type: str  # z_bracket, metal_hooks, plastic_hooks
    mounting_by_manufacturer: bool = True
    mesh_type: str  # стандартное, антипыль, антимошка, антикошка
    impost: bool = False
    impost_orientation: Optional[str] = None  # вертикально, горизонтально
    notes: Optional[str] = None
    item_price: float = 0

class OrderCreate(BaseModel):
    items: List[OrderItem]
    desired_date: str
    notes: Optional[str] = None
    contact_phone: Optional[str] = None

class OrderResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    order_number: Optional[str] = None  # МС-0001, МС-0002, etc.
    user_id: str
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    items: List[OrderItem]
    total_price: float
    status: str  # new, in_progress, ready, delivered, cancelled
    status_history: Optional[List[dict]] = None  # История изменений статусов
    desired_date: str
    notes: Optional[str] = None
    contact_phone: Optional[str] = None
    created_at: str
    updated_at: str

class OrderStatusUpdate(BaseModel):
    status: str

class StatusHistoryEntry(BaseModel):
    status: str
    changed_at: str
    changed_by: Optional[str] = None  # admin user id

class PriceSettings(BaseModel):
    base_price_per_sqm: float = 2500  # за квадратный метр
    door_type_multiplier: float = 1.3
    roller_type_multiplier: float = 1.5
    ral_painting_cost: float = 1500
    mesh_antidust_extra: float = 500
    mesh_antimosquito_extra: float = 300
    mesh_anticat_extra: float = 800
    impost_cost: float = 400
    mounting_z_bracket: float = 200
    mounting_metal_hooks: float = 150
    mounting_plastic_hooks: float = 100

# Telegram Bot Order Flow States
class TelegramOrderState:
    """Состояния для flow заказа в Telegram"""
    IDLE = "idle"
    AWAITING_TYPE = "awaiting_type"
    AWAITING_MESH = "awaiting_mesh"
    AWAITING_WIDTH = "awaiting_width"
    AWAITING_HEIGHT = "awaiting_height"
    AWAITING_QUANTITY = "awaiting_quantity"
    AWAITING_COLOR = "awaiting_color"
    AWAITING_RAL = "awaiting_ral"
    AWAITING_MOUNTING = "awaiting_mounting"
    AWAITING_IMPOST = "awaiting_impost"
    AWAITING_IMPOST_ORIENTATION = "awaiting_impost_orientation"
    AWAITING_PHONE = "awaiting_phone"
    AWAITING_CONFIRM = "awaiting_confirm"
    AWAITING_MORE_ITEMS = "awaiting_more_items"

# ===================== AUTH HELPERS =====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, is_admin: bool = False) -> str:
    payload = {
        "user_id": user_id,
        "is_admin": is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_admin_user(user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ===================== PRICE CALCULATOR =====================

async def get_price_settings() -> PriceSettings:
    settings = await db.settings.find_one({"type": "price"}, {"_id": 0})
    if settings:
        return PriceSettings(**settings.get("data", {}))
    return PriceSettings()

def calculate_item_price(item: OrderItem, settings: PriceSettings) -> float:
    # Базовая цена по площади
    area_sqm = (item.width * item.height) / 1000000  # mm2 to m2
    price = area_sqm * settings.base_price_per_sqm
    
    # Множитель по типу установки
    if item.installation_type == "дверная":
        price *= settings.door_type_multiplier
    elif item.installation_type == "роллетная":
        price *= settings.roller_type_multiplier
    
    # RAL покраска
    if item.color.startswith("ral_"):
        price += settings.ral_painting_cost
    
    # Тип полотна
    if item.mesh_type == "антипыль":
        price += settings.mesh_antidust_extra
    elif item.mesh_type == "антимошка":
        price += settings.mesh_antimosquito_extra
    elif item.mesh_type == "антикошка":
        price += settings.mesh_anticat_extra
    
    # Импост
    if item.impost:
        price += settings.impost_cost
    
    # Крепление
    if item.mounting_type == "z_bracket":
        price += settings.mounting_z_bracket
    elif item.mounting_type == "metal_hooks":
        price += settings.mounting_metal_hooks
    elif item.mounting_type == "plastic_hooks":
        price += settings.mounting_plastic_hooks
    
    return round(price * item.quantity, 2)

# ===================== ORDER NUMBER GENERATION =====================

async def generate_order_number() -> str:
    """Генерация номера заказа в формате МС-0001"""
    # Get current counter
    counter = await db.counters.find_one_and_update(
        {"_id": "order_number"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    seq = counter.get("seq", 1)
    return f"МС-{seq:04d}"

async def get_order_by_number(order_number: str):
    """Найти заказ по номеру МС-XXXX"""
    return await db.orders.find_one({"order_number": order_number}, {"_id": 0})

# ===================== TELEGRAM BOT =====================

async def send_telegram_message(chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None):
    if not TELEGRAM_TOKEN:
        logger.warning("Telegram token not configured")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

async def answer_callback_query(callback_query_id: str, text: str = None):
    """Ответить на callback query"""
    if not TELEGRAM_TOKEN:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Failed to answer callback query: {e}")

async def edit_message_text(chat_id: int, message_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None):
    """Редактировать сообщение"""
    if not TELEGRAM_TOKEN:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")

# ===================== GOOGLE SHEETS =====================

def get_sheets_service():
    """Получить сервис Google Sheets API"""
    if not GOOGLE_CREDENTIALS_FILE or not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        logger.warning("Google credentials file not found")
        return None
    
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Failed to create Google Sheets service: {e}")
        return None

async def append_order_to_sheets(order: dict):
    """Добавить заказ в Google Sheets"""
    if not GOOGLE_SPREADSHEET_ID:
        logger.warning("Google Spreadsheet ID not configured")
        return
    
    def _append():
        service = get_sheets_service()
        if not service:
            return
        
        try:
            rows = []
            for item in order["items"]:
                # Build notes string
                notes_parts = []
                if item.get("impost"):
                    notes_parts.append(f"импост {item.get('impost_orientation', '')}")
                elif item.get("width", 0) > 1200 or item.get("height", 0) > 1200:
                    notes_parts.append("без импоста")
                if not item.get("mounting_by_manufacturer", True):
                    notes_parts.append("без прикручивания крепления")
                if item.get("notes"):
                    notes_parts.append(item["notes"])
                
                row = [
                    order.get("order_number", order["id"][:8]),  # Номер заказа МС-XXXX
                    order["created_at"][:10],  # Дата
                    order.get("user_name", ""),  # Клиент
                    order.get("contact_phone", order.get("user_phone", "")),  # Телефон
                    item["installation_type"],  # Тип установки
                    str(item["width"]),  # Ширина
                    str(item["height"]),  # Высота
                    str(item["quantity"]),  # Количество
                    item["color"],  # Цвет
                    item["mounting_type"],  # Крепление
                    item["mesh_type"],  # Полотно
                    "; ".join(notes_parts) if notes_parts else "",  # Примечание
                    str(item.get("item_price", 0)),  # Цена позиции
                    str(order["total_price"]),  # Общая сумма
                    order["status"],  # Статус
                    order["desired_date"]  # Желаемая дата
                ]
                rows.append(row)
            
            body = {"values": rows}
            service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SPREADSHEET_ID,
                range="A:P",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body
            ).execute()
            
            logger.info(f"Order {order.get('order_number', order['id'][:8])} appended to Google Sheets")
        except Exception as e:
            logger.error(f"Failed to append order to Google Sheets: {e}")
    
    await asyncio.to_thread(_append)

async def setup_sheets_header():
    """Создать заголовки в таблице если их нет"""
    if not GOOGLE_SPREADSHEET_ID:
        return
    
    def _setup():
        service = get_sheets_service()
        if not service:
            return
        
        try:
            # Check if header exists
            result = service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SPREADSHEET_ID,
                range="A1:P1"
            ).execute()
            
            values = result.get("values", [])
            if not values or not values[0]:
                # Add header row
                headers = [[
                    "№ заказа", "Дата", "Клиент", "Телефон", 
                    "Тип установки", "Ширина", "Высота", "Кол-во",
                    "Цвет", "Крепление", "Полотно", "Примечание",
                    "Цена поз.", "Сумма", "Статус", "Желаемая дата"
                ]]
                service.spreadsheets().values().update(
                    spreadsheetId=GOOGLE_SPREADSHEET_ID,
                    range="A1:P1",
                    valueInputOption="RAW",
                    body={"values": headers}
                ).execute()
                logger.info("Google Sheets headers created")
        except Exception as e:
            logger.error(f"Failed to setup Google Sheets header: {e}")
    
    await asyncio.to_thread(_setup)

async def notify_admins_new_order(order: dict):
    """Уведомление админов о новом заказе"""
    admins = await db.users.find({"is_admin": True, "telegram_id": {"$ne": None}}, {"_id": 0}).to_list(100)
    
    items_text = ""
    for i, item in enumerate(order["items"], 1):
        items_text += f"\n{i}. {item['width']}x{item['height']}мм, {item['quantity']}шт - {item['installation_type']}"
    
    text = f"""
<b>Новый заказ #{order['id'][:8]}</b>

<b>Клиент:</b> {order.get('user_name', 'Не указан')}
<b>Телефон:</b> {order.get('contact_phone', order.get('user_phone', 'Не указан'))}

<b>Позиции:</b>{items_text}

<b>Сумма:</b> {order['total_price']} руб.
<b>Желаемая дата:</b> {order['desired_date']}
"""
    if order.get("notes"):
        text += f"\n<b>Примечание:</b> {order['notes']}"
    
    for admin in admins:
        await send_telegram_message(admin["telegram_id"], text)

# ===================== AUTH ROUTES =====================

@api_router.post("/auth/register")
async def register(data: UserCreate):
    # Check if user exists
    existing = await db.users.find_one({"phone": data.phone})
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким телефоном уже существует")
    
    user = {
        "id": str(uuid.uuid4()),
        "phone": data.phone,
        "password": hash_password(data.password),
        "name": data.name,
        "telegram_id": data.telegram_id,
        "is_admin": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user)
    
    token = create_token(user["id"], user["is_admin"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "phone": user["phone"],
            "name": user["name"],
            "is_admin": user["is_admin"]
        }
    }

@api_router.post("/auth/login")
async def login(data: UserLogin):
    user = await db.users.find_one({"phone": data.phone}, {"_id": 0})
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Неверный телефон или пароль")
    
    token = create_token(user["id"], user.get("is_admin", False))
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "phone": user["phone"],
            "name": user["name"],
            "is_admin": user.get("is_admin", False)
        }
    }

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(**user)

# ===================== ORDER ROUTES =====================

@api_router.post("/orders")
async def create_order(data: OrderCreate, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    price_settings = await get_price_settings()
    
    items_data = []
    total_price = 0
    
    for item in data.items:
        item_dict = item.model_dump()
        
        # Build notes
        notes_parts = []
        if item.notes:
            notes_parts.append(item.notes)
        
        # Check impost recommendation
        if (item.width > 1200 or item.height > 1200) and not item.impost:
            notes_parts.append("без импоста")
        elif item.impost and item.impost_orientation:
            notes_parts.append(f"импост {item.impost_orientation}")
        
        # Check mounting
        if not item.mounting_by_manufacturer:
            notes_parts.append("без прикручивания крепления")
        
        if notes_parts:
            item_dict["notes"] = "; ".join(notes_parts)
        
        item_dict["item_price"] = calculate_item_price(item, price_settings)
        total_price += item_dict["item_price"]
        items_data.append(item_dict)
    
    order_number = await generate_order_number()
    
    order = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "user_id": user["id"],
        "user_name": user["name"],
        "user_phone": user["phone"],
        "items": items_data,
        "total_price": round(total_price, 2),
        "status": "new",
        "status_history": [{"status": "new", "changed_at": datetime.now(timezone.utc).isoformat()}],
        "desired_date": data.desired_date,
        "notes": data.notes,
        "contact_phone": data.contact_phone or user["phone"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.orders.insert_one(order)
    
    # Notify admins and add to Google Sheets
    background_tasks.add_task(notify_admins_new_order, order)
    background_tasks.add_task(append_order_to_sheets, order)
    
    return OrderResponse(**order)

@api_router.get("/orders", response_model=List[OrderResponse])
async def get_user_orders(user: dict = Depends(get_current_user)):
    orders = await db.orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [OrderResponse(**o) for o in orders]

@api_router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order["user_id"] != user["id"] and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Нет доступа")
    return OrderResponse(**order)

@api_router.put("/orders/{order_id}")
async def update_order(
    order_id: str,
    data: OrderCreate,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Редактирование заказа (только для статуса 'new')"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order["user_id"] != user["id"] and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Нет доступа")
    if order["status"] != "new":
        raise HTTPException(status_code=400, detail="Редактирование возможно только для новых заказов")
    
    price_settings = await get_price_settings()
    
    items_data = []
    total_price = 0
    
    for item in data.items:
        item_dict = item.model_dump()
        
        notes_parts = []
        if item.notes:
            notes_parts.append(item.notes)
        
        if (item.width > 1200 or item.height > 1200) and not item.impost:
            notes_parts.append("без импоста")
        elif item.impost and item.impost_orientation:
            notes_parts.append(f"импост {item.impost_orientation}")
        
        if not item.mounting_by_manufacturer:
            notes_parts.append("без прикручивания крепления")
        
        if notes_parts:
            item_dict["notes"] = "; ".join(notes_parts)
        
        item_dict["item_price"] = calculate_item_price(item, price_settings)
        total_price += item_dict["item_price"]
        items_data.append(item_dict)
    
    updated_order = {
        "items": items_data,
        "total_price": round(total_price, 2),
        "desired_date": data.desired_date,
        "notes": data.notes,
        "contact_phone": data.contact_phone or user["phone"],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.orders.update_one({"id": order_id}, {"$set": updated_order})
    
    # Get updated order
    result = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return OrderResponse(**result)

@api_router.delete("/orders/{order_id}")
async def cancel_order(order_id: str, user: dict = Depends(get_current_user)):
    """Отмена заказа (только для статуса 'new')"""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order["user_id"] != user["id"] and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Нет доступа")
    if order["status"] != "new":
        raise HTTPException(status_code=400, detail="Отмена возможна только для новых заказов")
    
    await db.orders.update_one(
        {"id": order_id}, 
        {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "message": "Заказ отменён"}

# ===================== ADMIN ROUTES =====================

@api_router.get("/admin/orders", response_model=List[OrderResponse])
async def get_all_orders(
    status: Optional[str] = None,
    user: dict = Depends(get_admin_user)
):
    query = {}
    if status:
        query["status"] = status
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [OrderResponse(**o) for o in orders]

@api_router.put("/admin/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    data: OrderStatusUpdate,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_admin_user)
):
    valid_statuses = ["new", "in_progress", "ready", "delivered", "cancelled"]
    if data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    # Get old status for comparison
    old_order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    old_status = old_order.get("status") if old_order else None
    
    result = await db.orders.find_one_and_update(
        {"id": order_id},
        {
            "$set": {"status": data.status, "updated_at": datetime.now(timezone.utc).isoformat()},
            "$push": {"status_history": {"status": data.status, "changed_at": datetime.now(timezone.utc).isoformat(), "changed_by": user["id"]}}
        },
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # Send push notification to customer via Telegram
    if old_status != data.status:
        customer = await db.users.find_one({"id": result["user_id"]}, {"_id": 0})
        if customer and customer.get("telegram_id"):
            status_emoji = {
                "new": "🆕", "in_progress": "🔧", "ready": "✅",
                "delivered": "📦", "cancelled": "❌"
            }
            status_names = {
                "new": "Новый",
                "in_progress": "В работе",
                "ready": "Готов к выдаче",
                "delivered": "Выдан",
                "cancelled": "Отменён"
            }
            
            emoji = status_emoji.get(data.status, "📋")
            status_name = status_names.get(data.status, data.status)
            
            # Build detailed notification
            items_summary = ", ".join([f"{i['width']}×{i['height']}" for i in result["items"][:3]])
            if len(result["items"]) > 3:
                items_summary += f" и ещё {len(result['items']) - 3}"
            
            text = f"""
{emoji} <b>Статус заказа обновлён!</b>

<b>Заказ:</b> #{order_id[:8]}
<b>Новый статус:</b> {status_name}
<b>Сумма:</b> {result['total_price']} ₽
<b>Позиции:</b> {items_summary}
"""
            if data.status == "ready":
                text += "\n✅ <b>Ваш заказ готов к выдаче!</b>\nСвяжитесь с нами для получения."
            elif data.status == "in_progress":
                text += "\n🔧 <b>Ваш заказ принят в работу!</b>\nОжидайте уведомления о готовности."
            elif data.status == "delivered":
                text += "\n📦 <b>Заказ выдан!</b>\nСпасибо за заказ! Будем рады видеть вас снова."
            elif data.status == "cancelled":
                text += "\n❌ <b>Заказ отменён.</b>\nЕсли у вас есть вопросы, свяжитесь с нами."
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📋 Все мои заказы", "callback_data": "my_orders"}],
                    [{"text": "🛒 Новый заказ", "callback_data": "new_order"}]
                ]
            }
            
            background_tasks.add_task(send_telegram_message, customer["telegram_id"], text, "HTML", keyboard)
    
    # Exclude _id from response
    result.pop("_id", None)
    return OrderResponse(**result)

@api_router.get("/admin/stats")
async def get_admin_stats(user: dict = Depends(get_admin_user)):
    total = await db.orders.count_documents({})
    new_orders = await db.orders.count_documents({"status": "new"})
    in_progress = await db.orders.count_documents({"status": "in_progress"})
    ready = await db.orders.count_documents({"status": "ready"})
    delivered = await db.orders.count_documents({"status": "delivered"})
    
    # Calculate revenue from delivered orders
    pipeline = [
        {"$match": {"status": "delivered"}},
        {"$group": {"_id": None, "total": {"$sum": "$total_price"}}}
    ]
    revenue_result = await db.orders.aggregate(pipeline).to_list(1)
    revenue = revenue_result[0]["total"] if revenue_result else 0
    
    return {
        "total_orders": total,
        "new_orders": new_orders,
        "in_progress": in_progress,
        "ready": ready,
        "delivered": delivered,
        "revenue": round(revenue, 2)
    }

@api_router.get("/admin/users")
async def get_all_users(user: dict = Depends(get_admin_user)):
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(1000)
    return users

@api_router.put("/admin/users/{user_id}/admin")
async def toggle_admin(user_id: str, user: dict = Depends(get_admin_user)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    new_admin_status = not target.get("is_admin", False)
    await db.users.update_one({"id": user_id}, {"$set": {"is_admin": new_admin_status}})
    return {"success": True, "is_admin": new_admin_status}

# ===================== PRICE SETTINGS ROUTES =====================

@api_router.get("/admin/settings/price")
async def get_price_settings_route(user: dict = Depends(get_admin_user)):
    settings = await get_price_settings()
    return settings.model_dump()

@api_router.put("/admin/settings/price")
async def update_price_settings(data: PriceSettings, user: dict = Depends(get_admin_user)):
    await db.settings.update_one(
        {"type": "price"},
        {"$set": {"data": data.model_dump()}},
        upsert=True
    )
    return {"success": True}

# ===================== PRICE CALCULATION (PUBLIC) =====================

@api_router.post("/calculate-price")
async def calculate_order_price(items: List[OrderItem]):
    price_settings = await get_price_settings()
    total = 0
    result_items = []
    
    for item in items:
        price = calculate_item_price(item, price_settings)
        result_items.append({
            "width": item.width,
            "height": item.height,
            "quantity": item.quantity,
            "price": price
        })
        total += price
    
    return {
        "items": result_items,
        "total": round(total, 2)
    }


# ===================== TELEGRAM WEBHOOK =====================

from telegram_bot import (
    TelegramOrderState, build_main_menu_keyboard, build_order_type_keyboard,
    build_mesh_type_keyboard, build_color_keyboard, build_mounting_keyboard,
    build_yes_no_keyboard, build_impost_orientation_keyboard, build_confirm_keyboard,
    build_cancel_keyboard, format_order_summary, TYPE_NAMES, MESH_NAMES, MOUNT_NAMES,
    STATUS_EMOJI, STATUS_NAMES
)

# Telegram Order Session Management
async def get_tg_session(chat_id: int) -> dict:
    session = await db.telegram_sessions.find_one({"chat_id": chat_id}, {"_id": 0})
    if not session:
        session = {
            "chat_id": chat_id,
            "state": TelegramOrderState.IDLE,
            "order_data": {},
            "items": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.telegram_sessions.insert_one(session)
    return session

async def update_tg_session(chat_id: int, updates: dict):
    await db.telegram_sessions.update_one({"chat_id": chat_id}, {"$set": updates}, upsert=True)

async def clear_tg_session(chat_id: int):
    await db.telegram_sessions.update_one(
        {"chat_id": chat_id},
        {"$set": {"state": TelegramOrderState.IDLE, "order_data": {}, "items": []}}
    )

async def calculate_item_price_for_tg(item: dict) -> float:
    settings = await get_price_settings()
    area_sqm = (item['width'] * item['height']) / 1000000
    price = area_sqm * settings.base_price_per_sqm
    
    if item['installation_type'] == "дверная":
        price *= settings.door_type_multiplier
    elif item['installation_type'] == "роллетная":
        price *= settings.roller_type_multiplier
    
    if item.get('color', '').startswith('ral_'):
        price += settings.ral_painting_cost
    
    mesh_type = item.get('mesh_type', 'стандартное')
    if mesh_type == "антипыль":
        price += settings.mesh_antidust_extra
    elif mesh_type == "антимошка":
        price += settings.mesh_antimosquito_extra
    elif mesh_type == "антикошка":
        price += settings.mesh_anticat_extra
    
    if item.get('impost'):
        price += settings.impost_cost
    
    mount_type = item.get('mounting_type', 'z_bracket')
    if mount_type == "z_bracket":
        price += settings.mounting_z_bracket
    elif mount_type == "metal_hooks":
        price += settings.mounting_metal_hooks
    elif mount_type == "plastic_hooks":
        price += settings.mounting_plastic_hooks
    
    return round(price * item.get('quantity', 1), 2)

@api_router.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        logger.info(f"Telegram webhook: {data.get('callback_query', {}).get('data', data.get('message', {}).get('text', ''))[:50]}")
        
        # Handle callback queries
        if "callback_query" in data:
            cb = data["callback_query"]
            callback_id = cb["id"]
            chat_id = cb["message"]["chat"]["id"]
            message_id = cb["message"]["message_id"]
            cbd = cb.get("data", "")
            
            await answer_callback_query(callback_id)
            session = await get_tg_session(chat_id)
            
            if cbd == "cancel_order":
                await clear_tg_session(chat_id)
                await edit_message_text(chat_id, message_id, "❌ <b>Заказ отменён</b>\n\nВыберите действие:", reply_markup=build_main_menu_keyboard())
            
            elif cbd == "back_main":
                await clear_tg_session(chat_id)
                await edit_message_text(chat_id, message_id, "<b>Главное меню</b>\n\nВыберите действие:", reply_markup=build_main_menu_keyboard())
            
            elif cbd == "new_order":
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_TYPE, "order_data": {}, "items": []})
                await edit_message_text(chat_id, message_id, "<b>🛒 Новый заказ</b>\n\nВыберите тип москитной сетки:", reply_markup=build_order_type_keyboard())
            
            elif cbd.startswith("type_"):
                itype = cbd.replace("type_", "")
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_MESH, "order_data.installation_type": itype})
                await edit_message_text(chat_id, message_id, f"<b>Тип:</b> {TYPE_NAMES.get(itype, itype)}\n\nВыберите тип полотна:", reply_markup=build_mesh_type_keyboard())
            
            elif cbd.startswith("mesh_"):
                mesh = cbd.replace("mesh_", "")
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_DIMENSIONS, "order_data.mesh_type": mesh})
                await edit_message_text(chat_id, message_id, f"<b>Полотно:</b> {mesh}\n\n📏 <b>Введите размеры:</b>\nширина высота [кол-во]\n\n<i>Например: 800 1200 2</i>\n<i>или: 800 1200 (1 шт)</i>", reply_markup=build_cancel_keyboard())
            
            elif cbd.startswith("color_"):
                color = cbd.replace("color_", "")
                if color == "ral":
                    await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_RAL})
                    await edit_message_text(chat_id, message_id, "🎨 <b>Введите код RAL</b>\n\n<i>Например: 7016</i>", reply_markup=build_cancel_keyboard())
                else:
                    await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_MOUNTING, "order_data.color": color})
                    await edit_message_text(chat_id, message_id, f"<b>Цвет:</b> {color}\n\n🔧 Выберите крепление:", reply_markup=build_mounting_keyboard())
            
            elif cbd.startswith("mount_"):
                mount = cbd.replace("mount_", "")
                session = await get_tg_session(chat_id)
                od = session.get("order_data", {})
                if od.get("width", 0) > 1200 or od.get("height", 0) > 1200:
                    await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_IMPOST, "order_data.mounting_type": mount})
                    await edit_message_text(chat_id, message_id, "⚠️ <b>Рекомендуется импост</b>\n(размер > 1200 мм)\n\nДобавить?", reply_markup=build_yes_no_keyboard("impost"))
                else:
                    await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_PHONE, "order_data.mounting_type": mount, "order_data.impost": False})
                    await edit_message_text(chat_id, message_id, "📱 <b>Введите телефон</b>\n\n<i>+375295012233</i>", reply_markup=build_cancel_keyboard())
            
            elif cbd == "impost_yes":
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_IMPOST_ORIENTATION, "order_data.impost": True})
                await edit_message_text(chat_id, message_id, "➕ <b>Ориентация импоста:</b>", reply_markup=build_impost_orientation_keyboard())
            
            elif cbd == "impost_no":
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_PHONE, "order_data.impost": False})
                await edit_message_text(chat_id, message_id, "📱 <b>Введите телефон</b>\n\n<i>+375295012233</i>", reply_markup=build_cancel_keyboard())
            
            elif cbd.startswith("impost_") and cbd not in ["impost_yes", "impost_no"]:
                orient = cbd.replace("impost_", "")
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_PHONE, "order_data.impost_orientation": orient})
                await edit_message_text(chat_id, message_id, "📱 <b>Введите телефон</b>\n\n<i>+375295012233</i>", reply_markup=build_cancel_keyboard())
            
            elif cbd == "confirm_order":
                session = await get_tg_session(chat_id)
                items = session.get("items", [])
                od = session.get("order_data", {})
                
                if not items:
                    await edit_message_text(chat_id, message_id, "❌ Нет позиций", reply_markup=build_main_menu_keyboard())
                    return {"ok": True}
                
                user = await db.users.find_one({"telegram_id": chat_id}, {"_id": 0})
                if not user:
                    user = {"id": str(uuid.uuid4()), "phone": od.get("phone", "tg"), "password": hash_password(str(chat_id)), "name": f"Telegram #{chat_id}", "telegram_id": chat_id, "is_admin": False, "created_at": datetime.now(timezone.utc).isoformat()}
                    await db.users.insert_one(user)
                
                total = sum(i.get("price", 0) for i in items)
                order_items = [{
                    "installation_type": i["installation_type"], "width": i["width"], "height": i["height"],
                    "quantity": i.get("quantity", 1), "color": i["color"], "ral_color_description": i.get("ral_color_description"),
                    "mounting_type": i["mounting_type"], "mounting_by_manufacturer": True, "mesh_type": i["mesh_type"],
                    "impost": i.get("impost", False), "impost_orientation": i.get("impost_orientation"), "notes": "", "item_price": i.get("price", 0)
                } for i in items]
                
                order_number = await generate_order_number()
                
                order = {
                    "id": str(uuid.uuid4()), "order_number": order_number, "user_id": user["id"], "user_name": user["name"], "user_phone": od.get("phone", user.get("phone")),
                    "items": order_items, "total_price": total, "status": "new",
                    "status_history": [{"status": "new", "changed_at": datetime.now(timezone.utc).isoformat()}],
                    "desired_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d"),
                    "notes": "Заказ через Telegram", "contact_phone": od.get("phone"),
                    "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()
                }
                await db.orders.insert_one(order)
                background_tasks.add_task(append_order_to_sheets, order)
                background_tasks.add_task(notify_admins_new_order, order)
                await clear_tg_session(chat_id)
                
                # Show after-order keyboard with view options
                await edit_message_text(chat_id, message_id, f"✅ <b>Заказ оформлен!</b>\n\n<b>№:</b> {order_number}\n<b>Сумма:</b> {total} ₽\n<b>Позиций:</b> {len(items)}\n\nМы свяжемся с вами!", reply_markup=build_after_order_keyboard(order_number))
            
            elif cbd.startswith("view_order_"):
                order_num = cbd.replace("view_order_", "")
                order = await get_order_by_number(order_num)
                if order:
                    status = STATUS_NAMES.get(order['status'], order['status'])
                    emoji = STATUS_EMOJI.get(order['status'], '❓')
                    
                    # Build items list
                    items_text = ""
                    for i, item in enumerate(order['items'], 1):
                        items_text += f"\n{i}. {item['width']}×{item['height']} мм × {item['quantity']} шт"
                    
                    t = f"{emoji} <b>Заказ {order_num}</b>\n\n"
                    t += f"<b>Статус:</b> {status}\n"
                    t += f"<b>Сумма:</b> {order['total_price']} ₽\n"
                    t += f"<b>Желаемая дата:</b> {order['desired_date']}\n"
                    t += f"\n<b>Позиции:</b>{items_text}"
                    
                    await edit_message_text(chat_id, message_id, t, reply_markup=build_main_menu_keyboard())
                else:
                    await edit_message_text(chat_id, message_id, f"❌ Заказ {order_num} не найден", reply_markup=build_main_menu_keyboard())
            
            elif cbd == "add_more_items":
                session = await get_tg_session(chat_id)
                phone = session.get("order_data", {}).get("phone")
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_TYPE, "order_data": {"phone": phone}})
                await edit_message_text(chat_id, message_id, "<b>➕ Добавить позицию</b>\n\nВыберите тип:", reply_markup=build_order_type_keyboard())
            
            elif cbd == "track_order":
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_ORDER_TRACK})
                await edit_message_text(chat_id, message_id, "🔍 <b>Отследить заказ</b>\n\nВведите номер заказа:\n<i>Например: МС-0001</i>", reply_markup=build_cancel_keyboard())
            
            elif cbd == "my_orders":
                user = await db.users.find_one({"telegram_id": chat_id}, {"_id": 0})
                if not user:
                    text = "<b>Заказов пока нет</b>\n\nОформите первый!"
                else:
                    orders = await db.orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
                    if not orders:
                        text = "<b>У вас пока нет заказов</b>"
                    else:
                        text = "<b>📋 Ваши заказы:</b>\n\n"
                        for o in orders:
                            on = o.get('order_number', f"#{o['id'][:8]}")
                            text += f"{STATUS_EMOJI.get(o['status'], '❓')} <b>{on}</b> - {STATUS_NAMES.get(o['status'], o['status'])}\n   💰 {o['total_price']} ₽\n\n"
                await edit_message_text(chat_id, message_id, text, reply_markup=build_main_menu_keyboard())
            
            elif cbd == "help":
                await edit_message_text(chat_id, message_id, "<b>❓ Помощь</b>\n\n<b>Как заказать:</b>\n1. Новый заказ\n2. Тип сетки\n3. Полотно\n4. Размеры (ширина высота кол-во)\n5. Цвет и крепление\n6. Подтвердить\n\n<b>Размеры:</b> 150-3000 мм\n<b>Кол-во:</b> 1-30 шт\n\n<b>Отследить заказ:</b> кнопка 🔍", reply_markup=build_main_menu_keyboard())
            
            return {"ok": True}
        
        # Handle text messages
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            name = msg.get("from", {}).get("first_name", "")
            
            session = await get_tg_session(chat_id)
            state = session.get("state", TelegramOrderState.IDLE)
            
            if text == "/start":
                await clear_tg_session(chat_id)
                await send_telegram_message(chat_id, f"<b>Добро пожаловать, {name}!</b>\n\n🪟 Сервис заказа москитных сеток\n\nВыберите действие:", reply_markup=build_main_menu_keyboard())
            elif text in ["/help", "/cancel"]:
                await clear_tg_session(chat_id)
                await send_telegram_message(chat_id, "Команды: /start /orders /help /track", reply_markup=build_main_menu_keyboard())
            elif text == "/orders":
                user = await db.users.find_one({"telegram_id": chat_id}, {"_id": 0})
                if user:
                    orders = await db.orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
                    if orders:
                        t = "<b>📋 Заказы:</b>\n\n"
                        for o in orders:
                            on = o.get('order_number', f"#{o['id'][:8]}")
                            t += f"{STATUS_EMOJI.get(o['status'], '❓')} {on} - {STATUS_NAMES.get(o['status'], o['status'])}\n   {o['total_price']} ₽\n\n"
                        await send_telegram_message(chat_id, t, reply_markup=build_main_menu_keyboard())
                    else:
                        await send_telegram_message(chat_id, "Заказов нет", reply_markup=build_main_menu_keyboard())
                else:
                    await send_telegram_message(chat_id, "Заказов нет", reply_markup=build_main_menu_keyboard())
            elif text == "/track":
                await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_ORDER_TRACK})
                await send_telegram_message(chat_id, "🔍 <b>Отследить заказ</b>\n\nВведите номер:\n<i>Например: МС-0001</i>", reply_markup=build_cancel_keyboard())
            
            elif state == TelegramOrderState.AWAITING_ORDER_TRACK:
                order_num = text.strip().upper()
                if not order_num.startswith("МС-"):
                    order_num = f"МС-{order_num.replace('МС', '').replace('-', '').zfill(4)}"
                
                order = await get_order_by_number(order_num)
                if order:
                    on = order.get('order_number', order_num)
                    status = STATUS_NAMES.get(order['status'], order['status'])
                    emoji = STATUS_EMOJI.get(order['status'], '❓')
                    
                    history_text = ""
                    if order.get('status_history'):
                        history_text = "\n\n<b>История:</b>\n"
                        for h in order['status_history'][-5:]:
                            hs = STATUS_NAMES.get(h['status'], h['status'])
                            dt = h['changed_at'][:10]
                            history_text += f"• {hs} ({dt})\n"
                    
                    t = f"{emoji} <b>Заказ {on}</b>\n\n"
                    t += f"<b>Статус:</b> {status}\n"
                    t += f"<b>Сумма:</b> {order['total_price']} ₽\n"
                    t += f"<b>Позиций:</b> {len(order['items'])}\n"
                    t += f"<b>Дата:</b> {order['desired_date']}"
                    t += history_text
                    
                    await clear_tg_session(chat_id)
                    await send_telegram_message(chat_id, t, reply_markup=build_main_menu_keyboard())
                else:
                    await send_telegram_message(chat_id, f"❌ Заказ {order_num} не найден\n\nПроверьте номер и попробуйте снова:", reply_markup=build_cancel_keyboard())
            
            elif state == TelegramOrderState.AWAITING_DIMENSIONS:
                # Parse: width height [quantity]
                parts = text.strip().split()
                try:
                    if len(parts) < 2:
                        await send_telegram_message(chat_id, "❌ Введите: ширина высота [кол-во]\n\n<i>Например: 800 1200 2</i>", reply_markup=build_cancel_keyboard())
                    else:
                        w = int(parts[0])
                        h = int(parts[1])
                        q = int(parts[2]) if len(parts) > 2 else 1
                        
                        errors = []
                        if w < 150 or w > 3000:
                            errors.append(f"Ширина {w} - должна быть 150-3000")
                        if h < 150 or h > 3000:
                            errors.append(f"Высота {h} - должна быть 150-3000")
                        if q < 1 or q > 30:
                            errors.append(f"Количество {q} - должно быть 1-30")
                        
                        if errors:
                            await send_telegram_message(chat_id, "❌ " + "\n".join(errors), reply_markup=build_cancel_keyboard())
                        else:
                            session = await get_tg_session(chat_id)
                            itype = session.get("order_data", {}).get("installation_type", "")
                            await update_tg_session(chat_id, {
                                "state": TelegramOrderState.AWAITING_COLOR,
                                "order_data.width": w,
                                "order_data.height": h,
                                "order_data.quantity": q
                            })
                            await send_telegram_message(chat_id, f"<b>Размер:</b> {w}×{h} мм, {q} шт\n\n🎨 Выберите цвет:", reply_markup=build_color_keyboard(itype))
                except ValueError:
                    await send_telegram_message(chat_id, "❌ Введите числа: ширина высота [кол-во]\n\n<i>Например: 800 1200 2</i>", reply_markup=build_cancel_keyboard())
            
            elif state == TelegramOrderState.AWAITING_RAL:
                ral = text.strip()
                if 3 <= len(ral) <= 10:
                    await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_MOUNTING, "order_data.color": f"ral_{ral}", "order_data.ral_color_description": ral})
                    await send_telegram_message(chat_id, f"<b>RAL:</b> {ral}\n\n🔧 Крепление:", reply_markup=build_mounting_keyboard())
                else:
                    await send_telegram_message(chat_id, "❌ Введите код RAL (7016)", reply_markup=build_cancel_keyboard())
            
            elif state == TelegramOrderState.AWAITING_PHONE:
                phone = text.strip()
                if len(phone) >= 5:
                    session = await get_tg_session(chat_id)
                    od = session.get("order_data", {})
                    item = {
                        "installation_type": od.get("installation_type"), "width": od.get("width"), "height": od.get("height"),
                        "quantity": od.get("quantity", 1), "color": od.get("color"), "ral_color_description": od.get("ral_color_description"),
                        "mounting_type": od.get("mounting_type"), "mesh_type": od.get("mesh_type"),
                        "impost": od.get("impost", False), "impost_orientation": od.get("impost_orientation")
                    }
                    item["price"] = await calculate_item_price_for_tg(item)
                    
                    items = session.get("items", [])
                    items.append(item)
                    
                    await update_tg_session(chat_id, {"state": TelegramOrderState.AWAITING_CONFIRM, "order_data.phone": phone, "items": items})
                    summary = format_order_summary(items, {"phone": phone})
                    await send_telegram_message(chat_id, summary + "\n<b>Подтвердите:</b>", reply_markup=build_confirm_keyboard())
                else:
                    await send_telegram_message(chat_id, "❌ Телефон некорректный", reply_markup=build_cancel_keyboard())
            
            else:
                await send_telegram_message(chat_id, "Используйте меню или /start", reply_markup=build_main_menu_keyboard())
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"ok": False, "error": str(e)}

# ===================== GOOGLE SHEETS EXPORT =====================

@api_router.post("/admin/export/sheets")
async def export_to_google_sheets(
    order_ids: Optional[List[str]] = None,
    user: dict = Depends(get_admin_user)
):
    """Экспорт заказов в Google Sheets (требует настройки OAuth)"""
    # Для MVP возвращаем данные в формате для копирования
    query = {}
    if order_ids:
        query["id"] = {"$in": order_ids}
    
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    # Format for Google Sheets
    rows = [["№ заказа", "Дата", "Клиент", "Телефон", "Тип установки", "Ширина", "Высота", "Кол-во", "Цвет", "Крепление", "Полотно", "Примечание", "Цена позиции", "Общая сумма", "Статус", "Желаемая дата"]]
    
    for order in orders:
        for item in order["items"]:
            rows.append([
                order["id"][:8],
                order["created_at"][:10],
                order.get("user_name", ""),
                order.get("contact_phone", order.get("user_phone", "")),
                item["installation_type"],
                str(item["width"]),
                str(item["height"]),
                str(item["quantity"]),
                item["color"],
                item["mounting_type"],
                item["mesh_type"],
                item.get("notes", ""),
                str(item.get("item_price", 0)),
                str(order["total_price"]),
                order["status"],
                order["desired_date"]
            ])
    
    return {"rows": rows, "total_orders": len(orders)}

# ===================== PUBLIC ROUTES =====================

@api_router.get("/")
async def root():
    return {"message": "Москитные сетки API", "version": "1.0"}

@api_router.get("/health")
async def health():
    return {"status": "ok"}

# Include router
app.include_router(api_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

# Create default admin user on startup
@app.on_event("startup")
async def create_default_admin():
    admin = await db.users.find_one({"phone": "admin"})
    if not admin:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "phone": "admin",
            "password": hash_password("admin123"),
            "name": "Администратор",
            "telegram_id": None,
            "is_admin": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info("Default admin user created: phone=admin, password=admin123")
    
    # Setup Google Sheets header
    await setup_sheets_header()
