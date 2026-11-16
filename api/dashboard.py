"""
FastAPI Dashboard Application.
Serves a responsive single-page quantitative dashboard (Tailwind CSS + Alpine.js)
and mounts all REST API routes.
"""

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config.settings import settings
from storage.database import init_db
from api.routes import router
from api.auth import verify_token
from engine.instance import engine
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on web service startup
    logger.info("Initializing database and starting engine warm-up...")
    await init_db()
    # Warm up engine (loads precomputed levels, universe, and triggers initial scan)
    await engine.warm_up()
    engine.start_schedules()
    yield
    await engine.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Enable CORS for developer flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NSE Breakout Quant Screener | Live Institutional Dashboard</title>
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Alpine.js -->
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#f0fdf4',
              500: '#22c55e',
              600: '#16a34a',
              700: '#15803d',
            },
            dark: {
              900: '#0b0f19',
              800: '#111827',
              700: '#1f2937',
              600: '#374151'
            }
          }
        }
      }
    }
  </script>
  <style>
    [x-cloak] { display: none !important; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #111827; }
    ::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }
  </style>
</head>
<body class="bg-dark-900 text-slate-100 min-h-screen font-sans antialiased" x-data="dashboardApp()" x-init="init()">

  <!-- Top Navigation Header -->
  <header class="border-b border-dark-700 bg-dark-800/80 backdrop-blur sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <div class="h-9 w-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-black">
        ⚡
      </div>
      <div>
        <h1 class="font-bold text-lg leading-tight tracking-wide flex items-center gap-2">
          NSE BREAKOUT QUANT
          <span class="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium">LIVE</span>
        </h1>
        <p class="text-xs text-slate-400">Institutional Real-Time F&O Screener (ATH | 52W | DC50)</p>
      </div>
    </div>

    <!-- Live Status Indicators -->
    <div class="flex items-center space-x-6 text-sm">
      <div class="flex items-center space-x-2">
        <span class="h-2.5 w-2.5 rounded-full" :class="health.market_open ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'"></span>
        <span class="text-xs text-slate-300" x-text="health.market_open ? 'MARKET OPEN (NSE)' : 'MARKET CLOSED'"></span>
      </div>

      <div class="hidden sm:flex items-center space-x-2 text-xs text-slate-400">
        <span>Latency:</span>
        <span class="text-slate-200 font-mono font-medium" x-text="(health.last_scan_duration_ms || 0).toFixed(0) + 'ms'"></span>
      </div>

      <!-- Token / Auth Badge -->
      <div class="flex items-center space-x-2">
        <span class="text-xs px-2 py-1 bg-dark-700 rounded text-slate-300 font-mono" x-text="'Symbols: ' + (health.universe_size || tableData.length || 0)"></span>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto p-6 space-y-6">

    <!-- Metrics Cards Banner -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div 
        @click="activeTab = 'breakouts'" 
        role="button"
        title="Click to view Today's Confirmed Breakouts"
        :class="activeTab === 'breakouts' ? 'ring-1 ring-emerald-500/60 border-emerald-500/50 bg-dark-700/40' : 'border-dark-700 bg-dark-800'"
        class="hover:bg-dark-700/60 border hover:border-emerald-500/50 rounded-xl p-4 flex items-center justify-between cursor-pointer transition transform active:scale-95 group">
        <div>
          <p class="text-xs text-slate-400 uppercase tracking-wider font-semibold group-hover:text-emerald-400 transition">Today's Breakouts</p>
          <h3 class="text-2xl font-bold text-emerald-400 mt-1" x-text="signals.breakouts ? signals.breakouts.length : 0">0</h3>
          <p class="text-xs text-slate-500 mt-1">Confirmed alert triggers</p>
        </div>
        <div class="p-3 bg-emerald-500/10 group-hover:bg-emerald-500/20 rounded-lg text-emerald-400 text-xl font-bold transition">🚀</div>
      </div>

      <div 
        @click="activeTab = 'near'" 
        role="button"
        title="Click to view Near-Breakout Watchlist (<1%)"
        :class="activeTab === 'near' ? 'ring-1 ring-amber-500/60 border-amber-500/50 bg-dark-700/40' : 'border-dark-700 bg-dark-800'"
        class="hover:bg-dark-700/60 border hover:border-amber-500/50 rounded-xl p-4 flex items-center justify-between cursor-pointer transition transform active:scale-95 group">
        <div>
          <p class="text-xs text-slate-400 uppercase tracking-wider font-semibold group-hover:text-amber-400 transition">Near Breakout (&lt;1%)</p>
          <h3 class="text-2xl font-bold text-amber-400 mt-1" x-text="signals.near_breakouts ? signals.near_breakouts.length : 0">0</h3>
          <p class="text-xs text-slate-500 mt-1">High-probability watch</p>
        </div>
        <div class="p-3 bg-amber-500/10 group-hover:bg-amber-500/20 rounded-lg text-amber-400 text-xl font-bold transition">🎯</div>
      </div>

      <div 
        @click="activeTab = 'all'" 
        role="button"
        title="Click to view Full F&O Universe"
        :class="activeTab === 'all' ? 'ring-1 ring-cyan-500/60 border-cyan-500/50 bg-dark-700/40' : 'border-dark-700 bg-dark-800'"
        class="hover:bg-dark-700/60 border hover:border-cyan-500/50 rounded-xl p-4 flex items-center justify-between cursor-pointer transition transform active:scale-95 group">
        <div>
          <p class="text-xs text-slate-400 uppercase tracking-wider font-semibold group-hover:text-cyan-400 transition">Tracked F&O Stocks</p>
          <h3 class="text-2xl font-bold text-cyan-400 mt-1" x-text="health.universe_size || tableData.length || 0">0</h3>
          <p class="text-xs text-slate-500 mt-1">Dynamic NSE Universe</p>
        </div>
        <div class="p-3 bg-cyan-500/10 group-hover:bg-cyan-500/20 rounded-lg text-cyan-400 text-xl font-bold transition">📊</div>
      </div>

      <div class="bg-dark-800 border border-dark-700 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p class="text-xs text-slate-400 uppercase tracking-wider font-semibold">Engine State</p>
          <h3 class="text-xl font-bold mt-1" :class="health.is_paused ? 'text-amber-400' : 'text-emerald-400'" x-text="health.is_paused ? 'PAUSED' : health.status || 'READY'"></h3>
          <p class="text-xs text-slate-500 mt-1" x-text="'Last: ' + formatTime(health.last_scan_utc)"></p>
        </div>
        <button 
          @click="openSettingsModal()" 
          title="Engine Settings & Controls"
          class="p-3 bg-slate-700/50 hover:bg-slate-700 text-slate-300 hover:text-emerald-400 rounded-lg text-xl font-bold transition transform active:scale-95 cursor-pointer border border-transparent hover:border-slate-600 focus:outline-none">
          ⚙️
        </button>
      </div>
    </div>

    <!-- Tab Navigation & Action Controls -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-dark-700 pb-3">
      <div class="flex space-x-2">
        <button 
          @click="activeTab = 'breakouts'" 
          :class="activeTab === 'breakouts' ? 'bg-dark-700 text-emerald-400 border-emerald-500/40' : 'text-slate-400 hover:text-slate-200'"
          class="px-3.5 py-1.5 rounded-lg text-sm font-medium border border-transparent transition">
          🚀 Live Breakouts
        </button>

        <button 
          @click="activeTab = 'near'" 
          :class="activeTab === 'near' ? 'bg-dark-700 text-amber-400 border-amber-500/40' : 'text-slate-400 hover:text-slate-200'"
          class="px-3.5 py-1.5 rounded-lg text-sm font-medium border border-transparent transition">
          🎯 Near-Breakout Watchlist
        </button>

        <button 
          @click="activeTab = 'all'" 
          :class="activeTab === 'all' ? 'bg-dark-700 text-cyan-400 border-cyan-500/40' : 'text-slate-400 hover:text-slate-200'"
          class="px-3.5 py-1.5 rounded-lg text-sm font-medium border border-transparent transition">
          📑 All F&O Universe
        </button>

        <button 
          @click="activeTab = 'alerts'" 
          :class="activeTab === 'alerts' ? 'bg-dark-700 text-indigo-400 border-indigo-500/40' : 'text-slate-400 hover:text-slate-200'"
          class="px-3.5 py-1.5 rounded-lg text-sm font-medium border border-transparent transition">
          💬 Alert Log
        </button>
      </div>

      <!-- Screener Dropdown, Search & Controls -->
      <div class="flex flex-wrap items-center gap-2.5">
        <!-- Screener Dropdown Selector -->
        <div class="relative">
          <select 
            x-model="selectedScreener"
            class="bg-dark-800 border border-dark-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/50 cursor-pointer font-medium">
            <option value="">⚡ All Screeners (12 Conditions)</option>
            <optgroup label="ATH & ATL Screeners">
              <option value="ATH">🚀 ATH Breakout (BUY)</option>
              <option value="ATL">🔻 ATL Breakdown (SELL)</option>
            </optgroup>
            <optgroup label="52-Week Screeners">
              <option value="52W_HIGH">📈 52-Week High Breakout (BUY)</option>
              <option value="52W_LOW">📉 52-Week Low Breakdown (SELL)</option>
            </optgroup>
            <optgroup label="Donchian Channel Screeners">
              <option value="DC50_HIGH">🎯 Donchian 50 High (BUY)</option>
              <option value="DC50_LOW">🔻 Donchian 50 Low (SELL)</option>
              <option value="DC20_HIGH">🎯 Donchian 20 High (BUY)</option>
              <option value="DC20_LOW">🔻 Donchian 20 Low (SELL)</option>
            </optgroup>
            <optgroup label="Supertrend Daily (1D)">
              <option value="ST_DAILY_10_1_BUY">🟢 ST Daily (10,1) BUY</option>
              <option value="ST_DAILY_10_1_SELL">🔴 ST Daily (10,1) SELL</option>
              <option value="ST_DAILY_10_2_BUY">🟢 ST Daily (10,2) BUY</option>
              <option value="ST_DAILY_10_2_SELL">🔴 ST Daily (10,2) SELL</option>
            </optgroup>
          </select>
        </div>

        <!-- Search Input -->
        <input 
          type="text" 
          x-model="searchQuery" 
          placeholder="Filter by symbol or sector..." 
          class="bg-dark-800 border border-dark-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/50 w-44">
        
        <!-- Alert Subscriptions Manager Button -->
        <button 
          @click="openSubscriptionsModal()" 
          title="Configure which alerts to subscribe to"
          class="bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-indigo-300 rounded-lg px-3 py-1.5 text-xs flex items-center gap-1.5 transition font-semibold">
          🔔 Subscriptions (<span x-text="subscribedCount">16</span>)
        </button>

        <!-- Force Live Scan Button -->
        <button 
          @click="forceScanAndRefresh()" 
          title="Trigger immediate live scan and refresh"
          class="bg-dark-800 hover:bg-dark-700 border border-dark-700 rounded-lg px-3 py-1.5 text-slate-300 text-xs flex items-center gap-1.5 transition">
          <span :class="isLoading ? 'animate-spin' : ''">🔄</span> Force Live Scan
        </button>
      </div>
    </div>

    <!-- TAB 1: LIVE BREAKOUTS -->
    <div x-show="activeTab === 'breakouts'" x-cloak>
      <div class="bg-dark-800 border border-dark-700 rounded-xl overflow-hidden">
        <div class="px-5 py-3 border-b border-dark-700 flex items-center justify-between">
          <div>
            <h2 class="text-sm font-semibold text-slate-200">Latest Live Breakouts</h2>
            <span class="text-xs text-slate-400">Showing newest alerts first • Strict zero look-ahead</span>
          </div>
          <span class="text-xs font-mono text-emerald-400 font-semibold" x-text="filteredBreakouts.length + ' latest alerts'"></span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-dark-900/60 text-slate-400 border-b border-dark-700 uppercase tracking-wider font-semibold">
              <tr>
                <th class="px-4 py-3">Symbol</th>
                <th class="px-4 py-3">LTP</th>
                <th class="px-4 py-3">% Change</th>
                <th class="px-4 py-3">Level Broken</th>
                <th class="px-4 py-3">% Above</th>
                <th class="px-4 py-3">Triggers</th>
                <th class="px-4 py-3">RVOL</th>
                <th class="px-4 py-3">ATR(20)</th>
                <th class="px-4 py-3">Sector</th>
                <th class="px-4 py-3">Time (IST)</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-dark-700">
              <template x-for="item in filteredBreakouts.slice(0, 50)" :key="item.symbol + item.time">
                <tr class="hover:bg-dark-700/40 transition font-mono">
                  <td class="px-4 py-3 font-bold text-white flex items-center gap-2">
                    <span class="text-emerald-400 font-sans">⚡</span>
                    <span x-text="item.symbol"></span>
                  </td>
                  <td class="px-4 py-3 font-semibold text-emerald-400" x-text="'₹' + item.ltp.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-3" :class="item.pct_change >= 0 ? 'text-emerald-400' : 'text-rose-400'" x-text="(item.pct_change > 0 ? '+' : '') + item.pct_change.toFixed(2) + '%'"></td>
                  <td class="px-4 py-3 text-slate-300" x-text="'₹' + item.level_broken.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-3 text-emerald-400 font-bold" x-text="'+' + item.pct_above.toFixed(2) + '%'"></td>
                  <td class="px-4 py-3">
                    <span class="px-2 py-0.5 rounded text-[10px] font-sans font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" x-text="item.trigger_types"></span>
                  </td>
                  <td class="px-4 py-3 font-semibold" :class="item.rvol >= 1.5 ? 'text-amber-400' : 'text-slate-300'" x-text="item.rvol.toFixed(1) + 'x'"></td>
                  <td class="px-4 py-3 text-slate-400" x-text="'₹' + item.atr_20.toFixed(2)"></td>
                  <td class="px-4 py-3 text-slate-400 font-sans" x-text="item.sector"></td>
                  <td class="px-4 py-3 text-slate-400 font-sans" x-text="formatTime(item.time)"></td>
                </tr>
              </template>
              <tr x-show="!filteredBreakouts || filteredBreakouts.length === 0">
                <td colspan="10" class="px-4 py-8 text-center text-slate-400 font-sans">
                  No breakouts triggered yet today.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 2: NEAR-BREAKOUT WATCHLIST -->
    <div x-show="activeTab === 'near'" x-cloak>
      <div class="bg-dark-800 border border-dark-700 rounded-xl overflow-hidden">
        <div class="px-5 py-3 border-b border-dark-700 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-200">Near-Breakout Watchlist (&lt;1.0% from Level)</h2>
          <span class="text-xs text-amber-400 font-medium">Primed Setups</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-dark-900/60 text-slate-400 border-b border-dark-700 uppercase tracking-wider font-semibold">
              <tr>
                <th class="px-4 py-3">Symbol</th>
                <th class="px-4 py-3">Current Price</th>
                <th class="px-4 py-3">Target Trigger</th>
                <th class="px-4 py-3">Breakout Level</th>
                <th class="px-4 py-3">Distance</th>
                <th class="px-4 py-3">Sector</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-dark-700">
              <template x-for="item in filteredNearBreakouts" :key="item.symbol + item.target_type">
                <tr class="hover:bg-dark-700/40 transition font-mono">
                  <td class="px-4 py-3 font-bold text-white flex items-center gap-2">
                    <span class="text-amber-400 font-sans">🎯</span>
                    <span x-text="item.symbol"></span>
                  </td>
                  <td class="px-4 py-3 font-semibold text-slate-200" x-text="'₹' + item.current_price.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-3">
                    <span class="px-2 py-0.5 rounded text-[10px] font-sans font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30" x-text="item.target_type"></span>
                  </td>
                  <td class="px-4 py-3 text-slate-300" x-text="'₹' + item.target_level.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-3 text-amber-400 font-bold" x-text="'-' + item.distance_pct.toFixed(2) + '%'"></td>
                  <td class="px-4 py-3 text-slate-400 font-sans" x-text="item.sector"></td>
                </tr>
              </template>
              <tr x-show="!filteredNearBreakouts || filteredNearBreakouts.length === 0">
                <td colspan="6" class="px-4 py-8 text-center text-slate-400 font-sans">
                  No stocks currently within 1.0% of breakout levels.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 3: ALL F&O UNIVERSE TABLE -->
    <div x-show="activeTab === 'all'" x-cloak>
      <div class="bg-dark-800 border border-dark-700 rounded-xl overflow-hidden">
        <div class="px-5 py-3 border-b border-dark-700 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-200">NSE F&O Full Universe Snapshot</h2>
          <span class="text-xs text-slate-400 font-mono" x-text="'Total: ' + filteredTableData.length + ' stocks'"></span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-dark-900/60 text-slate-400 border-b border-dark-700 uppercase tracking-wider font-semibold">
              <tr>
                <th class="px-4 py-3">Symbol</th>
                <th class="px-4 py-3">LTP</th>
                <th class="px-4 py-3">% Change</th>
                <th class="px-4 py-3">ATH High</th>
                <th class="px-4 py-3">Dist ATH</th>
                <th class="px-4 py-3">52W High</th>
                <th class="px-4 py-3">Dist 52W</th>
                <th class="px-4 py-3">DC50 High</th>
                <th class="px-4 py-3">Dist DC50</th>
                <th class="px-4 py-3">RVOL</th>
                <th class="px-4 py-3">ST Daily</th>
                <th class="px-4 py-3">ST 15m</th>
                <th class="px-4 py-3">Status</th>
                <th class="px-4 py-3">Feed Source</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-dark-700">
              <template x-for="item in filteredTableData" :key="item.symbol">
                <tr class="hover:bg-dark-700/40 transition font-mono">
                  <td class="px-4 py-2.5 font-bold text-white" x-text="item.symbol"></td>
                  <td class="px-4 py-2.5 font-semibold text-slate-200" x-text="'₹' + item.ltp.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-2.5" :class="item.p_change >= 0 ? 'text-emerald-400' : 'text-rose-400'" x-text="(item.p_change > 0 ? '+' : '') + item.p_change.toFixed(2) + '%'"></td>
                  <td class="px-4 py-2.5 text-slate-300" x-text="'₹' + item.ath_high.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-2.5" :class="item.dist_ath >= 0 ? 'text-emerald-400 font-bold' : 'text-slate-400'" x-text="(item.dist_ath > 0 ? '+' : '') + item.dist_ath.toFixed(2) + '%'"></td>
                  <td class="px-4 py-2.5 text-slate-300" x-text="'₹' + item.high_52w.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-2.5" :class="item.dist_52w >= 0 ? 'text-emerald-400 font-bold' : 'text-slate-400'" x-text="(item.dist_52w > 0 ? '+' : '') + item.dist_52w.toFixed(2) + '%'"></td>
                  <td class="px-4 py-2.5 text-slate-300" x-text="'₹' + item.donchian_50.toLocaleString('en-IN', {minimumFractionDigits: 2})"></td>
                  <td class="px-4 py-2.5" :class="item.dist_dc50 >= 0 ? 'text-emerald-400 font-bold' : 'text-slate-400'" x-text="(item.dist_dc50 > 0 ? '+' : '') + item.dist_dc50.toFixed(2) + '%'"></td>
                  <td class="px-4 py-2.5 font-semibold" :class="item.rvol >= 1.5 ? 'text-amber-400' : 'text-slate-400'" x-text="item.rvol.toFixed(1) + 'x'"></td>
                  <td class="px-4 py-2.5">
                    <span class="inline-flex gap-1 items-center font-sans text-[10px]">
                      <span class="px-1 py-0.5 rounded" :class="item.st_daily_10_1 === 1 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'" title="ST Daily (10,1)">10,1</span>
                      <span class="px-1 py-0.5 rounded" :class="item.st_daily_10_2 === 1 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'" title="ST Daily (10,2)">10,2</span>
                    </span>
                  </td>
                  <td class="px-4 py-2.5">
                    <span class="inline-flex gap-1 items-center font-sans text-[10px]">
                      <span class="px-1 py-0.5 rounded" :class="item.st_15m_10_1 === 1 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'" title="ST 15m (10,1)">10,1</span>
                      <span class="px-1 py-0.5 rounded" :class="item.st_15m_10_2 === 1 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'" title="ST 15m (10,2)">10,2</span>
                    </span>
                  </td>
                  <td class="px-4 py-2.5">
                    <span 
                      class="px-2 py-0.5 rounded text-[10px] font-sans font-bold"
                      :class="{
                        'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30': item.status.includes('BREAKOUT'),
                        'bg-amber-500/20 text-amber-400 border border-amber-500/30': item.status === 'NEAR BREAKOUT',
                        'text-slate-500': item.status === 'NORMAL'
                      }"
                      x-text="item.status">
                    </span>
                  </td>
                  <td class="px-4 py-2.5">
                    <span 
                      class="px-2 py-0.5 rounded text-[10px] font-sans font-semibold"
                      :class="{
                        'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30': item.source.includes('YAHOO') || item.source.includes('NSE'),
                        'bg-slate-700 text-slate-400': item.source === 'CACHE' || item.source === 'LOADING'
                      }"
                      x-text="item.source.replace('_FALLBACK', ' (LIVE)').replace('_BULK', ' (NSE)')">
                    </span>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 4: ALERT LOG -->
    <div x-show="activeTab === 'alerts'" x-cloak>
      <div class="bg-dark-800 border border-dark-700 rounded-xl overflow-hidden">
        <div class="px-5 py-3 border-b border-dark-700 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-200">Dispatched Telegram Alert Audit Log</h2>
          <span class="text-xs text-slate-400">Deduplicated per day</span>
        </div>
        <div class="p-4 space-y-3">
          <template x-for="alert in filteredAlertsLog.slice(0, 50)" :key="alert.id">
            <div class="p-3 bg-dark-900 border border-dark-700 rounded-lg flex items-center justify-between text-xs">
              <div class="flex items-center space-x-3">
                <span class="text-lg">🚨</span>
                <div>
                  <div class="font-bold text-white flex items-center gap-2">
                    <span x-text="alert.symbol"></span>
                    <span class="px-1.5 py-0.2 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-normal" x-text="alert.trigger_types"></span>
                  </div>
                  <p class="text-slate-400 mt-0.5">
                    LTP: <span class="font-mono text-slate-200" x-text="'₹' + alert.ltp.toFixed(2)"></span> | 
                    Level: <span class="font-mono text-slate-300" x-text="'₹' + alert.level_broken.toFixed(2)"></span> | 
                    Clearance: <span class="text-emerald-400 font-bold" x-text="'+' + alert.pct_above.toFixed(2) + '%'"></span> | 
                    RVOL: <span class="text-amber-400" x-text="alert.rvol.toFixed(1) + 'x'"></span>
                  </p>
                </div>
              </div>
              <div class="text-right text-slate-400 font-mono text-[11px]" x-text="formatTime(alert.alert_time)"></div>
            </div>
          </template>
          <div x-show="!filteredAlertsLog || filteredAlertsLog.length === 0" class="text-center py-8 text-slate-400 text-xs">
            No alerts match selected criteria today.
          </div>
        </div>
      </div>
    </div>

    <!-- Settings & Engine Controls Modal -->
    <div 
      x-show="showSettingsModal" 
      x-cloak 
      class="fixed inset-0 z-50 overflow-y-auto bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
      @keydown.escape.window="showSettingsModal = false">
      
      <div 
        @click.away="showSettingsModal = false"
        class="bg-dark-800 border border-dark-700 rounded-2xl max-w-2xl w-full p-6 space-y-6 shadow-2xl relative">
        
        <!-- Modal Header -->
        <div class="flex items-center justify-between border-b border-dark-700 pb-4">
          <div class="flex items-center space-x-3">
            <div class="h-10 w-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-xl">
              ⚙️
            </div>
            <div>
              <h3 class="text-base font-bold text-white">Engine Settings & System Controls</h3>
              <p class="text-xs text-slate-400">Institutional F&O Scanner Configuration</p>
            </div>
          </div>
          <button 
            @click="showSettingsModal = false"
            class="h-8 w-8 rounded-lg bg-dark-700 text-slate-400 hover:text-white flex items-center justify-center font-bold text-sm transition">
            ✕
          </button>
        </div>

        <!-- Scanner Operations Control -->
        <div class="bg-dark-900 border border-dark-700 rounded-xl p-4 space-y-3">
          <h4 class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Live Scanner Controls</h4>
          <div class="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <div class="flex items-center space-x-2">
                <span class="h-2.5 w-2.5 rounded-full" :class="health.is_paused ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'"></span>
                <span class="text-sm font-bold" :class="health.is_paused ? 'text-amber-400' : 'text-emerald-400'" x-text="health.is_paused ? 'SCANNER IS PAUSED' : 'SCANNER ACTIVE (RUNNING)'"></span>
              </div>
              <p class="text-xs text-slate-400 mt-1">Polling NSE/Yahoo every <span class="font-mono text-slate-200" x-text="sysSettings.poll_interval_sec || 45"></span>s during market hours.</p>
            </div>
            <button 
              @click="togglePauseScanner()"
              :class="health.is_paused ? 'bg-emerald-600 hover:bg-emerald-500 text-white' : 'bg-amber-600 hover:bg-amber-500 text-white'"
              class="px-4 py-2 rounded-lg text-xs font-bold transition shadow-lg flex items-center gap-2">
              <span x-text="health.is_paused ? '▶ Resume Scanner' : '⏸ Pause Scanner'"></span>
            </button>
          </div>
        </div>

        <!-- Indicator Grid -->
        <div class="space-y-3">
          <h4 class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Active Quantitative Indicators</h4>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
            <div class="bg-dark-900 border border-dark-700 rounded-lg p-3">
              <span class="text-slate-400">All-Time High (ATH)</span>
              <p class="font-bold text-emerald-400 mt-0.5">BUY & SELL (ATL)</p>
            </div>
            <div class="bg-dark-900 border border-dark-700 rounded-lg p-3">
              <span class="text-slate-400">52-Week High / Low</span>
              <p class="font-bold text-cyan-400 mt-0.5">252D Lookback</p>
            </div>
            <div class="bg-dark-900 border border-dark-700 rounded-lg p-3">
              <span class="text-slate-400">Donchian Channels</span>
              <p class="font-bold text-indigo-400 mt-0.5">DC 50 &amp; DC 20</p>
            </div>
            <div class="bg-dark-900 border border-dark-700 rounded-lg p-3">
              <span class="text-slate-400">Supertrend Daily</span>
              <p class="font-bold text-amber-400 mt-0.5">(10, 1) &amp; (10, 2)</p>
            </div>
            <div class="bg-dark-900 border border-dark-700 rounded-lg p-3">
              <span class="text-slate-400">Supertrend 15-Min</span>
              <p class="font-bold text-purple-400 mt-0.5">(10, 1) &amp; (10, 2)</p>
            </div>
            <div class="bg-dark-900 border border-dark-700 rounded-lg p-3">
              <span class="text-slate-400">Alert Mode</span>
              <p class="font-bold text-emerald-400 mt-0.5">Separate 3-Line Alerts</p>
            </div>
          </div>
        </div>

        <!-- Telemetry & Telegram Info -->
        <div class="bg-dark-900 border border-dark-700 rounded-xl p-4 space-y-2 text-xs">
          <h4 class="font-semibold text-slate-300 uppercase tracking-wider">Telegram & Feed Integration</h4>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-400">
            <div>• Telegram Bot: <span class="font-semibold" :class="sysSettings.telegram_configured ? 'text-emerald-400' : 'text-slate-500'" x-text="sysSettings.telegram_configured ? 'CONNECTED' : 'NOT CONFIGURED'"></span></div>
            <div>• Registered Chats: <span class="font-mono text-slate-200" x-text="sysSettings.telegram_chats_count || 0"></span></div>
            <div>• Dynamic Universe: <span class="font-mono text-slate-200" x-text="health.universe_size || 218"></span> equities</div>
            <div>• Deduplication: <span class="text-emerald-400 font-semibold">Active (1/day + 1.5%)</span></div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between pt-2 border-t border-dark-700 text-xs">
          <span class="text-slate-500">Edit config/config.yaml to change thresholds</span>
          <button 
            @click="showSettingsModal = false"
            class="px-4 py-2 bg-dark-700 hover:bg-dark-600 text-slate-200 rounded-lg font-medium transition">
            Close
          </button>
        </div>

      </div>
    </div>

    <!-- Alert Subscriptions Modal -->
    <div 
      x-show="showSubscriptionsModal" 
      x-cloak 
      class="fixed inset-0 z-50 overflow-y-auto bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      @keydown.escape.window="showSubscriptionsModal = false">
      
      <div 
        @click.away="showSubscriptionsModal = false"
        class="bg-dark-800 border border-dark-700 rounded-2xl max-w-3xl w-full p-6 space-y-5 shadow-2xl relative">
        
        <!-- Modal Header -->
        <div class="flex items-center justify-between border-b border-dark-700 pb-4">
          <div class="flex items-center space-x-3">
            <div class="h-10 w-10 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-xl">
              🔔
            </div>
            <div>
              <h3 class="text-base font-bold text-white">Alert Subscriptions & Notifications</h3>
              <p class="text-xs text-slate-400">Choose which screener conditions send automatic Telegram alerts</p>
            </div>
          </div>
          <button 
            @click="showSubscriptionsModal = false"
            class="h-8 w-8 rounded-lg bg-dark-700 text-slate-400 hover:text-white flex items-center justify-center font-bold text-sm transition">
            ✕
          </button>
        </div>

        <!-- Quick Select Controls -->
        <div class="flex flex-wrap items-center justify-between gap-3 bg-dark-900 border border-dark-700 rounded-xl p-3 text-xs">
          <div class="flex flex-wrap items-center gap-1.5">
            <span class="text-slate-400 mr-1">Quick Select:</span>
            <button @click="selectAllSubscriptions()" class="px-2.5 py-1 rounded bg-dark-700 hover:bg-dark-600 text-slate-200 transition font-medium">All (12)</button>
            <button @click="selectBuyOnly()" class="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30 transition font-medium">Only BUYs (6)</button>
            <button @click="selectSellOnly()" class="px-2.5 py-1 rounded bg-rose-500/20 text-rose-400 hover:bg-rose-500/30 border border-rose-500/30 transition font-medium">Only SELLs (6)</button>
            <button @click="deselectAllSubscriptions()" class="px-2.5 py-1 rounded bg-dark-700 hover:bg-dark-600 text-slate-400 hover:text-slate-200 transition">Deselect All</button>
          </div>
          <div class="text-slate-300 font-mono text-xs">
            Subscribed: <span class="font-bold text-indigo-400" x-text="subscribedIds.length"></span> / <span x-text="subscriptionScreeners.length || 12"></span>
          </div>
        </div>

        <!-- Screeners Checkbox Grid -->
        <div class="max-h-[50vh] overflow-y-auto space-y-4 pr-1">
          <template x-for="category in screenerCategories" :key="category">
            <div class="space-y-2">
              <h4 class="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2" x-text="category"></h4>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <template x-for="s in getScreenersByCategory(category)" :key="s.id">
                  <label 
                    class="flex items-start space-x-3 p-3 rounded-xl border transition cursor-pointer select-none"
                    :class="subscribedIds.includes(s.id) ? 'bg-dark-900 border-indigo-500/50 shadow-sm shadow-indigo-500/5' : 'bg-dark-900/40 border-dark-700 hover:border-slate-600 opacity-60'">
                    <input 
                      type="checkbox" 
                      :value="s.id" 
                      x-model="subscribedIds" 
                      class="mt-0.5 h-4 w-4 rounded border-dark-600 text-indigo-600 focus:ring-0 focus:outline-none bg-dark-800 cursor-pointer">
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center space-x-2">
                        <span class="text-xs font-bold text-white truncate" x-text="s.title"></span>
                        <span 
                          class="px-1.5 py-0.2 rounded text-[9px] font-bold"
                          :class="s.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'"
                          x-text="s.side">
                        </span>
                      </div>
                      <p class="text-[11px] text-slate-400 mt-0.5" x-text="s.description"></p>
                    </div>
                  </label>
                </template>
              </div>
            </div>
          </template>
        </div>

        <!-- Save Feedback Message -->
        <div x-show="saveSuccessMsg" x-cloak class="p-2.5 bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded-lg text-xs font-semibold text-center" x-text="saveSuccessMsg"></div>

        <!-- Footer -->
        <div class="flex items-center justify-between pt-3 border-t border-dark-700 text-xs">
          <span class="text-slate-500">Unselected screeners will not send Telegram alerts</span>
          <div class="flex items-center space-x-2">
            <button 
              @click="showSubscriptionsModal = false"
              class="px-4 py-2 bg-dark-700 hover:bg-dark-600 text-slate-300 rounded-lg font-medium transition">
              Cancel
            </button>
            <button 
              @click="saveSubscriptions()"
              :disabled="isSavingSubs"
              class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-bold transition shadow-lg flex items-center gap-2">
              <span x-show="isSavingSubs" class="animate-spin">⏳</span>
              <span x-text="isSavingSubs ? 'Saving...' : '💾 Save Preferences'"></span>
            </button>
          </div>
        </div>

      </div>
    </div>

  </main>

  <script>
    function dashboardApp() {
      return {
        activeTab: 'breakouts',
        searchQuery: '',
        selectedScreener: '',
        isLoading: false,
        showSettingsModal: false,
        showSubscriptionsModal: false,
        isSavingSubs: false,
        saveSuccessMsg: '',
        sysSettings: {},
        health: {},
        signals: { breakouts: [], near_breakouts: [] },
        tableData: [],
        alertsLog: [],
        subscriptionScreeners: [],
        subscribedIds: [
          'ATH', 'ATL', '52W_HIGH', '52W_LOW',
          'DC50_HIGH', 'DC50_LOW', 'DC20_HIGH', 'DC20_LOW',
          'ST_DAILY_10_1_BUY', 'ST_DAILY_10_1_SELL', 'ST_DAILY_10_2_BUY', 'ST_DAILY_10_2_SELL'
        ],

        init() {
          this.refreshData();
          this.loadSubscriptionsQuietly();
          // Auto-refresh every 15 seconds during live sessions
          setInterval(() => this.refreshData(), 15000);
        },

        get subscribedCount() {
          return this.subscribedIds.length;
        },

        get screenerCategories() {
          const cats = [];
          for (const s of this.subscriptionScreeners) {
            if (!cats.includes(s.category)) cats.push(s.category);
          }
          return cats.length ? cats : ['ATH / ATL', '52-Week', 'Donchian Channels', 'Supertrend 15-Min', 'Supertrend Daily'];
        },

        getScreenersByCategory(cat) {
          return this.subscriptionScreeners.filter(s => s.category === cat);
        },

        async loadSubscriptionsQuietly() {
          try {
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token') || localStorage.getItem('screener_token') || '';
            const headers = token ? { 'X-API-Token': token } : {};
            const res = await fetch('/api/subscriptions', { headers });
            if (res.ok) {
              const data = await res.json();
              this.subscriptionScreeners = data.screeners || [];
              this.subscribedIds = (data.screeners || []).filter(s => s.is_subscribed).map(s => s.id);
            }
          } catch (e) {
            console.error('Failed to load subscriptions quietly:', e);
          }
        },

        async openSubscriptionsModal() {
          this.showSubscriptionsModal = true;
          this.saveSuccessMsg = '';
          await this.loadSubscriptionsQuietly();
        },

        async saveSubscriptions() {
          this.isSavingSubs = true;
          this.saveSuccessMsg = '';
          try {
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token') || localStorage.getItem('screener_token') || '';
            const headers = {
              'Content-Type': 'application/json',
              ...(token ? { 'X-API-Token': token } : {})
            };
            const res = await fetch('/api/subscriptions', {
              method: 'POST',
              headers,
              body: JSON.stringify({ subscriptions: this.subscribedIds })
            });
            if (res.ok) {
              this.saveSuccessMsg = `✓ Successfully saved ${this.subscribedIds.length} alert subscriptions!`;
              setTimeout(() => { this.saveSuccessMsg = ''; }, 3500);
            }
          } catch (e) {
            console.error('Failed to save subscriptions:', e);
          } finally {
            this.isSavingSubs = false;
          }
        },

        selectAllSubscriptions() {
          this.subscribedIds = this.subscriptionScreeners.map(s => s.id);
        },

        deselectAllSubscriptions() {
          this.subscribedIds = [];
        },

        selectBuyOnly() {
          this.subscribedIds = this.subscriptionScreeners.filter(s => s.side === 'BUY').map(s => s.id);
        },

        selectSellOnly() {
          this.subscribedIds = this.subscriptionScreeners.filter(s => s.side === 'SELL').map(s => s.id);
        },

        async forceScanAndRefresh() {
          this.isLoading = true;
          try {
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token') || localStorage.getItem('screener_token') || '';
            const headers = token ? { 'X-API-Token': token } : {};
            await fetch('/api/scan', { method: 'POST', headers });
            // Wait 2.5s for initial background quotes to arrive, then refresh view
            setTimeout(() => this.refreshData(), 2500);
          } catch (e) {
            console.error('Scan trigger failed:', e);
          } finally {
            this.isLoading = false;
          }
        },

        async openSettingsModal() {
          this.showSettingsModal = true;
          try {
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token') || localStorage.getItem('screener_token') || '';
            const headers = token ? { 'X-API-Token': token } : {};
            const res = await fetch('/api/admin/settings', { headers });
            if (res.ok) {
              this.sysSettings = await res.json();
            }
          } catch (e) {
            console.error('Failed to load system settings:', e);
          }
        },

        async togglePauseScanner() {
          try {
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token') || localStorage.getItem('screener_token') || '';
            const headers = token ? { 'X-API-Token': token } : {};
            const endpoint = this.health.is_paused ? '/api/admin/resume' : '/api/admin/pause';
            const res = await fetch(endpoint, { method: 'POST', headers });
            if (res.ok) {
              await this.refreshData();
              if (this.showSettingsModal) {
                await this.openSettingsModal();
              }
            }
          } catch (e) {
            console.error('Failed to toggle scanner pause:', e);
          }
        },

        async refreshData() {
          this.isLoading = true;
          try {
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token') || localStorage.getItem('screener_token') || '';
            const headers = token ? { 'X-API-Token': token } : {};

            const [hRes, sRes, tRes, aRes] = await Promise.all([
              fetch('/api/health', { headers }),
              fetch('/api/signals', { headers }),
              fetch('/api/table', { headers }),
              fetch('/api/alerts', { headers })
            ]);

            if (hRes.ok) this.health = await hRes.json();
            if (sRes.ok) this.signals = await sRes.json();
            if (tRes.ok) this.tableData = await tRes.json();
            if (aRes.ok) this.alertsLog = await aRes.json();
          } catch (e) {
            console.error('Failed to refresh dashboard data:', e);
          } finally {
            this.isLoading = false;
          }
        },

        formatTime(isoString) {
          if (!isoString) return 'N/A';
          try {
            const d = new Date(isoString);
            return d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false });
          } catch {
            return isoString;
          }
        },

        get filteredBreakouts() {
          const q = this.searchQuery.toUpperCase();
          const scr = this.selectedScreener;
          return (this.signals.breakouts || []).filter(item => {
            const matchQ = !q || item.symbol.includes(q) || (item.sector && item.sector.toUpperCase().includes(q));
            const matchScr = !scr || (item.trigger_types && item.trigger_types.includes(scr));
            return matchQ && matchScr;
          });
        },

        get filteredNearBreakouts() {
          const q = this.searchQuery.toUpperCase();
          const scr = this.selectedScreener;
          return (this.signals.near_breakouts || []).filter(item => {
            const matchQ = !q || item.symbol.includes(q) || (item.sector && item.sector.toUpperCase().includes(q));
            const matchScr = !scr || (item.target_type && (item.target_type === scr || item.target_type.includes(scr)));
            return matchQ && matchScr;
          });
        },

        get filteredTableData() {
          const q = this.searchQuery.toUpperCase();
          const scr = this.selectedScreener;
          return this.tableData.filter(item => {
            const matchQ = !q || item.symbol.includes(q) || (item.sector && item.sector.toUpperCase().includes(q));
            if (!matchQ) return false;
            if (!scr) return true;
            if (item.triggers && item.triggers.includes(scr)) return true;
            if (item.status && item.status.includes(scr)) return true;
            return false;
          });
        },

        get filteredAlertsLog() {
          const q = this.searchQuery.toUpperCase();
          const scr = this.selectedScreener;
          return (this.alertsLog || []).filter(item => {
            const matchQ = !q || item.symbol.includes(q) || (item.sector && item.sector.toUpperCase().includes(q));
            const matchScr = !scr || (item.trigger_types && item.trigger_types.includes(scr));
            return matchQ && matchScr;
          });
        }
      }
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serve the reactive quantitative screener dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)
