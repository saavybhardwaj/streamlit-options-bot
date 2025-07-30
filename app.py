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
