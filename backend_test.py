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

    def test_telegram_webhook(self):
        """Test Telegram webhook endpoint with all bot commands"""
        print("\n" + "="*50)
        print("TESTING TELEGRAM WEBHOOK - ALL BOT COMMANDS")
        print("="*50)
        
        # Test /start command
        start_webhook_data = {
            "message": {
                "chat": {"id": 123456789},
                "text": "/start",
                "from": {"id": 123456789, "first_name": "TestUser"}
            }
        }
        
        success1, result1 = self.run_test(
            "Telegram Bot /start command",
            "POST",
            "telegram/webhook",
            200,
            start_webhook_data
        )
        
        # Test /help command  
        help_webhook_data = {
            "message": {
                "chat": {"id": 123456789},
                "text": "/help",
                "from": {"id": 123456789, "first_name": "TestUser"}
            }
        }
        
        success2, result2 = self.run_test(
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
        
        success3, result3 = self.run_test(
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
        
        success4, result4 = self.run_test(
            "Telegram Bot unknown command",
            "POST",
            "telegram/webhook",
            200,
            unknown_webhook_data
        )
        
        if success1 and success2 and success3:
            print("✅ All Telegram bot commands (/start, /help, /orders) working correctly")
        
        return success1 and success2 and success3 and success4

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
            self.test_telegram_webhook
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