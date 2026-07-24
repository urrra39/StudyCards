"""Old-money visual theme for the Streamlit app.

A single CSS injection (rather than a Streamlit theme config file) because
config.toml theming cannot touch typography, borders, gradients, motion, or
component internals - everything that actually sells the aesthetic.

Design brief: a private library in a townhouse, not a SaaS dashboard. Deep
emerald walls, parchment text, engraved brass rules, high-contrast serif
display type, and no rounded "app" corners.

Motion brief: wealth moves slowly. Every animation here is easing-led and
long (400-900ms), never bouncy, never elastic. Content settles rather than
pops; gold catches the light rather than flashing. The vocabulary is:

    rise      - content lifts into place from below with a soft blur
    gild      - a highlight sweeps across brass, like light on metal
    draw      - hairline rules extend from the centre outward
    turn      - the review card rotates in 3D to reveal its answer
    breathe   - a very slow ambient pulse on focal accents

Palette:
    Deep emerald    #0A1F1C  (app background)
    Dark slate      #0F172A  (sidebar / secondary surfaces)
    Soft pine       #162825  (card surfaces)
    Champagne gold  #D4AF37 / muted brass #C5A059  (accents, borders)
    Cream parchment #F9F6F0  (primary text)

Accessibility notes:
    - Every gold-on-emerald pairing used for body text clears WCAG AA.
    - Focus rings are never removed, only restyled in brass.
    - ALL motion collapses under prefers-reduced-motion, including the
      entrance animations, which are reduced to a plain opacity fade so no
      content can ever be left invisible.

Typography note: the webfont import is a progressive enhancement. Full local
serif stacks (Georgia, Iowan Old Style, Palatino) are declared on every rule,
so the app looks correct offline or when Google Fonts is blocked.
"""
from __future__ import annotations

from html import escape

_DISPLAY_STACK = "'Playfair Display', Georgia, 'Iowan Old Style', 'Times New Roman', serif"
_BODY_STACK = "'Cormorant Garamond', Georgia, 'Palatino Linotype', 'Times New Roman', serif"

OLD_MONEY_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,500;0,600;0,700;1,500&family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

:root {
    --emerald: #0A1F1C;
    --slate: #0F172A;
    --pine: #162825;
    --gold: #D4AF37;
    --brass: #C5A059;
    --cream: #F9F6F0;
    --ink: #071512;
    --display: 'Playfair Display', Georgia, 'Iowan Old Style', 'Times New Roman', serif;
    --body: 'Cormorant Garamond', Georgia, 'Palatino Linotype', 'Times New Roman', serif;
    --hairline: rgba(197, 160, 89, 0.34);
    --gild: rgba(212, 175, 55, 0.55);
    --ease-silk: cubic-bezier(0.22, 0.61, 0.36, 1);
    --ease-drape: cubic-bezier(0.16, 1, 0.3, 1);
}

/* ====================================================================
   MOTION VOCABULARY
   Long, eased, never bouncy. Wealth does not hurry.
   ==================================================================== */
