"""Streamlit frontend; all data and ML operations are delegated to FastAPI."""
import os
from pathlib import Path
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API = os.getenv("HARVESTSHIELD_API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="HarvestShield", page_icon="🌱", layout="wide", initial_sidebar_state="auto")
st.markdown("""<style>
.stApp {background: #f6f8f3;}
[data-testid="stSidebar"] {background: #e7eedf;}
h1,h2,h3 {color: #173b2e;}
[data-testid="stMetric"] {background:white;border:1px solid #dde6d5;border-radius:12px;padding:18px;}
div.stButton > button[kind="primary"] {background:#235c42;border-color:#235c42;}
.brand {font-size:25px;font-weight:750;color:#173b2e;letter-spacing:-.5px;}
.eyebrow {color:#597344;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;}
.subtitle {color:#647060;margin-top:-8px;}
</style>""", unsafe_allow_html=True)


def call(path, method="GET", **kwargs):
    try:
        r = requests.request(method, API + path, timeout=(4, 240), **kwargs)
        if not r.ok:
            try:
                detail = r.json().get("detail", "Request failed")
                if isinstance(detail, list):
                    detail = "; ".join(e.get("msg", "Invalid input") for e in detail)
            except ValueError:
                detail = "Backend returned an unreadable error."
            raise RuntimeError(str(detail))
        return r.json()
    except requests.RequestException:
        raise RuntimeError("Backend connection unavailable. Start FastAPI using Start-HarvestShield.ps1.") from None


def error_boundary(action):
    try:
        return action()
    except RuntimeError as exc:
        st.error(str(exc))
        return None


def money(value):
    return f"₹{value:,.0f}"


def chart_style(fig):
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white", font_color="#173b2e",
        legend_title_text="", margin=dict(l=10, r=10, t=20, b=10))
    if mode == "real":
        ceda_source = any("CEDA" in s.get("source", "") for s in audit["series"])
        public_source = any("Vandeet Shah" in s.get("source", "") for s in audit["series"])
        credit = "CEDA / AGMARKNET-DMI" if ceda_source else "Vandeet Shah / Kaggle historical release" if public_source else "Imported observations; see source audit"
        fig.add_annotation(text="Data: " + credit, xref="paper", yref="paper",
            x=1, y=-0.25, xanchor="right", yanchor="top", showarrow=False, font=dict(size=9))
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=100))
        logo = Path(__file__).resolve().parents[1] / "assets" / "ceda-logo.png"
        if ceda_source and logo.exists():
            from PIL import Image
            fig.add_layout_image(source=Image.open(logo), xref="paper", yref="paper", x=1, y=-0.1,
                sizex=0.16, sizey=0.12, xanchor="right", yanchor="top")
    return fig


with st.sidebar:
    st.markdown('<div class="brand">🌱 HarvestShield</div>', unsafe_allow_html=True)
    st.caption("Market insight. Clearer decisions.")
    st.divider()
    dataset = st.selectbox("Dataset", ["Demo · synthetic", "Real · imported records"],
        index=1 if os.getenv("HARVESTSHIELD_ENV", "local") == "production" else 0)
    mode = "demo" if dataset.startswith("Demo") else "real"
    page = st.radio("Workspace", ["Overview", "Forecasts", "Market comparison", "Data & models"])
    st.divider()
    st.caption("Classical ML · SDGs 1 & 2")
    st.caption("FastAPI backend / Streamlit frontend")
    if os.getenv("HARVESTSHIELD_ENV", "local") != "production":
        st.link_button("API documentation", API + "/docs")

health = error_boundary(lambda: call("/health"))
if not health:
    st.title("HarvestShield")
    st.info("Start both services from the project folder. See README.md for setup instructions.")
    st.stop()

# The shared dashboard never receives an admin credential. Protected operations
# belong to the authenticated backend/CLI, not an all-visitors Streamlit session.
writes_enabled = not health.get("read_only", False) and not health.get("admin_auth_required", False)

st.markdown('<div class="eyebrow">Agricultural market intelligence</div>', unsafe_allow_html=True)
st.title(page)
st.markdown('<p class="subtitle">Seven-day price forecasts and price-drop warnings for wholesale markets.</p>', unsafe_allow_html=True)
if mode == "demo":
    st.warning("DEMONSTRATION ONLY — fictional markets and synthetic prices. Forecasts, model scores, and revenue estimates are not real-world evidence.")
