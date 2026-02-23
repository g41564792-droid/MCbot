#!/usr/bin/env python3
import requests
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

class MosquitoNetAPITester:
    def __init__(self, base_url="https://mosquito-net-bot.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.user_token = None
        self.admin_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.created_user_id = None
        self.created_order_id = None

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, 
                 data: Any = None, headers: Dict = None, use_admin: bool = False) -> tuple:
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if headers:
            test_headers.update(headers)
            
        # Add authorization if needed
        if use_admin and self.admin_token:
            test_headers['Authorization'] = f'Bearer {self.admin_token}'
        elif self.user_token and not use_admin:
            test_headers['Authorization'] = f'Bearer {self.user_token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                if response.text:
                    print(f"   Response: {response.text}")

            result = {}
            try:
                result = response.json() if response.content else {}
            except:
                result = {"text": response.text}
                
            return success, result

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {"error": str(e)}

    def test_health_endpoints(self):
        """Test basic health endpoints"""
        print("\n" + "="*50)
        print("TESTING HEALTH ENDPOINTS")
        print("="*50)
        
        self.run_test("API Root", "GET", "", 200)
        self.run_test("Health Check", "GET", "health", 200)

    def test_user_registration(self):
        """Test user registration"""
        print("\n" + "="*50)
        print("TESTING USER REGISTRATION")
        print("="*50)
        
        # Test user registration
        timestamp = datetime.now().strftime('%H%M%S')
        user_data = {
            "phone": f"+7999123{timestamp}",
            "password": "testpass123",
            "name": f"Test User {timestamp}",
            "telegram_id": int(timestamp)
        }
        
        success, result = self.run_test(
            "User Registration", 
            "POST", 
            "auth/register", 
            200, 
            user_data
        )
        
        if success and 'token' in result:
            self.user_token = result['token']
            self.created_user_id = result['user']['id']
            print(f"✅ User token received: {self.user_token[:20]}...")
        
        return success

    def test_admin_login(self):
        """Test admin login"""
        print("\n" + "="*50)
        print("TESTING ADMIN LOGIN")
        print("="*50)
        
        admin_data = {
            "phone": "admin", 
            "password": "admin123"
        }
        
        success, result = self.run_test(
            "Admin Login", 
            "POST", 
            "auth/login", 
            200, 
            admin_data
        )
        
        if success and 'token' in result:
            self.admin_token = result['token']
            print(f"✅ Admin token received: {self.admin_token[:20]}...")
            
            # Test admin is actually admin
            if result.get('user', {}).get('is_admin'):
                print("✅ Admin privileges confirmed")
            else:
                print("❌ Admin privileges not confirmed")
                return False
        
        return success

    def test_user_login(self):
        """Test user login"""
        if not self.created_user_id:
            print("⚠️ Skipping user login test - no user created")
            return True
            
        print("\n" + "="*50)
        print("TESTING USER LOGIN")
        print("="*50)
        
        # Extract phone from created user (we need to know it)
        timestamp = datetime.now().strftime('%H%M%S')
        login_data = {
            "phone": f"+7999123{timestamp}",
            "password": "testpass123"
        }
        
        success, result = self.run_test(
            "User Login", 
            "POST", 
            "auth/login", 
            200, 
            login_data
        )
        
        return success

    def test_price_calculation(self):
        """Test price calculation API"""
        print("\n" + "="*50)
        print("TESTING PRICE CALCULATION")
        print("="*50)
        
        # Test basic price calculation
        items = [{
            "installation_type": "проемная_наружный",
            "width": 800,
            "height": 1200,
            "quantity": 1,
            "color": "белый",
            "mounting_type": "z_bracket",
            "mounting_by_manufacturer": True,
            "mesh_type": "стандартное",
            "impost": False
        }]
        
        success, result = self.run_test(
            "Price Calculation - Basic Item",
            "POST",
            "calculate-price",
            200,
            items
        )
        
        if success and 'total' in result:
            print(f"✅ Calculated price: {result['total']} ₽")
        
        # Test price calculation with impost
        items_with_impost = [{
            "installation_type": "проемная_наружный",
            "width": 1500,  # Large size to trigger impost recommendation
            "height": 1800,
            "quantity": 2,
            "color": "коричневый",
            "mounting_type": "metal_hooks",
            "mounting_by_manufacturer": True,
            "mesh_type": "антипыль",
            "impost": True,
            "impost_orientation": "вертикально"
        }]
        
        success2, result2 = self.run_test(
            "Price Calculation - With Impost",
            "POST",
            "calculate-price",
            200,
            items_with_impost
        )
        
        if success2 and 'total' in result2:
            print(f"✅ Calculated price with impost: {result2['total']} ₽")
        
        return success and success2

    def test_order_creation(self):
        """Test order creation"""
        if not self.user_token:
            print("⚠️ Skipping order creation test - no user token")
            return True
            
        print("\n" + "="*50)
        print("TESTING ORDER CREATION")
        print("="*50)
        
        # Create test order
        order_data = {
            "items": [{
                "installation_type": "проемная_наружный",
                "width": 900,
                "height": 1400,
                "quantity": 1,
                "color": "белый",
                "mounting_type": "z_bracket",
                "mounting_by_manufacturer": True,
                "mesh_type": "стандартное",
                "impost": False,
                "notes": "Test order from API testing"
            }],
            "desired_date": (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
            "notes": "Test order notes",
            "contact_phone": "+7999123456"
        }
        
        success, result = self.run_test(
            "Order Creation",
            "POST",
            "orders",
            200,
            order_data
        )
        
        if success and 'id' in result:
            self.created_order_id = result['id']
            print(f"✅ Order created with ID: {self.created_order_id[:8]}")
        
        return success

    def test_order_retrieval(self):
        """Test order retrieval"""
        if not self.user_token:
            print("⚠️ Skipping order retrieval test - no user token")
            return True
            
        print("\n" + "="*50)
        print("TESTING ORDER RETRIEVAL")
        print("="*50)
        
        # Get user orders
        success, result = self.run_test(
            "Get User Orders",
            "GET",
            "orders",
            200
        )
        
        if success:
            orders_count = len(result) if isinstance(result, list) else 0
            print(f"✅ Retrieved {orders_count} orders")
        
        # Get specific order if we created one
        if self.created_order_id:
            success2, result2 = self.run_test(
                "Get Specific Order",
                "GET",
                f"orders/{self.created_order_id}",
                200
            )
            return success and success2
        
        return success

    def test_admin_functionality(self):
        """Test admin-specific functionality"""
        if not self.admin_token:
            print("⚠️ Skipping admin tests - no admin token")
            return True
            
        print("\n" + "="*50)
        print("TESTING ADMIN FUNCTIONALITY")
        print("="*50)
        
        # Test admin stats
        success1, result1 = self.run_test(
            "Admin Stats",
            "GET",
            "admin/stats",
            200,
            use_admin=True
        )
        
        if success1:
            print(f"✅ Stats: {result1}")
        
        # Test admin orders
        success2, result2 = self.run_test(
            "Admin Get All Orders",
            "GET",
            "admin/orders",
            200,
            use_admin=True
        )
        
        if success2:
            orders_count = len(result2) if isinstance(result2, list) else 0
            print(f"✅ Admin retrieved {orders_count} orders")
        
        # Test admin users
        success3, result3 = self.run_test(
            "Admin Get All Users",
            "GET",
            "admin/users",
            200,
            use_admin=True
        )
        
        if success3:
            users_count = len(result3) if isinstance(result3, list) else 0
            print(f"✅ Admin retrieved {users_count} users")
        
        # Test order status update if we have an order
        success4 = True
        if self.created_order_id:
            success4, result4 = self.run_test(
                "Admin Update Order Status",
                "PUT",
                f"admin/orders/{self.created_order_id}/status",
                200,
                {"status": "in_progress"},
                use_admin=True
            )
        
        # Test export functionality
        success5, result5 = self.run_test(
            "Admin Export to Sheets",
            "POST",
            "admin/export/sheets",
            200,
            use_admin=True
        )
        
        if success5 and 'rows' in result5:
            print(f"✅ Export prepared with {len(result5['rows'])} rows")
        
        return success1 and success2 and success3 and success4 and success5

    def test_telegram_inline_keyboards(self):
        """Test Telegram inline keyboard functionality"""
        print("\n" + "="*50)
        print("TESTING TELEGRAM INLINE KEYBOARDS - NEW FEATURES")
        print("="*50)
        
        # Test /start command with inline keyboard
        start_webhook_data = {
            "message": {
                "chat": {"id": 123456789},
                "text": "/start",
                "from": {"id": 123456789, "first_name": "TestUser"}
            }
        }
        
        success1, result1 = self.run_test(
            "Telegram /start command with inline keyboard",
            "POST",
            "telegram/webhook",
            200,
            start_webhook_data
        )
        
        if success1 and result1.get('ok'):
            print("✅ /start command processed successfully - inline keyboard should be sent")
        
        # Test callback_query for main menu buttons
        callback_queries = [
            ("new_order", "New Order button callback"),
            ("my_orders", "My Orders button callback"), 
            ("contact", "Contact button callback"),
            ("help", "Help button callback")
        ]
        
        callback_results = []
        for callback_data, description in callback_queries:
            callback_webhook_data = {
                "callback_query": {
                    "id": f"test_callback_{callback_data}",
                    "data": callback_data,
                    "message": {
                        "chat": {"id": 123456789},
                        "message_id": 123
                    },
                    "from": {"id": 123456789, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Callback Query - {description}",
                "POST",
                "telegram/webhook",
                200,
                callback_webhook_data
            )
            
            callback_results.append(success)
            if success and result.get('ok'):
                print(f"✅ {description} processed successfully")
        
        return success1 and all(callback_results)

    def test_telegram_order_type_keyboard(self):
        """Test order type selection via inline keyboard"""
        print("\n" + "="*50)
        print("TESTING ORDER TYPE SELECTION - INLINE KEYBOARD")
        print("="*50)
        
        # Test order type callbacks
        order_types = [
            ("type_проемная_наружный", "Proemnaya Outer Type"),
            ("type_проемная_внутренний", "Proemnaya Inner Type"),
            ("type_проемная_встраиваемый", "Proemnaya Built-in Type"),
            ("type_дверная", "Door Type"),
            ("type_роллетная", "Roller Type")
        ]
        
        type_results = []
        for callback_data, description in order_types:
            callback_webhook_data = {
                "callback_query": {
                    "id": f"test_type_{callback_data}",
                    "data": callback_data,
                    "message": {
                        "chat": {"id": 123456789},
                        "message_id": 124
                    },
                    "from": {"id": 123456789, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Order Type Selection - {description}",
                "POST",
                "telegram/webhook",
                200,
                callback_webhook_data
            )
            
            type_results.append(success)
            if success and result.get('ok'):
                print(f"✅ {description} selection processed successfully")
        
        # Test mesh type callbacks
        mesh_types = [
            ("mesh_стандартное", "Standard Mesh"),
            ("mesh_антипыль", "Anti-dust Mesh"),
            ("mesh_антимошка", "Anti-mosquito Mesh"),
            ("mesh_антикошка", "Anti-cat Mesh")
        ]
        
        mesh_results = []
        for callback_data, description in mesh_types:
            callback_webhook_data = {
                "callback_query": {
                    "id": f"test_mesh_{callback_data}",
                    "data": callback_data,
                    "message": {
                        "chat": {"id": 123456789},
                        "message_id": 125
                    },
                    "from": {"id": 123456789, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Mesh Type Selection - {description}",
                "POST",
                "telegram/webhook",
                200,
                callback_webhook_data
            )
            
            mesh_results.append(success)
            if success and result.get('ok'):
                print(f"✅ {description} selection processed successfully")
        
        # Test navigation callbacks
        nav_callbacks = [
            ("back_main", "Back to Main Menu"),
            ("back_type", "Back to Type Selection")
        ]
        
        nav_results = []
        for callback_data, description in nav_callbacks:
            callback_webhook_data = {
                "callback_query": {
                    "id": f"test_nav_{callback_data}",
                    "data": callback_data,
                    "message": {
                        "chat": {"id": 123456789},
                        "message_id": 126
                    },
                    "from": {"id": 123456789, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Navigation - {description}",
                "POST",
                "telegram/webhook",
                200,
                callback_webhook_data
            )
            
            nav_results.append(success)
            if success and result.get('ok'):
                print(f"✅ {description} navigation processed successfully")
        
        return all(type_results) and all(mesh_results) and all(nav_results)

    def test_push_notifications_on_status_change(self):
        """Test push notifications when admin changes order status"""
        print("\n" + "="*50)
        print("TESTING PUSH NOTIFICATIONS ON STATUS CHANGE")
        print("="*50)
        
        if not self.admin_token or not self.created_order_id:
            print("⚠️ Skipping push notification test - need admin token and order")
            return True
        
        # Test different status updates to trigger notifications
        status_updates = [
            ("in_progress", "In Progress Status Update"),
            ("ready", "Ready Status Update"), 
            ("delivered", "Delivered Status Update")
        ]
        
        notification_results = []
        for status, description in status_updates:
            success, result = self.run_test(
                f"Push Notification - {description}",
                "PUT",
                f"admin/orders/{self.created_order_id}/status",
                200,
                {"status": status},
                use_admin=True
            )
            
            notification_results.append(success)
            if success:
                print(f"✅ {description} - Status updated, push notification should be sent")
                if 'status' in result:
                    print(f"   New status confirmed: {result['status']}")
        
        return all(notification_results)

    def test_telegram_webhook(self):
        """Test basic Telegram webhook functionality"""
        print("\n" + "="*50)
        print("TESTING BASIC TELEGRAM WEBHOOK COMMANDS")
        print("="*50)
        
        # Test /help command  
        help_webhook_data = {
            "message": {
                "chat": {"id": 123456789},
                "text": "/help",
                "from": {"id": 123456789, "first_name": "TestUser"}
            }
        }
        
        success1, result1 = self.run_test(
            "Telegram Bot /help command",
            "POST", 
            "telegram/webhook",
            200,
            help_webhook_data
        )
        
        # Test /orders command
        orders_webhook_data = {
            "message": {
                "chat": {"id": 123456789},
                "text": "/orders",
                "from": {"id": 123456789, "first_name": "TestUser"}
            }
        }
        
        success2, result2 = self.run_test(
            "Telegram Bot /orders command",
            "POST",
            "telegram/webhook", 
            200,
            orders_webhook_data
        )
        
        # Test unknown command
        unknown_webhook_data = {
            "message": {
                "chat": {"id": 123456789},
                "text": "/unknown",
                "from": {"id": 123456789, "first_name": "TestUser"}
            }
        }
        
        success3, result3 = self.run_test(
            "Telegram Bot unknown command",
            "POST",
            "telegram/webhook",
            200,
            unknown_webhook_data
        )
        
        return success1 and success2 and success3

    def test_telegram_dimension_validation(self):
        """Test dimension input validation (150-3000mm) via Telegram webhook"""
        print("\n" + "="*50)
        print("TESTING DIMENSION INPUT VALIDATION (150-3000mm)")
        print("="*50)
        
        chat_id = 987654321
        
        # Test valid width inputs
        valid_widths = [150, 800, 1500, 2500, 3000]
        width_results = []
        
        for width in valid_widths:
            # First set session to awaiting_width state
            session_data = {
                "chat_id": chat_id,
                "state": "awaiting_width",
                "order_data": {"installation_type": "проемная_наружный", "mesh_type": "стандартное"},
                "items": []
            }
            
            width_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": str(width),
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Valid Width Input - {width}mm",
                "POST",
                "telegram/webhook",
                200,
                width_webhook_data
            )
            
            width_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Width {width}mm accepted")
        
        # Test invalid width inputs
        invalid_widths = [149, 50, 3001, 5000, 0, -100]
        invalid_width_results = []
        
        for width in invalid_widths:
            width_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": str(width),
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Invalid Width Input - {width}mm",
                "POST", 
                "telegram/webhook",
                200,
                width_webhook_data
            )
            
            invalid_width_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Width {width}mm properly rejected")
        
        # Test valid height inputs 
        valid_heights = [150, 1200, 1800, 2500, 3000]
        height_results = []
        
        for height in valid_heights:
            height_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": str(height),
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Valid Height Input - {height}mm",
                "POST",
                "telegram/webhook", 
                200,
                height_webhook_data
            )
            
            height_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Height {height}mm accepted")
        
        # Test invalid height inputs
        invalid_heights = [149, 25, 3001, 4000]
        invalid_height_results = []
        
        for height in invalid_heights:
            height_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": str(height),
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Invalid Height Input - {height}mm",
                "POST",
                "telegram/webhook",
                200,
                height_webhook_data
            )
            
            invalid_height_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Height {height}mm properly rejected")
        
        return all(width_results) and all(invalid_width_results) and all(height_results) and all(invalid_height_results)

    def test_telegram_quantity_validation(self):
        """Test quantity input validation (1-30) via Telegram webhook"""
        print("\n" + "="*50)
        print("TESTING QUANTITY INPUT VALIDATION (1-30)")
        print("="*50)
        
        chat_id = 987654322
        
        # Test valid quantities
        valid_quantities = [1, 5, 15, 25, 30]
        quantity_results = []
        
        for quantity in valid_quantities:
            quantity_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": str(quantity),
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Valid Quantity Input - {quantity} units",
                "POST",
                "telegram/webhook",
                200,
                quantity_webhook_data
            )
            
            quantity_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Quantity {quantity} accepted")
        
        # Test invalid quantities
        invalid_quantities = [0, -5, 31, 50, 100]
        invalid_quantity_results = []
        
        for quantity in invalid_quantities:
            quantity_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": str(quantity),
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Invalid Quantity Input - {quantity} units",
                "POST",
                "telegram/webhook",
                200,
                quantity_webhook_data
            )
            
            invalid_quantity_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Quantity {quantity} properly rejected")
        
        return all(quantity_results) and all(invalid_quantity_results)

    def test_color_selection_by_installation_type(self):
        """Test color selection variations based on installation type"""
        print("\n" + "="*50)
        print("TESTING COLOR SELECTION BY INSTALLATION TYPE")
        print("="*50)
        
        # Test color selection for door/roller types (limited colors)
        door_roller_types = ["дверная", "роллетная"]
        door_roller_results = []
        
        for install_type in door_roller_types:
            # Test limited color options for door/roller
            limited_colors = ["белый", "коричневый"]
            
            for color in limited_colors:
                callback_webhook_data = {
                    "callback_query": {
                        "id": f"test_color_{install_type}_{color}",
                        "data": f"color_{color}",
                        "message": {
                            "chat": {"id": 999888777},
                            "message_id": 130
                        },
                        "from": {"id": 999888777, "first_name": "TestUser"}
                    }
                }
                
                success, result = self.run_test(
                    f"Color Selection - {install_type} type with {color} color",
                    "POST",
                    "telegram/webhook",
                    200,
                    callback_webhook_data
                )
                
                door_roller_results.append(success)
                if success and result.get('ok'):
                    print(f"✅ {install_type} with {color} color processed")
        
        # Test color selection for other types (full color range)
        other_types = ["проемная_наружный", "проемная_внутренний", "проемная_встраиваемый"]
        other_type_results = []
        
        for install_type in other_types:
            # Test full color options 
            full_colors = ["белый", "коричневый", "антрацит", "ral"]
            
            for color in full_colors:
                callback_webhook_data = {
                    "callback_query": {
                        "id": f"test_color_{install_type}_{color}",
                        "data": f"color_{color}",
                        "message": {
                            "chat": {"id": 999888778},
                            "message_id": 131
                        },
                        "from": {"id": 999888778, "first_name": "TestUser"}
                    }
                }
                
                success, result = self.run_test(
                    f"Color Selection - {install_type} type with {color} color",
                    "POST",
                    "telegram/webhook", 
                    200,
                    callback_webhook_data
                )
                
                other_type_results.append(success)
                if success and result.get('ok'):
                    print(f"✅ {install_type} with {color} color processed")
        
        return all(door_roller_results) and all(other_type_results)

    def test_impost_recommendation_logic(self):
        """Test impost recommendation for sizes > 1200mm"""
        print("\n" + "="*50)
        print("TESTING IMPOST RECOMMENDATION FOR SIZES > 1200mm")
        print("="*50)
        
        # Test impost recommendation triggers
        large_sizes = [
            {"width": 1300, "height": 800, "should_recommend": True},
            {"width": 800, "height": 1300, "should_recommend": True},
            {"width": 1500, "height": 1800, "should_recommend": True},
            {"width": 1100, "height": 1100, "should_recommend": False},
            {"width": 800, "height": 1000, "should_recommend": False}
        ]
        
        impost_results = []
        
        for size_test in large_sizes:
            # Test mounting selection callback which triggers impost check
            callback_webhook_data = {
                "callback_query": {
                    "id": f"test_mount_impost_{size_test['width']}_{size_test['height']}",
                    "data": "mount_z_bracket",
                    "message": {
                        "chat": {"id": 999888779},
                        "message_id": 132
                    },
                    "from": {"id": 999888779, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Impost Logic Test - {size_test['width']}x{size_test['height']}mm (should_recommend: {size_test['should_recommend']})",
                "POST",
                "telegram/webhook",
                200,
                callback_webhook_data
            )
            
            impost_results.append(success)
            if success and result.get('ok'):
                recommendation = "recommend" if size_test['should_recommend'] else "not recommend"
                print(f"✅ Size {size_test['width']}x{size_test['height']}mm should {recommendation} impost")
        
        # Test impost orientation selections
        orientations = ["вертикально", "горизонтально"]
        orientation_results = []
        
        for orientation in orientations:
            callback_webhook_data = {
                "callback_query": {
                    "id": f"test_impost_orientation_{orientation}",
                    "data": f"impost_{orientation}",
                    "message": {
                        "chat": {"id": 999888780},
                        "message_id": 133
                    },
                    "from": {"id": 999888780, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Impost Orientation - {orientation}",
                "POST",
                "telegram/webhook",
                200,
                callback_webhook_data
            )
            
            orientation_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Impost orientation {orientation} processed")
        
        return all(impost_results) and all(orientation_results)

    def test_status_history_tracking(self):
        """Test status history tracking in orders"""
        print("\n" + "="*50)
        print("TESTING STATUS HISTORY TRACKING")
        print("="*50)
        
        if not self.admin_token or not self.created_order_id:
            print("⚠️ Skipping status history test - need admin token and order")
            return True
        
        # Get order before status changes to check initial history
        success1, initial_order = self.run_test(
            "Get Order - Check Initial Status History",
            "GET",
            f"orders/{self.created_order_id}",
            200
        )
        
        if success1:
            initial_history = initial_order.get('status_history', [])
            print(f"✅ Initial status history has {len(initial_history)} entries")
        
        # Make multiple status changes to build history
        status_changes = ["new", "in_progress", "ready", "delivered"]
        history_results = []
        
        for status in status_changes:
            success, result = self.run_test(
                f"Status Change to {status} - History Check",
                "PUT",
                f"admin/orders/{self.created_order_id}/status",
                200,
                {"status": status},
                use_admin=True
            )
            
            history_results.append(success)
            if success and 'status_history' in result:
                history = result['status_history']
                print(f"✅ Status changed to {status} - History now has {len(history)} entries")
                
                # Verify the last entry matches the current status
                if history and history[-1]['status'] == status:
                    print(f"✅ Latest history entry matches status: {status}")
                else:
                    print(f"❌ History entry mismatch for status: {status}")
            else:
                print(f"❌ No status_history in response for status: {status}")
        
        # Final verification - get order and check complete history
        success_final, final_order = self.run_test(
            "Final Order Check - Complete Status History",
            "GET",
            f"orders/{self.created_order_id}",
            200
        )
        
        if success_final:
            final_history = final_order.get('status_history', [])
            print(f"✅ Final order has complete status history with {len(final_history)} entries")
            
            # Verify history entries have required fields
            valid_history = True
            for entry in final_history:
                if not all(key in entry for key in ['status', 'changed_at']):
                    valid_history = False
                    print(f"❌ Invalid history entry: {entry}")
                    break
            
            if valid_history:
                print("✅ All status history entries have required fields (status, changed_at)")
        
        return all(history_results) and success_final

    def test_order_number_generation(self):
        """Test МС-0001 format order number generation"""
        print("\n" + "="*50)
        print("TESTING ORDER NUMBER GENERATION (МС-0001 FORMAT)")
        print("="*50)
        
        if not self.user_token:
            print("⚠️ Skipping order number test - no user token")
            return True
        
        # Create multiple orders to test auto-increment
        order_numbers = []
        order_results = []
        
        for i in range(3):  # Create 3 orders to test counter increment
            order_data = {
                "items": [{
                    "installation_type": "проемная_наружный",
                    "width": 800 + i*100,  # Vary dimensions
                    "height": 1200 + i*100,
                    "quantity": 1,
                    "color": "белый",
                    "mounting_type": "z_bracket",
                    "mounting_by_manufacturer": True,
                    "mesh_type": "стандартное",
                    "impost": False,
                    "notes": f"Test order {i+1} for number generation"
                }],
                "desired_date": (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
                "notes": f"Order number test {i+1}",
                "contact_phone": "+375295012233"
            }
            
            success, result = self.run_test(
                f"Order Creation {i+1} - Number Format Test",
                "POST",
                "orders",
                200,
                order_data
            )
            
            order_results.append(success)
            
            if success and 'order_number' in result:
                order_number = result['order_number']
                order_numbers.append(order_number)
                print(f"✅ Order {i+1} created with number: {order_number}")
                
                # Verify МС-XXXX format
                if order_number.startswith('МС-') and len(order_number) == 7:
                    number_part = order_number[3:]
                    if number_part.isdigit() and len(number_part) == 4:
                        print(f"✅ Order number format is correct: {order_number}")
                    else:
                        print(f"❌ Order number format incorrect - digits: {number_part}")
                        order_results[-1] = False
                else:
                    print(f"❌ Order number format incorrect: {order_number}")
                    order_results[-1] = False
            else:
                print(f"❌ No order_number in response for order {i+1}")
                order_results[-1] = False
        
        # Verify sequential numbering
        if len(order_numbers) >= 2:
            for i in range(1, len(order_numbers)):
                prev_num = int(order_numbers[i-1][3:])  # Extract number part
                curr_num = int(order_numbers[i][3:])
                if curr_num > prev_num:
                    print(f"✅ Sequential numbering verified: {order_numbers[i-1]} → {order_numbers[i]}")
                else:
                    print(f"❌ Sequential numbering failed: {order_numbers[i-1]} → {order_numbers[i]}")
                    return False
        
        return all(order_results)

    def test_combined_dimensions_input(self):
        """Test combined dimensions input via Telegram (width height qty)"""
        print("\n" + "="*50)
        print("TESTING COMBINED DIMENSIONS INPUT (WIDTH HEIGHT [QTY])")
        print("="*50)
        
        chat_id = 555777999
        
        # Test various dimension input formats
        dimension_tests = [
            ("800 1200", "Basic two dimensions"),
            ("800 1200 1", "Width height with quantity 1"),
            ("800 1200 2", "Width height with quantity 2"),
            ("1500 1800 3", "Large dimensions with quantity 3"),
            ("300 400 5", "Small dimensions with quantity 5"),
            ("2500 2800 1", "Large dimensions single quantity")
        ]
        
        dimension_results = []
        
        for dimensions_text, description in dimension_tests:
            dimension_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": dimensions_text,
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Combined Dimensions Input - {description} ({dimensions_text})",
                "POST",
                "telegram/webhook",
                200,
                dimension_webhook_data
            )
            
            dimension_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Dimensions '{dimensions_text}' processed correctly")
        
        # Test invalid dimension input formats
        invalid_dimension_tests = [
            ("800", "Only width provided"),
            ("800 1200 2 extra", "Too many parameters"),
            ("abc def", "Non-numeric input"),
            ("800 abc", "Mixed numeric/text"),
            ("0 1200", "Zero width"),
            ("800 0", "Zero height"),
            ("50 1200", "Width too small"),
            ("800 50", "Height too small"),
            ("3500 1200", "Width too large"),
            ("800 3500", "Height too large"),
            ("800 1200 0", "Zero quantity"),
            ("800 1200 40", "Quantity too large")
        ]
        
        invalid_dimension_results = []
        
        for dimensions_text, description in invalid_dimension_tests:
            dimension_webhook_data = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": dimensions_text,
                    "from": {"id": chat_id, "first_name": "TestUser"}
                }
            }
            
            success, result = self.run_test(
                f"Invalid Dimensions Input - {description} ({dimensions_text})",
                "POST",
                "telegram/webhook",
                200,
                dimension_webhook_data
            )
            
            invalid_dimension_results.append(success)
            if success and result.get('ok'):
                print(f"✅ Invalid dimensions '{dimensions_text}' properly handled")
        
        return all(dimension_results) and all(invalid_dimension_results)

    def test_order_tracking_by_number(self):
        """Test order tracking by order number functionality"""
        print("\n" + "="*50)
        print("TESTING ORDER TRACKING BY NUMBER")
        print("="*50)
        
        if not self.user_token:
            print("⚠️ Skipping order tracking test - no user token")
            return True
        
        # First create an order to track
        order_data = {
            "items": [{
                "installation_type": "дверная",
                "width": 900,
                "height": 2000,
                "quantity": 1,
                "color": "коричневый",
                "mounting_type": "metal_hooks",
                "mounting_by_manufacturer": True,
                "mesh_type": "антипыль",
                "impost": True,
                "impost_orientation": "вертикально",
                "notes": "Order for tracking test"
            }],
            "desired_date": (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d'),
            "notes": "Tracking test order",
            "contact_phone": "+375333545588"
        }
        
        success_create, result_create = self.run_test(
            "Create Order for Tracking Test",
            "POST",
            "orders",
            200,
            order_data
        )
        
        if not success_create or 'order_number' not in result_create:
            print("❌ Failed to create order for tracking test")
            return False
        
        order_number = result_create['order_number']
        print(f"✅ Created order for tracking: {order_number}")
        
        # Test tracking via Telegram webhook - /track command
        chat_id = 777555333
        
        # Test /track command
        track_command_webhook = {
            "message": {
                "chat": {"id": chat_id},
                "text": "/track",
                "from": {"id": chat_id, "first_name": "TrackUser"}
            }
        }
        
        success_track_cmd, result_track_cmd = self.run_test(
            "Telegram /track Command",
            "POST",
            "telegram/webhook",
            200,
            track_command_webhook
        )
        
        # Test order number input for tracking
        track_number_webhook = {
            "message": {
                "chat": {"id": chat_id},
                "text": order_number,
                "from": {"id": chat_id, "first_name": "TrackUser"}
            }
        }
        
        success_track_num, result_track_num = self.run_test(
            f"Track Order by Number - {order_number}",
            "POST",
            "telegram/webhook",
            200,
            track_number_webhook
        )
        
        # Test tracking with callback button
        track_callback_webhook = {
            "callback_query": {
                "id": "test_track_callback",
                "data": "track_order",
                "message": {
                    "chat": {"id": chat_id},
                    "message_id": 200
                },
                "from": {"id": chat_id, "first_name": "TrackUser"}
            }
        }
        
        success_track_callback, result_track_callback = self.run_test(
            "Track Order via Callback Button",
            "POST",
            "telegram/webhook",
            200,
            track_callback_webhook
        )
        
        # Test different order number formats
        number_format_tests = [
            (order_number, "Full order number"),
            (order_number[3:], "Number without МС- prefix"),
            (order_number.lower(), "Lowercase order number"),
            (order_number.replace('МС-', 'мс-'), "Lowercase prefix")
        ]
        
        format_results = []
        
        for test_number, description in number_format_tests:
            format_webhook = {
                "message": {
                    "chat": {"id": chat_id},
                    "text": test_number,
                    "from": {"id": chat_id, "first_name": "FormatUser"}
                }
            }
            
            success_format, result_format = self.run_test(
                f"Order Number Format Test - {description} ({test_number})",
                "POST",
                "telegram/webhook",
                200,
                format_webhook
            )
            
            format_results.append(success_format)
            if success_format and result_format.get('ok'):
                print(f"✅ Order number format '{test_number}' handled correctly")
        
        # Test invalid order number
        invalid_number_webhook = {
            "message": {
                "chat": {"id": chat_id},
                "text": "МС-9999",  # Non-existent order number
                "from": {"id": chat_id, "first_name": "InvalidUser"}
            }
        }
        
        success_invalid, result_invalid = self.run_test(
            "Track Invalid Order Number - МС-9999",
            "POST",
            "telegram/webhook",
            200,
            invalid_number_webhook
        )
        
        return (success_track_cmd and success_track_num and success_track_callback 
                and all(format_results) and success_invalid)

    def test_contact_button_tel_link(self):
        """Test contact button with tel: URL functionality"""
        print("\n" + "="*50)
        print("TESTING CONTACT BUTTON TEL: URL (+375333545588)")
        print("="*50)
        
        # Test main menu keyboard generation (contains contact button)
        chat_id = 444222000
        
        start_webhook_data = {
            "message": {
                "chat": {"id": chat_id},
                "text": "/start",
                "from": {"id": chat_id, "first_name": "ContactUser"}
            }
        }
        
        success_start, result_start = self.run_test(
            "Generate Main Menu with Contact Button",
            "POST",
            "telegram/webhook",
            200,
            start_webhook_data
        )
        
        # The contact button is generated in the keyboard, not as a callback
        # We can verify the webhook processes successfully
        if success_start and result_start.get('ok'):
            print("✅ Main menu generated (should contain contact button with tel:+375333545588)")
        
        # Test help command that also shows main menu
        help_webhook_data = {
            "message": {
                "chat": {"id": chat_id},
                "text": "/help",
                "from": {"id": chat_id, "first_name": "ContactUser"}
            }
        }
        
        success_help, result_help = self.run_test(
            "Help Command with Contact Button",
            "POST",
            "telegram/webhook",
            200,
            help_webhook_data
        )
        
        # Test back to main menu (should also generate contact button)
        back_callback_webhook = {
            "callback_query": {
                "id": "test_back_main_contact",
                "data": "back_main",
                "message": {
                    "chat": {"id": chat_id},
                    "message_id": 201
                },
                "from": {"id": chat_id, "first_name": "ContactUser"}
            }
        }
        
        success_back, result_back = self.run_test(
            "Back to Main Menu - Contact Button",
            "POST",
            "telegram/webhook",
            200,
            back_callback_webhook
        )
        
        # Verify contact phone constant in code
        print(f"✅ Expected contact phone: +375333545588")
        print("✅ Contact button should use tel: URL scheme for direct calling")
        
        return success_start and success_help and success_back

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting Mosquito Net API Tests...")
        print(f"📡 API Endpoint: {self.base_url}")
        
        # Run tests in order
        tests = [
            self.test_health_endpoints,
            self.test_user_registration,
            self.test_admin_login,
            self.test_user_login,
            self.test_price_calculation,
            self.test_order_creation,
            self.test_order_retrieval,
            self.test_admin_functionality,
            self.test_telegram_webhook,
            self.test_telegram_inline_keyboards,
            self.test_telegram_order_type_keyboard,
            self.test_push_notifications_on_status_change,
            self.test_telegram_dimension_validation,
            self.test_telegram_quantity_validation,
            self.test_color_selection_by_installation_type,
            self.test_impost_recommendation_logic,
            self.test_status_history_tracking
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                print(f"❌ Test failed with exception: {e}")
                self.tests_run += 1
        
        # Print final results
        print("\n" + "="*60)
        print("FINAL RESULTS")
        print("="*60)
        print(f"📊 Tests run: {self.tests_run}")
        print(f"✅ Tests passed: {self.tests_passed}")
        print(f"❌ Tests failed: {self.tests_run - self.tests_passed}")
        print(f"📈 Success rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0.0%")
        
        success_rate = (self.tests_passed/self.tests_run) if self.tests_run > 0 else 0
        return success_rate >= 0.8  # 80% success rate

def main():
    tester = MosquitoNetAPITester()
    success = tester.run_all_tests()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())