@keyframes sc-rise {
    from { opacity: 0; transform: translateY(18px); filter: blur(6px); }
    to   { opacity: 1; transform: translateY(0);    filter: blur(0); }
}
@keyframes sc-fade {
    from { opacity: 0; }
    to   { opacity: 1; }
}
@keyframes sc-draw {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
}
@keyframes sc-gild {
    0%   { background-position: -220% 0; }
    100% { background-position: 220% 0; }
}
@keyframes sc-turn {
    from { opacity: 0; transform: perspective(1400px) rotateX(-9deg) translateY(16px); }
    to   { opacity: 1; transform: perspective(1400px) rotateX(0) translateY(0); }
}
@keyframes sc-breathe {
    0%, 100% { box-shadow: 0 0 0 rgba(212,175,55,0); }
    50%      { box-shadow: 0 0 22px rgba(212,175,55,0.22); }
}
@keyframes sc-seal {
    0%   { opacity: 0; transform: scale(1.5) rotate(-14deg); }
    60%  { opacity: 1; transform: scale(0.96) rotate(2deg); }
    100% { opacity: 1; transform: scale(1) rotate(0); }
}
@keyframes sc-ember {
    0%, 100% { opacity: 0.55; }
    50%      { opacity: 1; }
}
@keyframes sc-sheen {
    /* A diagonal light bar sweeping across a surface. */
    0%   { transform: translateX(-140%) skewX(-18deg); }
    100% { transform: translateX(240%) skewX(-18deg); }
}
@keyframes sc-pulse {
    /* A ring of light expanding and fading - used while a key is verified. */
    0%   { box-shadow: 0 0 0 0 rgba(212,175,55,0.45); }
    70%  { box-shadow: 0 0 0 12px rgba(212,175,55,0); }
    100% { box-shadow: 0 0 0 0 rgba(212,175,55,0); }
}
@keyframes sc-glow {
    /* A slow verdant-to-gold luminance swell for success confirmations. */
    0%, 100% { box-shadow: 0 0 8px rgba(212,175,55,0.14); }
    50%      { box-shadow: 0 0 26px rgba(212,175,55,0.4); }
}
@keyframes sc-shake {
    /* A restrained, single settle-shake for error confirmations. No jitter. */
    0%   { transform: translateX(0); }
    20%  { transform: translateX(-5px); }
    40%  { transform: translateX(4px); }
    60%  { transform: translateX(-3px); }
    80%  { transform: translateX(2px); }
    100% { transform: translateX(0); }
}
@keyframes sc-float {
    /* An almost imperceptible hover for framed cards at rest. */
    0%, 100% { transform: translateY(0); }
    50%      { transform: translateY(-3px); }
}

/* ---- App canvas: lamplight on dark panelling ---- */
.stApp {
    background:
        radial-gradient(1200px 620px at 50% -12%, rgba(212,175,55,0.10) 0%, transparent 62%),
        radial-gradient(ellipse at top, #0D2622 0%, var(--emerald) 55%),
        var(--emerald);
    background-attachment: fixed;
    color: var(--cream);
    animation: sc-fade 900ms var(--ease-silk) both;
}
.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image: linear-gradient(90deg, transparent 0, transparent calc(50% - 1px),
        rgba(197,160,89,0.05) 50%, transparent calc(50% + 1px), transparent 100%);
    z-index: 0;
}
.block-container {
    position: relative;
    z-index: 1;
    padding-top: 3rem;
    max-width: 1180px;
    animation: sc-rise 760ms var(--ease-drape) both;
}

/* ---- Sidebar: a panelled door sliding open ---- */
/* The panel used to sit in slate blue, which read as a different product
   bolted onto the emerald canvas. It is now the darkest green in the palette
   with a gold seam, so the room is one room. --slate survives as a token for
   deep shadows. */
[data-testid="stSidebar"] {
    background:
        radial-gradient(120% 60% at 0% 0%, rgba(212,175,55,0.10) 0%, transparent 60%),
        linear-gradient(180deg, #0C231F 0%, var(--ink) 62%, #061210 100%);
    border-right: 1px solid var(--gild);
    box-shadow: inset -18px 0 34px rgba(0,0,0,0.34);
    animation: sc-fade 800ms var(--ease-silk) both;
}
[data-testid="stSidebar"] .block-container { padding-top: 2rem; }
[data-testid="stSidebar"] .element-container {
    animation: sc-rise 620ms var(--ease-drape) both;
}

/* ---- Typography ---- */
h1, h2, h3, h4, h5 {
    font-family: var(--display) !important;
    color: var(--cream) !important;
    letter-spacing: 0.02em;
    font-weight: 600 !important;
}
h1 {
    font-size: 2.7rem !important;
    letter-spacing: 0.06em;
    padding-bottom: 0.3em;
    margin-bottom: 0.2em !important;
    position: relative;
    text-shadow: 0 1px 0 rgba(0,0,0,0.55), 0 -1px 0 rgba(249,246,240,0.06);
    background: linear-gradient(100deg,
        var(--cream) 32%, #FFF4CF 46%, var(--gold) 52%, var(--cream) 66%);
    background-size: 220% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: sc-rise 820ms var(--ease-drape) both, sc-gild 5.5s var(--ease-silk) 900ms infinite;
}
h1::after {
    content: "";
    position: absolute;
    left: 0; right: 0; bottom: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--brass) 18%, var(--gold) 50%, var(--brass) 82%, transparent);
    transform-origin: center;
    animation: sc-draw 1100ms var(--ease-drape) 260ms both;
}
h2 { font-size: 1.72rem !important; }
h3 {
    font-size: 1.28rem !important;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--brass) !important;
}

