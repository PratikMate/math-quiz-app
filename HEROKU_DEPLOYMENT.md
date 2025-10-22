# Heroku Deployment Guide

This guide walks you through deploying the Competitive Math Quiz application to Heroku.

## Prerequisites

1. **Heroku CLI**: Install from [https://devcenter.heroku.com/articles/heroku-cli](https://devcenter.heroku.com/articles/heroku-cli)
2. **Git**: Ensure your project is in a Git repository
3. **Google Gemini API Key**: Get one from [Google AI Studio](https://makersuite.google.com/app/apikey)

## Quick Deployment

### Option 1: Automated Script (Recommended)

Run the deployment script:

```bash
./deploy.sh
```

This script will:
- Create a new Heroku app
- Add required buildpacks (Python + Node.js)
- Add PostgreSQL and Redis add-ons
- Set environment variables
- Deploy the application
- Run database migrations

### Option 2: Manual Deployment

#### Step 1: Create Heroku App

```bash
# Login to Heroku
heroku login

# Create a new app (replace 'your-app-name' with desired name)
heroku create your-app-name

# Or let Heroku generate a name
heroku create
```

#### Step 2: Add Buildpacks

```bash
heroku buildpacks:add heroku/python
heroku buildpacks:add heroku/nodejs
```

#### Step 3: Add Add-ons

```bash
# PostgreSQL database
heroku addons:create heroku-postgresql:mini

# Redis cache
heroku addons:create heroku-redis:mini
```

#### Step 4: Set Environment Variables

```bash
# Required configuration
heroku config:set ENVIRONMENT=production
heroku config:set DEBUG=false
heroku config:set LOG_LEVEL=INFO

# API Keys (replace with your actual keys)
heroku config:set GEMINI_API_KEY=your_gemini_api_key_here
heroku config:set SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

# CORS configuration (replace with your frontend domain)
heroku config:set CORS_ORIGINS=https://your-frontend-domain.com

# Performance settings
heroku config:set MAX_CONCURRENT_USERS=100
heroku config:set RATE_LIMIT_PER_MINUTE=60
heroku config:set DATABASE_POOL_SIZE=20
heroku config:set REDIS_POOL_SIZE=20
```

#### Step 5: Deploy

```bash
# Add and commit your changes
git add .
git commit -m "Deploy to Heroku"

# Push to Heroku
git push heroku main
```

#### Step 6: Run Database Migrations

```bash
heroku run "cd backend && alembic upgrade head"
```

## Configuration Details

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key for math problem generation | `AIzaSyC...` |
| `SECRET_KEY` | Secret key for application security | Auto-generated |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `https://myapp.com,https://www.myapp.com` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENT_USERS` | 100 | Maximum concurrent WebSocket connections |
| `RATE_LIMIT_PER_MINUTE` | 60 | API rate limit per IP per minute |
| `DATABASE_POOL_SIZE` | 20 | PostgreSQL connection pool size |
| `REDIS_POOL_SIZE` | 20 | Redis connection pool size |
| `LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Add-ons Configuration

#### PostgreSQL
- **Plan**: `heroku-postgresql:mini` (free tier)
- **Automatic**: Database URL is automatically set as `DATABASE_URL`

#### Redis
- **Plan**: `heroku-redis:mini` (free tier)
- **Automatic**: Redis URL is automatically set as `REDIS_URL`

## Post-Deployment

### Verify Deployment

1. **Check app status**:
   ```bash
   heroku ps
   ```

2. **View logs**:
   ```bash
   heroku logs --tail
   ```

3. **Test the application**:
   ```bash
   heroku open
   ```

### Monitoring

#### View Application Logs
```bash
# Real-time logs
heroku logs --tail

# Recent logs
heroku logs --num 100

# Filter by component
heroku logs --source app
```

#### Check Resource Usage
```bash
# View dyno status
heroku ps

# View add-on status
heroku addons

# View configuration
heroku config
```

#### Database Management
```bash
# Connect to PostgreSQL
heroku pg:psql

# View database info
heroku pg:info

# Run migrations
heroku run "cd backend && alembic upgrade head"

# Reset database (CAUTION: This deletes all data)
heroku pg:reset DATABASE_URL --confirm your-app-name
```

#### Redis Management
```bash
# View Redis info
heroku redis:info

# Connect to Redis CLI
heroku redis:cli

# View Redis metrics
heroku redis:stats
```

## Scaling

### Horizontal Scaling
```bash
# Scale web dynos
heroku ps:scale web=2

# Scale down
heroku ps:scale web=1
```

### Vertical Scaling
```bash
# Upgrade to standard dyno
heroku ps:type web=standard-1x

# Upgrade database
heroku addons:upgrade heroku-postgresql:basic

# Upgrade Redis
heroku addons:upgrade heroku-redis:premium-0
```

## Troubleshooting

### Common Issues

#### 1. Application Crashes on Startup
```bash
# Check logs for errors
heroku logs --tail

# Common causes:
# - Missing environment variables
# - Database connection issues
# - Port binding problems
```

#### 2. WebSocket Connection Issues
- Ensure your frontend is connecting to the correct Heroku app URL
- Check CORS configuration
- Verify WebSocket support is enabled

#### 3. Database Connection Errors
```bash
# Check database status
heroku pg:info

# Run migrations
heroku run "cd backend && alembic upgrade head"

# Reset database if needed
heroku pg:reset DATABASE_URL --confirm your-app-name
```

#### 4. Redis Connection Issues
```bash
# Check Redis status
heroku redis:info

# Restart Redis
heroku addons:destroy heroku-redis
heroku addons:create heroku-redis:mini
```

### Performance Optimization

#### 1. Enable HTTP/2
Heroku automatically enables HTTP/2 for HTTPS connections.

#### 2. Use CDN for Static Assets
Consider using a CDN for frontend assets to reduce load times.

#### 3. Database Optimization
- Add database indexes for frequently queried fields
- Use connection pooling (already configured)
- Monitor slow queries

#### 4. Redis Optimization
- Use Redis for session storage and caching
- Monitor memory usage
- Implement cache expiration policies

## Security Considerations

### 1. Environment Variables
- Never commit sensitive data to Git
- Use Heroku config vars for all secrets
- Rotate API keys regularly

### 2. HTTPS
- Heroku automatically provides HTTPS
- Ensure your frontend uses HTTPS URLs

### 3. CORS Configuration
- Set specific origins instead of "*" in production
- Update CORS_ORIGINS when adding new domains

### 4. Rate Limiting
- Monitor rate limit effectiveness
- Adjust limits based on usage patterns

## Maintenance

### Regular Tasks

#### 1. Update Dependencies
```bash
# Update Python packages
pip install --upgrade -r requirements.txt

# Update Node.js packages
cd frontend && npm update
```

#### 2. Monitor Logs
```bash
# Set up log monitoring
heroku logs --tail | grep ERROR
```

#### 3. Database Maintenance
```bash
# Backup database
heroku pg:backups:capture

# View backups
heroku pg:backups
```

#### 4. Performance Monitoring
- Monitor response times
- Check error rates
- Monitor resource usage

## Support

For issues with:
- **Heroku Platform**: [Heroku Support](https://help.heroku.com/)
- **Application Code**: Check the GitHub repository issues
- **API Keys**: Refer to respective service documentation

## Cost Optimization

### Free Tier Limits
- **Dynos**: 550-1000 free hours per month
- **PostgreSQL**: 10,000 rows, 1GB storage
- **Redis**: 25MB memory

### Upgrade Recommendations
- **Standard Dynos**: For better performance and no sleep mode
- **Hobby PostgreSQL**: For more storage and connections
- **Premium Redis**: For larger memory and better performance