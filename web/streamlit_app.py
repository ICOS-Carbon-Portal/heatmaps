# Standard imports
import datetime
import tempfile
from pathlib import Path

# Related imports
import pandas as pd
import streamlit as st
from PIL import Image

# Local imports
from heatmaps.generator import generate_heatmap, generate_period_heatmap, optimal_bin_size

st.set_page_config(
    page_title="ICOS Heatmaps",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon=Image.open(Path(__file__).parent / "favicon.ico"),
)

st.markdown(
    """
    <style>
    [data-testid="stHeader"] { display: none; }
    [data-testid="stAppViewBlockContainer"] { padding-top: 0.5rem !important; }
    .block-container { padding-top: 0.5rem !important; }
    [data-testid="stSidebarContent"] { padding-top: 0.5rem; }
    [data-testid="stImage"] img {
        max-height: 70vh;
        width: auto !important;
        object-fit: contain;
    }
    [data-testid="collapsedControl"] { display: none; }
    [data-testid="stBaseButton-headerNoPadding"] { display: none; }
    [data-testid="stDecoration"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("ICOS Heatmaps")
st.caption("Generate data-coverage heatmaps for ICOS atmosphere and ecosystem stations.")

today = datetime.date.today()
default_start = datetime.date(today.year - 1, 1, 1)
default_end = datetime.date(today.year - 1, 12, 31)

with st.sidebar:
    domain = st.selectbox("Domain", ["atmosphere", "ecosystem"])
    use_cache = st.checkbox("Use cache", value=True)

    date_range = st.date_input(
        "Date range",
        value=(default_start, default_end),
    )

    if not isinstance(date_range, (list, tuple)) or len(date_range) < 2:
        st.info("Select a start and end date.")
        generate = False
    else:
        start_date, end_date = date_range[0], date_range[1]
        bin_choice = st.selectbox("Bin size", ["auto-detect", "monthly", "weekly"], index=2)
        generate = True if use_cache else st.button("Generate", use_container_width=True)

if generate:
    try:
        if use_cache:
            Path("/tmp/heatmaps_cache").mkdir(parents=True, exist_ok=True)
        cache_dir = Path("/tmp/heatmaps_cache") if use_cache else None

        with st.spinner("Fetching data and generating heatmap…"):
            with tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)

                is_full_year = (
                    start_date.month == 1
                    and start_date.day == 1
                    and end_date.month == 12
                    and end_date.day == 31
                    and start_date.year == end_date.year
                )

                if is_full_year:
                    resolved_bin = "monthly" if bin_choice == "auto-detect" else bin_choice
                    output_path = generate_heatmap(
                        domain=domain,
                        year=start_date.year,
                        bin_size=resolved_bin,
                        output_dir=output_dir,
                        cache_dir=cache_dir,
                    )
                else:
                    start = pd.Timestamp(start_date, tz="UTC")
                    end = pd.Timestamp(f"{end_date} 23:59:59", tz="UTC")
                    resolved_bin = (
                        optimal_bin_size(start, end)
                        if bin_choice == "auto-detect"
                        else bin_choice
                    )
                    output_path = generate_period_heatmap(
                        domain=domain,
                        start=start,
                        end=end,
                        bin_size=resolved_bin,
                        output_dir=output_dir,
                        cache_dir=cache_dir,
                    )

                image_bytes = output_path.read_bytes()
                filename = output_path.name

        col1, col2, col3 = st.columns([0.5, 9, 0.5])
        with col2:
            st.image(image_bytes, use_container_width=True)
            st.download_button(
                label="Download PNG",
                data=image_bytes,
                file_name=filename,
                mime="image/png",
            )
    except Exception as exc:
        st.error(str(exc))