.stMarkdown, p, li, label, .stCaption, [data-testid="stCaptionContainer"] {
    font-family: var(--body);
    color: var(--cream);
    font-size: 1.07rem;
    line-height: 1.62;
}
[data-testid="stCaptionContainer"], .stCaption, small {
    color: rgba(249,246,240,0.62) !important;
    font-style: italic;
    letter-spacing: 0.015em;
}
strong, b { color: var(--gold); font-weight: 600; }
a, a:visited {
    color: var(--brass);
    text-decoration: none;
    background-image: linear-gradient(var(--gold), var(--gold));
    background-size: 0% 1px;
    background-repeat: no-repeat;
    background-position: left 92%;
    transition: background-size 520ms var(--ease-drape), color 400ms ease;
}
a:hover { color: var(--gold); background-size: 100% 1px; }
code, kbd, pre {
    font-family: 'SF Mono', 'Cascadia Mono', Consolas, monospace !important;
    background: rgba(7,21,18,0.7) !important;
    color: var(--brass) !important;
    border: 1px solid rgba(197,160,89,0.22);
    border-radius: 2px;
}

/* ---- Buttons: engraved brass with a slow shine passing over ---- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    position: relative;
    overflow: hidden;
    background: linear-gradient(160deg, rgba(212,175,55,0.16), rgba(197,160,89,0.05));
    color: var(--gold);
    border: 1px solid var(--brass);
    border-radius: 2px;
    font-family: var(--body);
    font-weight: 600;
    font-size: 0.94rem;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    padding: 0.46rem 1.05rem;
    transition: background 520ms var(--ease-silk), border-color 420ms ease,
                box-shadow 520ms var(--ease-silk), color 420ms ease,
                transform 320ms var(--ease-drape), letter-spacing 520ms var(--ease-drape);
}
.stButton > button::after {
    content: "";
    position: absolute;
    top: 0; bottom: 0; left: -60%;
    width: 45%;
    background: linear-gradient(100deg, transparent, rgba(255,244,207,0.30), transparent);
    transform: skewX(-18deg);
    transition: left 780ms var(--ease-silk);
}
.stButton > button:hover::after { left: 130%; }
/* A resting brass sheen crosses every button on a long loop, so the surface
   reads as polished metal catching the light even before you touch it. */
.stButton > button::before {
    content: "";
    position: absolute;
    top: 0; bottom: 0; left: 0;
    width: 40%;
    background: linear-gradient(100deg, transparent, rgba(255,244,207,0.18), transparent);
    transform: translateX(-140%) skewX(-18deg);
    animation: sc-sheen 7s var(--ease-silk) 1.5s infinite;
    pointer-events: none;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
    border-color: var(--gold);
    background: linear-gradient(160deg, rgba(212,175,55,0.30), rgba(197,160,89,0.10));
    box-shadow: 0 6px 26px rgba(212, 175, 55, 0.22);
    color: var(--cream);
    transform: translateY(-2px);
    letter-spacing: 0.16em;
}
.stButton > button:active {
    transform: translateY(1px) scale(0.985);
    transition-duration: 90ms;
    box-shadow: inset 0 2px 8px rgba(0,0,0,0.4);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(160deg, rgba(212,175,55,0.34), rgba(197,160,89,0.14));
    color: var(--cream);
    border-color: var(--gold);
    animation: sc-breathe 5s ease-in-out infinite;
}
/* While a rerun is in flight (a key check, an extraction) Streamlit dims the
   app with a running indicator; ring the focused button with an expanding
   pulse so the wait reads as deliberate rather than frozen. */
