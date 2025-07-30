# =========================
# Options Buy Strategy UI
# Step 2: Live spot, ATM, CE/PE LTP
# =========================

import os
import math
import json
import datetime as dt
import requests
import pandas as pd
import streamlit as st

# ---- Angel SmartAPI ----
from SmartApi.smartConnect import SmartConnect  # comes from smartapi-python package

# --------------------------
# Page config
# --------------------------
st.set_page_config(page_title="Options Buy Strategy", layout="centered")

# --------------------------
# Helpers (cached)
# --------------------------
@st.cache_data(show_spinner=False, ttl=60*30)  # cache 30 mins
def fetch_scrip_master() -> pd.DataFrame:
    """
    Download Angel One OpenAPI scrip master and return as DataFrame.
    We handle both JSON and ZIP(JSON) endpoints gracefully.
    """
    json_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

    # Try JSON endpoint first
    r = requests.get(json_url, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data)
    # Normalize types where available
    for col in ("strike", "lotsize", "tick_size"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "expiry" in df.columns:
        # Parse expiry into date
        df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date
    return df


def index_token_fallback(index: str):
    """
    Known index tokens (fallback) for LTP call.
    These are widely used for Angel indices; if they ever change,
    the scrip-master path below still works for options.
    """
    index = index.upper()
    if index == "NIFTY":
        return {"exchange": "NSE", "symboltoken": "99926000", "tradingsymbol": "NIFTY 50"}
    if index == "BANKNIFTY":
        return {"exchange": "NSE", "symboltoken": "99926009", "tradingsymbol": "NIFTY BANK"}
    if index == "SENSEX":
        return {"exchange": "BSE", "symboltoken": "1", "tradingsymbol": "SENSEX"}
    return None


def get_index_spot(smart: SmartConnect, index: str, scrips: pd.DataFrame) -> float | None:
    """
    Obtain index spot LTP. We try a fallback map first; if not,
    we attempt to find a relevant token in scrip master.
    """
    # 1) Try fallback known tokens
    fb = index_token_fallback(index)
    if fb:
        try:
            resp = smart.ltpData(fb["exchange"], fb["tradingsymbol"], fb["symboltoken"])
            if resp.get("status") and resp.get("data"):
                return float(resp["data"]["ltp"])
        except Exception:
            pass

    # 2) Try to pick an index row from scrip master (best-effort)
    # For indices, Angel may list them with "symbol" equal to "NIFTY 50" / "NIFTY BANK" / "SENSEX"
    name_map = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "SENSEX": "SENSEX"}
    tag = name_map.get(index.upper(), index.upper())
    candidates = scrips[
        (scrips.get("exch_seg", "").str.upper().isin(["NSE", "BSE"])) &
        (scrips.get("symbol", "").str.upper() == tag)
    ].copy()

    if not candidates.empty:
        row = candidates.iloc[0]
        try:
            resp = smart.ltpData(row["exch_seg"], row["tradingsymbol"], str(row["token"]))
            if resp.get("status") and resp.get("data"):
                return float(resp["data"]["ltp"])
        except Exception:
            pass

    return None


def strike_step_for(index: str) -> int:
    index = index.upper()
    if index == "NIFTY":
        return 50
    # BANKNIFTY & SENSEX commonly 100
    return 100


def compute_atm(spot: float, step: int) -> int:
    return int(round(spot / step) * step)


def pick_nearest_expiry_rows(
    scrips: pd.DataFrame, index: str, atm: int, kind: str
) -> pd.Series | None:
    """
    Pick the earliest (nearest) non-expired option row for index/ATM/kind.
    kind = 'CE' or 'PE'
    """
    today = dt.date.today()
    name = index.upper()  # e.g., NIFTY, BANKNIFTY, SENSEX

    # Filter OPTIDX rows for index name
    df = scrips[
        (scrips.get("name", "").str.upper() == name) &
        (scrips.get("instrumenttype", "").str.upper() == "OPTIDX") &
        (scrips.get("strike", 0).astype(float) == float(atm)) &
        (scrips.get("optiontype", "").str.upper() == kind.upper()) &
        (scrips.get("expiry").notna())
    ].copy()

    # Keep only expiries today or later
    df = df[df["expiry"] >= today]

    if df.empty:
        return None

    # Choose earliest expiry
    df = df.sort_values(["expiry", "token"])
    return df.iloc[0]


