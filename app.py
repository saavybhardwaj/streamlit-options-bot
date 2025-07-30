import os
import json
import streamlit as st

# Try to import SmartConnect from either package name
SmartConnect = None
_import_err = None
try:
    from SmartApi.smartConnect import SmartConnect  # popular path
except Exception as e1:
    _import_err = e1
    try:
        from smartapi.smartConnect import SmartConnect  # alternate path
    except Exception as e2:
        _import_err = (e1, e2)

# ---------- UI SETUP ----------
st.set_page_config(page_title="Options Buy Strategy", layout="centered")
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")

# ---------- SESSION DEFAULTS ----------
for k, v in {
    "logged_in": False,
    "user_id": None,
    "jwt_token": None,
    "feed_token": None,
    "profile": None,
    "raw_login_response": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------- ENV KEY INDICATOR ----------
API_KEY = os.getenv("ANGEL_API_KEY", "")
if API_KEY:
    st.success("✅ ANGEL_API_KEY is present.")
else:
    st.error("❌ ANGEL_API_KEY is missing. Add it in Render → Settings → Environment and redeploy.")

# ---------- IMPORT STATUS ----------
if SmartConnect is None:
    with st.expander("SmartAPI import status (diagnostics)"):
        st.error("Could not import SmartConnect from SmartApi/smartapi.")
        st.write("Import errors:", _import_err)
        st.stop()

# ---------- HELPERS ----------
def _mask_token(tok: str, n: int = 6) -> str:
    """mask a token for safe display"""
    if not tok or len(tok) <= 2 * n:
        return "***"
    return f"{tok[:n]}...{tok[-n:]}"

def _normalize_token(token_raw: str | None) -> str | None:
    """remove 'Bearer ' prefix if present"""
    if not token_raw:
        return None
    if token_raw.startswith("Bearer "):
        return token_raw[len("Bearer "):]
    return token_raw

# ---------------- LOGIN FORM (replace this section) ----------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# Simple version stamp so we can confirm the deployed code
st.caption("UI build: v0.3 — login-rerun fix")

if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        user_id = st.text_input("Enter your Angel One Client ID", value=st.session_state.get("user_id", ""))
        mpin    = st.text_input("Enter your MPIN", type="password")
        totp    = st.text_input("Enter your TOTP", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        try:
            # Persist user_id so it stays filled if there’s an error
            st.session_state.user_id = user_id

            # --- Angel One session ---
            smart_api = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
            data = smart_api.generateSession(user_id, mpin, totp)

            # Store session safely
            st.session_state.jwt_token   = (data or {}).get("data", {}).get("jwtToken")
            st.session_state.feed_token  = (data or {}).get("data", {}).get("feedToken")
            st.session_state.profile     = smart_api.getProfile((data or {}).get("data", {}).get("jwtToken"))
            st.session_state.logged_in   = True

            st.success("✅ Login successful!")
            # IMPORTANT: switch to post-login branch immediately
            try:
                st.experimental_rerun()   # Streamlit < 1.30
            except Exception:
                st.rerun()                 # Streamlit ≥ 1.30
        except Exception as e:
            st.error(f"Login failed: {e}")
else:
    # ---------------- POST-LOGIN UI ----------------
    st.success(f"Welcome, {st.session_state.user_id}!")
    # (your post-login block with index → ATM → CE/PE, etc., goes here)

# ---------- POST-LOGIN ----------
else:
    st.success(f"Welcome, {st.session_state.user_id}!")

    # Re-create a SmartConnect (stateless client). We already have jwt token if needed later.
    smart_api = SmartConnect(api_key=API_KEY)

    # ---- UI: Pick index ----
    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY"])  # SENSEX later
    st.caption("SENSEX support coming next. For now NIFTY/BANKNIFTY spot → ATM CE/PE are supported.")

    # ---- Helpers for search + LTP ----
    def search_instruments(query: str, exch: str | None = None):
        """
        Angel SmartAPI search. Returns list of instruments. We show raw in expander for debugging.
        """
        try:
            resp = smart_api.searchScrip(searchKey=query)
            # Response format: {'status': True, 'message': 'SUCCESS', 'data': [{...}, ...]}
            items = (resp or {}).get("data") or []
            if exch:
                items = [it for it in items if str(it.get("exch_seg", "")).upper() == exch.upper()]
            return items, resp
        except Exception as e:
            return [], {"status": False, "error": str(e)}

    def ltp_by_token(exchange: str, tradingsymbol: str, symboltoken: str):
        try:
            ltp_resp = smart_api.ltpData(
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                symboltoken=symboltoken
            )
            # Typical: {'status': True, 'data': {'ltp': 123.45, ...}}
            ltp = ((ltp_resp or {}).get("data") or {}).get("ltp")
            return ltp, ltp_resp
        except Exception as e:
            return None, {"status": False, "error": str(e)}

    # ---- 1) Find SPOT LTP for selected index ----
    # We try a few queries to be robust across account universes.
    spot_candidates = {
        "NIFTY": ["NIFTY 50", "NIFTY", "NSE NIFTY 50"],
        "BANKNIFTY": ["NIFTY BANK", "BANKNIFTY", "NSE NIFTY BANK"]
    }

    chosen_spot = None
    spot_search_dump = {}
    for q in spot_candidates.get(index, []):
        items, raw = search_instruments(q, exch="NSE")
        spot_search_dump[q] = raw
        # Heuristic: prefer items with symbol like "NIFTY 50" / "NIFTY BANK" and instrumenttype = 'INDEX'
        prefer = [it for it in items if str(it.get("symbol", "")).upper().startswith(index)]
        if prefer:
            chosen_spot = prefer[0]
            break
        if items:
            chosen_spot = items[0]
            break

    if not chosen_spot:
        st.error("Could not locate spot instrument for the selected index. See the search diagnostics below.")
        with st.expander("Spot search diagnostics"):
            st.json(spot_search_dump)
        st.stop()

    spot_exch = chosen_spot.get("exch_seg", "NSE")
    spot_symbol = chosen_spot.get("symbol") or chosen_spot.get("tradingsymbol") or ""
    spot_token = chosen_spot.get("token") or chosen_spot.get("symboltoken") or ""

    spot_ltp, spot_ltp_raw = ltp_by_token(spot_exch, spot_symbol, spot_token)

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric(f"{index} Spot LTP", value=f"{spot_ltp:.2f}" if spot_ltp else "N/A")
    with col_b:
        st.caption(f"Instrument: {spot_symbol} | Token: {spot_token}")

    with st.expander("Spot LTP raw response"):
        st.json(spot_ltp_raw)

    # ---- 2) Compute ATM strike ----
    if index == "NIFTY":
        step = 50
    else:  # BANKNIFTY
        step = 100

    if spot_ltp:
        atm = round(round(spot_ltp / step) * step)
    else:
        atm = None

    st.subheader("📌 ATM Detection")
    if atm is None:
        st.warning("Could not compute ATM because spot LTP was not available.")
        st.stop()
    else:
        st.write(f"**ATM Strike** (step {step}): **{atm}**")

    # ---- 3) Find nearest weekly CE/PE by searching NFO OPTIDX ----
    # We'll search by text and then filter:
    # - exch_seg == 'NFO'
    # - instrumenttype == 'OPTIDX'
    # - symbol contains index name
    # - strike matches atm
    # Among matches, pick the smallest (nearest) expiry date if available.
    def parse_expiry_str(s: str) -> tuple:
        """Return sortable tuple (yyyy, mm, dd) if possible, else high value."""
        # Many formats exist; we try to detect digits inside the string.
        import re, datetime as _dt
        y, m, d = 9999, 12, 31
        try:
            # Try common dd-MMM-YYYY (or similar)
            # This is intentionally broad; diagnostics will show exact fields.
            if re.search(r"\d{1,2}", s) and re.search(r"[A-Za-z]{3}", s) and re.search(r"\d{4}", s):
                day = int(re.search(r"\d{1,2}", s).group())
                mon_str = re.search(r"[A-Za-z]{3}", s).group().lower()
                yr = int(re.search(r"\d{4}", s).group())
                mon_map = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
                month = mon_map.get(mon_str, 12)
                return (yr, month, day)
        except Exception:
            pass
        return (y, m, d)

    def pick_option_contract(opt_type: str):  # 'CE' or 'PE'
        q = f"{index} {atm} {opt_type}"
        items, raw = search_instruments(q, exch="NFO")
        # filter
        flt = []
        for it in items:
            if str(it.get("exch_seg")).upper() != "NFO":
                continue
            if str(it.get("instrumenttype", "")).upper() not in ("OPTIDX", "OPT"):
                continue
            # strike might be 'strike' or 'strike_price'
            strike_val = it.get("strike") or it.get("strike_price") or it.get("strikeprice")
            try:
                strike_val = int(float(strike_val))
            except Exception:
                continue
            if strike_val != atm:
                continue
            if str(it.get("symbol", "")).upper().find(opt_type) == -1 and str(it.get("name", "")).upper().find(opt_type) == -1:
                continue
            flt.append(it)

        if not flt:
            return None, raw, []

        # Pick nearest expiry (we try 'expiry' field if present)
        def expiry_key(it):
            exp = str(it.get("expiry") or it.get("expiry_date") or "")
            return parse_expiry_str(exp)

        flt_sorted = sorted(flt, key=expiry_key)
        chosen = flt_sorted[0]
        return chosen, raw, flt_sorted

    ce, ce_raw, ce_list = pick_option_contract("CE")
    pe, pe_raw, pe_list = pick_option_contract("PE")

    # Diagnostics
    with st.expander("CE search diagnostics"):
        st.json({"chosen": ce, "list_count": len(ce_list), "raw": ce_raw})
    with st.expander("PE search diagnostics"):
        st.json({"chosen": pe, "list_count": len(pe_list), "raw": pe_raw})

    # ---- 4) Fetch CE/PE LTP ----
    ce_ltp = pe_ltp = None
    if ce:
        c_ex = ce.get("exch_seg", "NFO")
        c_sym = ce.get("symbol") or ce.get("tradingsymbol") or ""
        c_tok = ce.get("token") or ce.get("symboltoken") or ""
        ce_ltp, ce_ltp_raw = ltp_by_token(c_ex, c_sym, c_tok)
        with st.expander("CE LTP raw"):
            st.json(ce_ltp_raw)

    if pe:
        p_ex = pe.get("exch_seg", "NFO")
        p_sym = pe.get("symbol") or pe.get("tradingsymbol") or ""
        p_tok = pe.get("token") or pe.get("symboltoken") or ""
        pe_ltp, pe_ltp_raw = ltp_by_token(p_ex, p_sym, p_tok)
        with st.expander("PE LTP raw"):
            st.json(pe_ltp_raw)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("ATM", value=atm)
    with col2:
        st.metric("CE LTP", value=f"{ce_ltp:.2f}" if ce_ltp is not None else "N/A")
    with col3:
        st.metric("PE LTP", value=f"{pe_ltp:.2f}" if pe_ltp is not None else "N/A")

    # ---- Action buttons (no live orders yet) ----
    st.markdown("### 🚦 Actions (wiring orders next)")
    st.button("Refresh quotes")

    # ---- Session (safe) + Logout ----
    with st.expander("Session (safe)"):
        st.write({
            "user_id": st.session_state.user_id,
            "jwt_token(masked)": _mask_token(st.session_state.jwt_token),
            "feed_token(masked)": _mask_token(st.session_state.feed_token or ""),
            "profile_keys": list((st.session_state.profile or {}).keys())
        })

    if st.button("Logout"):
        for k in ["logged_in", "user_id", "jwt_token", "feed_token", "profile", "raw_login_response"]:
            st.session_state.pop(k, None)
        st.experimental_rerun()
