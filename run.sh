#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "===================================================="
echo "    AI Stock Assistant Setup & Execution Script"
echo "===================================================="

# 1. Detect / Setup Virtual Environment
if [ -d "venv" ]; then
    echo "✔ Virtual environment 'venv' detected. Activating..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "✔ Virtual environment '.venv' detected. Activating..."
    source .venv/bin/activate
else
    echo "❓ No virtual environment detected."
    read -p "Would you like to create a new virtual environment? (y/n): " create_env
    if [[ "$create_env" =~ ^[Yy]$ ]]; then
        echo "Creating virtual environment 'venv'..."
        python3 -m venv venv
        source venv/bin/activate
    else
        echo "⚠ Proceeding with global python environment..."
    fi
fi

# 2. Upgrade pip and install dependencies
echo "⬇ Upgrading pip and installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Check for Environment Keys
if [ ! -f ".env" ]; then
    echo "❓ No .env configuration file detected."
    read -p "Would you like to configure your GROQ_API_KEY now? (y/n): " config_env
    if [[ "$config_env" =~ ^[Yy]$ ]]; then
        read -sp "Enter your GROQ_API_KEY: " groq_key
        echo ""
        echo "GROQ_API_KEY=$groq_key" > .env
        echo "✔ .env file created successfully with GROQ_API_KEY."
    else
        echo "⚠ Proceeding without Groq API key (AI summaries will fall back to local rule-based text)."
    fi
else
    echo "✔ .env configuration file detected."
fi

# 4. Refresh Cache databases
echo "📡 Refreshing stock databases (NSE/BSE and F&O lot sizes)..."
python scripts/refresh_stock_master.py
python scripts/refresh_fno_master.py
echo "✔ Cache database refresh complete."

# 5. Launch Streamlit Web UI
echo "🚀 Launching AI Stock Assistant dashboard..."
streamlit run app.py
