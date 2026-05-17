# NEXUS BOT PRO

AI-powered crypto trading dashboard and backtesting platform.

## Features
- Trading dashboard
- Backtesting
- AI signal engine
- Risk management
- Plotly charts
- Streamlit UI
- Exchange integration

## Deployment

### Install
```bash
pip install -r requirements.txt
```

### Run locally
```bash
streamlit run app.py
```

### Render Start Command
```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## Structure
- app.py -> UI
- engine.py -> trading engine
- logic.py -> strategy logic
- risk_management.py -> risk controls
