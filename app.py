# app.py — Step 3: signals + paper trading + alerts + (optional) live orders
from __future__ import annotations

import os, json, math, smtplib
import datetime as dt
from email.mime.text import MIMEText
from io import StringIO
from typing import Optional, Tuple, List

import pandas as pd
import requests
import streamlit as st
from SmartApi.smartConnect import SmartConnect


# --------------------- Page & session ---------------------
st.set_page_config(page_title="Options Buy Strategy", layout="centered")
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.caption("Build: Step 3 — signals, paper trading, alerts, optional live orders")

API_KEY = os.getenv("ANGEL_API_KEY", "").strip()
st.caption(f"ANGEL_API_KEY present: {'✅' if bool(API_KEY) else '❌'}")

def _init_state():
    defaults = {
        "logged_in": False,
        "user_id": "",
        "mpin": "",
        "totp": "",
        "smart": None,
        "auth": None,
        "feed_token": "",
        "profile": None,
        "index_choice": "NIFTY",
        "scrips": None,
        "positions": [],     # list of dicts for paper/live orders
        "trade_log": [],     # append-only for display
        "last_refresh": 0,
    }
    for k,v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v
_init_state()


# --------------------- Data helpers ---------------------
@st.cache_data(ttl=3600)
def load_scrip_master() -> pd.DataFrame:
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.csv"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    return df

def col_upper(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].astype(str).str.upper() if col in df.columns else pd.Series([""]*len(df), index=df.index)

def atm_step_for_index(index: str) -> int:
    return {"NIFTY": 50, "BANKNIFTY": 100, "SENSEX": 100}.get(index.upper(), 50)

def pick_nearest_future_row(scrips: pd.DataFrame, index: str) -> Optional[pd.Series]:
    if scrips is None or scrips.empty: return None
    df = scrips.copy()
    if "expiry" not in df.columns: return None
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date
    name_u = col_upper(df, "name")
    instr_u = col_upper(df, "instrumenttype")
    today = dt.date.today()
    sub = df[(name_u==index.upper()) & (instr_u=="FUTIDX") & df["expiry"].notna() & (df["expiry"]>=today)].copy()
    if sub.empty: return None
    sub.sort_values(["expiry","token"], inplace=True, kind="mergesort")
    return sub.iloc[0]

def nearest_options_expiry(scrips: pd.DataFrame, index: str) -> Optional[dt.date]:
    if scrips is None or scrips.empty: return None
    df = scrips.copy()
    if "expiry" not in df.columns: return None
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date
    name_u = col_upper(df, "name")
    instr_u = col_upper(df, "instrumenttype")
    today = dt.date.today()
    sub = df[(name_u==index.upper()) & (instr_u=="OPTIDX") & df["expiry"].notna() & (df["expiry"]>=today)].copy()
    if sub.empty: return None
    sub.sort_values("expiry", inplace=True, kind="mergesort")
    return sub.iloc[0]["expiry"]

def pick_nearest_expiry_row_for_strike(scrips: pd.DataFrame, index: str, strike: int, kind: str) -> Optional[pd.Series]:
    if scrips is None or scrips.empty: return None
    df = scrips.copy()
    if "expiry" not in df.columns: return None
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date
    name_u = col_upper(df, "name")
    instr_u = col_upper(df, "instrumenttype")
    opt_u  = col_upper(df, "optiontype")
    strikes = pd.to_numeric(df["strike"], errors="coerce") if "strike" in df.columns else pd.Series([float("nan")]*len(df), index=df.index)
    today = dt.date.today()
    sub = df[
        (name_u==index.upper()) & (instr_u=="OPTIDX") & (opt_u==kind.upper()) &
        (strikes == float(strike)) & df["expiry"].notna() & (df["expiry"]>=today)
    ].copy()
    if sub.empty: return None
    sub.sort_values(["expiry","token"], inplace=True, kind="mergesort")
    return sub.iloc[0]

def get_ltp(smart: SmartConnect, exch: str, tsym: str, token: str) -> Optional[float]:
    try:
        r = smart.ltpData(exch, tsym, str(token))
        if r and r.get("status") and r.get("data") and "ltp" in r["data"]:
            return float(r["data"]["ltp"])
    except Exception as e:
        st.warning(f"LTP failed for {tsym} ({exch}:{token}) → {e}")
    return None

