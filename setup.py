#!/usr/bin/env python3
"""
Setup script for WWII History Video Automation
Creates necessary directories and validates configuration
"""

import os
import json
import sys
from pathlib import Path

def create_directories():
    """Create necessary directories"""
    directories = [
        'productions',
        'output',
        'segments',
        'media'
    ]
    
    print("📁 Creating directories...")
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        # Create .gitkeep to preserve directory structure
        gitkeep = Path(directory) / '.gitkeep'
        gitkeep.touch(exist_ok=True)
        print(f"  ✅ {directory}/")
    
    print()

def validate_env_vars():
    """Validate required environment variables"""
    required_vars = {
        'TELEGRAM_BOT_TOKEN': 'Telegram bot token from @BotFather',
        'TELEGRAM_CHAT_ID': 'Your Telegram chat ID',
        'YOUTUBE_CREDENTIALS': 'YouTube OAuth credentials JSON',
    }
    
    optional_vars = {
        'GITHUB_TOKEN': 'GitHub personal access token (for bot server)',
        'GITHUB_REPO': 'GitHub repository (username/repo-name)',
        'TELEGRAM_WEBHOOK_URL': 'Bot webhook URL (for production)',
    }
    
    print("🔍 Checking environment variables...")
    print()
    
    all_valid = True
    
    # Check required variables
    for var, description in required_vars.items():
        value = os.environ.get(var)
        if value:
            # Mask sensitive data
            if 'TOKEN' in var or 'CREDENTIALS' in var:
                display = value[:10] + '...' + value[-5:] if len(value) > 15 else '***'
            else:
                display = value
            print(f"  ✅ {var}: {display}")
        else:
            print(f"  ❌ {var}: NOT SET")
            print(f"     → {description}")
            all_valid = False
    
    print()
    
    # Check optional variables
    print("Optional variables:")
    for var, description in optional_vars.items():
        value = os.environ.get(var)
        if value:
            if 'TOKEN' in var:
                display = value[:10] + '...'
            else:
                display = value
            print(f"  ✅ {var}: {display}")
        else:
            print(f"  ⚠️  {var}: not set")
            print(f"     → {description}")
    
    print()
    return all_valid

def validate_youtube_credentials():
    """Validate YouTube credentials format"""
    creds = os.environ.get('YOUTUBE_CREDENTIALS')
    
    if not creds:
        return False
    
    try:
        creds_dict = json.loads(creds)
        required_keys = ['token', 'refresh_token', 'client_id', 'client_secret']
        
        missing_keys = [key for key in required_keys if key not in creds_dict]
        
        if missing_keys:
            print(f"  ⚠️  YouTube credentials missing keys: {', '.join(missing_keys)}")
            return False
        
        print("  ✅ YouTube credentials format is valid")
        return True
        
    except json.JSONDecodeError:
        print("  ❌ YouTube credentials is not valid JSON")
        return False

def test_telegram_connection():
    """Test Telegram bot connection"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("  ⚠️  Cannot test - TELEGRAM_BOT_TOKEN not set")
        return False
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/getMe"
        response = requests.get(url, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            bot_info = result['result']
            print(f"  ✅ Bot connected: @{bot_info['username']}")
            print(f"     Name: {bot_info['first_name']}")
            return True
        else:
            print(f"  ❌ Bot connection failed: {result.get('description', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error testing bot connection: {e}")
        return False

def create_example_script():
    """Create example production script"""
    example = """TITLE: The Silent Heroes of Operation Overlord
DESCRIPTION: Discover the untold stories of the brave soldiers who changed the course of history during D-Day. This documentary explores lesser-known accounts from the beaches of Normandy, featuring first-hand testimonies and historical analysis.
TAGS: WWII, D-Day, Normandy, World War 2, History, Documentary, Operation Overlord, Historical Stories
SCRIPT:
June 6th, 1944. The beaches of Normandy bore witness to one of humanity's most pivotal moments. While history remembers the generals and the grand strategy, countless individual acts of heroism remain untold.

Today, we uncover the silent heroes of Operation Overlord. These are the stories of men whose courage shaped history, yet their names were never written in textbooks.

In the predawn darkness of that fateful day, thousands of paratroopers descended behind enemy lines. Among them was Private James Miller, a 19-year-old from Ohio, carrying nothing but his rifle and an unwavering determination.

As his parachute caught the wind, Miller had no way of knowing that his actions in the next 72 hours would save the lives of an entire company. But that's exactly what happened.

Our story begins in the hedgerows of Normandy, where Miller and his fellow soldiers faced an enemy they couldn't see. The bocage country, with its ancient stone walls and dense vegetation, became a deadly maze.

[Continue with your full narration script...]

This is a complete production request. The bot will process this, generate audio, and request media for each 30-second segment.
"""
    
    example_file = Path('example_script.txt')
    if not example_file.exists():
        with open(example_file, 'w', encoding='utf-8') as f:
            f.write(example)
        print(f"  ✅ Created {example_file}")
    else:
        print(f"  ℹ️  {example_file} already exists")

def main():
    """Main setup function"""
    print("="*60)
    print("🎬 WWII History Video Automation - Setup")
    print("="*60)
    print()
    
    # Create directories
    create_directories()
    
    # Validate environment
    env_valid = validate_env_vars()
    
    print("🔍 Validating configurations...")
    print()
    
    # Validate YouTube credentials
    youtube_valid = validate_youtube_credentials()
    
    # Test Telegram connection
    print("🤖 Testing Telegram bot connection...")
    telegram_valid = test_telegram_connection()
    print()
    
    # Create example
    print("📝 Creating example files...")
    create_example_script()
    print()
    
    # Summary
    print("="*60)
    print("📊 Setup Summary")
    print("="*60)
    print()
    
    if env_valid and youtube_valid and telegram_valid:
        print("✅ All checks passed!")
        print()
        print("Next steps:")
        print("  1. Deploy telegram_bot.py to your server")
        print("  2. Set webhook URL in environment")
        print("  3. Configure GitHub secrets")
        print("  4. Send a test message to your bot")
        print()
        print("📱 Send /start to your bot to begin!")
        return 0
    else:
        print("⚠️  Some checks failed")
        print()
        print("Please fix the issues above and run setup again.")
        print()
        print("For help, see README.md")
        return 1

if __name__ == '__main__':
    sys.exit(main())
