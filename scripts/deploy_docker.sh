#!/bin/bash
# =====================================================================
# Google Cloud VM Docker Deployment Script
# =====================================================================
set -e

echo "🐳 [1/3] Installing Docker & Docker Compose..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-compose

# Add current user to docker group
sudo usermod -aG docker $USER

echo "🚀 [2/3] Building and starting Docker container..."
sudo docker-compose up -d --build

echo ""
echo "====================================================================="
echo "✅ DOCKER CONTAINER RUNNING!"
echo "====================================================================="
echo "📜 View live logs: sudo docker-compose logs -f"
echo "🔄 Restart:       sudo docker-compose restart"
echo "⏹️ Stop:          sudo docker-compose down"
echo "🌐 Web Dashboard: http://<YOUR_VM_EXTERNAL_IP>:8000"
echo "====================================================================="
