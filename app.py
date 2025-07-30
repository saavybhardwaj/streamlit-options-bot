import streamlit as st

# Set page config for better mobile responsiveness
st.set_page_config(page_title="Options Buy Strategy", layout="centered")

# App title and description
st.title("Options Buy Strategy - NIFTY/BANKNIFTY/SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")

# --- AUTH & INDEX SELECTION FORM ---
with st.form("auth_form"):
    st.subheader("🔐 User Login")
    user_id = st.text_input("Enter your Angel One Client ID")
    mpin = st.text_input("Enter your MPIN", type="password")
    totp = st.text_input("Enter your TOTP", type="password")
    submitted = st.form_submit_button("Login")

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