[data-testid="stStatusWidget"] ~ div .stButton > button:focus,
.stApp[data-teststate="running"] .stButton > button:focus {
    animation: sc-pulse 1.6s var(--ease-silk) infinite;
}
.stButton > button:focus-visible,
.stTextInput input:focus-visible,
[data-baseweb="select"]:focus-within {
    outline: 2px solid var(--gold) !important;
    outline-offset: 2px !important;
}

/* ---- Surfaces ---- */
[data-testid="stMetric"], .sc-card, .sc-plaque {
    background: linear-gradient(150deg, rgba(22,40,37,0.86), rgba(15,23,42,0.66));
    backdrop-filter: blur(7px);
    border: 1px solid rgba(212, 175, 55, 0.4);
    border-radius: 4px;
    padding: 1.1rem 1.3rem;
    box-shadow: 0 4px 22px rgba(0, 0, 0, 0.35);
}
[data-testid="stMetric"] {
    border-radius: 2px;
    border-color: var(--hairline);
    animation: sc-rise 700ms var(--ease-drape) both;
    transition: transform 560ms var(--ease-drape), box-shadow 560ms var(--ease-silk),
                border-color 460ms ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    border-color: var(--gild);
    box-shadow: 0 14px 34px rgba(0,0,0,0.44);
}
[data-testid="stMetricValue"] {
    color: var(--gold) !important;
    font-family: var(--display) !important;
    font-size: 2.15rem !important;
    letter-spacing: 0.02em;
}
[data-testid="stMetricLabel"] {
    color: var(--cream) !important;
    opacity: 0.72;
    font-family: var(--body) !important;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.78rem !important;
}

/* ---- The review card: a framed plate that turns into view ---- */
.sc-card {
    position: relative;
    padding: 2rem 2.2rem;
    border: 1px solid var(--gild);
    box-shadow: 0 10px 40px rgba(0,0,0,0.45), inset 0 0 0 1px rgba(212,175,55,0.10);
    transform-style: preserve-3d;
    /* Turn into view once, then breathe with a barely-there float at rest so a
       displayed card feels suspended rather than pinned to the page. */
    animation: sc-turn 820ms var(--ease-drape) both,
               sc-float 7s var(--ease-silk) 1200ms infinite;
    transition: transform 620ms var(--ease-drape), box-shadow 620ms var(--ease-silk);
}
.sc-card:hover {
    transform: perspective(1400px) translateY(-4px) rotateX(1.2deg);
    box-shadow: 0 22px 60px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(212,175,55,0.18);
}
.sc-card::after {
    content: "";
    position: absolute;
    inset: 7px;
    border: 1px solid rgba(197,160,89,0.24);
    pointer-events: none;
    animation: sc-fade 900ms var(--ease-silk) 220ms both;
}
.sc-kicker {
    color: var(--brass);
    font-family: var(--body);
    font-size: 0.8em;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-bottom: 0.55em;
    animation: sc-fade 700ms var(--ease-silk) 160ms both;
}
.sc-question {
    font-family: var(--display);
    font-size: 1.46em;
    line-height: 1.42;
    color: var(--cream);
    animation: sc-rise 760ms var(--ease-drape) 120ms both;
}
.sc-answer {
    margin-top: 1.05em;
    padding-top: 0.95em;
    border-top: 1px solid rgba(197,160,89,0.28);
    color: var(--cream);
    opacity: 0.92;
    font-family: var(--body);
    font-size: 1.1em;
    line-height: 1.6;
    animation: sc-rise 820ms var(--ease-drape) 260ms both;
}

