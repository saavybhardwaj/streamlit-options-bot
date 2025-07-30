import streamlit as st

# Set page config for better mobile responsiveness
st.set_page_config(page_title="Options Buy Strategy", layout="centered")

# App title and description
st.title("Options Buy Strategy - NIFTY/BANKNIFTY/SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")

# --- AUTH & INDEX SELECTION FORM ---
with st.form("auth_form"):
    from smartapi.smartConnect import SmartConnect
import datetime

# Angel One login function
def angel_login(user_id, mpin, totp):
    try:
        obj = SmartConnect(api_key=user_id)  # Using user_id as API key
        session = obj.generateSession(mpin, totp)
        refresh_token = session['data']['refreshToken']
        profile = obj.getProfile(refresh_token)
        return obj, profile
    except Exception as e:
        st.error(f"Login failed: {e}")
        return None, None

    st.subheader("🔐 User Login")

    user_id = st.text_input("Enter your Angel One Client ID")
    mpin = st.text_input("Enter your MPIN", type="password")
    totp = st.text_input("Enter your TOTP", type="password")

    index_choice = st.selectbox("Select Index", ["NIFTY", "BANKNIFTY", "SENSEX"])

    submitted = st.form_submit_button("🔓 Login & Continue")
    if submitted:
    st.session_state.logged_in = False  # Reset session
    with st.spinner("Logging into Angel One..."):
        obj, profile = angel_login(user_id, mpin, totp)
        if obj:
            st.success(f"Welcome {profile['data']['name']}")
            st.session_state.logged_in = True
            st.session_state.api = obj
        else:
            st.error("Invalid credentials or login failed.")


if submitted:
    st.success(f"✅ Logged in for {index_choice} - Strategy will initialize soon...")
else:
    st.info("ℹ️ Please login with your Angel credentials and choose an index.")

