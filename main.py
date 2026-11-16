"""
NSE Breakout Screener - Application Entry Point.
Starts FastAPI web service and background scanner via modern lifespan.
"""

from api.dashboard import app
from engine.instance import engine, repo, bot, dedup, scanner

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print(" 🚀 NSE BREAKOUT QUANT SCREENER")
    print(" 🌐 Open Web Dashboard in your browser: http://127.0.0.1:8000")
    print("="*60 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
