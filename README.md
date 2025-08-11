git clone <repo> app && cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# заполни config/settings(.env) и т.д.
python main.py  # один раз интерактивно, чтобы залогиниться и создать *.session
Ctrl+C


# /etc/systemd/system/telethon-bot.service
[Unit]
Description=Telethon bot service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
Group=YOUR_USER
WorkingDirectory=/opt/app  # путь к проекту
Environment=PYTHONUNBUFFERED=1
Environment=LOG_LEVEL=INFO
# Если используешь .env:
# EnvironmentFile=/opt/app/.env
ExecStart=/opt/app/.venv/bin/python /opt/app/main.py
Restart=on-failure
RestartSec=5
# Лимиты на перезапуски, чтобы не циклилось
StartLimitInterval=60
StartLimitBurst=5

# Опционально: отдельный лог-файл
# StandardOutput=append:/opt/app/logs/service.log
# StandardError=append:/opt/app/logs/service.err.log

[Install]
WantedBy=multi-user.target



sudo systemctl daemon-reload
sudo systemctl enable --now telethon-bot.service
sudo systemctl status telethon-bot.service
# лог смотреть:
journalctl -u telethon-bot.service -f


cd /opt/app
git pull
. .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart telethon-bot.service
