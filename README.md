# Felix Farm Stars

Monorepo проекта:

- `api/` — общий backend API
- `bot/` — Telegram bot для админки
- `web/` — Telegram Mini App для пользователей

## Локальный запуск

### api
```bash
source api/venv/bin/activate
python3 -m uvicorn api.main:app --reload --port 8000
```

### bot
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m bot.bot
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
```