else:
    st.info("Imported market records · Wholesale estimates, not guaranteed transaction prices. Check variety, units, freshness, and model evaluation.")
    feed_status = error_boundary(lambda: call("/api/feed/status"))
    if feed_status:
        state = feed_status["state"]
        if state == "missing_key":
            st.warning("Automatic prices: waiting for DATA_GOV_API_KEY in the deployment environment.")
        elif state == "error":
            code = feed_status.get("error_code") or "UNCLASSIFIED"
            st.warning(f"Automatic prices [{code}]: " + feed_status["message"] + " Next retry (UTC): " + str(feed_status["next_attempt"]))
        elif state in ("waiting", "fetching"):
            st.info("Automatic prices: first refresh is pending or in progress. Reload this page shortly.")
        elif state == "success":
            st.caption(f"Automatic prices · last successful check (UTC): {feed_status['last_success']} · next check: {feed_status['next_attempt']}")
            if feed_status["page_limit_reached"]:
                st.warning("Feed page limit reached: this snapshot may omit markets. Narrow the configured filters or review the page limit.")
        else:
            st.caption("Automatic price collection is disabled by the deployment administrator.")

audit = error_boundary(lambda: call("/api/audit", params={"mode": mode}))
if audit is None:
    st.stop()
all_series = audit["series"]
configured_feed = feed_status.get("filters", {}) if mode == "real" and feed_status else {}
state_options = sorted({s["state"] for s in all_series} | ({configured_feed["state"]} if configured_feed.get("state") else set()))


def reset_browse_market():
    st.session_state.pop(f"browse_market_{mode}", None)


with st.sidebar:
    st.divider()
    st.caption("Browse stored market data")
    selected_state = st.selectbox("State", state_options, index=None,
        accept_new_options=True, placeholder="All states — select or type",
        key=f"browse_state_{mode}", on_change=reset_browse_market,
        help="Suggestions come from imported data and the configured feed. Type an official name if absent; this filters stored records, not the collection schedule.")
    state_series = [s for s in all_series if not selected_state or s["state"].casefold() == selected_state.strip().casefold()]
    selected_market = st.selectbox("Mandi / market", sorted({s["market"] for s in state_series}), index=None,
        accept_new_options=True, placeholder="All mandis — select or type",
        key=f"browse_market_{mode}", help="Choose a known mandi or type its exact reported name. Clear to show all. Changing state clears the mandi selection.")
if selected_state or selected_market:
    visible = [s for s in state_series if not selected_market or s["market"].casefold() == selected_market.strip().casefold()]
    audit = {**audit, "series": visible, "rows": sum(s["rows"] for s in visible)}
    if not visible:
        st.info("No stored records match this state/mandi. Selecting a name does not change the server's automatic collection area or create a forecast. Clear the filters to see all available data.")
visible_ids = {s["series_id"] for s in audit["series"]}
if mode == "real" and audit["series"]:
    newest = max(s["last_date"] for s in audit["series"])
    if all(s["age_days"] > 3 for s in audit["series"]):
        st.warning(f"HISTORICAL DATA ONLY — latest stored observation is {newest}. Current forecasts are withheld. Use Historical replay on Forecasts or Market comparison for a held-out research demonstration.")
    if any(s["grade"] == "Unspecified" for s in audit["series"]):
        st.caption("Source grade is unreported. Matching broad variety labels does not verify equivalent produce quality; selling comparisons are restricted to historical research replay.")


def forecast_data():
    params = {"mode": mode}
    if replay_date is not None:
        params["replay_date"] = str(replay_date)
    result = error_boundary(lambda: call("/api/forecasts", params=params))
    if result and (selected_state or selected_market):
        result = {**result, "items": [s for s in result["items"] if s["series_id"] in visible_ids],
            "withheld": [s for s in result["withheld"] if s["series_id"] in visible_ids]}
    return result


