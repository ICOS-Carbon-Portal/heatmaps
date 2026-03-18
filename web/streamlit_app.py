# Standard imports
import datetime
import tempfile
from pathlib import Path

# Related imports
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

# Local imports
from heatmaps.generator import generate_heatmap, generate_period_heatmap, optimal_bin_size

_DOMAIN_ANIMATIONS = {
    "atmosphere": """
<canvas id="c" style="width:100%;height:55px;display:block;margin-top:6px"></canvas>
<script>
const canvas = document.getElementById('c');
canvas.width = window.innerWidth;
canvas.height = 55;
const ctx = canvas.getContext('2d');
const W = canvas.width, H = canvas.height;
ctx.strokeStyle = '#5b9bd5';
ctx.lineCap = 'round';
ctx.lineJoin = 'round';

// Timeline per gust:
//   0 → DRAW_DUR          : left spiral winds up, streak sweeps right
//   DRAW_DUR → CURL_END   : end-curl appears at the streak tip, spinning
//   FADE_START → TOTAL    : both curls + streak fade together
const DRAW_DUR = 0.50, CURL_DUR = 0.35;
const FADE_START = 0.85, TOTAL = 1.50;

const gusts = [
  { cx:W*.10, cy:H*.28, r:H*.22, turns:1.5, spinR:2.8,
    cp1x:W*.25, cp1y:H*-.12, cp2x:W*.62, cp2y:H*.20, ex:W*.96, ey:H*.40, thick:2.0, delay:0.00 },
  { cx:W*.07, cy:H*.74, r:H*.15, turns:1.2, spinR:2.2,
    cp1x:W*.22, cp1y:H*.54,  cp2x:W*.55, cp2y:H*.64, ex:W*.88, ey:H*.72, thick:1.5, delay:0.05 },
];

// Draw the main gust: left spiral (winds in) → bezier streak.
function drawGust(g, progress, phase) {
  const SN = Math.round(g.turns * 42), BN = 26;
  const total = Math.round(progress * (SN + BN));
  if (total < 1) return;
  ctx.lineWidth = g.thick;
  ctx.beginPath();
  ctx.moveTo(g.cx + g.r * Math.cos(phase), g.cy + g.r * Math.sin(phase));
  const sn = Math.min(total, SN);
  for (let i = 1; i <= sn; i++) {
    const t = i / SN;
    const a = phase + t * g.turns * Math.PI * 2;
    const r = g.r * (1 - t * 0.88);
    ctx.lineTo(g.cx + r * Math.cos(a), g.cy + r * Math.sin(a));
  }
  if (total > SN) {
    const bn = total - SN;
    for (let i = 1; i <= bn; i++) {
      const t = i / BN, mt = 1 - t;
      ctx.lineTo(
        mt*mt*mt*g.cx + 3*mt*mt*t*g.cp1x + 3*mt*t*t*g.cp2x + t*t*t*g.ex,
        mt*mt*mt*g.cy + 3*mt*mt*t*g.cp1y + 3*mt*t*t*g.cp2y + t*t*t*g.ey
      );
    }
  }
  ctx.stroke();
}

// Draw a smaller spinning curl at the streak endpoint — appears after the streak arrives.
function drawEndCurl(g, progress, phase) {
  const r0 = g.r * 0.62, turns = 1.2;
  const SN = Math.round(turns * 36);
  const total = Math.round(progress * SN);
  if (total < 1) return;
  ctx.lineWidth = g.thick * 0.8;
  ctx.beginPath();
  ctx.moveTo(g.ex + r0 * Math.cos(phase), g.ey + r0 * Math.sin(phase));
  for (let i = 1; i <= total; i++) {
    const t = i / SN;
    const a = phase + t * turns * Math.PI * 2;
    const r = r0 * (1 - t * 0.88);
    ctx.lineTo(g.ex + r * Math.cos(a), g.ey + r * Math.sin(a));
  }
  ctx.stroke();
}

const t0 = performance.now();
function frame() {
  const dt = (performance.now() - t0) / 1000;
  if (dt > TOTAL) return;
  ctx.clearRect(0, 0, W, H);
  ctx.globalAlpha = dt < 0.12 ? dt / 0.12
                  : dt < FADE_START ? 1
                  : Math.max(0, 1 - (dt - FADE_START) / (TOTAL - FADE_START));
  gusts.forEach(g => {
    const lt = dt - g.delay;
    const phase = g.spinR * dt;
    const base = ctx.globalAlpha;
    // Main gust fades out as the end curl grows — gust "moves" to the right.
    const gustFade = lt < DRAW_DUR ? 1 : Math.max(0, 1 - (lt - DRAW_DUR) / CURL_DUR);
    ctx.globalAlpha = base * gustFade;
    drawGust(g, Math.min(1, Math.max(0, lt / DRAW_DUR)), phase);
    ctx.globalAlpha = base;
    drawEndCurl(g, Math.min(1, Math.max(0, (lt - DRAW_DUR) / CURL_DUR)), phase);
  });
  requestAnimationFrame(frame);
}
frame();
</script>
""",
    "ecosystem": """
<canvas id="c" style="width:100%;height:55px;display:block;margin-top:6px"></canvas>
<script>
const canvas = document.getElementById('c');
canvas.width = window.innerWidth;
canvas.height = 55;
const ctx = canvas.getContext('2d');
const leaves = Array.from({length:20}, (_,i) => ({
  x:(i/20+Math.random()*0.03)*canvas.width,
  y:-6-Math.random()*50,
  sz:5+Math.random()*7,
  vy:1.1+Math.random()*1.4,
  swing:Math.random()*Math.PI*2,
  swingS:0.022+Math.random()*0.022,
  rot:Math.random()*Math.PI*2,
  rotS:(Math.random()-0.5)*0.07,
  hue:105+Math.random()*35,
}));
function drawLeaf(x,y,sz,rot,alpha,hue) {
  ctx.save(); ctx.translate(x,y); ctx.rotate(rot); ctx.globalAlpha=alpha;
  ctx.beginPath(); ctx.ellipse(0,0,sz*0.38,sz,0,0,Math.PI*2);
  ctx.fillStyle=`hsl(${hue},52%,34%)`; ctx.fill();
  ctx.beginPath(); ctx.moveTo(0,-sz); ctx.lineTo(0,sz);
  ctx.strokeStyle=`rgba(0,70,0,0.35)`; ctx.lineWidth=0.6; ctx.stroke();
  ctx.restore();
}
const t0 = performance.now();
function frame() {
  const dt=(performance.now()-t0)/1000;
  if(dt>1.5) return;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const fade=dt<0.25?dt/0.25:dt<0.9?1:Math.max(0,1-(dt-0.9)/0.6);
  leaves.forEach(l=>{
    l.y+=l.vy; l.swing+=l.swingS; l.rot+=l.rotS;
    l.x+=Math.sin(l.swing)*0.75;
    drawLeaf(l.x,l.y,l.sz,l.rot,fade,l.hue);
  });
  requestAnimationFrame(frame);
}
frame();
</script>
""",
}

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
    [data-testid="stSkeleton"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

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

# Title row — animation appears next to the title on domain switch
if "prev_domain" not in st.session_state:
    st.session_state.prev_domain = domain
    domain_changed = True  # play animation on first page load
else:
    domain_changed = st.session_state.prev_domain != domain
    st.session_state.prev_domain = domain

title_col, anim_col, _ = st.columns([3, 3, 14])
with title_col:
    st.title("ICOS Heatmaps")
if domain_changed:
    with anim_col:
        components.html(_DOMAIN_ANIMATIONS[domain], height=65)

st.caption("Generate data-coverage heatmaps for ICOS atmosphere and ecosystem stations.")

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