/* ---- Ornamental rule: hairlines drawn outward from a brass caption ---- */
.sc-rule {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    margin: 2.2rem 0 1.4rem;
    color: var(--brass);
}
.sc-rule::before, .sc-rule::after {
    content: "";
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--hairline), transparent);
    animation: sc-draw 1000ms var(--ease-drape) both;
}
.sc-rule span {
    font-family: var(--body);
    font-size: 0.76rem;
    letter-spacing: 0.26em;
    text-transform: uppercase;
    white-space: nowrap;
    animation: sc-fade 900ms var(--ease-silk) 200ms both;
}

/* ---- Monogram: a brass roundel stamped into the page ---- */
.sc-monogram {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.3rem;
}
.sc-monogram .mark {
    width: 56px; height: 56px;
    flex: 0 0 56px;
    display: grid;
    place-items: center;
    border: 1px solid var(--brass);
    border-radius: 50%;
    color: var(--gold);
    font-family: var(--display);
    font-size: 1.22rem;
    letter-spacing: 0.06em;
    box-shadow: inset 0 0 14px rgba(212,175,55,0.14);
    animation: sc-seal 1000ms var(--ease-drape) both;
    transition: transform 720ms var(--ease-drape), box-shadow 720ms var(--ease-silk);
}
.sc-monogram .mark:hover {
    transform: rotate(360deg);
    box-shadow: inset 0 0 20px rgba(212,175,55,0.3), 0 0 26px rgba(212,175,55,0.22);
}
.sc-monogram .est {
    font-family: var(--body);
    font-size: 0.76rem;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    color: rgba(249,246,240,0.55);
    animation: sc-fade 900ms var(--ease-silk) 420ms both;
}
.sc-plaque { animation: sc-rise 720ms var(--ease-drape) both; }

/* ---- Inputs ---- */
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div,
[data-baseweb="select"] > div {
    background-color: var(--pine) !important;
    color: var(--cream) !important;
    border: 1px solid rgba(197, 160, 89, 0.5) !important;
    border-radius: 2px !important;
    font-family: var(--body) !important;
    transition: border-color 460ms ease, box-shadow 560ms var(--ease-silk),
                background-color 460ms ease;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--gold) !important;
    box-shadow: 0 0 14px rgba(212, 175, 55, 0.28) !important;
}
.stTextInput label, .stSelectbox label, .stFileUploader label {
    font-family: var(--body) !important;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-size: 0.76rem !important;
    color: var(--brass) !important;
}
[data-baseweb="popover"] li {
    font-family: var(--body) !important;
    transition: background-color 320ms ease, padding-left 380ms var(--ease-drape);
}
[data-baseweb="popover"] li:hover { padding-left: 1.15rem; }

/* ---- Expanders, dividers, alerts ---- */
[data-testid="stExpander"] {
    border: 1px solid rgba(212, 175, 55, 0.3);
    border-radius: 3px;
    background: rgba(22, 40, 37, 0.5);
    transition: border-color 520ms ease, box-shadow 620ms var(--ease-silk);
}
[data-testid="stExpander"]:hover {
    border-color: var(--gild);
    box-shadow: 0 10px 30px rgba(0,0,0,0.34);
}
[data-testid="stExpander"] summary {
    font-family: var(--body) !important;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-size: 0.84rem;
    color: var(--brass) !important;
    transition: color 380ms ease, letter-spacing 520ms var(--ease-drape);
}
[data-testid="stExpander"] summary:hover {
    color: var(--gold) !important;
    letter-spacing: 0.18em;
}
hr { border-color: var(--hairline) !important; }
[data-testid="stAlert"] {
    background: rgba(22,40,37,0.72) !important;
    border: 1px solid var(--hairline) !important;
    border-left: 3px solid var(--brass) !important;
    border-radius: 2px !important;
    color: var(--cream) !important;
    font-family: var(--body) !important;
    animation: sc-rise 620ms var(--ease-drape) both;
}
/* Verdict feedback earns motion matched to its meaning: success swells with a
   gold glow, error settles with a single restrained shake. Streamlit tags
   alerts by kind via data-baseweb="notification" variants. */
