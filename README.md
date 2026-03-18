# Felix Farm Stars

Monorepo проекта:

- `api/` — общий backend API
- `bot/` — Telegram bot для админки
- `web/` — Telegram Mini App для пользователей

## Локальный запуск

### api
```bash
cd api
source venv/bin/activate
python3 -m uvicorn main:app --reload --port 8000
```

### bot
```bash
cd bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 bot.py
```

### web
```bash
cd web
npm install
npm run dev
```
```bash
cd web
ngrok http 3000
```


## Локальный билд
```bash
cd web
npm run build
npm run start
```