replay_date = None
if mode == "real" and page in ("Forecasts", "Market comparison"):
    replay = st.checkbox("Historical replay (research only)", value=False)
    if replay:
        report = error_boundary(lambda: call("/api/report", params={"mode": mode}))
        if report:
            period = report["splits"]["test"]
            replay_date = st.date_input("Replay observation date", value=pd.Timestamp(period["end"]).date(),
                min_value=pd.Timestamp(period["start"]).date(), max_value=pd.Timestamp(period["end"]).date())
            st.warning("HISTORICAL REPLAY — archived observations, not current prices or selling advice. Only held-out dates are allowed; later observations are excluded from features.")


def model_report():
    return error_boundary(lambda: call("/api/report", params={"mode": mode}))


def show_report(report):
    a, b, c = st.columns(3)
    a.metric("Held-out price MAE", money(report["test_regression"]["mae"]) + "/q")
    skill = report["test_mae_skill"]
    b.metric("MAE improvement vs persistence", f"{skill:.1%}" if skill is not None else "Unavailable")
    c.metric("Test price-drop events", report["test_risk"]["events"])
    st.caption(f"Forecast: {report['selected_regressor']} · Risk: {report['selected_classifier']} · Calibration: {report['calibration']}")
    for warning in report["warnings"]:
        st.warning(warning)
    with st.expander("Evaluation details and honest limitations"):
        st.write("Models were selected using validation data. Test dates remain later than training; seven-day target gaps separate periods.")
        st.dataframe(pd.DataFrame(report["splits"]).T, width="stretch")
        st.write("Validation model comparison (lower MAE/Brier is better)")
        st.dataframe(pd.DataFrame(report["validation_regressors"]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(report["validation_classifiers"]), hide_index=True, width="stretch")
        st.write("Held-out risk results")
        st.json({k: v for k, v in report["test_risk"].items() if k != "reliability_bins"})
        if "test_risk_baseline" in report:
            st.caption(f"Constant-frequency risk baseline Brier: {report['test_risk_baseline']['brier']:.4f} (lower is better).")
        bins = pd.DataFrame(report["test_risk"]["reliability_bins"])
        if not bins.empty:
            fig = px.scatter(bins, x="predicted_probability", y="observed_frequency", size="rows",
                labels={"predicted_probability": "Mean predicted probability", "observed_frequency": "Observed drop frequency"}, range_x=[0, 1], range_y=[0, 1])
            fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line=dict(dash="dash", color="#99a58e"))
            st.plotly_chart(chart_style(fig), width="stretch")
        st.caption(report["interval_note"] + f" Held-out coverage: {report['test_interval_coverage']:.1%}.")
        st.dataframe(pd.DataFrame(report["per_market"]), hide_index=True, width="stretch")
        st.download_button("Download evaluation JSON", data=__import__("json").dumps(report, indent=2), file_name=f"{mode}_evaluation.json", mime="application/json")


if page == "Overview":
    cols = st.columns(4)
    cols[0].metric("Markets / produce series", len(audit["series"]))
    cols[1].metric("Stored observations", f"{audit['rows']:,}")
    cols[2].metric("Forecast horizon", "7 calendar days")
    cols[3].metric("Drop-event definition", "15% decline")
    if not audit["rows"]:
        if mode == "real" and not writes_enabled:
            st.info("No real records yet. The backend collects configured daily prices automatically when its API key is set. Check the refresh status above; historical training data must be prepared by the administrator.")
        else:
            st.info("No records in this dataset yet. Open Data & models to load the demo or import historical CSV records.")
    else:
        st.subheader("Latest reported prices")
        data = pd.DataFrame(audit["series"])
        st.dataframe(data[["market", "commodity", "variety", "grade", "latest_modal_price", "last_date", "age_days"]], hide_index=True, width="stretch")
        groups = {(s["commodity"], s["variety"], s["grade"]) for s in audit["series"]}
        selected = st.selectbox("Produce for historical chart", sorted(groups), format_func=lambda g: " · ".join(g))
        records = call("/api/history", params={"mode": mode, "limit": 10000})["records"]
        history = pd.DataFrame(records)
        history = history[history.series_id.isin(visible_ids)]
        history = history[(history.commodity == selected[0]) & (history.variety == selected[1]) & (history.grade == selected[2])]
        history["date"] = pd.to_datetime(history.date)
        history = history[history.date >= history.date.max() - pd.Timedelta(days=180)]
        history["market_label"] = history.market + " · " + history.district
        fig = px.line(history, x="date", y="modal_price", color="market_label", color_discrete_sequence=["#235c42", "#a9752c", "#518a99", "#8172aa"], labels={"modal_price": "Modal price (INR/quintal)", "date": "Observation date"})
        st.plotly_chart(chart_style(fig), width="stretch")
        st.caption("Last 180 days shown. Gaps between reported dates can include closures; the chart is not a continuous auction feed.")
    st.subheader("How HarvestShield helps")
    left, right = st.columns(2)
    with left:
        st.write("**Look ahead**")
        st.write("Forecast prices from recent market patterns and inspect the probability of a substantial drop.")
    with right:
        st.write("**Compare like with like**")
        st.write("Compare the same produce and selling date after transport and market costs, with uncertainty visible.")

