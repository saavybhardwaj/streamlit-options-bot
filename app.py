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

# ---------- LOGIN FORM ----------
if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        user_id = st.text_input("Enter your Angel One Client ID", value=st.session_state.user_id or "")
        mpin = st.text_input("Enter your MPIN", type="password")
        totp = st.text_input("Enter your TOTP", type="password")
        submit = st.form_submit_button("Login")

    if submit:
        if not API_KEY:
            st.error("Please set ANGEL_API_KEY in environment first.")
        elif not (user_id and mpin and totp):
            st.error("Please fill all fields.")
        else:
            try:
                smart_api = SmartConnect(api_key=API_KEY)
                data = smart_api.generateSession(user_id, mpin, totp)

                # Save raw response for diagnostics (do not log sensitive tokens)
                st.session_state.raw_login_response = {
                    "status": data.get("status"),
                    "message": data.get("message"),
                    "has_data": bool(data.get("data")),
                    # DO NOT print the real tokens; just flags
                    "has_jwtToken": bool((data.get("data") or {}).get("jwtToken")),
                    "has_feedToken": bool((data.get("data") or {}).get("feedToken")),
                }

                if not data or not isinstance(data, dict) or not data.get("data"):
                    st.error("Login failed: empty/invalid response from API.")
                else:
                    payload = data["data"]

                    # Newer SmartAPI returns jwtToken + feedToken (no access_token)
                    jwt_token_raw = payload.get("jwtToken")          # may include 'Bearer '
                    feed_token = payload.get("feedToken")

                    jwt_token = _normalize_token(jwt_token_raw)

                    if not jwt_token:
                        st.error("Login failed: response did not include jwtToken.")
                        with st.expander("Show raw response"):
                            st.code(json.dumps(data, indent=2), language="json")
                    else:
                        # Store in session
                        st.session_state.user_id = user_id
                        st.session_state.jwt_token = jwt_token
                        st.session_state.feed_token = feed_token

                        # Try fetching profile (some SDKs expect bare token, some accept Bearer)
                        profile = None
                        try:
                            profile = smart_api.getProfile(jwt_token)  # bare token
                        except Exception:
                            try:
                                profile = smart_api.getProfile(jwt_token_raw)  # with Bearer
                            except Exception:
                                profile = None

                        st.session_state.profile = profile
                        st.session_state.logged_in = True
                        st.success("✅ Login successful!")

                        with st.expander("Session (safe)"):
                            st.write({
                                "user_id": st.session_state.user_id,
                                "jwt_token(masked)": _mask_token(st.session_state.jwt_token),
                                "feed_token(masked)": _mask_token(st.session_state.feed_token or ""),
                                "profile_keys": list((st.session_state.profile or {}).keys())
                            })

            except Exception as e:
                st.error(f"Login failed with exception: {e}")

    # Optional: Publisher OAuth link
    st.markdown("---")
    st.subheader("📲 Mobile OAuth (Publisher Login) (optional)")
    if API_KEY:
        oauth_url = f"https://smartapi.angelbroking.com/publisher-login?api_key={API_KEY}"
        st.link_button("Open Publisher Login", oauth_url)
    else:
        st.caption("Set ANGEL_API_KEY to enable OAuth link.")

    if st.session_state.raw_login_response:
        with st.expander("Last login response (safe)"):
            st.json(st.session_state.raw_login_response)

# ---------- POST-LOGIN ----------
else:
    st.success(f"Welcome, {st.session_state.user_id}!")
    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.info(f"You selected **{index}**. Strategy dashboard coming next…")

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
