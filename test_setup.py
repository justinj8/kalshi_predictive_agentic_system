"""
Test Setup - Verify all required packages are installed correctly
"""

def test_imports():
    """Test that all required packages can be imported."""
    results = []
    
    # Core Dependencies
    packages = [
        ("python-dotenv", "dotenv"),
        ("pydantic", "pydantic"),
        ("pydantic-settings", "pydantic_settings"),
        
        # LangChain & LangGraph
        ("langchain", "langchain"),
        ("langchain-anthropic", "langchain_anthropic"),
        ("langgraph", "langgraph"),
        ("langchain-community", "langchain_community"),
        
        # Anthropic API
        ("anthropic", "anthropic"),
        
        # Kalshi API
        ("kalshi-python", "kalshi_python"),
        
        # Data Processing
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("pandas-ta", "pandas_ta"),
        
        # News & Social Media APIs
        ("newsapi-python", "newsapi"),
        ("praw", "praw"),
        ("tweepy", "tweepy"),
        ("requests", "requests"),
        ("beautifulsoup4", "bs4"),
        
        # Database
        ("sqlalchemy", "sqlalchemy"),
        ("alembic", "alembic"),
        
        # Scheduling
        ("apscheduler", "apscheduler"),
        
        # Logging & Monitoring
        ("loguru", "loguru"),
        ("python-json-logger", "pythonjsonlogger"),
        
        # Utilities
        ("python-dateutil", "dateutil"),
        ("pytz", "pytz"),
        ("tenacity", "tenacity"),
        
        # Testing
        ("pytest", "pytest"),
        ("pytest-asyncio", "pytest_asyncio"),
        ("pytest-cov", "pytest_cov"),
        ("httpx", "httpx"),
        
        # Data Visualization
        ("matplotlib", "matplotlib"),
        ("seaborn", "seaborn"),
        ("plotly", "plotly"),
        
        # Optional
        ("openai", "openai"),
    ]
    
    print("=" * 60)
    print("Testing Package Imports")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for package_name, import_name in packages:
        try:
            __import__(import_name)
            print(f"✅ {package_name:<25} - OK")
            passed += 1
        except ImportError as e:
            print(f"❌ {package_name:<25} - FAILED: {e}")
            failed += 1
            results.append((package_name, str(e)))
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed > 0:
        print("\nFailed packages:")
        for pkg, error in results:
            print(f"  - {pkg}: {error}")
        return False
    
    print("\n🎉 All packages installed successfully!")
    return True


if __name__ == "__main__":
    success = test_imports()
    exit(0 if success else 1)
