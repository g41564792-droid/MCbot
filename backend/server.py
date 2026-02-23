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
    user_id: str
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    items: List[OrderItem]
    total_price: float
    status: str  # new, in_progress, ready, delivered, cancelled
    desired_date: str
    notes: Optional[str] = None
    contact_phone: Optional[str] = None
    created_at: str
    updated_at: str

class OrderStatusUpdate(BaseModel):
    status: str

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
                    order["id"][:8],  # ID заказа
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
            
            logger.info(f"Order {order['id'][:8]} appended to Google Sheets")
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
                    "ID заказа", "Дата", "Клиент", "Телефон", 
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
    
    order = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": user["name"],
        "user_phone": user["phone"],
        "items": items_data,
        "total_price": round(total_price, 2),
        "status": "new",
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
    
    result = await db.orders.find_one_and_update(
        {"id": order_id},
        {"$set": {"status": data.status, "updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # Notify customer
    customer = await db.users.find_one({"id": result["user_id"]}, {"_id": 0})
    if customer and customer.get("telegram_id"):
        status_names = {
            "new": "Новый",
            "in_progress": "В работе",
            "ready": "Готов к выдаче",
            "delivered": "Выдан",
            "cancelled": "Отменён"
        }
        text = f"<b>Статус заказа #{order_id[:8]} изменён</b>\n\nНовый статус: {status_names.get(data.status, data.status)}"
        background_tasks.add_task(send_telegram_message, customer["telegram_id"], text)
    
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

# Inline keyboard builders
def build_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🛒 Новый заказ", "callback_data": "new_order"},
                {"text": "📋 Мои заказы", "callback_data": "my_orders"}
            ],
            [
                {"text": "📞 Связаться", "callback_data": "contact"},
                {"text": "❓ Помощь", "callback_data": "help"}
            ]
        ]
    }

def build_order_type_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🪟 Проёмная (наружная)", "callback_data": "type_проемная_наружный"}],
            [{"text": "🪟 Проёмная (внутренняя)", "callback_data": "type_проемная_внутренний"}],
            [{"text": "🪟 Проёмная (встраиваемая)", "callback_data": "type_проемная_встраиваемый"}],
            [{"text": "🚪 Дверная", "callback_data": "type_дверная"}],
            [{"text": "🔄 Роллетная", "callback_data": "type_роллетная"}],
            [{"text": "◀️ Назад", "callback_data": "back_main"}]
        ]
    }

def build_mesh_type_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📐 Стандартное", "callback_data": "mesh_стандартное"}],
            [{"text": "🌫️ Антипыль (+500₽)", "callback_data": "mesh_антипыль"}],
            [{"text": "🦟 Антимошка (+300₽)", "callback_data": "mesh_антимошка"}],
            [{"text": "🐱 Антикошка (+800₽)", "callback_data": "mesh_антикошка"}],
            [{"text": "◀️ Назад", "callback_data": "back_type"}]
        ]
    }

def build_back_keyboard(callback_data: str = "back_main"):
    return {
        "inline_keyboard": [
            [{"text": "◀️ Назад в меню", "callback_data": callback_data}]
        ]
    }

