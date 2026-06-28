# MeTiger Inc. Website Deployment Guide

This guide will walk you through deploying the MeTiger Inc. website on Ubuntu using Nginx and Gunicorn.

## Prerequisites

- Ubuntu 20.04+ server
- Python 3.8+
- Nginx
- Domain name (optional, but recommended)

## Step 1: Update System and Install Dependencies

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3 python3-pip python3-venv nginx -y

# Install additional tools
sudo apt install git curl -y
```

## Step 2: Set Up Project Directory

```bash
# Create project directory
sudo mkdir -p /var/www/metiger-site
sudo chown $USER:$USER /var/www/metiger-site

# Navigate to project directory
cd /var/www/metiger-site

# Copy your project files here (or clone from git)
# Make sure all your files are in this directory:
# - app.py
# - requirements.txt
# - templates/ (directory with all HTML files)
# - static/ (directory for static files, if any)
```

## Step 3: Set Up Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Test the application
python app.py
```

## Step 4: Configure Gunicorn

Create a Gunicorn configuration file:

```bash
# Create gunicorn config file
nano gunicorn.conf.py
```

Add the following content to `gunicorn.conf.py`:

```python
bind = "127.0.0.1:8000"
workers = 3
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True
```

## Step 5: Create Systemd Service

Create a systemd service file for Gunicorn:

```bash
sudo nano /etc/systemd/system/metiger-site.service
```

Add the following content:

```ini
[Unit]
Description=MeTiger Inc. Website
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/metiger-site
Environment="PATH=/var/www/metiger-site/venv/bin"
ExecStart=/var/www/metiger-site/venv/bin/gunicorn --config gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

## Step 6: Configure Nginx

Create Nginx configuration file:

```bash
sudo nano /etc/nginx/sites-available/metiger-site
```

Add the following content:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;  # Replace with your domain

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Optional: Serve static files directly with Nginx
    location /static {
        alias /var/www/metiger-site/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
}
```

Enable the site:

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/metiger-site /etc/nginx/sites-enabled/

# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

## Step 7: Set Up SSL with Let's Encrypt (Optional but Recommended)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Test automatic renewal
sudo certbot renew --dry-run
```

## Step 8: Start Services

```bash
# Set proper permissions
sudo chown -R www-data:www-data /var/www/metiger-site
sudo chmod -R 755 /var/www/metiger-site

# Start and enable services
sudo systemctl start metiger-site
sudo systemctl enable metiger-site
sudo systemctl start nginx
sudo systemctl enable nginx

# Check service status
sudo systemctl status metiger-site
sudo systemctl status nginx
```

## Step 9: Configure Firewall

```bash
# Install and configure UFW
sudo apt install ufw -y

# Allow SSH, HTTP, and HTTPS
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'

# Enable firewall
sudo ufw enable
```

## Step 10: Monitor and Maintain

### Check Logs

```bash
# Application logs
sudo journalctl -u metiger-site -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Restart Services

```bash
# Restart application
sudo systemctl restart metiger-site

# Restart Nginx
sudo systemctl restart nginx
```

### Update Application

```bash
# Navigate to project directory
cd /var/www/metiger-site

# Pull latest changes (if using git)
# git pull origin main

# Activate virtual environment
source venv/bin/activate

# Install new dependencies (if any)
pip install -r requirements.txt

# Restart application
sudo systemctl restart metiger-site
```

## Environment Variables

For production, set these environment variables:

```bash
# Create environment file
sudo nano /var/www/metiger-site/.env
```

Add:

```bash
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
```

Update the systemd service to load environment variables:

```bash
sudo nano /etc/systemd/system/metiger-site.service
```

Add this line under `[Service]`:

```ini
EnvironmentFile=/var/www/metiger-site/.env
```

## Performance Optimization

### Nginx Caching

Add to your Nginx configuration:

```nginx
# Add to server block
location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### Gunicorn Optimization

Adjust worker count based on CPU cores:

```bash
# Check CPU cores
nproc

# Update gunicorn.conf.py
workers = 2 * CPU_CORES + 1
```

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure www-data owns the files
   ```bash
   sudo chown -R www-data:www-data /var/www/metiger-site
   ```

2. **Port Already in Use**: Check what's using port 8000
   ```bash
   sudo netstat -tlnp | grep :8000
   ```

3. **Nginx 502 Bad Gateway**: Check if Gunicorn is running
   ```bash
   sudo systemctl status metiger-site
   ```

### Health Check

Create a simple health check endpoint in your Flask app:

```python
@app.route('/health')
def health():
    return {'status': 'healthy'}, 200
```

## Security Considerations

1. **Keep system updated**: `sudo apt update && sudo apt upgrade`
2. **Use strong passwords**: For SSH and database access
3. **Configure fail2ban**: For SSH protection
4. **Regular backups**: Set up automated backups
5. **Monitor logs**: Watch for suspicious activity

## Backup Strategy

```bash
# Create backup script
sudo nano /usr/local/bin/backup-metiger.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/metiger-site"
mkdir -p $BACKUP_DIR

# Backup application files
tar -czf $BACKUP_DIR/metiger-site-$DATE.tar.gz /var/www/metiger-site

# Keep only last 7 days of backups
find $BACKUP_DIR -name "metiger-site-*.tar.gz" -mtime +7 -delete
```

Make it executable:

```bash
sudo chmod +x /usr/local/bin/backup-metiger.sh

# Add to crontab for daily backups
sudo crontab -e
# Add: 0 2 * * * /usr/local/bin/backup-metiger.sh
```

## Monitoring

Consider setting up monitoring with tools like:
- **Prometheus + Grafana**: For metrics
- **ELK Stack**: For log analysis
- **Uptime monitoring**: Services like Pingdom or UptimeRobot

Your MeTiger Inc. website should now be fully deployed and accessible!





