import os
import json
import datetime
import streamlit as st

# --- Try both module names; different SmartAPI builds expose different packages ---
SmartConnect = None
_import_err = None
try:
    # Most common with the GitHub build (smartapi-python)
    from SmartApi.smartConnect import SmartConnect  # noqa: N813
except Exception as e1:
    _import_err = e1
    try:
        # Some environments expose it under "smartapi"
        from smartapi.smartConnect import SmartConnect  # type: ignore  # noqa: N813
    except Exception as e2:
        _import_err = (e1, e2)

# --- Streamlit Page Setup ---
st.set_page_config(page_title="Options Buy Strategy", layout="centered")
st.title("📈 Options Buy Strategy - NIFTY / BANKNIFTY / SENSEX")
st.markdown("This is a demo app for deploying a real-time options strategy using Angel One API.")

# --- Session defaults ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "raw_login_response" not in st.session_state:
    st.session_state.raw_login_response = None

# --- API Key indicator ---
API_KEY = os.getenv("ANGEL_API_KEY", "")
with st.container():
    if API_KEY:
        st.success("✅ ANGEL_API_KEY is present in environment.")
    else:
        st.error("❌ ANGEL_API_KEY is missing. Add it in Render → Settings → Environment.")

# --- Import status indicator ---
if SmartConnect is None:
    with st.expander("SmartAPI import status (diagnostics)", expanded=False):
        st.error("Could not import SmartConnect from SmartApi/smartapi.")
        st.write("Import errors:", _import_err)
        st.info(
            "Check that requirements.txt contains either:\n"
            "• smartapi-python @ git+https://github.com/angel-one/smartapi-python.git\n"
            "…or the correct SmartAPI package for your environment."
        )

# --- Login Form ---
if not st.session_state.logged_in:
    with st.form("auth_form"):
        st.subheader("🔐 User Login")
        user_id = st.text_input("Enter your Angel One Client ID", value="", help="e.g., A12345678")
        mpin = st.text_input("Enter your MPIN", type="password")
        totp = st.text_input("Enter your TOTP", type="password")
        submit = st.form_submit_button("Login")

    # --- Attempt login on submit ---
    if submit:
        if not API_KEY:
            st.error("Add ANGEL_API_KEY in Render environment and redeploy.")
        elif SmartConnect is None:
            st.error("SmartConnect is not available. See diagnostics above.")
        elif not (user_id and mpin and totp):
            st.error("Please fill all fields.")
        else:
            try:
                smart_api = SmartConnect(api_key=API_KEY)
                # NOTE: Many SmartAPI builds expect PASSWORD+TOTP here.
                # Angel may reject MPIN on server-side for this route.
                data = smart_api.generateSession(user_id, mpin, totp)

                # Keep raw response for diagnostics
                st.session_state.raw_login_response = data

                # Defensive checks before accessing token
                if not data:
                    st.error("Login API returned an empty response.")
                elif not isinstance(data, dict):
                    st.error(f"Unexpected response type: {type(data)}")
                elif "data" not in data or not data["data"]:
                    st.error("Login API did not return a 'data' object.")
                    with st.expander("Show raw response"):
                        st.code(json.dumps(data, indent=2), language="json")
                elif "access_token" not in data["data"]:
                    st.error("Login API did not return 'access_token'. Server likely rejected MPIN for this route.")
                    with st.expander("Show raw response"):
                        st.code(json.dumps(data, indent=2), language="json")
                    st.info(
                        "✅ Recommended: use Angel's Publisher Login (mobile OAuth) below to obtain a request_token, "
                        "then exchange it for an access_token server-side."
                    )
                else:
                    # Success path
                    st.session_state["access_token"] = data["data"]["access_token"]
                    # Some builds expose getfeedToken()/getProfile; guard with try/except
                    try:
                        st.session_state["feed_token"] = smart_api.getfeedToken()
                    except Exception:
                        st.session_state["feed_token"] = None
                    try:
                        st.session_state["profile"] = smart_api.getProfile(st.session_state["access_token"])
                    except Exception:
                        st.session_state["profile"] = None

                    st.session_state["user_id"] = user_id
                    st.session_state.logged_in = True
                    st.success("✅ Login successful!")

            except Exception as e:
                st.error(f"Login failed with exception: {e}")

    # --- Mobile OAuth (Publisher Login) fallback / recommended path ---
    st.markdown("---")
    st.subheader("📲 Prefer Mobile OAuth (Publisher Login)?")
    oauth_url = f"https://smartapi.angelbroking.com/publisher-login?api_key={API_KEY}" if API_KEY else None
    st.markdown(
        "Angel One enforces MPIN on mobile; some server routes reject MPIN. "
        "Use the official Publisher Login to authenticate via the Angel app:"
    )
    col1, col2 = st.columns(2)
    with col1:
        if oauth_url:
            st.link_button("Open Publisher Login", oauth_url, help="Opens Angel OAuth (mobile).")
        else:
            st.button("Open Publisher Login", disabled=True)
    with col2:
        st.caption("After login, you'll receive a request_token via your redirect URL, "
                   "which you must exchange for an access_token on the server.")

    # Show last raw response (if any)
    if st.session_state.raw_login_response:
        with st.expander("Last login response (raw)"):
            st.code(json.dumps(st.session_state.raw_login_response, indent=2), language="json")

else:
    # --- Post-login UI ---
    st.success(f"Welcome, {st.session_state.get('user_id', 'User')}! 🎉")
    st.markdown("### Choose Index")
    index = st.selectbox("📊 Index", ["NIFTY", "BANKNIFTY", "SENSEX"])
    st.info(f"You selected **{index}**. Strategy dashboard coming next…")

    with st.expander("Session (debug)"):
        safe = {
            "has_access_token": bool(st.session_state.get("access_token")),
            "has_feed_token": bool(st.session_state.get("feed_token")),
            "profile_keys": list((st.session_state.get("profile") or {}).keys())
        }
        st.json(safe)

    if st.button("Logout"):
        for k in ["logged_in", "access_token", "feed_token", "profile", "raw_login_response", "user_id"]:
            st.session_state.pop(k, None)
        st.experimental_rerun()