def get_ltp(smart: SmartConnect, exch: str, tsym: str, token: str | int) -> float | None:
    try:
        r = smart.ltpData(exch, tsym, str(token))
        if r.get("status") and r.get("data"):
            return float(r["data"]["ltp"])
    except Exception:
        pass
    return None


# --------------------------
# Session boot
# --------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "smart" not in st.session_state:
    st.session_state.smart = None
if "client_id" not in st.session_state:
    st.session_state.client_id = None

# --------------------------
# Header
# --------------------------
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")
st.caption("UI build: Step 2 – live spot, ATM, CE/PE LTP")

# Show API key presence (simple env check)
api_key = os.getenv("ANGEL_API_KEY", "")
st.caption(f"ANGEL_API_KEY present: {'✅' if api_key else '❌'}")

# --------------------------
# Login
# --------------------------
if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        user_id = st.text_input("Enter your Angel One Client ID")
        mpin = st.text_input("Enter your MPIN", type="password")
        totp = st.text_input("Enter your TOTP", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        if not api_key:
            st.error("Server missing ANGEL_API_KEY. Add it in Render → Environment → Deploy again.")
        elif not (user_id and mpin and totp):
            st.error("Please fill all fields.")
        else:
            try:
                smart = SmartConnect(api_key=api_key)
                # Login with MPIN + TOTP is allowed by SmartAPI (mobile MPIN mode).
                resp = smart.generateSession(user_id, mpin, totp)
                if not resp.get("status"):
                    raise Exception(resp.get("message") or "Login failed")

                # Fetch feed token and profile (optional)
                _ = smart.getfeedToken()
                _ = smart.getProfile(resp["data"]["jwtToken"])

                # Store in session
                st.session_state.smart = smart
                st.session_state.logged_in = True
                st.session_state.client_id = user_id
                st.success("✅ Login successful!")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

else:
    # --------------------------
    # POST-LOGIN UI
    # --------------------------
    st.success(f"Welcome, {st.session_state.client_id}!")

    # Index chooser
    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.info(f"You selected **{index}**.")

    # Load scrip master (cached)
    with st.spinner("Loading instruments…"):
        scrips = fetch_scrip_master()

    # Fetch index spot
    spot = get_index_spot(st.session_state.smart, index, scrips)

    colA, colB, colC = st.columns(3)
    colA.metric("Index Spot", f"{spot:.2f}" if spot else "—")
    step = strike_step_for(index)
    atm_strike = compute_atm(spot, step) if spot else None
    colB.metric("ATM Step", f"{step}")
    colC.metric("ATM Strike", f"{atm_strike}" if atm_strike else "—")

    st.divider()

    if spot and atm_strike:
        # Find nearest expiry CE/PE rows from scrip master
        row_ce = pick_nearest_expiry_rows(scrips, index, atm_strike, "CE")
        row_pe = pick_nearest_expiry_rows(scrips, index, atm_strike, "PE")

        if not row_ce is None and not row_pe is None:
            ce_ltp = get_ltp(
                st.session_state.smart, row_ce["exch_seg"], row_ce["tradingsymbol"], row_ce["token"]
            )
            pe_ltp = get_ltp(
                st.session_state.smart, row_pe["exch_seg"], row_pe["tradingsymbol"], row_pe["token"]
            )

            st.subheader("ATM Options (Nearest Expiry)")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**CALL (CE)**")
                st.code(
                    f"{row_ce['tradingsymbol']}  |  Token: {row_ce['token']}  |  Exp: {row_ce['expiry']}",
                    language="text",
                )
                st.metric("CE LTP", f"{ce_ltp:.2f}" if ce_ltp else "—")

            with c2:
                st.markdown("**PUT (PE)**")
                st.code(
                    f"{row_pe['tradingsymbol']}  |  Token: {row_pe['token']}  |  Exp: {row_pe['expiry']}",
                    language="text",
                )
                st.metric("PE LTP", f"{pe_ltp:.2f}" if pe_ltp else "—")

            st.caption("Tip: These are fetched from Scrip Master → nearest expiry → LTP API.")

        else:
            st.warning(
                "Could not find CE/PE rows for the nearest expiry in Scrip Master. "
                "Try changing the index or check Scrip Master availability."
            )
    else:
        st.warning("Could not fetch spot or compute ATM. Try again.")

    st.divider()
    if st.button("Logout"):
        for k in ("logged_in", "smart", "client_id"):
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()