[data-testid="stAlert"][kind="success"],
[data-baseweb="notification"][data-kind="positive"] {
    animation: sc-rise 560ms var(--ease-drape) both, sc-glow 2.4s var(--ease-silk) 560ms 2;
    border-left-color: var(--gold) !important;
}
[data-testid="stAlert"][kind="error"],
[data-baseweb="notification"][data-kind="negative"] {
    animation: sc-rise 400ms var(--ease-drape) both, sc-shake 520ms var(--ease-silk) 400ms 1;
    border-left-color: #b4442f !important;
}

/* ---- Progress: brass filling with a travelling ember ---- */
[data-testid="stProgress"] > div > div > div { background: rgba(7,21,18,0.8) !important; }
[data-testid="stProgress"] > div > div > div > div {
    background: linear-gradient(90deg, var(--brass), var(--gold), #FFF4CF, var(--gold), var(--brass)) !important;
    background-size: 220% 100% !important;
    animation: sc-gild 2.6s linear infinite;
    transition: width 560ms var(--ease-silk);
}

/* ---- File uploader ---- */
[data-testid="stFileUploaderDropzone"] {
    background: rgba(22, 40, 37, 0.7);
    border: 1px dashed var(--brass);
    border-radius: 3px;
    transition: border-color 460ms ease, background-color 520ms ease,
                transform 520ms var(--ease-drape), box-shadow 560ms var(--ease-silk);
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--gold);
    background: rgba(22, 40, 37, 0.9);
    transform: translateY(-2px);
    box-shadow: 0 12px 30px rgba(0,0,0,0.4);
}

/* ---- Tabs ---- */
[data-baseweb="tab-list"] { border-bottom: 1px solid var(--hairline); gap: 0.4rem; }
[data-baseweb="tab"] {
    font-family: var(--body) !important;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    font-size: 0.8rem !important;
    color: rgba(249,246,240,0.6) !important;
    transition: color 420ms ease, letter-spacing 520ms var(--ease-drape);
}
[data-baseweb="tab"]:hover { color: var(--brass) !important; letter-spacing: 0.19em; }
[aria-selected="true"][data-baseweb="tab"] { color: var(--gold) !important; }

/* ---- Staggered entrance for stacked content ---- */
.main .element-container { animation: sc-rise 640ms var(--ease-drape) both; }
.main .element-container:nth-child(1) { animation-delay: 40ms; }
.main .element-container:nth-child(2) { animation-delay: 90ms; }
.main .element-container:nth-child(3) { animation-delay: 140ms; }
.main .element-container:nth-child(4) { animation-delay: 190ms; }
.main .element-container:nth-child(5) { animation-delay: 240ms; }
.main .element-container:nth-child(n+6) { animation-delay: 290ms; }

/* ====================================================================
   THE ATELIER PANEL - gilded sidebar
   The sidebar is the one panel the user stares at while waiting, so it
   carries the fullest gold treatment: a leafed title, brass-lit labels
   and fields that warm on focus.
   ==================================================================== */
[data-testid="stSidebar"] h2 {
    font-size: 2.05rem !important;
    letter-spacing: 0.05em;
    text-transform: none;
    background: linear-gradient(100deg,
        var(--brass) 28%, var(--gold) 44%, #FFF4CF 52%, var(--gold) 60%, var(--brass) 76%);
    background-size: 220% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: sc-rise 760ms var(--ease-drape) both,
               sc-gild 6s var(--ease-silk) 800ms infinite;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: var(--brass) !important;
    font-style: italic;
    letter-spacing: 0.05em;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label {
    color: var(--gold) !important;
    letter-spacing: 0.2em;
    text-shadow: 0 0 12px rgba(212, 175, 55, 0.22);
}
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] .stTextInput input {
    border-color: var(--gold) !important;
    color: var(--gold) !important;
    box-shadow: inset 0 0 16px rgba(212, 175, 55, 0.1);
}
[data-testid="stSidebar"] [data-baseweb="select"] > div:hover {
    box-shadow: inset 0 0 20px rgba(212, 175, 55, 0.2),
                0 0 18px rgba(212, 175, 55, 0.16);
}
[data-testid="stSidebar"] [data-baseweb="select"] svg { fill: var(--gold) !important; }
[data-testid="stSidebar"] { border-right: 1px solid var(--gold); }

/* ---- Chrome ---- */
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--ink); }
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--brass), #8a6f3d);
    border-radius: 0;
    border: 2px solid var(--ink);
}
::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, var(--gold), var(--brass)); }
::selection { background: rgba(212,175,55,0.28); color: var(--cream); }

