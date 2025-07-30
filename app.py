# ===== Imports =====
from smartapi.smartConnect import SmartConnect
import streamlit as st
import datetime
import pyotp

# ===== Page Config =====
st.set_page_config(page_title="Options Buy Strategy", layout="centered")

# ===== Title and Description =====
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a live app for deploying a real-time options strategy using Angel One SmartAPI.")

# ===== Initialize Session State =====
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# ===== Login Logic =====
if st.session_state.get("auth_submitted") and not st.session_state.get("logged_in"):
    try:
        smart_api = SmartConnect(api_key="6La9FonG")  # Replace with your real API key
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
        st.error(f"❌ Login failed: {e}")

# ===== Login Form =====
if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 Angel One Login")
        user_id = st.text_input("Enter your Angel One Client ID")
        mpin = st.text_input("Enter your MPIN", type="password")
        totp = st.text_input("Enter your TOTP", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if user_id and mpin and totp:
                st.session_state.auth_submitted = True
                st.session_state.user_id = user_id
                st.session_state.mpin = mpin
                st.session_state.totp = totp
                st.experimental_rerun()
            else:
                st.error("❌ Please fill in all fields.")
else:
    # ===== Post-login Dashboard =====
    st.success(f"Welcome, {st.session_state.user_id}!")

    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.markdown(f"✅ You have selected **{index}**")

    st.info("🚧 Strategy dashboard coming soon... Real-time Angel One integration is next!")

    # ===== Logout =====
    if st.button("Logout"):
        st.session_state.logged_in = False
        for key in ["auth_submitted", "user_id", "mpin", "totp", "access_token", "feed_token", "profile"]:
            st.session_state.pop(key, None)
        st.experimental_rerun()
