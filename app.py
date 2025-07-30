# 🔎 TEMP: show whether ANGEL_API_KEY is available (do not print the key!)
st.caption("ANGEL_API_KEY present: " + ("✅" if os.getenv("ANGEL_API_KEY") else "❌"))
from SmartApi.smartConnect import SmartConnect    # <- keep exact case
import streamlit as st
import datetime
import os
from SmartApi.smartConnect import SmartConnect  # <- note the capital S and A!
import streamlit as st
import datetime

st.set_page_config(page_title="Options Buy Strategy", layout="centered")

st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")

# --- Session state defaults ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "auth_submitted" not in st.session_state:
    st.session_state["auth_submitted"] = False

# --- Login form ---
with st.form("auth_form"):
    st.subheader("🔐 User Login")
    user_id = st.text_input("Enter your Angel One Client ID")
    mpin = st.text_input("Enter your MPIN", type="password")
    totp = st.text_input("Enter your TOTP", type="password")
    submit = st.form_submit_button("Login")
    if submit:
        st.session_state["auth_submitted"] = True
        st.session_state["user_id"] = user_id
        st.session_state["mpin"] = mpin
        st.session_state["totp"] = totp

# --- Login logic after form submission ---
if st.session_state.get("auth_submitted") and not st.session_state.get("logged_in"):
    try:
        smart_api = SmartConnect(api_key="6La9FonG")  # TODO: put your key or use secrets
        data = smart_api.generateSession(
            st.session_state["user_id"],
            st.session_state["mpin"],
            st.session_state["totp"]
        )
        st.session_state["access_token"] = data["data"]["access_token"]
        st.session_state["feed_token"] = smart_api.getfeedToken()
        st.session_state["profile"] = smart_api.getProfile(st.session_state["access_token"])
        st.session_state["logged_in"] = True
        st.success("✅ Login successful!")
    except Exception as e:
        st.session_state["logged_in"] = False
        st.error(f"Login failed: {e}")

# --- Post-login placeholder ---
if st.session_state.get("logged_in"):
    st.success(f"Welcome, {st.session_state.get('user_id', '')}!")
    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.write(f"Selected index: **{index}**")
else:
    st.info("Please login with your Angel credentials.")
