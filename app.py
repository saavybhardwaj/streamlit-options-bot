# Add this at the top
from smartapi.smartConnect import SmartConnect
import streamlit as st
import datetime
import streamlit as st

# Set page config
st.set_page_config(page_title="Options Buy Strategy", layout="centered")

# Title and description
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# Login form
if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        user_id = st.text_input("Enter your Angel One Client ID")
        mpin = st.text_input("Enter your MPIN", type="password")
        totp = st.text_input("Enter your TOTP", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if user_id and mpin and totp:
                # Placeholder: You can add SmartAPI login logic here
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.success("✅ Login successful!")
            else:
                st.error("❌ Please fill in all fields.")
else:
    # Post-login UI
    st.success(f"Welcome, {st.session_state.user_id}!")

    index = st.selectbox("📊 Choose an Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.markdown(f"✅ You have selected **{index}**")

    st.info("🚧 Strategy dashboard coming soon... Real-time Angel One integration is next!")

    # Logout button
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.experimental_rerun()

# Login logic after form submission
if st.session_state.get("auth_submitted") and not st.session_state.get("logged_in"):
    try:
        smart_api = SmartConnect(api_key="6La9FonG")
        data = smart_api.generateSession(st.session_state["user_id"], st.session_state["mpin"], st.session_state["totp"])
        st.session_state["access_token"] = data["data"]["access_token"]
        st.session_state["feed_token"] = smart_api.getfeedToken()
        st.session_state["profile"] = smart_api.getProfile(st.session_state["access_token"])
        st.session_state["logged_in"] = True
        st.success("✅ Login successful!")
    except Exception as e:
        st.error(f"Login failed: {e}")