/* ====================================================================
   MOTION AND PRINT PREFERENCES
   Entrance animations use "both" fill mode, so simply disabling them
   would leave content stuck at opacity 0. Every animated element is
   therefore reset to a plain, near-instant fade - never to "none".
   ==================================================================== */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-name: sc-fade !important;
        animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.001ms !important;
        scroll-behavior: auto !important;
    }
    h1, [data-testid="stSidebar"] h2 {
        -webkit-text-fill-color: var(--cream);
        background: none;
    }
    .sc-card:hover, [data-testid="stMetric"]:hover, .stButton > button:hover {
        transform: none;
    }
}
@media print {
    .stApp { background: #fff !important; color: #000 !important; }
    [data-testid="stSidebar"], .stButton { display: none !important; }
    .sc-card { border: 1px solid #999; box-shadow: none; }
    *, *::before, *::after { animation: none !important; }
}
</style>
"""


def inject_theme() -> None:
    """Apply the old-money theme. Call once at the top of every page."""
    import streamlit as st  # deferred so non-UI code can import this module

    st.markdown(OLD_MONEY_CSS, unsafe_allow_html=True)


def card_html(question: str, answer: str = "", concept: str = "") -> str:
    """Render a flashcard as a themed HTML block (used with unsafe_allow_html).

    SECURITY: question/answer/concept originate from user-uploaded documents
    and LLM output, and are injected into the page with ``unsafe_allow_html``.
    Every interpolated value is HTML-escaped here so a document containing
    ``<script>`` or an ``onerror=`` attribute cannot execute in the session.
    Escaping lives in this function (not at the call sites) so there is exactly
    one place that can get it wrong.
    """
    safe_question = escape(question, quote=True)
    safe_answer = escape(answer, quote=True)
    safe_concept = escape(concept, quote=True)

    concept_row = (
        f'<div class="sc-kicker" style="text-transform:uppercase;">{safe_concept}</div>'
        if concept
        else ""
    )
    answer_row = f'<div class="sc-answer">{safe_answer}</div>' if answer else ""
    return (
        '<div class="sc-card" style="margin-bottom:1rem;">'
        f"{concept_row}"
        f'<div class="sc-question">{safe_question}</div>'
        f"{answer_row}"
        "</div>"
    )


def monogram_html(initials: str = "SC", established: str = "") -> str:
    """Brass roundel monogram for the page header."""
    safe_initials = escape(initials, quote=True)
    tagline = (
        f'<div class="est">{escape(established, quote=True)}</div>' if established else ""
    )
    return (
        '<div class="sc-monogram">'
        f'<div class="mark">{safe_initials}</div>'
        f"<div>{tagline}</div>"
        "</div>"
    )


def rule_html(label: str = "") -> str:
    """Ornamental section divider; a hairline broken by a small caption."""
    inner = f"<span>{escape(label, quote=True)}</span>" if label else ""
    return f'<div class="sc-rule">{inner}</div>'


def plaque_html(label: str, value: str, note: str = "") -> str:
    """Small engraved plaque for a single labelled figure."""
    footnote = (
        f'<div class="sc-kicker" style="margin:0.5em 0 0;opacity:0.7;">'
        f"{escape(note, quote=True)}</div>"
        if note
        else ""
    )
    return (
        '<div class="sc-plaque">'
        f'<div class="sc-kicker">{escape(label, quote=True)}</div>'
        f'<div style="font-family:{_DISPLAY_STACK};font-size:1.5rem;color:#D4AF37;">'
        f"{escape(value, quote=True)}</div>"
        f"{footnote}"
        "</div>"
    )
