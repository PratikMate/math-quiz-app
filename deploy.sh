#!/bin/bash

# Heroku Deployment Script for Competitive Math Quiz
# This script helps deploy the application to Heroku with proper configuration

set -e  # Exit on any error

echo "🚀 Starting Heroku deployment for Competitive Math Quiz..."

# Check if Heroku CLI is installed
if ! command -v heroku &> /dev/null; then
    echo "❌ Heroku CLI is not installed. Please install it first:"
    echo "   https://devcenter.heroku.com/articles/heroku-cli"
    exit 1
fi

# Check if user is logged in to Heroku
if ! heroku auth:whoami &> /dev/null; then
    echo "❌ Please log in to Heroku first:"
    echo "   heroku login"
    exit 1
fi

# Get app name from user or use default
read -p "Enter Heroku app name (or press Enter for auto-generated): " APP_NAME

# Create Heroku app
if [ -z "$APP_NAME" ]; then
    echo "📱 Creating new Heroku app..."
    heroku create
else
    echo "📱 Creating Heroku app: $APP_NAME"
    heroku create "$APP_NAME"
fi

# Get the actual app name (in case it was auto-generated)
APP_NAME=$(heroku apps:info --json | python3 -c "import sys, json; print(json.load(sys.stdin)['app']['name'])")
echo "✅ App created: $APP_NAME"

# Add buildpacks
echo "🔧 Adding buildpacks..."
heroku buildpacks:add heroku/python --app "$APP_NAME"
heroku buildpacks:add heroku/nodejs --app "$APP_NAME"

# Add add-ons
echo "🗄️  Adding PostgreSQL add-on..."
heroku addons:create heroku-postgresql:mini --app "$APP_NAME"

echo "🔴 Adding Redis add-on..."
heroku addons:create heroku-redis:mini --app "$APP_NAME"

# Set environment variables
echo "⚙️  Setting environment variables..."

# Required environment variables
heroku config:set ENVIRONMENT=production --app "$APP_NAME"
heroku config:set DEBUG=false --app "$APP_NAME"
heroku config:set LOG_LEVEL=INFO --app "$APP_NAME"

# Performance settings
heroku config:set MAX_CONCURRENT_USERS=100 --app "$APP_NAME"
heroku config:set RATE_LIMIT_PER_MINUTE=60 --app "$APP_NAME"
heroku config:set DATABASE_POOL_SIZE=20 --app "$APP_NAME"
heroku config:set REDIS_POOL_SIZE=20 --app "$APP_NAME"

# Generate secret key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
heroku config:set SECRET_KEY="$SECRET_KEY" --app "$APP_NAME"

# Prompt for required API keys
echo ""
echo "🔑 Please provide the following required configuration:"
echo ""

read -p "Enter your Google Gemini API key: " GEMINI_API_KEY
if [ -z "$GEMINI_API_KEY" ]; then
    echo "❌ Gemini API key is required!"
    exit 1
fi
heroku config:set GEMINI_API_KEY="$GEMINI_API_KEY" --app "$APP_NAME"

read -p "Enter your frontend domain (e.g., https://myapp-frontend.herokuapp.com): " FRONTEND_DOMAIN
if [ -z "$FRONTEND_DOMAIN" ]; then
    FRONTEND_DOMAIN="https://$APP_NAME.herokuapp.com"
fi
heroku config:set CORS_ORIGINS="$FRONTEND_DOMAIN" --app "$APP_NAME"

# Deploy the application
echo ""
echo "🚀 Deploying application..."
git add .
git commit -m "Deploy to Heroku" || echo "No changes to commit"
git push heroku main

# Run database migrations
echo "🗄️  Running database migrations..."
heroku run "cd backend && alembic upgrade head" --app "$APP_NAME"

# Open the application
echo ""
echo "✅ Deployment complete!"
echo "🌐 Your app is available at: https://$APP_NAME.herokuapp.com"
echo ""
echo "📊 Useful commands:"
echo "   heroku logs --tail --app $APP_NAME                 # View logs"
echo "   heroku config --app $APP_NAME                      # View config vars"
echo "   heroku ps --app $APP_NAME                          # View dynos"
echo "   heroku addons --app $APP_NAME                      # View add-ons"
echo "   heroku run bash --app $APP_NAME                    # Access shell"
echo ""

read -p "Open the app in your browser? (y/n): " OPEN_APP
if [ "$OPEN_APP" = "y" ] || [ "$OPEN_APP" = "Y" ]; then
    heroku open --app "$APP_NAME"
fi

echo "🎉 Deployment script completed successfully!"