elif page == "Forecasts":
    forecasts = forecast_data()
    if forecasts:
        fitted_ist = pd.Timestamp(forecasts["model_trained_at"]).tz_convert("Asia/Kolkata").strftime("%Y-%m-%d %H:%M IST")
        st.caption(f"Data freshness checked on {forecasts['as_of']} · Model fitted {fitted_ist}")
        for i, row in enumerate(forecasts["items"]):
            with st.container(border=True):
                st.subheader(row["market"])
                st.caption(f"{row['commodity']} · {row['variety']} · {row['grade']} · Observation {row['observation_date']} → Forecast {row['forecast_date']}")
                a, b, c = st.columns(3)
                a.metric("Latest price / quintal", money(row["current_price"]))
                b.metric("Forecast price / quintal", money(row["forecast_price"]), f"{(row['forecast_price']/row['current_price']-1):+.1%}", delta_color="off")
                c.metric("Estimated ≥15% drop risk", f"{row['drop_probability']:.1%}")
                st.caption(f"Approximate interval: {money(row['interval_low'])}–{money(row['interval_high'])}/quintal. Calibration: {row['calibration']}.")
                if row["alert"]:
                    st.warning("Price-drop warning: estimated risk meets the fixed 30% alert threshold.")
        if not forecasts["items"]:
            st.info("No supported fresh forecasts. Review withheld markets or import recent observations.")
        if forecasts["withheld"]:
            with st.expander("Why some forecasts are withheld", expanded=True):
                st.dataframe(pd.DataFrame(forecasts["withheld"])[["market", "reason"]], hide_index=True, width="stretch")
        report = model_report()
        if report:
            st.subheader("Model evidence")
            show_report(report)

elif page == "Market comparison":
    forecasts = forecast_data()
    if forecasts and len(forecasts["items"]) >= 2:
        groups = {}
        for row in forecasts["items"]:
            key = (row["commodity"], row["variety"], row["grade"], row["forecast_date"])
            groups.setdefault(key, []).append(row)
        supported = [k for k, v in groups.items() if len(v) >= 2]
        if not supported:
            st.info("At least two fresh markets must have matching produce and forecast dates.")
        else:
            selected = st.selectbox("Produce and planned selling date", supported, format_func=lambda k: " · ".join(k))
            rows = groups[selected]
            st.caption("Costs below are TOTAL INR amounts for the entire shipment, not per-quintal costs. No recommendation to delay selling is made.")
            with st.form("comparison"):
                quantity = st.number_input("Quantity (quintals; 1 quintal = 100 kg)", min_value=0.01, max_value=100000.0, value=10.0, step=1.0)
                costs = []
                for row in rows:
                    a, b, c = st.columns([2, 1, 1])
                    a.write(f"**{row['market']}**")
                    transport = b.number_input("Total transport (INR)", min_value=0.0, max_value=1e9, value=0.0, step=100.0, key=f"transport_{mode}_{row['series_id']}")
                    fees = c.number_input("Total market fees (INR)", min_value=0.0, max_value=1e9, value=0.0, step=50.0, key=f"fees_{mode}_{row['series_id']}")
                    costs.append({"series_id": row["series_id"], "transport_cost": transport, "market_fees": fees})
                submit = st.form_submit_button("Compare estimated net revenue", type="primary")
            if submit:
                result = error_boundary(lambda: call("/api/compare", "POST", json={"mode": mode, "replay_date": str(replay_date) if replay_date else None, "quantity_quintals": quantity, "markets": costs}))
                if result:
                    st.subheader("Comparison results")
                    table = pd.DataFrame(result["rows"])[["market", "forecast_price", "drop_probability", "total_cost", "estimated_net_revenue", "net_interval_low", "net_interval_high"]]
                    st.dataframe(table, hide_index=True, width="stretch")
                    fig = px.bar(table, x="market", y="estimated_net_revenue", color_discrete_sequence=["#235c42"], labels={"estimated_net_revenue": "Estimated net revenue (INR)", "market": "Market"})
                    st.plotly_chart(chart_style(fig), width="stretch")
                    if result["intervals_overlap"]:
                        st.warning("Estimated revenue intervals overlap. The displayed ranking is uncertain.")
                    st.caption(result["note"])
                    st.download_button("Export comparison CSV", table.to_csv(index=False).encode(), f"{mode}_market_comparison.csv", "text/csv")
    elif forecasts:
        st.info("At least two fresh supported markets are needed. Load/train the demo or import sufficient real history.")

