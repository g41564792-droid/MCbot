# Telegram Bot Order Flow Module
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)

# Contact phone number
CONTACT_PHONE = "+375333545588"

# Telegram Bot Order Flow States
class TelegramOrderState:
    IDLE = "idle"
    AWAITING_TYPE = "awaiting_type"
    AWAITING_MESH = "awaiting_mesh"
    AWAITING_DIMENSIONS = "awaiting_dimensions"  # Combined: width height quantity
    AWAITING_COLOR = "awaiting_color"
    AWAITING_RAL = "awaiting_ral"
    AWAITING_MOUNTING = "awaiting_mounting"
    AWAITING_IMPOST = "awaiting_impost"
    AWAITING_IMPOST_ORIENTATION = "awaiting_impost_orientation"
    AWAITING_PHONE = "awaiting_phone"
    AWAITING_CONFIRM = "awaiting_confirm"
    AWAITING_ORDER_TRACK = "awaiting_order_track"  # For tracking orders

# Inline keyboard builders
def build_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🛒 Новый заказ", "callback_data": "new_order"}],
            [{"text": "📋 Мои заказы", "callback_data": "my_orders"}],
            [{"text": "🔍 Отследить заказ", "callback_data": "track_order"}],
            [{"text": "📞 Контакты", "callback_data": "contact"}, {"text": "❓ Помощь", "callback_data": "help"}]
        ]
    }

def build_after_order_keyboard(order_number: str):
    """Клавиатура после оформления заказа"""
    return {
        "inline_keyboard": [
            [{"text": f"📋 Посмотреть заказ {order_number}", "callback_data": f"view_order_{order_number}"}],
            [{"text": "📋 Все мои заказы", "callback_data": "my_orders"}],
            [{"text": "🛒 Новый заказ", "callback_data": "new_order"}],
            [{"text": "🏠 Главное меню", "callback_data": "back_main"}]
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
            [{"text": "❌ Отмена", "callback_data": "cancel_order"}]
        ]
    }

def build_mesh_type_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📐 Стандартное", "callback_data": "mesh_стандартное"}],
            [{"text": "🌫️ Антипыль (+500₽)", "callback_data": "mesh_антипыль"}],
            [{"text": "🦟 Антимошка (+300₽)", "callback_data": "mesh_антимошка"}],
            [{"text": "🐱 Антикошка (+800₽)", "callback_data": "mesh_антикошка"}],
            [{"text": "❌ Отмена", "callback_data": "cancel_order"}]
        ]
    }

def build_color_keyboard(installation_type: str):
    if installation_type in ["дверная", "роллетная"]:
        return {
            "inline_keyboard": [
                [{"text": "⬜ Белый", "callback_data": "color_белый"}],
                [{"text": "🟫 Коричневый", "callback_data": "color_коричневый"}],
                [{"text": "❌ Отмена", "callback_data": "cancel_order"}]
            ]
        }
    return {
        "inline_keyboard": [
            [{"text": "⬜ Белый", "callback_data": "color_белый"}, {"text": "🟫 Коричневый", "callback_data": "color_коричневый"}],
            [{"text": "⬛ Антрацит", "callback_data": "color_антрацит"}],
            [{"text": "🎨 Другой цвет (RAL)", "callback_data": "color_ral"}],
            [{"text": "❌ Отмена", "callback_data": "cancel_order"}]
        ]
    }

def build_mounting_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🔧 Z-образные кронштейны", "callback_data": "mount_z_bracket"}],
            [{"text": "🔩 Металлические зацепы", "callback_data": "mount_metal_hooks"}],
            [{"text": "📎 Пластиковые зацепы", "callback_data": "mount_plastic_hooks"}],
            [{"text": "❌ Отмена", "callback_data": "cancel_order"}]
        ]
    }

def build_yes_no_keyboard(prefix: str):
    return {
        "inline_keyboard": [
            [{"text": "✅ Да", "callback_data": f"{prefix}_yes"}, {"text": "❌ Нет", "callback_data": f"{prefix}_no"}]
        ]
    }

def build_impost_orientation_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "↕️ Вертикально", "callback_data": "impost_вертикально"}],
            [{"text": "↔️ Горизонтально", "callback_data": "impost_горизонтально"}]
        ]
    }

def build_confirm_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "✅ Подтвердить заказ", "callback_data": "confirm_order"}],
            [{"text": "➕ Добавить ещё позицию", "callback_data": "add_more_items"}],
            [{"text": "❌ Отменить", "callback_data": "cancel_order"}]
        ]
    }

def build_cancel_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "❌ Отменить заказ", "callback_data": "cancel_order"}]
        ]
    }

TYPE_NAMES = {
    "проемная_наружный": "Проёмная (наружная)",
    "проемная_внутренний": "Проёмная (внутренняя)",
    "проемная_встраиваемый": "Проёмная (встраиваемая)",
    "дверная": "Дверная",
    "роллетная": "Роллетная"
}

MESH_NAMES = {
    "стандартное": "Стандартное",
    "антипыль": "Антипыль",
    "антимошка": "Антимошка",
    "антикошка": "Антикошка"
}

MOUNT_NAMES = {
    "z_bracket": "Z-образные кронштейны",
    "metal_hooks": "Металлические зацепы",
    "plastic_hooks": "Пластиковые зацепы"
}

STATUS_EMOJI = {"new": "🆕", "in_progress": "🔧", "ready": "✅", "delivered": "📦", "cancelled": "❌"}
STATUS_NAMES = {"new": "Новый", "in_progress": "В работе", "ready": "Готов", "delivered": "Выдан", "cancelled": "Отменён"}

def format_order_summary(items: list, order_data: dict) -> str:
    text = "<b>📋 Ваш заказ:</b>\n\n"
    total = 0
    
    for i, item in enumerate(items, 1):
        text += f"<b>Позиция {i}:</b>\n"
        text += f"  📏 Размер: {item['width']}×{item['height']} мм\n"
        text += f"  🔢 Количество: {item['quantity']} шт\n"
        text += f"  🏠 Тип: {TYPE_NAMES.get(item['installation_type'], item['installation_type'])}\n"
        text += f"  🎨 Цвет: {item['color']}\n"
        text += f"  🔧 Крепление: {MOUNT_NAMES.get(item['mounting_type'], item['mounting_type'])}\n"
        text += f"  🕸️ Полотно: {MESH_NAMES.get(item['mesh_type'], item['mesh_type'])}\n"
        if item.get('impost'):
            text += f"  ➕ Импост: {item.get('impost_orientation', 'да')}\n"
        text += f"  💰 Цена: {item.get('price', 0)} ₽\n\n"
        total += item.get('price', 0)
    
    text += f"<b>💰 Итого: {total} ₽</b>\n"
    if order_data.get('phone'):
        text += f"📱 Телефон: {order_data['phone']}\n"
    
    return text