@api_router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"Telegram webhook received: {data}")
        
        # Handle callback queries (inline button presses)
        if "callback_query" in data:
            callback = data["callback_query"]
            callback_id = callback["id"]
            chat_id = callback["message"]["chat"]["id"]
            message_id = callback["message"]["message_id"]
            callback_data = callback.get("data", "")
            user_first_name = callback.get("from", {}).get("first_name", "")
            
            await answer_callback_query(callback_id)
            
            if callback_data == "back_main":
                webapp_url = os.environ.get('WEBAPP_URL', 'https://mosquito-net-bot.preview.emergentagent.com')
                text = f"""
<b>Главное меню</b>

Выберите действие или перейдите на сайт для оформления заказа:
{webapp_url}
"""
                await edit_message_text(chat_id, message_id, text, reply_markup=build_main_menu_keyboard())
            
            elif callback_data == "new_order":
                text = """
<b>🛒 Новый заказ</b>

Выберите тип москитной сетки:
"""
                await edit_message_text(chat_id, message_id, text, reply_markup=build_order_type_keyboard())
            
            elif callback_data.startswith("type_"):
                installation_type = callback_data.replace("type_", "")
                type_names = {
                    "проемная_наружный": "Проёмная (наружная)",
                    "проемная_внутренний": "Проёмная (внутренняя)",
                    "проемная_встраиваемый": "Проёмная (встраиваемая)",
                    "дверная": "Дверная",
                    "роллетная": "Роллетная"
                }
                type_name = type_names.get(installation_type, installation_type)
                
                text = f"""
<b>Выбран тип: {type_name}</b>

Теперь выберите тип полотна:
"""
                await edit_message_text(chat_id, message_id, text, reply_markup=build_mesh_type_keyboard())
            
            elif callback_data == "back_type":
                text = """
<b>🛒 Новый заказ</b>

Выберите тип москитной сетки:
"""
                await edit_message_text(chat_id, message_id, text, reply_markup=build_order_type_keyboard())
            
            elif callback_data.startswith("mesh_"):
                webapp_url = os.environ.get('WEBAPP_URL', 'https://mosquito-net-bot.preview.emergentagent.com')
                text = f"""
<b>✅ Отлично!</b>

Для завершения заказа перейдите на сайт и укажите точные размеры:

🔗 {webapp_url}

<i>На сайте вы сможете:</i>
• Указать точные размеры в миллиметрах
• Выбрать цвет и крепление
• Добавить несколько позиций
• Увидеть итоговую стоимость
"""
                await edit_message_text(chat_id, message_id, text, reply_markup=build_back_keyboard())
            
            elif callback_data == "my_orders":
                user = await db.users.find_one({"telegram_id": chat_id}, {"_id": 0})
                if not user:
                    text = f"""
<b>Аккаунт не найден</b>

Для просмотра заказов зарегистрируйтесь на сайте и укажите ваш Telegram ID.

<b>Ваш Telegram ID:</b> <code>{chat_id}</code>
"""
                else:
                    orders = await db.orders.find(
                        {"user_id": user["id"]}, 
                        {"_id": 0}
                    ).sort("created_at", -1).limit(5).to_list(5)
                    
                    if not orders:
                        text = "<b>У вас пока нет заказов</b>\n\nОформите первый заказ!"
                    else:
                        status_emoji = {
                            "new": "🆕", "in_progress": "🔧", "ready": "✅",
                            "delivered": "📦", "cancelled": "❌"
                        }
                        status_names = {
                            "new": "Новый", "in_progress": "В работе", "ready": "Готов",
                            "delivered": "Выдан", "cancelled": "Отменён"
                        }
                        
                        text = f"<b>📋 Ваши заказы ({user['name']}):</b>\n\n"
                        for order in orders:
                            emoji = status_emoji.get(order["status"], "❓")
                            status = status_names.get(order["status"], order["status"])
                            text += f"{emoji} <b>#{order['id'][:8]}</b> - {status}\n"
                            text += f"   💰 {order['total_price']} ₽ | 📅 {order['desired_date']}\n\n"
                
                await edit_message_text(chat_id, message_id, text, reply_markup=build_back_keyboard())
            
            elif callback_data == "contact":
                text = """
<b>📞 Контакты</b>

Для связи с нами:
• Напишите в этот чат - мы ответим
• Позвоните по телефону

Мы работаем: Пн-Пт 9:00-18:00
"""
                await edit_message_text(chat_id, message_id, text, reply_markup=build_back_keyboard())
            
            elif callback_data == "help":
                text = """
<b>❓ Помощь</b>

<b>Как сделать заказ:</b>
1. Нажмите "Новый заказ"
2. Выберите тип сетки
3. Перейдите на сайт для указания размеров
4. Получайте уведомления о статусе

<b>Типы сеток:</b>
• Проёмная - для окон
• Дверная - для дверей
• Роллетная - сворачивающаяся

<b>Типы полотна:</b>
• Стандартное - базовое
• Антипыль - мелкая ячейка
• Антимошка - защита от мошек
• Антикошка - усиленное
"""
                await edit_message_text(chat_id, message_id, text, reply_markup=build_back_keyboard())
            
            return {"ok": True}
        
        # Handle regular messages
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            user_first_name = message.get("from", {}).get("first_name", "")
            
            if text == "/start":
                webapp_url = os.environ.get('WEBAPP_URL', 'https://mosquito-net-bot.preview.emergentagent.com')
                response_text = f"""
<b>Добро пожаловать, {user_first_name}!</b>

Сервис заказа москитных сеток к вашим услугам.

<b>Ваш Telegram ID:</b> <code>{chat_id}</code>
<i>(укажите при регистрации для уведомлений)</i>

Выберите действие:
"""
                await send_telegram_message(chat_id, response_text, reply_markup=build_main_menu_keyboard())
            
            elif text == "/help":
                response_text = """
<b>Справка по боту</b>

<b>Команды:</b>
/start - Главное меню
/orders - Мои заказы
/help - Эта справка

<b>Типы москитных сеток:</b>
• Проёмная (наружная, внутренняя, встраиваемая)
• Дверная
• Роллетная

<b>Типы полотна:</b>
• Стандартное
• Антипыль (+500₽)
• Антимошка (+300₽)
• Антикошка (+800₽)
"""
                await send_telegram_message(chat_id, response_text, reply_markup=build_main_menu_keyboard())
            
            elif text == "/orders":
                user = await db.users.find_one({"telegram_id": chat_id}, {"_id": 0})
                if not user:
                    response_text = f"""
<b>Аккаунт не найден</b>

Для просмотра заказов зарегистрируйтесь на сайте и укажите ваш Telegram ID.

<b>Ваш Telegram ID:</b> <code>{chat_id}</code>
"""
                else:
                    orders = await db.orders.find(
                        {"user_id": user["id"]}, 
                        {"_id": 0}
                    ).sort("created_at", -1).limit(5).to_list(5)
                    
                    if not orders:
                        response_text = "<b>У вас пока нет заказов</b>\n\nОформите первый заказ!"
                    else:
                        status_emoji = {
                            "new": "🆕", "in_progress": "🔧", "ready": "✅",
                            "delivered": "📦", "cancelled": "❌"
                        }
                        status_names = {
                            "new": "Новый", "in_progress": "В работе", "ready": "Готов",
                            "delivered": "Выдан", "cancelled": "Отменён"
                        }
                        
                        response_text = f"<b>📋 Ваши заказы ({user['name']}):</b>\n\n"
                        for order in orders:
                            emoji = status_emoji.get(order["status"], "❓")
                            status = status_names.get(order["status"], order["status"])
                            items_count = len(order["items"])
                            response_text += f"{emoji} <b>#{order['id'][:8]}</b>\n"
                            response_text += f"   Позиций: {items_count}, Сумма: {order['total_price']} ₽\n"
                            response_text += f"   Статус: {status}\n"
                            response_text += f"   Дата: {order['desired_date']}\n\n"
                
                await send_telegram_message(chat_id, response_text, reply_markup=build_main_menu_keyboard())
            
            else:
                response_text = """
Не понял команду. Используйте меню или команды:
/start - Главное меню
/orders - Мои заказы
/help - Справка
"""
                await send_telegram_message(chat_id, response_text, reply_markup=build_main_menu_keyboard())
        
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
    rows = [["ID заказа", "Дата", "Клиент", "Телефон", "Тип установки", "Ширина", "Высота", "Кол-во", "Цвет", "Крепление", "Полотно", "Примечание", "Цена позиции", "Общая сумма", "Статус", "Желаемая дата"]]
    
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