elif page == "Data & models":
    st.subheader("Dataset workspace")
    if not writes_enabled:
        st.info("Read-only dashboard. Import, feed refresh and model training are reserved for the deployment administrator. Reports, replay and comparisons remain available.")
    if mode == "demo":
        st.write("Load three years of deterministic synthetic data for four fictional markets. Demo and real records are stored separately.")
        if st.button("Load synthetic demonstration", type="primary", disabled=not writes_enabled):
            result = error_boundary(lambda: call("/api/demo", "POST"))
            if result:
                st.success(f"Demo ready: {result.get('inserted', 0):,} new rows.")
                st.rerun()
    else:
        st.write("Import permitted historical records. Units must be INR/quintal; keep market, variety, and grade identities consistent.")
        if audit["series"]:
            with st.expander("Loaded data sources and provenance"):
                for source in sorted({s["source"] for s in audit["series"]}):
                    st.write(source)
                st.caption("Published historical records are distinct from authenticated government daily updates. Audit raw files and the source manifest when presenting results.")
        st.download_button("Download CSV header template", "date,state,district,market,commodity,variety,grade,unit,min_price,max_price,modal_price\n", "harvestshield_template.csv", "text/csv")
        with st.form("import"):
            upload = st.file_uploader("Historical observations (UTF-8 CSV, up to 20 MB)", type=["csv"], disabled=not writes_enabled)
            source = st.text_input("Source / provenance", placeholder="AGMARKNET report URL, download date, crop and units")
            import_submit = st.form_submit_button("Validate and import", disabled=not writes_enabled)
        if import_submit:
            if not upload or not source.strip():
                st.error("Select a CSV and provide a source note.")
            else:
                result = error_boundary(lambda: call("/api/import", "POST", files={"file": (upload.name, upload.getvalue(), "text/csv")}, data={"source": source}))
                if result:
                    st.success(f"Imported {result['inserted']:,} new rows; {result['repeated']:,} identical repeats skipped.")
        with st.expander("Government daily-feed connector"):
            st.write("A daily snapshot does not replace historical training data. Configure DATA_GOV_API_KEY in the backend environment and restart it.")
            st.caption("Backend key configured: " + ("yes" if health["feed_key_configured"] else "no"))
            feed_states = sorted({s["state"] for s in all_series} | {configured_feed.get("state", "Maharashtra")})
            def reset_feed_market():
                st.session_state.pop("feed_market", None)
            state = st.selectbox("Feed state (official spelling)", feed_states,
                index=feed_states.index(configured_feed.get("state", "Maharashtra")),
                accept_new_options=True, key="feed_state", on_change=reset_feed_market,
                help="Select a suggested state or type its exact official name.")
            crop = st.text_input("Commodity (official spelling)", value=configured_feed.get("commodity", "Tomato"))
            markets = sorted({s["market"] for s in all_series if s["state"].casefold() == state.strip().casefold()})
            market = st.selectbox("Feed mandi / market (optional)", markets, index=None,
                accept_new_options=True, placeholder="All mandis — select or type", key="feed_market",
                help="Suggestions come from imported observations for this state, not a complete national directory.")
            st.caption("These fields apply to a manual administrator refresh only. Automatic collection uses the deployment's configured filters.")
            feed_submit = st.button("Fetch reported daily prices", disabled=not writes_enabled)
            if feed_submit:
                with st.spinner("Fetching reported prices from the government API…"):
                    result = error_boundary(lambda: call("/api/feed/refresh", "POST", json={"state": state, "commodity": crop, "market": market or ""}))
                if result:
                    st.success(f"Fetched {result['received']:,} records; inserted {result['inserted']:,}.")
                    st.info(result["note"])
    st.subheader("Coverage audit")
    if audit["series"]:
        st.dataframe(pd.DataFrame(audit["series"])[["market", "commodity", "variety", "grade", "first_date", "last_date", "rows", "calendar_gap_days", "coverage_fraction", "seven_day_label_count", "age_days"]], hide_index=True, width="stretch")
    else:
        st.info("No observations yet.")
    st.caption(audit["note"])
    st.subheader("Train and evaluate")
    st.write("Fits classical models, selects them on validation dates, and evaluates on untouched later test dates. Existing artifacts for this dataset are replaced after a successful run.")
    eligible = [s for s in audit["series"] if s["seven_day_label_count"] >= 120]
    labels = {s["series_id"]: f"{s['market']} / {s['variety']} / {s['grade']}" for s in eligible}
    selected_series = st.multiselect("Historical training cohort (up to 20 series)", options=list(labels), default=list(labels)[:20], format_func=lambda sid: labels[sid], max_selections=20, disabled=not writes_enabled)
    st.caption("Only series with at least 120 exact seven-day labels appear here. Daily snapshots remain separate and never receive an inferred historical grade.")
    if st.button("Train models and generate report", disabled=not writes_enabled or not selected_series, type="primary"):
        with st.spinner("Training classical ML models and evaluating chronological holdouts…"):
            report = error_boundary(lambda: call("/api/train", "POST", json={"mode": mode, "series_ids": selected_series}))
        if report:
            st.success("Training complete. Inspect the evidence below before interpreting forecasts.")
            st.session_state[f"report_{mode}"] = report
    if audit["rows"]:
        try:
            report = call("/api/report", params={"mode": mode})
            show_report(report)
        except RuntimeError:
            st.caption("No trained model yet for this dataset.")
        st.subheader("Rolling historical experiments")
        if st.button("Run three expanding-window backtests", disabled=not writes_enabled or not selected_series):
            with st.spinner("Training each historical prefix with earlier-only data…"):
                result = error_boundary(lambda: call("/api/backtest", "POST", json={"mode": mode, "series_ids": selected_series}))
            if result:
                st.success("Rolling backtests completed; the main model was retained.")
        try:
            backtest = call("/api/backtest", params={"mode": mode})
            rows = [{"data_cutoff": r["cutoff"], "price_model": r["selected_regressor"], "price_mae": r["test_regression"]["mae"],
                "persistence_mae": r["test_persistence"]["mae"], "risk_brier": r["test_risk"]["brier"],
                "baseline_brier": r["test_risk_baseline"]["brier"]} for r in backtest["runs"]]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption(backtest["note"])
            st.download_button("Download backtest JSON", __import__("json").dumps(backtest, indent=2), f"{mode}_backtests.json", "application/json")
        except RuntimeError:
            st.caption("No rolling backtests yet for this dataset.")

st.divider()
st.caption("HarvestShield · Seven-calendar-day horizon · Forecasting and cost comparison only · Observed wholesale prices may differ from individual transactions.")
if mode == "real" and any("CEDA" in s.get("source", "") for s in audit["series"]):
    st.caption('Data: "CEDA Agri Market Data (CEDA-AMD), 2000-2023" — Centre for Economic Data & Analysis, Ashoka University; underlying AGMARKNET/DMI reports. Noncommercial research. No CEDA endorsement.')
    logo = Path(__file__).resolve().parents[1] / "assets" / "ceda-logo.png"
    _, right = st.columns([5, 1])
    with right:
        st.image(str(logo) if logo.exists() else "https://viz.ceda.ashoka.edu.in/assets/logo.png", width=100)