# Historical 5m candles for FUTIDX (SmartAPI)
def get_futidx_candles(smart: SmartConnect, token: str, from_dt: dt.datetime, to_dt: dt.datetime) -> pd.DataFrame:
    payload = {
        "exchange": "NFO",
        "symboltoken": str(token),
        "interval": "FIVE_MINUTE",
        "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate":   to_dt.strftime("%Y-%m-%d %H:%M"),
    }
    try:
        r = smart.getCandleData(payload)
        data = (r or {}).get("data") or []
        # format: [time, open, high, low, close, volume]
        rows = []
        for row in data:
            rows.append({
                "time": pd.to_datetime(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low":  float(row[3]),
                "close":float(row[4]),
                "volume": float(row[5]),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        st.warning(f"Candles fetch failed: {e}")
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])

# --------------------- Strategy engine (buy-only) ---------------------
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()

def vwap(df: pd.DataFrame) -> pd.Series:
    # simple intraday VWAP proxy using hlc3 and volume
    hlc3 = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_pv = (hlc3 * df["volume"]).cumsum()
    cum_v  = df["volume"].cumsum().replace(0, pd.NA)
    return cum_pv / cum_v

def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def generate_signal(df: pd.DataFrame,
                    ema_fast=5, ema_slow=13,
                    breakout_lookback=10,
                    atr_len=14,
                    session_start="09:15", session_end="15:25") -> Tuple[Optional[str], dict]:
    """
    Returns ('CE' or 'PE' or None, context)
    - Trend filter: close > VWAP and EMA(5) > EMA(13)  => bullish
                    close < VWAP and EMA(5) < EMA(13)  => bearish
    - Breakout: bullish close > highest high of last N bars
                bearish close < lowest low of last N bars
    - ATR floor: recent ATR >= 0.6% of close to avoid dead markets
    - Time filter: only inside session window
    """
    ctx = {"reason": [], "entry_price": None, "stop": None, "target": None}

    if df.empty or len(df) < max(ema_slow, breakout_lookback, atr_len) + 2:
        ctx["reason"].append("Not enough candles")
        return None, ctx

    df = df.copy().reset_index(drop=True)
    df["ema_fast"] = ema(df["close"], ema_fast)
    df["ema_slow"] = ema(df["close"], ema_slow)
    df["vwap"] = vwap(df)
    df["atr"] = atr(df, atr_len)

    last = df.iloc[-1]
    time_last = last["time"]
    if isinstance(time_last, pd.Timestamp):
        tm = time_last.time()
        start_h, start_m = map(int, session_start.split(":"))
        end_h, end_m = map(int, session_end.split(":"))
        inside = (tm >= dt.time(start_h,start_m)) and (tm <= dt.time(end_h,end_m))
    else:
        inside = True
    if not inside:
        ctx["reason"].append("Outside trading window")
        return None, ctx

    # momentum floor
    if last["atr"] <= 0.006 * last["close"]:
        ctx["reason"].append("ATR too small (sideways)")
        return None, ctx

    hh = df["high"].shift(1).rolling(breakout_lookback).max().iloc[-1]
    ll = df["low"].shift(1).rolling(breakout_lookback).min().iloc[-1]

    bullish = (last["close"] > last["vwap"]) and (last["ema_fast"] > last["ema_slow"]) and (last["close"] > hh)
    bearish = (last["close"] < last["vwap"]) and (last["ema_fast"] < last["ema_slow"]) and (last["close"] < ll)

    if bullish:
        ctx["reason"].append("Trend up + breakout")
        ctx["entry_price"] = float(last["close"])
        ctx["stop"] = float(df["low"].tail(3).min())  # last swing area
        ctx["target"] = float(last["close"] + 1.5 * last["atr"])
        return "CE", ctx

    if bearish:
        ctx["reason"].append("Trend down + breakdown")
        ctx["entry_price"] = float(last["close"])
        ctx["stop"] = float(df["high"].tail(3).max())
        ctx["target"] = float(last["close"] - 1.5 * last["atr"])
        return "PE", ctx

    ctx["reason"].append("No setup")
    return None, ctx

# --------------------- Alerts ---------------------
def send_webhook(payload: dict):
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not url: return
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        st.warning(f"Webhook failed: {e}")

def send_email(subject: str, body: str):
    host = os.getenv("SMTP_HOST","").strip()
    port = int(os.getenv("SMTP_PORT","0") or 0)
    user = os.getenv("SMTP_USER","").strip()
    pwd  = os.getenv("SMTP_PASS","").strip()
    to   = os.getenv("ALERT_EMAIL_TO","").strip()
    if not (host and port and user and pwd and to): return
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            s.login(user, pwd)
            s.sendmail(user, [to], msg.as_string())
    except Exception as e:
        st.warning(f"Email failed: {e}")

# --------------------- Logging ---------------------
def append_trade_log(entry: dict):
    st.session_state.trade_log.append(entry)
    # CSV (ephemeral). For persistence, attach a Render Disk or Google Sheets.
    try:
        df = pd.DataFrame(st.session_state.trade_log)
        df.to_csv("/tmp/trades.csv", index=False)
    except Exception as e:
        st.warning(f"CSV write failed: {e}")

def log_to_gsheet(entry: dict):
    js = os.getenv("GSPREAD_SERVICE_ACCOUNT_JSON","").strip()
    if not js: return
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        info = json.loads(js)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(os.getenv("GSHEET_ID","").strip())  # set GSHEET_ID in env if you prefer
        ws = sh.sheet1
        ws.append_row([entry.get(k,"") for k in sorted(entry.keys())], value_input_option="USER_ENTERED")
    except Exception as e:
        st.warning(f"GSheet log failed: {e}")

# --------------------- Login UI ---------------------
if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        st.session_state.user_id = st.text_input("Angel One Client ID", value=st.session_state.user_id)
        st.session_state.mpin = st.text_input("MPIN", type="password")
        st.session_state.totp = st.text_input("TOTP", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        if not API_KEY:
            st.error("ANGEL_API_KEY missing in environment.")
        elif not (st.session_state.user_id and st.session_state.mpin and st.session_state.totp):
            st.error("Fill all fields.")
        else:
            try:
                smart = SmartConnect(api_key=API_KEY)
                auth = smart.generateSession(st.session_state.user_id, st.session_state.mpin, st.session_state.totp)
                if not auth or not auth.get("status"): raise RuntimeError(auth.get("message","Login failed"))
                st.session_state.smart = smart
                st.session_state.auth = auth.get("data", {})
                st.session_state.feed_token = smart.getfeedToken()
                try:
                    st.session_state.profile = smart.getProfile(st.session_state.auth.get("jwtToken",""))
                except Exception:
                    st.session_state.profile = None
                st.session_state.logged_in = True
                st.success("✅ Login successful!")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

# --------------------- Post-login UI ---------------------
else:
    uid = st.session_state.user_id or ""
    st.success(f"Welcome, **{uid}**!")

    # Index & strike controls
    st.subheader("📊 Index & Strike")
    left, right = st.columns([2,1])
    with left:
        st.session_state.index_choice = st.selectbox("Index", ["NIFTY","BANKNIFTY","SENSEX"],
                                                     index=["NIFTY","BANKNIFTY","SENSEX"].index(st.session_state.index_choice))
    index = st.session_state.index_choice
    step = atm_step_for_index(index)
    strike_mode = st.radio("Strike Mode", ["ATM","ITM","OTM"], horizontal=True)
    offset_steps = st.number_input("Offset Steps (x strike step)", min_value=0, max_value=20, value=0)

    # load scrip master
    if st.session_state.scrips is None:
        with st.spinner("Loading instruments…"):
            st.session_state.scrips = load_scrip_master()
    scrips = st.session_state.scrips

    # pick FUTIDX & candles
    fut_row = pick_nearest_future_row(scrips, index)
    if fut_row is None:
        st.error("No FUTIDX found for this index.")
        st.stop()

    # fetch recent 5m candles (today - yesterday)
    now = dt.datetime.now()
    start = (now - dt.timedelta(days=5)).replace(hour=9, minute=15, second=0, microsecond=0)
    candles = get_futidx_candles(st.session_state.smart, str(fut_row.get("token","")), start, now)

    if candles.empty:
        st.error("No candles received. Try again later.")
        st.stop()

    # compute live proxy spot and ATM
    last_close = float(candles["close"].iloc[-1])
    atm_base = int(round(last_close / step) * step)
    if strike_mode == "ITM":
        atm_strike = atm_base + (offset_steps * step) if index in ["NIFTY","SENSEX"] else atm_base + (offset_steps * step)
    elif strike_mode == "OTM":
        atm_strike = atm_base - (offset_steps * step) if index in ["NIFTY","SENSEX"] else atm_base - (offset_steps * step)
    else:
        atm_strike = atm_base

    # nearest expiry + CE/PE rows
    ce_row = pick_nearest_expiry_row_for_strike(scrips, index, atm_strike, "CE")
    pe_row = pick_nearest_expiry_row_for_strike(scrips, index, atm_strike, "PE")

    # show levels
    a,b,c = st.columns(3)
    a.metric("FUTIDX Last", f"{last_close:.2f}")
    b.metric("Step", step)
    c.metric("Chosen Strike", atm_strike)

    # LTPs for chosen CE/PE
    ce_ltp = pe_ltp = None
    if ce_row is not None:
        ce_ltp = get_ltp(st.session_state.smart, ce_row.get("exch_seg","NFO"), ce_row.get("tradingsymbol",""), str(ce_row.get("token","")))
    if pe_row is not None:
        pe_ltp = get_ltp(st.session_state.smart, pe_row.get("exch_seg","NFO"), pe_row.get("tradingsymbol",""), str(pe_row.get("token","")))

    st.markdown("### 🎯 Selected Options")
    c1,c2 = st.columns(2)
    with c1:
        st.write("**CALL (CE)**")
        st.json({
            "symbol": ce_row.get("tradingsymbol","") if ce_row is not None else "",
            "expiry": str(ce_row.get("expiry","")) if ce_row is not None else "",
            "token":  str(ce_row.get("token",""))  if ce_row is not None else "",
            "ltp": None if ce_ltp is None else round(ce_ltp,2)
        })
    with c2:
        st.write("**PUT (PE)**")
        st.json({
            "symbol": pe_row.get("tradingsymbol","") if pe_row is not None else "",
            "expiry": str(pe_row.get("expiry","")) if pe_row is not None else "",
            "token":  str(pe_row.get("token",""))  if pe_row is not None else "",
            "ltp": None if pe_ltp is None else round(pe_ltp,2)
        })

    st.divider()

    # --------------------- Signals (buy-only) ---------------------
    with st.expander("⚙️ Signal Settings", expanded=True):
        ema_fast = st.number_input("EMA Fast", 1, 50, 5)
        ema_slow = st.number_input("EMA Slow", 2, 100, 13)
        breakout_lookback = st.number_input("Breakout lookback (bars)", 3, 50, 10)
        atr_len = st.number_input("ATR length", 5, 30, 14)
        session_start = st.text_input("Session start (HH:MM)", "09:15")
        session_end   = st.text_input("Session end (HH:MM)", "15:25")
        _ = st.text("Signals run on FUTIDX 5m candles.")

    side, ctx = generate_signal(
        candles, ema_fast=int(ema_fast), ema_slow=int(ema_slow),
        breakout_lookback=int(breakout_lookback), atr_len=int(atr_len),
        session_start=session_start, session_end=session_end
    )
    st.write("**Signal:**", side or "No setup")
    st.write("Context:", ctx)

    # Suggested instrument to buy
    chosen_opt = None
    if side == "CE" and ce_row is not None:
        chosen_opt = ("NFO", ce_row.get("tradingsymbol",""), str(ce_row.get("token","")), ce_ltp)
    elif side == "PE" and pe_row is not None:
        chosen_opt = ("NFO", pe_row.get("tradingsymbol",""), str(pe_row.get("token","")), pe_ltp)

    # --------------------- Orders (paper by default) ---------------------
    st.subheader("🧾 Order Settings")
    col1,col2,col3 = st.columns(3)
    with col1:
        qty = st.number_input("Quantity (lots * lot-size or absolute)", 1, 10000, 25)
    with col2:
        rr_target = st.number_input("Target RR (x ATR spot proxy)", 0.5, 5.0, 1.5, step=0.1)
    with col3:
        rr_stop   = st.number_input("Stop RR (x ATR spot proxy)", 0.2, 5.0, 1.0, step=0.1)

    enable_live_orders = st.toggle("✅ Place LIVE orders (danger)", value=False,
                                   help="If OFF: paper trade only. If ON: placeOrder() on Angel.")

    def place_live_order(exchange: str, tradingsymbol: str, token: str, txn_type: str, qty: int, product="MIS", ordertype="MARKET"):
        try:
            orderparams = {
                "variety": "NORMAL",
                "tradingsymbol": tradingsymbol,
                "symboltoken": str(token),
                "transactiontype": txn_type,  # BUY / SELL
                "exchange": exchange,         # NFO
                "ordertype": ordertype,       # MARKET/LIMIT
                "producttype": product,       # MIS/NRML/CNC
                "duration": "DAY",
                "quantity": int(qty),
            }
            r = st.session_state.smart.placeOrder(orderparams)
            return r
        except Exception as e:
            return {"status": False, "message": str(e)}

    st.markdown("### 🚦 Actions")

    if st.button("Evaluate & (Paper) Execute"):
        if chosen_opt is None:
            st.warning("No eligible option for the current signal.")
        else:
            exch, tsym, tok, ltp0 = chosen_opt
            side_txn = "BUY"  # buy-only
            entry_ltp = get_ltp(st.session_state.smart, exch, tsym, tok) or ltp0 or 0.0

            # Derive simple option targets using spot ATR context:
            # We use ctx['target'] and ctx['stop'] (spot), map to option >= proportional %
            if ctx.get("entry_price") and ctx.get("target") and ctx.get("stop"):
                spot_entry = ctx["entry_price"]; spot_tgt = ctx["target"]; spot_stp = ctx["stop"]
                # percentage move on spot
                pct_up = (spot_tgt/spot_entry - 1.0)
                pct_dn = (1.0 - spot_stp/spot_entry)
                opt_tgt = entry_ltp * (1.0 + max(0.15, pct_up*1.5))  # conservative uplift
                opt_sl  = max(0.05, min(0.35, pct_dn*1.2)) * entry_ltp
                target_price = round(opt_tgt, 2)
                stop_price   = round(entry_ltp - opt_sl, 2)
            else:
                target_price = round(entry_ltp * 1.25, 2)
                stop_price   = round(entry_ltp * 0.90, 2)

            if enable_live_orders:
                resp = place_live_order(exch, tsym, tok, side_txn, qty)
                st.write("Live order response:", resp)
                status = "LIVE-PLACED" if (resp or {}).get("status") else "LIVE-FAIL"
            else:
                status = "PAPER"

            entry = {
                "ts": dt.datetime.now().isoformat(timespec="seconds"),
                "index": index,
                "signal": side,
                "exchange": exch,
                "symbol": tsym,
                "token": tok,
                "qty": int(qty),
                "entry_ltp": round(entry_ltp,2),
                "target_price": target_price,
                "stop_price": stop_price,
                "status": status,
            }
            st.session_state.positions.append(entry)
            append_trade_log({**entry, "event": "ENTER"})
            log_to_gsheet({**entry, "event": "ENTER"})

            # Alerts
            send_webhook({"type":"enter", **entry})
            send_email(
                subject=f"[ENTER-{status}] {index} {side} {tsym}",
                body=json.dumps(entry, indent=2)
            )
            st.success(f"Order logged → {status}")

    # Manage open paper positions: simple MTM & exit buttons
    if st.session_state.positions:
        st.markdown("### 📒 Open Positions (paper/live view)")
        rows = []
        for pos in st.session_state.positions:
            # get current LTP
            ltp_now = get_ltp(st.session_state.smart, pos["exchange"], pos["symbol"], pos["token"]) or pos["entry_ltp"]
            mtm = (ltp_now - pos["entry_ltp"]) * pos["qty"]
            rows.append({**pos, "ltp_now": round(ltp_now,2), "mtm": round(mtm,2)})
        dfp = pd.DataFrame(rows)
        st.dataframe(dfp, use_container_width=True)

        # Exit all (paper)
        if st.button("Exit All (Paper)"):
            new_positions = []
            for pos in st.session_state.positions:
                ltp_now = get_ltp(st.session_state.smart, pos["exchange"], pos["symbol"], pos["token"]) or pos["entry_ltp"]
                exit_entry = {**pos, "exit_ltp": round(ltp_now,2), "event":"EXIT", "ts": dt.datetime.now().isoformat(timespec="seconds")}
                append_trade_log(exit_entry); log_to_gsheet(exit_entry)
                send_webhook({"type":"exit", **exit_entry})
                send_email(subject=f"[EXIT] {pos['index']} {pos['signal']} {pos['symbol']}",
                           body=json.dumps(exit_entry, indent=2))
            st.session_state.positions = new_positions
            st.success("All paper positions exited.")

    # Trade log viewer
    if st.session_state.trade_log:
        st.markdown("### 🧾 Trade Log (latest 50)")
        st.dataframe(pd.DataFrame(st.session_state.trade_log).tail(50), use_container_width=True)

    st.divider()
    if st.button("Logout"):
        st.session_state.clear()
        _init_state()
        st.rerun()
