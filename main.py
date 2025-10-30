#!/usr/bin/env python3
"""
YouTube Transcript & Summary Application
Main entry point for the Flask application.

This file serves as the primary entry point for running the YouTube Transcript
and Summary application. It handles configuration, environment setup, and
application startup.

Usage:
    python main.py [--port PORT] [--host HOST] [--debug]
    
Environment Variables:
    PORT: Port number to run the server on (default: 8080)
    HOST: Host address to bind to (default: 0.0.0.0)
    DEBUG: Enable debug mode (default: False)
"""

import os
import sys
import argparse
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from app import app
    print("✅ Application modules loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import application modules: {e}")
    print("Make sure you're in the correct directory and all dependencies are installed.")
    sys.exit(1)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='YouTube Transcript & Summary Application',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                          # Run with default settings
    python main.py --port 5000              # Run on port 5000
    python main.py --host 127.0.0.1 --debug # Run locally with debug mode
    python main.py --port 8080 --host 0.0.0.0 # Run for production
        """
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=int(os.environ.get("PORT", 8080)),
        help='Port number to run the server on (default: 8080 or PORT env var)'
    )
    
    parser.add_argument(
        '--host',
        type=str,
        default=os.environ.get("HOST", "0.0.0.0"),
        help='Host address to bind to (default: 0.0.0.0 or HOST env var)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        default=os.environ.get("DEBUG", "").lower() in ('true', '1', 'yes'),
        help='Enable debug mode (default: False or DEBUG env var)'
    )
    
    parser.add_argument(
        '--config-dir',
        type=str,
        default='config',
        help='Configuration directory path (default: config)'
    )
    
    return parser.parse_args()

def setup_environment(args):
    """Setup application environment and configuration paths."""
    # Set configuration paths
    config_dir = Path(project_root) / args.config_dir
    
    # Ensure config directory exists
    if not config_dir.exists():
        print(f"⚠️ Configuration directory not found: {config_dir}")
        print("Using default configuration...")
    else:
        print(f"✅ Using configuration directory: {config_dir}")
    
    # Set environment variables for the application
    os.environ.setdefault('CONFIG_DIR', str(config_dir))
    os.environ.setdefault('PROJECT_ROOT', str(project_root))
    
    return config_dir

def print_startup_info(host, port, debug, config_dir):
    """Print application startup information."""
    print("\n" + "="*60)
    print("🚀 YouTube Transcript & Summary Application")
    print("="*60)
    print(f"📂 Project Root: {project_root}")
    print(f"⚙️  Config Dir:   {config_dir}")
    print(f"🌐 Server URL:   http://{host}:{port}")
    print(f"🔧 Debug Mode:   {'Enabled' if debug else 'Disabled'}")
    print(f"📝 Environment:  {'Development' if debug else 'Production'}")
    print("="*60)
    print("Available endpoints:")
    print("  • Main UI:        http://{0}:{1}/".format(host, port))
    print("  • Health Check:   http://{0}:{1}/api/health".format(host, port))
    print("  • API Docs:       http://{0}:{1}/api/".format(host, port))
    print("="*60)
    if debug:
        print("⚠️  DEBUG MODE: Do not use in production!")
    print("Press Ctrl+C to stop the server\n")

def main():
    """Main application entry point."""
    try:
        # Parse command line arguments
        args = parse_arguments()
        
        # Setup environment
        config_dir = setup_environment(args)
        
        # Print startup information
        print_startup_info(args.host, args.port, args.debug, config_dir)
        
        # Configure Flask app settings
        app.config['DEBUG'] = args.debug
        app.config['HOST'] = args.host
        app.config['PORT'] = args.port
        
        # Run the application
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            use_reloader=False  # Disable reloader to prevent Crawl4AI conflicts
        )
        
    except KeyboardInterrupt:
        print("\n👋 Application stopped by user")
    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()