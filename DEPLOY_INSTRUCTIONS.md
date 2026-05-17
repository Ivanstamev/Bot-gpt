
# NEXUS BOT PRO — FIXED VERSION

## Какво е поправено
- По-бързо зареждане
- Поправен черен Plotly chart
- Намален data load
- Demo balance minimum = 1
- Default demo balance = 20
- Backtest stability fixes
- NaN protection
- Better Streamlit stability

## Как да качиш в GitHub

1. Създай нов repository
2. Upload ZIP contents
3. Commit files
4. Свържи Render

## Render настройки

Build Command:
pip install -r requirements.txt

Start Command:
streamlit run app.py --server.port $PORT --server.address 0.0.0.0

Python Version:
3.11

## Препоръчително
- Upgrade към FastAPI + React по-късно
- Добавяне на PostgreSQL
- Async exchange layer
