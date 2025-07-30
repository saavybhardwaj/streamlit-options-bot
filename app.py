# ---------------------
# Imports & page config
# ---------------------
import os
import datetime
import streamlit as st
from SmartApi.smartConnect import SmartConnect  # correct import

st.set_page_config(page_title="Options Buy Strategy", layout="centered")

# ---------------------
# Helpers
# ---------------------
def get_api_key() -> str:
    """Read API key from Render env vars."""
    return os.getenv("ANGEL_API_KEY", "").strip()

# ---------------------
# UI header
# ---------------------
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")

# TEMP check: shows if env var is available (remove later)
st.caption("ANGEL_API_KEY present: " + ("✅" if get_api_key() else "❌"))

# ---------------------
# Session state defaults
# ---------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "auth_submitted" not in st.session_state:
    st.session_state.auth_submitted = False

# ---------------------
# Login form (only if not logged in)
# ---------------------
if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        user_id = st.text_input("Enter your Angel One Client ID")
        mpin = st.text_input("Enter your MPIN", type="password")
        totp = st.text_input("Enter your TOTP", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        if user_id and mpin and totp:
            # Save inputs in session and trigger login logic after rerun
            st.session_state.user_id = user_id
            st.session_state.mpin = mpin
            st.session_state.totp = totp
            st.session_state.auth_submitted = True
            st.rerun()
        else:
            st.error("❌ Please fill in all fields.")

# ---------------------
# Login logic after form submission
# ---------------------
if st.session_state.get("auth_submitted") and not st.session_state.get("logged_in"):
    api_key = get_api_key()
    if not api_key:
        st.error("ANGEL_API_KEY is not set in Render → Environment. Add it and click **Save & Deploy**.")
        st.stop()

    try:
        smart_api = SmartConnect(api_key=api_key)
        data = smart_api.generateSession(
            st.session_state["user_id"],
            st.session_state["mpin"],
            st.session_state["totp"]
        )

        if not data or not data.get("data"):
            raise Exception(f"Empty/invalid response: {data}")

        st.session_state["access_token"] = data["data"]["access_token"]
        st.session_state["feed_token"] = smart_api.getfeedToken()
        st.session_state["profile"] = smart_api.getProfile(st.session_state["access_token"])
        st.session_state["logged_in"] = True
        st.success("✅ Login successful!")
    except Exception as e:
        st.session_state["logged_in"] = False
        st.error(f"Login failed: {e}")

# ---------------------
# Post-login UI
# ---------------------
if st.session_state.logged_in:
    st.success(f"Welcome, {st.session_state.user_id} 👋")
    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.markdown(f"✅ You have selected **{index}**")
    st.info("🚧 Strategy dashboard coming soon... Real-time Angel One integration is next!")

    if st.button("Logout"):
        for k in ("logged_in", "auth_submitted", "user_id", "mpin", "totp",
                  "access_token", "feed_token", "profile"):
            st.session_state.pop(k, None)
        st.rerun()
