#!/usr/bin/env python3
"""
Comprehensive test suite for Borg Web UI
Tests all core functionality including API endpoints, authentication, routing, and application health.
"""

import requests
import json
import time
import sys
from typing import Dict, Any, Optional

class BorgWebUITester:
    def __init__(self, base_url: str = "http://localhost:7879"):
        self.base_url = base_url
        self.session = requests.Session()
        self.auth_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, message: str = "", details: Any = None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "details": details
        })
        
        if not success:
            print(f"   Details: {details}")
    
    def test_server_availability(self) -> bool:
        """Test if the server is running and accessible"""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                self.log_test("Server Availability", True, "Server is running and accessible")
                return True
            else:
                self.log_test("Server Availability", False, f"Server returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            self.log_test("Server Availability", False, f"Server not accessible: {str(e)}")
            return False
    
    def test_spa_routing(self) -> bool:
        """Test SPA routing - all frontend routes should serve index.html"""
        frontend_routes = ["/dashboard", "/config", "/backup", "/archives", "/restore", 
                          "/schedule", "/logs", "/settings", "/repositories", "/ssh-keys", "/health"]
        
        all_passed = True
        for route in frontend_routes:
            try:
                response = self.session.get(f"{self.base_url}{route}", timeout=5)
                if response.status_code == 200 and "<!doctype html>" in response.text.lower():
                    self.log_test(f"SPA Routing {route}", True, "Serves frontend correctly")
                else:
                    self.log_test(f"SPA Routing {route}", False, f"Expected 200 with HTML, got {response.status_code}")
                    all_passed = False
            except requests.exceptions.RequestException as e:
                self.log_test(f"SPA Routing {route}", False, f"Request failed: {str(e)}")
                all_passed = False
        
        return all_passed
    
    def test_api_routes_exist(self) -> bool:
        """Test that API routes exist and return proper responses"""
        api_routes = [
            ("/api", "GET"),
            ("/api/docs", "GET"),
            ("/api/health/system", "GET"),
        ]
        
        all_passed = True
        for route, method in api_routes:
            try:
                if method == "GET":
                    response = self.session.get(f"{self.base_url}{route}", timeout=5)
                else:
                    response = self.session.post(f"{self.base_url}{route}", timeout=5)
                
                if response.status_code in [200, 401, 403]:  # 401/403 are expected for protected routes
                    self.log_test(f"API Route {route}", True, f"Returns status {response.status_code}")
                else:
                    self.log_test(f"API Route {route}", False, f"Unexpected status {response.status_code}")
                    all_passed = False
            except requests.exceptions.RequestException as e:
                self.log_test(f"API Route {route}", False, f"Request failed: {str(e)}")
                all_passed = False
        
        return all_passed
    
    def test_authentication(self) -> bool:
        """Test authentication flow"""
        try:
            # Test login with correct credentials
            login_data = {"username": "admin", "password": "admin123"}
            response = self.session.post(f"{self.base_url}/api/auth/login", data=login_data, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.auth_token = data["access_token"]
                    self.log_test("Authentication Login", True, "Successfully logged in and got token")
                    
                    # Test getting user info with token
                    headers = {"Authorization": f"Bearer {self.auth_token}"}
                    user_response = self.session.get(f"{self.base_url}/api/auth/me", headers=headers, timeout=5)
                    
                    if user_response.status_code == 200:
                        user_data = user_response.json()
                        if user_data.get("username") == "admin":
                            self.log_test("Authentication User Info", True, "Successfully retrieved user info")
                            return True
                        else:
                            self.log_test("Authentication User Info", False, "User info doesn't match expected")
                            return False
                    else:
                        self.log_test("Authentication User Info", False, f"Failed to get user info: {user_response.status_code}")
                        return False
                else:
                    self.log_test("Authentication Login", False, "No access token in response")
                    return False
            else:
                self.log_test("Authentication Login", False, f"Login failed with status {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_test("Authentication", False, f"Authentication request failed: {str(e)}")
            return False
    
    def test_protected_endpoints(self) -> bool:
        """Test protected endpoints with authentication"""
        if not self.auth_token:
            self.log_test("Protected Endpoints", False, "No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        protected_routes = [
            "/api/dashboard/status",
            "/api/dashboard/health",
            "/api/dashboard/metrics",
            "/api/repositories/",
            "/api/ssh-keys/"
        ]
        
        all_passed = True
        for route in protected_routes:
            try:
                response = self.session.get(f"{self.base_url}{route}", headers=headers, timeout=5)
                if response.status_code == 200:
                    self.log_test(f"Protected Endpoint {route}", True, "Accessible with auth")
                else:
                    self.log_test(f"Protected Endpoint {route}", False, f"Unexpected status {response.status_code}")
                    all_passed = False
            except requests.exceptions.RequestException as e:
                self.log_test(f"Protected Endpoint {route}", False, f"Request failed: {str(e)}")
                all_passed = False
        
        return all_passed
    
    def test_config_endpoints(self) -> bool:
        """Test configuration and settings endpoints"""
        if not self.auth_token:
            self.log_test("Config Endpoints", False, "No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}
        
        try:
            # Test config current endpoint
            response = self.session.get(f"{self.base_url}/api/config/current", headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if "content" in data and "parsed" in data:
                    self.log_test("Config Current Endpoint", True, "Config current endpoint accessible with proper structure")
                else:
                    self.log_test("Config Current Endpoint", False, "Missing required fields in response")
                    return False
            else:
                self.log_test("Config Current Endpoint", False, f"Failed with status {response.status_code}")
                return False
            
            # Test config templates endpoint
            response = self.session.get(f"{self.base_url}/api/config/templates", headers=headers, timeout=5)
            if response.status_code == 200:
                self.log_test("Config Templates Endpoint", True, "Config templates endpoint accessible")
            else:
                self.log_test("Config Templates Endpoint", False, f"Failed with status {response.status_code}")
                return False
            
            # Test config validation with valid config
            valid_config = """
repositories: []
retention:
  keep_daily: 7
  keep_weekly: 4
  keep_monthly: 6
  keep_yearly: 1
source_directories:
  - /home
  - /etc
exclude_patterns:
  - /tmp
  - /var/tmp
"""
            response = self.session.post(f"{self.base_url}/api/config/validate", 
                                       headers=headers, json={"content": valid_config}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("valid") == True:
                    self.log_test("Config Validation - Valid", True, "Valid configuration accepted")
                else:
                    self.log_test("Config Validation - Valid", False, f"Valid config rejected: {data.get('errors', [])}")
                    return False
            else:
                self.log_test("Config Validation - Valid", False, f"Validation failed with status {response.status_code}")
                return False
            
            # Test config validation with invalid config
            invalid_config = """
repositories: []
retention:
  keep_daily: invalid_value
source_directories:
  - /home
"""
            response = self.session.post(f"{self.base_url}/api/config/validate", 
                                       headers=headers, json={"content": invalid_config}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("valid") == False and data.get("errors"):
                    self.log_test("Config Validation - Invalid", True, "Invalid configuration properly rejected")
                else:
                    self.log_test("Config Validation - Invalid", False, "Invalid config not properly rejected")
                    return False
            else:
                self.log_test("Config Validation - Invalid", False, f"Validation failed with status {response.status_code}")
                return False
            
            return True
            
        except requests.exceptions.RequestException as e:
            self.log_test("Config Endpoints", False, f"Config endpoints test failed: {str(e)}")
            return False
    
    def test_health_endpoints(self) -> bool:
        """Test health and status endpoints"""
        if not self.auth_token:
            self.log_test("Health Endpoints", False, "No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            # Test dashboard health
            response = self.session.get(f"{self.base_url}/api/dashboard/health", headers=headers, timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                if health_data.get("status") in ["healthy", "warning"]:
                    self.log_test("Dashboard Health", True, f"Status: {health_data.get('status')}")
                else:
                    self.log_test("Dashboard Health", False, f"Unexpected health status: {health_data.get('status')}")
                    return False
            else:
                self.log_test("Dashboard Health", False, f"Failed with status {response.status_code}")
                return False
            
            # Test system health
            response = self.session.get(f"{self.base_url}/api/health/system", headers=headers, timeout=5)
            if response.status_code == 200:
                self.log_test("System Health", True, "System health endpoint accessible")
            else:
                self.log_test("System Health", False, f"Failed with status {response.status_code}")
                return False
            
            return True
            
        except requests.exceptions.RequestException as e:
            self.log_test("Health Endpoints", False, f"Health check failed: {str(e)}")
            return False
    
    def test_static_assets(self) -> bool:
        """Test that static assets are served correctly"""
        try:
            # Test main CSS file
            response = self.session.get(f"{self.base_url}/assets/index-4d255f1b.css", timeout=5)
            if response.status_code == 200 and "text/css" in response.headers.get("content-type", ""):
                self.log_test("Static CSS Assets", True, "CSS files served correctly")
            else:
                self.log_test("Static CSS Assets", False, f"CSS not served correctly: {response.status_code}")
                return False
            
            # Test main JS file
            response = self.session.get(f"{self.base_url}/assets/index-28918314.js", timeout=5)
            if response.status_code == 200 and "text/javascript" in response.headers.get("content-type", ""):
                self.log_test("Static JS Assets", True, "JS files served correctly")
            else:
                self.log_test("Static JS Assets", False, f"JS not served correctly: {response.status_code}")
                return False
            
            return True
            
        except requests.exceptions.RequestException as e:
            self.log_test("Static Assets", False, f"Static assets test failed: {str(e)}")
            return False
    
    def test_repository_operations(self) -> bool:
        """Test repository operations (create, list, delete)"""
        if not self.auth_token:
            self.log_test("Repository Operations", False, "No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}
        
        try:
            # Test listing repositories (should be empty initially)
            response = self.session.get(f"{self.base_url}/api/repositories/", headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("repositories") == []:
                    self.log_test("Repository List", True, "Repository list accessible and empty")
                else:
                    self.log_test("Repository List", False, "Repository list not working correctly")
                    return False
            else:
                self.log_test("Repository List", False, f"Failed with status {response.status_code}")
                return False
            
            # Test creating a repository
            import time
            timestamp = int(time.time())
            repo_data = {
                "name": f"test-repo-{timestamp}",
                "path": f"/backups/test-{timestamp}",
                "encryption": "repokey",
                "compression": "lz4",
                "repository_type": "local",
                "passphrase": "testpass123"
            }
            
            response = self.session.post(f"{self.base_url}/api/repositories/", 
                                       headers=headers, json=repo_data, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    repo_id = data.get("repository", {}).get("id")
                    self.log_test("Repository Create", True, f"Repository created with ID {repo_id}")
                    
                    # Test deleting the repository
                    if repo_id:
                        delete_response = self.session.delete(f"{self.base_url}/api/repositories/{repo_id}", 
                                                           headers=headers, timeout=10)
                        if delete_response.status_code == 200:
                            self.log_test("Repository Delete", True, "Repository deleted successfully")
                            return True
                        else:
                            self.log_test("Repository Delete", False, f"Delete failed with status {delete_response.status_code}")
                            return False
                    else:
                        self.log_test("Repository Delete", False, "No repository ID returned")
                        return False
                else:
                    self.log_test("Repository Create", False, f"Create failed: {data.get('detail', 'Unknown error')}")
                    return False
            else:
                self.log_test("Repository Create", False, f"Create failed with status {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_test("Repository Operations", False, f"Repository operations failed: {str(e)}")
            return False
    
    def test_error_handling(self) -> bool:
        """Test error handling for invalid requests"""
        try:
            # Test invalid API route
            response = self.session.get(f"{self.base_url}/api/nonexistent", timeout=5)
            if response.status_code == 404:
                self.log_test("Error Handling - Invalid API", True, "Properly returns 404 for invalid API route")
            else:
                self.log_test("Error Handling - Invalid API", False, f"Expected 404, got {response.status_code}")
                return False
            
            # Test invalid static asset
            response = self.session.get(f"{self.base_url}/assets/nonexistent.js", timeout=5)
            if response.status_code == 404:
                self.log_test("Error Handling - Invalid Asset", True, "Properly returns 404 for invalid asset")
            else:
                self.log_test("Error Handling - Invalid Asset", False, f"Expected 404, got {response.status_code}")
                return False
            
            return True
            
        except requests.exceptions.RequestException as e:
            self.log_test("Error Handling", False, f"Error handling test failed: {str(e)}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return results"""
        print("🚀 Starting Borg Web UI Test Suite")
        print("=" * 50)
        
        # Run tests in order
        tests = [
            ("Server Availability", self.test_server_availability),
            ("SPA Routing", self.test_spa_routing),
            ("API Routes", self.test_api_routes_exist),
            ("Authentication", self.test_authentication),
            ("Protected Endpoints", self.test_protected_endpoints),
            ("Config Endpoints", self.test_config_endpoints),
            ("Health Endpoints", self.test_health_endpoints),
            ("Static Assets", self.test_static_assets),
            ("Repository Operations", self.test_repository_operations),
            ("Error Handling", self.test_error_handling),
        ]
        
        results = {}
        for test_name, test_func in tests:
            print(f"\n📋 Running {test_name} tests...")
            try:
                success = test_func()
                results[test_name] = success
            except Exception as e:
                self.log_test(test_name, False, f"Test crashed: {str(e)}")
                results[test_name] = False
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, success in results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\n🎯 Overall Result: {passed}/{total} test categories passed")
        
        if passed == total:
            print("🎉 All tests passed! The application is working correctly.")
        else:
            print("⚠️  Some tests failed. Please check the details above.")
        
        return {
            "total_tests": total,
            "passed_tests": passed,
            "failed_tests": total - passed,
            "success_rate": passed / total if total > 0 else 0,
            "results": results,
            "detailed_results": self.test_results
        }

def main():
    """Main function to run the test suite"""
    import argparse

    parser = argparse.ArgumentParser(description="Test Borg Web UI")
    parser.add_argument("--url", default="http://localhost:7879",
                       help="Base URL of the application (default: http://localhost:7879)")
    parser.add_argument("--output", help="Output results to JSON file")

    args = parser.parse_args()

    tester = BorgWebUITester(args.url)
    results = tester.run_all_tests()
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📄 Results saved to {args.output}")
    
    # Exit with appropriate code
    if results["passed_tests"] == results["total_tests"]:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
