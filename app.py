# app.py  — build v0.4 (login rerun fix + clean structure)

import os
import streamlit as st
from SmartApi.smartConnect import SmartConnect  # NOTE: package is SmartApi (capital S/A)

# ---------- Page Config ----------
st.set_page_config(page_title="Options Buy Strategy", layout="centered")
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")
st.caption("UI build: v0.4 — syntax fix & rerun after login")

# ---------- Helpers ----------
def angel_login(user_id: str, mpin: str, totp: str):
    """Try to authenticate with Angel One SmartAPI.
    Returns (ok: bool, data_or_error: dict|str)."""
    try:
        api_key = os.getenv("ANGEL_API_KEY")
        if not api_key:
            return False, "ANGEL_API_KEY is missing in environment."

        smart = SmartConnect(api_key=api_key)
        data = smart.generateSession(user_id, mpin, totp)

        # Basic validation of response structure
        if not isinstance(data, dict) or "data" not in data or data.get("status") is not True:
            return False, f"Unexpected response: {data}"

        payload = data["data"]
        # Also fetch profile (optional)
        try:
            profile = smart.getProfile(payload.get("jwtToken"))
        except Exception:
            profile = None

        result = {
            "jwtToken": payload.get("jwtToken"),
            "feedToken": payload.get("feedToken"),
            "refreshToken": payload.get("refreshToken"),
            "clientcode": payload.get("clientcode"),
            "profile": profile,
        }
        return True, result
    except Exception as e:
        return False, str(e)

# ---------- Session State ----------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""

# ---------- Login or App ----------
if not st.session_state.logged_in:
    # ---- Login Form ----
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        user_id = st.text_input("Enter your Angel One Client ID", value=st.session_state.get("user_id", ""))
        mpin    = st.text_input("Enter your MPIN", type="password")
        totp    = st.text_input("Enter your TOTP", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        st.session_state.user_id = user_id  # keep filled
        if not (user_id and mpin and totp):
            st.error("❌ Please fill all fields.")
        else:
            ok, info = angel_login(user_id, mpin, totp)
            if ok:
                # Store session details
                st.session_state.jwt_token  = info.get("jwtToken")
                st.session_state.feed_token = info.get("feedToken")
                st.session_state.profile    = info.get("profile")
                st.session_state.logged_in  = True
                st.success("✅ Login successful!")
                # Important: switch to the post-login branch immediately
                try:
                    st.experimental_rerun()  # for older Streamlit
                except Exception:
                    st.rerun()
            else:
                st.error(f"Login failed: {info}")

    with st.expander("Session (safe)"):
        st.write({
            "logged_in": st.session_state.logged_in,
            "user_id": st.session_state.get("user_id"),
            "ANGEL_API_KEY_present": bool(os.getenv("ANGEL_API_KEY")),
        })

else:
    # ---- Post-login UI ----
    st.success(f"Welcome, {st.session_state.user_id}!")
    st.write("✅ You are logged in. Post-login strategy UI comes here.")
    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.info(f"You selected **{index}**. (Next: fetch spot, ATM, CE/PE LTP…)")

    if st.button("Logout"):
        for key in ["logged_in", "jwt_token", "feed_token", "profile"]:
            if key in st.session_state:
                del st.session_state[key]
        st.success("Logged out.")
        try:
            st.experimental_rerun()
        except Exception:
            st.rerun()
