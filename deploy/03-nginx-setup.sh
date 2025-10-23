#!/bin/bash

# Nginx Configuration Script for Local Life Assistant
# Run this script after deploy-app.sh

set -e

echo "🌐 Configuring Nginx..."

# Get domain name from command line argument or environment variable
DOMAIN_NAME=${1:-$DOMAIN_NAME}

if [ -z "$DOMAIN_NAME" ]; then
    # Fallback to interactive input for manual usage
    read -p "Enter your domain name (e.g., myapp.com): " DOMAIN_NAME

    if [ -z "$DOMAIN_NAME" ]; then
        echo "❌ Domain name is required!"
        exit 1
    fi
fi

# Create Nginx configuration (force overwrite)
echo "📝 Creating Nginx configuration for $DOMAIN_NAME..."
# Remove existing configuration if it exists
sudo rm -f /etc/nginx/sites-available/locallifeassistant
sudo rm -f /etc/nginx/sites-enabled/locallifeassistant

# Copy new configuration
sudo cp /opt/locallifeassistant/deploy/nginx.conf /etc/nginx/sites-available/locallifeassistant

# Replace placeholder domain in configuration
sudo sed -i "s/your-domain.com/$DOMAIN_NAME/g" /etc/nginx/sites-available/locallifeassistant

# Enable the site
echo "🔗 Enabling Nginx site..."
sudo ln -sf /etc/nginx/sites-available/locallifeassistant /etc/nginx/sites-enabled/

# Remove default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
echo "🧪 Testing Nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration is valid!"
    
    # Reload Nginx
    echo "🔄 Reloading Nginx..."
    sudo systemctl reload nginx
    
    echo "✅ Nginx configured successfully!"
    echo "📝 Next steps:"
    echo "   1. Update your DNS records to point to this server's IP"
    echo "   2. Run setup-ssl.sh to configure SSL certificates"
    echo "   3. Start the backend service: sudo systemctl start locallifeassistant-backend"
else
    echo "❌ Nginx configuration test failed!"
    exit 1
fi
